"""Execution-scoped evidence emitter and Evidence Plane v2 adapter.

Source of truth
---------------
The canonical on-disk layout produced by this module is execution scoped:

    results/<execution-id>/manifest.json
    results/<execution-id>/findings.json      (optional)
    results/<execution-id>/logs/<name>
    results/<execution-id>/artifacts/<name>
    results/<execution-id>/evidence/<name>

`manifest.json` is the single source of truth for one execution. Every other file is
referenced from the manifest by relative path, sha256 digest and byte size; large output
is never inlined into the manifest.

Adapter semantics
-----------------
Evidence Plane v2 (`evidence_plane.py` + `local_store.py`) remains the custody contract and
uses opaque `evidence://` storage references over a content-addressed store. This module
adapts one layout onto the other deterministically:

- every execution-scoped relative path `p` maps to
  `evidence://<campaign_id>/<run_id>/execution/<execution_id>/<p>`;
- the manifest itself is projected as a `restricted` record (custody of the full metadata);
- a bounded, digest-only summary derived from the manifest is projected as a `summary`
  record whose parent is the manifest record, making it the only exportable projection;
- referenced payload bytes are projected only on explicit request, always as `raw`
  (never exportable by the default sharing policy).

Deliberate non-claims: no encryption at rest, no WORM storage, no retention deletion, no
object storage, no execution replay, no offensive execution. Local controlled reference only.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import re
import sys
from pathlib import Path
from typing import Any, Iterable, Mapping

HERE = Path(__file__).resolve().parent

SCHEMA_VERSION = "1.0"
ADAPTER_ID = "execution-scoped-results-v1"
SUMMARY_POLICY_ID = "execution-manifest-summary-v1"

SECTIONS = ("logs", "artifacts", "evidence")
STATUSES = {"queued", "running", "completed", "failed", "cancelled"}
RESULTS = {"secure", "vulnerable", "inconclusive", "skipped", "error"}
CLASSIFICATIONS = {"raw", "restricted", "sanitized", "summary"}
DEFAULT_CLASSIFICATION = "sanitized"

SAFE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
SAFE_SEGMENT = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
SHA256 = re.compile(r"^[a-f0-9]{64}$")
TIMESTAMP = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d{1,6})?Z$")
MEDIA_TYPE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9.+_-]{0,63}/[A-Za-z0-9][A-Za-z0-9.+_-]{0,63}$")

MAX_REFS = 512
MAX_METADATA_FIELDS = 32
MAX_METADATA_STRING = 512
MAX_FINDINGS_BYTES = 1_048_576

SECRET_KEYS = {
    "authorization",
    "api_key",
    "argv",
    "command",
    "cookie",
    "credential",
    "password",
    "private_key",
    "secret",
    "stderr",
    "stdout",
    "token",
}


class ExecutionEvidenceError(ValueError):
    """Fail-closed execution-evidence bridge violation."""


def _load_sibling(name: str, filename: str):
    module_name = f"_evidence_execution_bridge_{name}"
    existing = sys.modules.get(module_name)
    if existing is not None:
        return existing
    spec = importlib.util.spec_from_file_location(module_name, HERE / filename)
    if not spec or not spec.loader:
        raise RuntimeError(f"cannot load evidence-plane sibling: {filename}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


_contract = _load_sibling("contract", "evidence_plane.py")
Correlation = _contract.Correlation
build_record = _contract.build_record


def sha256_hex(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def canonical_bytes(value: Mapping[str, Any]) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")


def _require_id(value: Any, *, name: str) -> str:
    if not isinstance(value, str) or not SAFE_ID.fullmatch(value):
        raise ExecutionEvidenceError(f"invalid identifier: {name}")
    return value


def _require_timestamp(value: Any, *, name: str) -> str:
    if not isinstance(value, str) or not TIMESTAMP.fullmatch(value):
        raise ExecutionEvidenceError(f"{name} must be an RFC3339 UTC timestamp ending in Z")
    return value


def _require_media_type(value: Any) -> str:
    if not isinstance(value, str) or not MEDIA_TYPE.fullmatch(value):
        raise ExecutionEvidenceError("invalid media type")
    return value


def _assert_bounded_metadata(metadata: Mapping[str, Any]) -> dict[str, Any]:
    if not isinstance(metadata, Mapping):
        raise ExecutionEvidenceError("metadata must be a mapping")
    if len(metadata) > MAX_METADATA_FIELDS:
        raise ExecutionEvidenceError("metadata exceeds the maximum field count")
    bounded: dict[str, Any] = {}
    for key, value in metadata.items():
        if not isinstance(key, str) or not SAFE_SEGMENT.fullmatch(key):
            raise ExecutionEvidenceError("invalid metadata key")
        normalized = key.lower().replace("-", "_")
        if normalized in SECRET_KEYS or set(normalized.split("_")) & SECRET_KEYS:
            raise ExecutionEvidenceError(f"secret-bearing or raw-output metadata field forbidden: {key}")
        if isinstance(value, str):
            if len(value) > MAX_METADATA_STRING:
                raise ExecutionEvidenceError("metadata string exceeds the maximum length")
        elif not isinstance(value, (bool, int, float)) and value is not None:
            raise ExecutionEvidenceError("metadata values must be scalar")
        bounded[key] = value
    return bounded


def _safe_member_path(root: Path, section: str, name: str) -> Path:
    if section not in SECTIONS:
        raise ExecutionEvidenceError(f"unsupported section: {section}")
    if not isinstance(name, str) or not name:
        raise ExecutionEvidenceError("member name is required")
    parts = name.split("/")
    if len(parts) > 4:
        raise ExecutionEvidenceError("member path is too deep")
    for part in parts:
        if part in {"", ".", ".."} or not SAFE_SEGMENT.fullmatch(part):
            raise ExecutionEvidenceError(f"unsafe member path segment: {part!r}")
    candidate = (root / section).joinpath(*parts)
    resolved_root = root.resolve()
    resolved = Path(os.path.normpath(candidate))
    if not resolved.is_relative_to(resolved_root):
        raise ExecutionEvidenceError("member path escapes the execution directory")
    if resolved.is_symlink():
        raise ExecutionEvidenceError("member path must not be a symlink")
    return resolved


def _atomic_write(path: Path, payload: bytes, *, mode: int = 0o600) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.is_symlink():
        raise ExecutionEvidenceError("refusing to write through a symlink")
    if path.exists():
        if path.read_bytes() != payload:
            raise ExecutionEvidenceError(f"immutable path already exists with different content: {path.name}")
        return
    tmp = path.parent / f".{path.name}.tmp-{os.getpid()}"
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL, mode)
    try:
        with os.fdopen(fd, "wb", closefd=True) as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp, path)
    except Exception:
        tmp.unlink(missing_ok=True)
        raise
    dir_fd = os.open(path.parent, os.O_RDONLY)
    try:
        os.fsync(dir_fd)
    finally:
        os.close(dir_fd)


class ExecutionEvidenceEmitter:
    """Deterministic local emitter for the execution-scoped evidence layout."""

    def __init__(
        self,
        results_root: str | Path,
        *,
        execution_id: str,
        environment: str,
        correlation: Any,
        scenario: str | None = None,
        target: str | None = None,
        tool: str | None = None,
        classification: str = DEFAULT_CLASSIFICATION,
        retention_policy_id: str = "default-30d",
        retain_until: str | None = None,
        legal_hold: bool = False,
        producer: str = "execution-evidence-bridge",
        protocol_version: str = "2.0",
    ) -> None:
        self.execution_id = _require_id(execution_id, name="execution_id")
        self.environment = _require_id(environment, name="environment")
        self.scenario = _require_id(scenario, name="scenario") if scenario is not None else None
        self.target = _require_id(target, name="target") if target is not None else None
        self.tool = _require_id(tool, name="tool") if tool is not None else None
        if classification not in CLASSIFICATIONS:
            raise ExecutionEvidenceError("unsupported evidence classification")
        self.classification = classification
        self.retention_policy_id = _require_id(retention_policy_id, name="retention_policy_id")
        if retain_until is not None:
            _require_timestamp(retain_until, name="retain_until")
        self.retain_until = retain_until
        self.legal_hold = bool(legal_hold)
        self.producer = _require_id(producer, name="producer")
        self.protocol_version = _require_id(protocol_version, name="protocol_version")

        correlation_dict = correlation.as_dict() if hasattr(correlation, "as_dict") else dict(correlation)
        if set(correlation_dict) != {"campaign_id", "run_id", "step_id", "attempt_id"}:
            raise ExecutionEvidenceError("correlation must carry campaign, run, step and attempt ids")
        for key, value in correlation_dict.items():
            _require_id(value, name=key)
        self.correlation = correlation_dict

        base = Path(results_root).expanduser()
        self.root = (base / self.execution_id).resolve()
        if self.root.exists() and not self.root.is_dir():
            raise ExecutionEvidenceError("execution root must be a directory")
        self.root.mkdir(parents=True, exist_ok=True)
        os.chmod(self.root, 0o700)

        self._refs: dict[str, list[dict[str, Any]]] = {section: [] for section in SECTIONS}
        self._findings: dict[str, Any] | None = None
        self._finalized = False

    # ---------------------------------------------------------------- writers

    def add_output(
        self,
        section: str,
        name: str,
        payload: bytes,
        *,
        media_type: str = "application/octet-stream",
        role: str = "output",
    ) -> dict[str, Any]:
        """Persist a referenced output file. Content is never inlined into the manifest."""
        if self._finalized:
            raise ExecutionEvidenceError("emitter is already finalized")
        if not isinstance(payload, bytes):
            raise ExecutionEvidenceError("payload must be bytes")
        _require_media_type(media_type)
        _require_id(role, name="role")
        total = sum(len(self._refs[item]) for item in SECTIONS)
        if total >= MAX_REFS:
            raise ExecutionEvidenceError("reference count exceeds the bounded maximum")
        path = _safe_member_path(self.root, section, name)
        _atomic_write(path, payload)
        relative = path.relative_to(self.root).as_posix()
        ref = {
            "path": relative,
            "role": role,
            "media_type": media_type,
            "sha256": sha256_hex(payload),
            "size_bytes": len(payload),
            "storage_ref": self.storage_ref(relative),
        }
        existing = {item["path"] for item in self._refs[section]}
        if relative in existing:
            raise ExecutionEvidenceError("duplicate reference path")
        self._refs[section].append(ref)
        return ref

    def add_log(self, name: str, payload: bytes, *, media_type: str = "text/plain") -> dict[str, Any]:
        return self.add_output("logs", name, payload, media_type=media_type, role="log")

    def add_artifact(
        self, name: str, payload: bytes, *, media_type: str = "application/octet-stream"
    ) -> dict[str, Any]:
        return self.add_output("artifacts", name, payload, media_type=media_type, role="artifact")

    def add_raw_output(self, name: str, payload: bytes, *, media_type: str = "text/plain") -> dict[str, Any]:
        """Reference bulk raw tool output; only the digest and path enter the manifest."""
        return self.add_output("evidence", name, payload, media_type=media_type, role="raw_output")

    def set_findings(self, findings: Mapping[str, Any]) -> dict[str, Any]:
        if self._finalized:
            raise ExecutionEvidenceError("emitter is already finalized")
        if not isinstance(findings, Mapping):
            raise ExecutionEvidenceError("findings must be a mapping")
        payload = canonical_bytes(findings)
        if len(payload) > MAX_FINDINGS_BYTES:
            raise ExecutionEvidenceError("findings payload exceeds the bounded maximum")
        path = self.root / "findings.json"
        _atomic_write(path, payload)
        self._findings = {
            "path": "findings.json",
            "role": "findings",
            "media_type": "application/json",
            "sha256": sha256_hex(payload),
            "size_bytes": len(payload),
            "storage_ref": self.storage_ref("findings.json"),
        }
        return dict(self._findings)

    # ---------------------------------------------------------------- adapter

    def storage_ref(self, relative_path: str) -> str:
        return (
            f"evidence://{self.correlation['campaign_id']}/{self.correlation['run_id']}"
            f"/execution/{self.execution_id}/{relative_path}"
        )

    # -------------------------------------------------------------- finalize

    def finalize(
        self,
        *,
        started_at: str,
        ended_at: str,
        status: str,
        result: str,
        metadata: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        if self._finalized:
            raise ExecutionEvidenceError("emitter is already finalized")
        _require_timestamp(started_at, name="started_at")
        _require_timestamp(ended_at, name="ended_at")
        if ended_at < started_at:
            raise ExecutionEvidenceError("ended_at cannot precede started_at")
        if status not in STATUSES:
            raise ExecutionEvidenceError("unsupported execution status")
        if result not in RESULTS:
            raise ExecutionEvidenceError("unsupported execution result")
        bounded_metadata = _assert_bounded_metadata(metadata or {})

        manifest: dict[str, Any] = {
            "schema_version": SCHEMA_VERSION,
            "adapter_id": ADAPTER_ID,
            "execution_id": self.execution_id,
            "environment": self.environment,
            "scenario": self.scenario,
            "target": self.target,
            "tool": self.tool,
            "producer": self.producer,
            "protocol_version": self.protocol_version,
            "started_at": started_at,
            "ended_at": ended_at,
            "status": status,
            "result": result,
            "classification": self.classification,
            "correlation": dict(self.correlation),
            "retention": {
                "policy_id": self.retention_policy_id,
                "retain_until": self.retain_until,
                "legal_hold": self.legal_hold,
            },
            "refs": {
                "findings": dict(self._findings) if self._findings else None,
                "logs": [dict(item) for item in sorted(self._refs["logs"], key=lambda i: i["path"])],
                "artifacts": [dict(item) for item in sorted(self._refs["artifacts"], key=lambda i: i["path"])],
                "evidence": [dict(item) for item in sorted(self._refs["evidence"], key=lambda i: i["path"])],
            },
            "metadata": bounded_metadata,
        }
        manifest["result_digest"] = sha256_hex(canonical_bytes(manifest))
        payload = canonical_bytes(manifest)
        _atomic_write(self.root / "manifest.json", payload)
        self._finalized = True
        return manifest


# ------------------------------------------------------------------ reading


def load_manifest(results_root: str | Path, execution_id: str) -> dict[str, Any]:
    _require_id(execution_id, name="execution_id")
    root = (Path(results_root).expanduser() / execution_id).resolve()
    path = root / "manifest.json"
    try:
        manifest = json.loads(path.read_bytes())
    except (OSError, json.JSONDecodeError) as exc:
        raise ExecutionEvidenceError("manifest unavailable or invalid") from exc
    if not isinstance(manifest, dict) or manifest.get("execution_id") != execution_id:
        raise ExecutionEvidenceError("manifest identity mismatch")
    return manifest


def manifest_refs(manifest: Mapping[str, Any]) -> list[dict[str, Any]]:
    refs = manifest.get("refs")
    if not isinstance(refs, Mapping):
        raise ExecutionEvidenceError("manifest refs are missing")
    collected: list[dict[str, Any]] = []
    findings = refs.get("findings")
    if isinstance(findings, Mapping):
        collected.append(dict(findings))
    for section in SECTIONS:
        items = refs.get(section)
        if items is None:
            continue
        if not isinstance(items, list):
            raise ExecutionEvidenceError(f"manifest refs.{section} must be a list")
        for item in items:
            if not isinstance(item, Mapping):
                raise ExecutionEvidenceError("manifest reference must be a mapping")
            collected.append(dict(item))
    if len(collected) > MAX_REFS:
        raise ExecutionEvidenceError("manifest reference count exceeds the bounded maximum")
    return collected


def verify_execution(results_root: str | Path, execution_id: str) -> dict[str, Any]:
    """Verify manifest digest and every referenced payload digest/size on disk."""
    manifest = load_manifest(results_root, execution_id)
    root = (Path(results_root).expanduser() / execution_id).resolve()

    declared = manifest.get("result_digest")
    body = {key: value for key, value in manifest.items() if key != "result_digest"}
    recomputed = sha256_hex(canonical_bytes(body))
    problems: list[str] = []
    if not isinstance(declared, str) or not SHA256.fullmatch(declared) or declared != recomputed:
        problems.append("result_digest mismatch")

    checked = 0
    for ref in manifest_refs(manifest):
        relative = ref.get("path")
        if not isinstance(relative, str):
            problems.append("reference path missing")
            continue
        parts = relative.split("/")
        if any(part in {"", ".", ".."} or not SAFE_SEGMENT.fullmatch(part) for part in parts):
            problems.append(f"unsafe reference path: {relative}")
            continue
        path = Path(os.path.normpath(root.joinpath(*parts)))
        if not path.is_relative_to(root):
            problems.append(f"reference escapes execution root: {relative}")
            continue
        if path.is_symlink() or not path.is_file():
            problems.append(f"reference is not a regular file: {relative}")
            continue
        payload = path.read_bytes()
        if sha256_hex(payload) != ref.get("sha256") or len(payload) != ref.get("size_bytes"):
            problems.append(f"reference digest or size mismatch: {relative}")
            continue
        checked += 1

    return {
        "execution_id": execution_id,
        "verified": not problems,
        "references_checked": checked,
        "result_digest": recomputed,
        "problems": problems,
    }


# ---------------------------------------------------------------- projection


def summarize_manifest(manifest: Mapping[str, Any]) -> dict[str, Any]:
    """Bounded, digest-only summary of an execution manifest. Never carries payload bytes."""
    refs = manifest.get("refs") or {}
    findings = refs.get("findings") if isinstance(refs, Mapping) else None
    summary = {
        "schema_version": SCHEMA_VERSION,
        "adapter_id": ADAPTER_ID,
        "execution_id": manifest.get("execution_id"),
        "environment": manifest.get("environment"),
        "scenario": manifest.get("scenario"),
        "target": manifest.get("target"),
        "tool": manifest.get("tool"),
        "started_at": manifest.get("started_at"),
        "ended_at": manifest.get("ended_at"),
        "status": manifest.get("status"),
        "result": manifest.get("result"),
        "correlation": dict(manifest.get("correlation") or {}),
        "result_digest": manifest.get("result_digest"),
        "findings_sha256": findings.get("sha256") if isinstance(findings, Mapping) else None,
        "reference_counts": {
            section: len(refs.get(section) or []) if isinstance(refs, Mapping) else 0 for section in SECTIONS
        },
        "reference_digests": sorted(
            str(ref.get("sha256")) for ref in manifest_refs(manifest) if ref.get("sha256")
        ),
    }
    return summary


def project_execution(
    store: Any,
    results_root: str | Path,
    execution_id: str,
    *,
    include_payloads: bool = False,
) -> dict[str, Any]:
    """Project a verified execution manifest onto Evidence Plane v2 records.

    Returns the manifest (restricted) and summary (exportable) evidence identifiers. Payload
    bytes of referenced outputs are projected as `raw` records only when explicitly requested.
    """
    verification = verify_execution(results_root, execution_id)
    if not verification["verified"]:
        raise ExecutionEvidenceError(f"execution evidence verification failed: {verification['problems']}")

    manifest = load_manifest(results_root, execution_id)
    root = (Path(results_root).expanduser() / execution_id).resolve()
    correlation_values = manifest.get("correlation") or {}
    correlation = Correlation(
        correlation_values["campaign_id"],
        correlation_values["run_id"],
        correlation_values["step_id"],
        correlation_values["attempt_id"],
    )
    retention = manifest.get("retention") or {}
    retention_policy_id = retention.get("policy_id") or "default-30d"
    retain_until = retention.get("retain_until")
    legal_hold = bool(retention.get("legal_hold"))
    producer = manifest.get("producer") or "execution-evidence-bridge"
    protocol_version = manifest.get("protocol_version") or "2.0"
    operation = f"execution.manifest.{manifest.get('status')}"
    created_at = manifest.get("ended_at")

    manifest_payload = canonical_bytes(manifest)
    manifest_record = build_record(
        correlation=correlation,
        classification="restricted",
        producer=producer,
        operation=operation,
        protocol_version=protocol_version,
        payload_sha256=sha256_hex(manifest_payload),
        payload_size=len(manifest_payload),
        media_type="application/json",
        storage_ref=f"evidence://{correlation.campaign_id}/{correlation.run_id}"
        f"/execution/{execution_id}/manifest.json",
        retention_policy_id=retention_policy_id,
        retain_until=retain_until,
        legal_hold=legal_hold,
        created_at=created_at,
    )
    manifest_id = store.put(manifest_record, manifest_payload)

    summary = summarize_manifest(manifest)
    summary_payload = canonical_bytes(summary)
    summary_record = build_record(
        correlation=correlation,
        classification="summary",
        producer="execution-evidence-summarizer",
        operation=operation,
        protocol_version=protocol_version,
        payload_sha256=sha256_hex(summary_payload),
        payload_size=len(summary_payload),
        media_type="application/json",
        storage_ref=f"evidence://{correlation.campaign_id}/{correlation.run_id}"
        f"/execution/{execution_id}/summary.json",
        retention_policy_id=retention_policy_id,
        retain_until=retain_until,
        legal_hold=legal_hold,
        parent_evidence_id=manifest_record["evidence_id"],
        redaction={
            "policy_id": SUMMARY_POLICY_ID,
            "source_sha256": manifest_record["content"]["sha256"],
            "mode": "digest_only_execution_summary",
            "removed_classes": ["raw_output"],
            "removed_fields": ["refs", "metadata", "classification", "retention"],
            "retained_fields": sorted(summary),
        },
        created_at=created_at,
    )
    summary_id = store.put(summary_record, summary_payload)

    payload_ids: list[dict[str, str]] = []
    if include_payloads:
        for ref in manifest_refs(manifest):
            relative = str(ref["path"])
            payload = root.joinpath(*relative.split("/")).read_bytes()
            record = build_record(
                correlation=correlation,
                classification="raw",
                producer=producer,
                operation=f"execution.output.{ref.get('role', 'output')}",
                protocol_version=protocol_version,
                payload_sha256=sha256_hex(payload),
                payload_size=len(payload),
                media_type=str(ref.get("media_type") or "application/octet-stream"),
                storage_ref=f"evidence://{correlation.campaign_id}/{correlation.run_id}"
                f"/execution/{execution_id}/{relative}",
                retention_policy_id=retention_policy_id,
                retain_until=retain_until,
                legal_hold=legal_hold,
                created_at=created_at,
            )
            payload_ids.append({"path": relative, "evidence_id": store.put(record, payload)})

    return {
        "execution_id": execution_id,
        "manifest_evidence_id": manifest_id,
        "summary_evidence_id": summary_id,
        "manifest_sha256": manifest_record["content"]["sha256"],
        "summary_sha256": summary_record["content"]["sha256"],
        "result_digest": manifest["result_digest"],
        "payload_evidence": payload_ids,
        "payloads_projected": bool(include_payloads),
    }


def emit_from_spec(spec: Mapping[str, Any], results_root: str | Path) -> dict[str, Any]:
    """Emit one execution from a bounded declarative spec (fixture/reference integration)."""
    if not isinstance(spec, Mapping):
        raise ExecutionEvidenceError("spec must be a mapping")
    allowed = {
        "execution_id",
        "environment",
        "scenario",
        "target",
        "tool",
        "correlation",
        "classification",
        "retention_policy_id",
        "retain_until",
        "legal_hold",
        "producer",
        "protocol_version",
        "started_at",
        "ended_at",
        "status",
        "result",
        "metadata",
        "findings",
        "outputs",
    }
    unknown = set(spec) - allowed
    if unknown:
        raise ExecutionEvidenceError(f"unsupported spec fields: {sorted(unknown)}")

    emitter = ExecutionEvidenceEmitter(
        results_root,
        execution_id=spec["execution_id"],
        environment=spec["environment"],
        correlation=spec["correlation"],
        scenario=spec.get("scenario"),
        target=spec.get("target"),
        tool=spec.get("tool"),
        classification=spec.get("classification", DEFAULT_CLASSIFICATION),
        retention_policy_id=spec.get("retention_policy_id", "default-30d"),
        retain_until=spec.get("retain_until"),
        legal_hold=bool(spec.get("legal_hold", False)),
        producer=spec.get("producer", "execution-evidence-bridge"),
        protocol_version=spec.get("protocol_version", "2.0"),
    )
    outputs: Iterable[Mapping[str, Any]] = spec.get("outputs") or []
    for output in outputs:
        if not isinstance(output, Mapping) or not set(output) <= {
            "section",
            "name",
            "role",
            "media_type",
            "source_path",
            "text",
        }:
            raise ExecutionEvidenceError("invalid output entry")
        if "source_path" in output and "text" in output:
            raise ExecutionEvidenceError("output entry must use either source_path or text")
        if "source_path" in output:
            payload = Path(str(output["source_path"])).expanduser().read_bytes()
        else:
            payload = str(output.get("text", "")).encode("utf-8")
        emitter.add_output(
            str(output.get("section", "artifacts")),
            str(output["name"]),
            payload,
            media_type=str(output.get("media_type", "application/octet-stream")),
            role=str(output.get("role", "output")),
        )
    if spec.get("findings") is not None:
        emitter.set_findings(spec["findings"])
    return emitter.finalize(
        started_at=spec["started_at"],
        ended_at=spec["ended_at"],
        status=spec["status"],
        result=spec["result"],
        metadata=spec.get("metadata"),
    )
