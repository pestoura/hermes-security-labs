#!/usr/bin/env python3
"""Custody bridge from terminal Runner outcomes to the existing Evidence Plane.

This module does not execute a Runner effect and does not create authorization.
It persists a validated terminal outcome after the adapter has already completed
(or replayed) the effect. Execution identity is derived from the Runner request
fingerprint, so exact logical retries address the same immutable custody record.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import sys
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

HERE = Path(__file__).resolve().parent
REPOSITORY_ROOT = HERE.parents[1]
RUNNER_SDK_SRC = REPOSITORY_ROOT / "platform" / "runner-protocol" / "src"

if str(RUNNER_SDK_SRC) not in sys.path:  # pragma: no cover - import wiring
    sys.path.insert(0, str(RUNNER_SDK_SRC))

from runner_protocol_v2 import (  # noqa: E402
    ProtocolValidationError,
    request_fingerprint,
    validate_semantics,
)

POLICY_PATH = HERE / "runner-outcome-policy.yaml"
EXECUTION_BRIDGE_PATH = HERE / "execution_bridge.py"


def _load_execution_bridge():
    name = "runner_outcome_execution_bridge"
    existing = sys.modules.get(name)
    if existing is not None:
        return existing
    spec = importlib.util.spec_from_file_location(name, EXECUTION_BRIDGE_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError("cannot load canonical execution evidence bridge")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


execution_bridge = _load_execution_bridge()

RUNNER_STATUS_MAP: dict[str, tuple[str, str]] = {
    "PASS": ("completed", "inconclusive"),
    "FAIL": ("completed", "inconclusive"),
    "INCONCLUSIVE": ("completed", "inconclusive"),
    "REFUSED": ("completed", "skipped"),
    "CANCELLED": ("cancelled", "skipped"),
    "ERROR": ("failed", "error"),
    "TIMED_OUT": ("failed", "error"),
}


class RunnerOutcomeCustodyError(ValueError):
    """Stable fail-closed custody error."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class CustodyResult:
    execution_id: str
    result_digest: str
    manifest_evidence_id: str
    summary_evidence_id: str
    replayed_custody: bool

    def as_safe_dict(self) -> dict[str, Any]:
        return {
            "execution_id": self.execution_id,
            "result_digest": self.result_digest,
            "manifest_evidence_id": self.manifest_evidence_id,
            "summary_evidence_id": self.summary_evidence_id,
            "replayed_custody": self.replayed_custody,
        }


def validate_policy(document: Any) -> list[str]:
    if not isinstance(document, Mapping):
        return ["Runner outcome custody policy must be an object"]
    findings: list[str] = []
    if document.get("schema_version") != "1.0":
        findings.append("schema_version must be '1.0'")
    if document.get("policy_id") != "hexor.runner.outcome.custody":
        findings.append("policy_id must be hexor.runner.outcome.custody")
    if document.get("state") not in {"DISABLED", "ENABLED"}:
        findings.append("state must be DISABLED or ENABLED")
    if document.get("default") != "deny":
        findings.append("default must be deny")
    if document.get("runtime_status") != "NOT_RUN":
        findings.append("runtime_status must remain NOT_RUN before live acceptance")
    if document.get("execution_authority") != "none":
        findings.append("Evidence custody must never claim execution authority")

    custody = document.get("custody")
    if not isinstance(custody, Mapping):
        return findings + ["custody must be an object"]
    expected = {
        "execution_manifest",
        "evidence_plane_projection",
        "include_payloads_in_projection",
        "classification",
        "retention_policy_id",
    }
    if set(custody) != expected:
        findings.append("custody exact fields do not match the canonical contract")
    if custody.get("execution_manifest") != "required":
        findings.append("execution_manifest must be required")
    if custody.get("evidence_plane_projection") != "required":
        findings.append("evidence_plane_projection must be required")
    if custody.get("include_payloads_in_projection") is not False:
        findings.append("payload projection must remain disabled in this lane")
    if custody.get("classification") != "sanitized":
        findings.append("Runner terminal outcome classification must be sanitized")
    retention = custody.get("retention_policy_id")
    if not isinstance(retention, str) or not retention:
        findings.append("retention_policy_id is required")
    return findings


def load_policy(path: Path | str = POLICY_PATH) -> dict[str, Any]:
    policy_path = Path(path)
    try:
        document = yaml.safe_load(policy_path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise RunnerOutcomeCustodyError("POLICY_UNREADABLE", str(exc)) from exc
    except yaml.YAMLError as exc:
        raise RunnerOutcomeCustodyError("POLICY_INVALID", str(exc)) from exc
    findings = validate_policy(document)
    if findings:
        raise RunnerOutcomeCustodyError("POLICY_INVALID", "; ".join(findings))
    return dict(document)


def _logical_correlation_matches(actual: Any, expected: Mapping[str, Any]) -> bool:
    if not isinstance(actual, Mapping):
        return False
    return all(
        actual.get(field) == expected.get(field)
        for field in ("campaign_id", "run_id", "step_id")
    )


def _execution_id(adapter_id: str, request: Mapping[str, Any]) -> tuple[str, str]:
    fingerprint = request_fingerprint(request)
    digest = hashlib.sha256(f"{adapter_id}:{fingerprint}".encode("utf-8")).hexdigest()
    return f"runner-{digest[:48]}", fingerprint


def _target_id(request: Mapping[str, Any]) -> str:
    try:
        target = request["operation"]["input"]["target"]
        target_type = target["type"]
        target_id = target["value"]
    except (KeyError, TypeError):
        raise RunnerOutcomeCustodyError(
            "REQUEST_TARGET_INVALID",
            "Runner request lacks canonical target envelope",
        ) from None
    if target_type != "lab-asset" or not isinstance(target_id, str) or not target_id:
        raise RunnerOutcomeCustodyError(
            "REQUEST_TARGET_INVALID",
            "Runner custody requires canonical lab-asset target",
        )
    return target_id


def _validate_output_digest(outcome: Mapping[str, Any]) -> str | None:
    output = outcome.get("output")
    if output is None:
        return None
    if not isinstance(output, Mapping):
        raise RunnerOutcomeCustodyError("OUTCOME_INVALID", "Runner output must be an object")
    payload = execution_bridge.canonical_bytes(output)
    digest = execution_bridge.sha256_hex(payload)
    refs = outcome.get("evidence_refs")
    if not isinstance(refs, list):
        raise RunnerOutcomeCustodyError(
            "OUTCOME_EVIDENCE_INVALID",
            "evidence_refs must be an array",
        )
    if not any(
        isinstance(ref, Mapping)
        and ref.get("kind") == "execution"
        and ref.get("sha256") == digest
        for ref in refs
    ):
        raise RunnerOutcomeCustodyError(
            "OUTCOME_EVIDENCE_DIGEST_MISMATCH",
            "Runner output digest is not bound by an execution evidence reference",
        )
    return digest


class RunnerOutcomeCustody:
    """Persist terminal outcomes into the canonical execution/evidence custody path."""

    def __init__(self, policy: Mapping[str, Any]) -> None:
        findings = validate_policy(policy)
        if findings:
            raise RunnerOutcomeCustodyError("POLICY_INVALID", "; ".join(findings))
        self._policy = dict(policy)

    @property
    def enabled(self) -> bool:
        return self._policy.get("state") == "ENABLED"

    def persist(
        self,
        *,
        request: dict[str, Any],
        outcome: dict[str, Any],
        adapter_id: str,
        principal_id: str,
        results_root: str | Path,
        evidence_store: Any,
    ) -> CustodyResult:
        if not self.enabled:
            raise RunnerOutcomeCustodyError(
                "CUSTODY_DISABLED",
                "Runner outcome custody policy is disabled",
            )
        if not isinstance(adapter_id, str) or not adapter_id:
            raise RunnerOutcomeCustodyError("ADAPTER_ID_INVALID", "adapter_id is required")
        if not isinstance(principal_id, str) or not principal_id:
            raise RunnerOutcomeCustodyError(
                "PRINCIPAL_ID_INVALID",
                "principal_id is required",
            )
        if evidence_store is None or not hasattr(evidence_store, "put"):
            raise RunnerOutcomeCustodyError(
                "EVIDENCE_STORE_UNAVAILABLE",
                "Evidence Plane store is required",
            )

        try:
            validate_semantics(request)
            validate_semantics(outcome)
        except ProtocolValidationError as exc:
            raise RunnerOutcomeCustodyError("RUNNER_MESSAGE_INVALID", str(exc)) from exc
        if request.get("message_type") != "runner.step.request":
            raise RunnerOutcomeCustodyError(
                "RUNNER_MESSAGE_INVALID",
                "custody requires runner.step.request",
            )
        if outcome.get("message_type") != "runner.outcome":
            raise RunnerOutcomeCustodyError(
                "RUNNER_MESSAGE_INVALID",
                "custody requires terminal runner.outcome",
            )
        if not _logical_correlation_matches(
            outcome.get("correlation"), request["correlation"]
        ):
            raise RunnerOutcomeCustodyError(
                "OUTCOME_CORRELATION_MISMATCH",
                "outcome logical correlation differs from request",
            )

        runner_status = outcome.get("status")
        mapped = RUNNER_STATUS_MAP.get(runner_status)
        if mapped is None:
            raise RunnerOutcomeCustodyError(
                "OUTCOME_STATUS_UNSUPPORTED",
                "unsupported Runner terminal status",
            )
        execution_status, execution_result = mapped
        output_digest = _validate_output_digest(outcome)
        execution_id, fingerprint = _execution_id(adapter_id, request)
        target_id = _target_id(request)
        capability_id = request["operation"]["capability_id"]
        if not isinstance(capability_id, str) or not capability_id:
            raise RunnerOutcomeCustodyError(
                "CAPABILITY_INVALID",
                "capability_id is required",
            )

        root = Path(results_root).expanduser()
        preexisting = (root / execution_id / "manifest.json").is_file()
        custody_policy = self._policy["custody"]
        emitter = execution_bridge.ExecutionEvidenceEmitter(
            root,
            execution_id=execution_id,
            environment="runner",
            correlation=outcome["correlation"],
            scenario="runner-step",
            target=target_id,
            tool=adapter_id,
            classification=custody_policy["classification"],
            retention_policy_id=custody_policy["retention_policy_id"],
            producer="runner-outcome-custody-v1",
            protocol_version=request["protocol_version"],
        )
        emitter.add_output(
            "evidence",
            "runner-outcome.json",
            execution_bridge.canonical_bytes(outcome),
            media_type="application/json",
            role="runner_outcome",
        )
        metadata: dict[str, Any] = {
            "adapter_id": adapter_id,
            "principal_id": principal_id,
            "capability_id": capability_id,
            "runner_status": runner_status,
            "logical_fingerprint": fingerprint,
            "source_attempt_id": outcome["correlation"]["attempt_id"],
            "runner_output_sha256": output_digest,
        }
        manifest = emitter.finalize(
            started_at=outcome["started_at"],
            ended_at=outcome["finished_at"],
            status=execution_status,
            result=execution_result,
            metadata=metadata,
        )
        verification = execution_bridge.verify_execution(root, execution_id)
        if not verification["verified"]:
            raise RunnerOutcomeCustodyError(
                "EXECUTION_EVIDENCE_INVALID",
                "execution evidence failed integrity verification",
            )
        try:
            projection = execution_bridge.project_execution(
                evidence_store,
                root,
                execution_id,
                include_payloads=custody_policy["include_payloads_in_projection"],
            )
        except Exception as exc:
            raise RunnerOutcomeCustodyError(
                "EVIDENCE_PROJECTION_FAILED",
                f"Evidence Plane projection failed safely: {type(exc).__name__}",
            ) from exc

        return CustodyResult(
            execution_id=execution_id,
            result_digest=manifest["result_digest"],
            manifest_evidence_id=projection["manifest_evidence_id"],
            summary_evidence_id=projection["summary_evidence_id"],
            replayed_custody=preexisting,
        )


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--policy", default=str(POLICY_PATH))
    parser.add_argument("command", choices=("validate",))
    args = parser.parse_args(list(argv) if argv is not None else None)
    try:
        policy = load_policy(args.policy)
        RunnerOutcomeCustody(policy)
    except RunnerOutcomeCustodyError as exc:
        print(f"FAIL {exc.code}: {exc}", file=sys.stderr)
        return 1
    print("OK Runner outcome custody policy is fail-closed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
