from __future__ import annotations

import hashlib
import json
import os
import re
from pathlib import Path
from typing import Any, Mapping

SHA256 = re.compile(r"^[a-f0-9]{64}$")
SNAPSHOT_ID = re.compile(r"^ks_[a-f0-9]{32}$")
RECORD_ID = re.compile(r"^kr_[a-f0-9]{32}$")
CAMPAIGN_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
TEMPORAL_ID = re.compile(r"^kte_[a-f0-9]{32}$")
PROPOSAL_ID = re.compile(r"^kpr_[a-f0-9]{32}$")
TEMPORAL_TYPES = {"epss", "kev", "vex"}

SNAPSHOT_KEYS = {
    "schema_version", "snapshot_id", "created_at", "source_record_ids", "snapshot_sha256", "immutable",
}
BINDING_KEYS = {"campaign_id", "knowledge_snapshot_id"}
TEMPORAL_KEYS = {"series", "observed_at", "value", "source_record_id", "append_only"}
PROPOSAL_KEYS = {
    "campaign_id", "knowledge_snapshot_id", "rationale", "proposed_steps",
    "proposal_state", "executable", "authorization_source",
}

FORBIDDEN_KEYS = {
    "argv", "authorization", "authorization_ref", "authorization_receipt", "command", "credential",
    "credentials", "cwd", "entrypoint", "environment", "password", "secret", "shell", "target", "token",
    "cookie", "api_key", "execution_allowed", "execution_authorized", "runner_request", "raw_evidence",
    "evidence_payload", "stdout", "stderr",
}

MAX_JSON_BYTES = 256 * 1024
MAX_STEPS = 2_000


class LocalKnowledgeAPIStoreError(ValueError):
    """Fail-closed local Security Knowledge API persistence violation."""


def _canonical(value: Any) -> bytes:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
    if len(encoded) > MAX_JSON_BYTES:
        raise LocalKnowledgeAPIStoreError("canonical payload exceeds local controlled bound")
    return encoded


def _digest(value: Any) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def _exact_mapping(value: Any, expected: set[str], *, name: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping) or set(value) != expected:
        raise LocalKnowledgeAPIStoreError(f"invalid {name} shape")
    return value


def _bounded_text(value: Any, *, name: str, maximum: int = 2048) -> str:
    if not isinstance(value, str) or not value or len(value) > maximum:
        raise LocalKnowledgeAPIStoreError(f"invalid {name}")
    return value


def _walk_keys(value: Any) -> set[str]:
    keys: set[str] = set()
    if isinstance(value, Mapping):
        for key, item in value.items():
            normalized = str(key).lower().replace("-", "_")
            keys.add(normalized)
            keys.update(_walk_keys(item))
    elif isinstance(value, list):
        for item in value:
            keys.update(_walk_keys(item))
    return keys


def _reject_forbidden(value: Any, *, name: str) -> None:
    forbidden = _walk_keys(value).intersection(FORBIDDEN_KEYS)
    if forbidden:
        raise LocalKnowledgeAPIStoreError(f"{name} contains forbidden execution, target, secret or authorization fields")


def _atomic_create(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    os.chmod(path.parent, 0o700)
    try:
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:
        if path.read_bytes() != payload:
            raise LocalKnowledgeAPIStoreError(f"immutable path already contains different content: {path.name}")
        return
    try:
        with os.fdopen(fd, "wb", closefd=True) as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
    except Exception:
        path.unlink(missing_ok=True)
        raise


def _snapshot_seed(snapshot: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "source_record_ids": snapshot["source_record_ids"],
        "created_at": snapshot["created_at"],
    }


def _validate_snapshot(snapshot: Mapping[str, Any]) -> None:
    _exact_mapping(snapshot, SNAPSHOT_KEYS, name="snapshot")
    if snapshot.get("schema_version") != "1.0" or snapshot.get("immutable") is not True:
        raise LocalKnowledgeAPIStoreError("snapshot must use immutable schema version 1.0")
    snapshot_id = snapshot.get("snapshot_id")
    if not isinstance(snapshot_id, str) or not SNAPSHOT_ID.fullmatch(snapshot_id):
        raise LocalKnowledgeAPIStoreError("invalid snapshot_id")
    created_at = _bounded_text(snapshot.get("created_at"), name="snapshot created_at", maximum=128)
    records = snapshot.get("source_record_ids")
    if not isinstance(records, list) or not records or records != sorted(set(records)):
        raise LocalKnowledgeAPIStoreError("snapshot source records must be a non-empty sorted unique list")
    if any(not isinstance(item, str) or not RECORD_ID.fullmatch(item) for item in records):
        raise LocalKnowledgeAPIStoreError("invalid snapshot source record id")
    seed = {"source_record_ids": records, "created_at": created_at}
    expected_hash = _digest(seed)
    if snapshot.get("snapshot_sha256") != expected_hash:
        raise LocalKnowledgeAPIStoreError("snapshot sha256 does not match canonical content")
    if snapshot_id != f"ks_{expected_hash[:32]}":
        raise LocalKnowledgeAPIStoreError("snapshot id does not match canonical content")


def _validate_binding(binding: Mapping[str, Any]) -> None:
    _exact_mapping(binding, BINDING_KEYS, name="campaign binding")
    campaign_id = binding.get("campaign_id")
    snapshot_id = binding.get("knowledge_snapshot_id")
    if not isinstance(campaign_id, str) or not CAMPAIGN_ID.fullmatch(campaign_id):
        raise LocalKnowledgeAPIStoreError("invalid campaign id")
    if not isinstance(snapshot_id, str) or not SNAPSHOT_ID.fullmatch(snapshot_id):
        raise LocalKnowledgeAPIStoreError("invalid campaign snapshot id")


def _validate_temporal(entry: Mapping[str, Any]) -> None:
    _exact_mapping(entry, TEMPORAL_KEYS, name="temporal entry")
    if entry.get("series") not in TEMPORAL_TYPES:
        raise LocalKnowledgeAPIStoreError("unsupported temporal series")
    _bounded_text(entry.get("observed_at"), name="temporal observed_at", maximum=128)
    record_id = entry.get("source_record_id")
    if not isinstance(record_id, str) or not RECORD_ID.fullmatch(record_id):
        raise LocalKnowledgeAPIStoreError("invalid temporal provenance record")
    if entry.get("append_only") is not True:
        raise LocalKnowledgeAPIStoreError("temporal entries must be append-only")
    _reject_forbidden(entry.get("value"), name="temporal value")
    _canonical(entry.get("value"))


def _validate_proposal(proposal: Mapping[str, Any]) -> None:
    _exact_mapping(proposal, PROPOSAL_KEYS, name="campaign proposal")
    campaign_id = proposal.get("campaign_id")
    snapshot_id = proposal.get("knowledge_snapshot_id")
    if not isinstance(campaign_id, str) or not CAMPAIGN_ID.fullmatch(campaign_id):
        raise LocalKnowledgeAPIStoreError("invalid proposal campaign id")
    if not isinstance(snapshot_id, str) or not SNAPSHOT_ID.fullmatch(snapshot_id):
        raise LocalKnowledgeAPIStoreError("invalid proposal snapshot id")
    _bounded_text(proposal.get("rationale"), name="proposal rationale", maximum=8192)
    if proposal.get("proposal_state") != "PROPOSAL_ONLY":
        raise LocalKnowledgeAPIStoreError("proposal must remain proposal-only")
    if proposal.get("executable") is not False:
        raise LocalKnowledgeAPIStoreError("proposal must not be executable")
    if proposal.get("authorization_source") != "CONTROL_PLANE_ONLY":
        raise LocalKnowledgeAPIStoreError("Control Plane must remain the sole authorization source")
    steps = proposal.get("proposed_steps")
    if not isinstance(steps, list) or not steps or len(steps) > MAX_STEPS:
        raise LocalKnowledgeAPIStoreError("proposal requires a bounded non-empty step list")
    for step in steps:
        if not isinstance(step, Mapping) or not step.get("operation") or not step.get("reason"):
            raise LocalKnowledgeAPIStoreError("proposal steps require operation and reason")
        _reject_forbidden(step, name="proposal step")
    _reject_forbidden({key: value for key, value in proposal.items() if key != "proposed_steps"}, name="proposal")
    _canonical(proposal)


class LocalKnowledgeAPIStore:
    """Controlled-local persistence for E-02 contracts.

    This store proves immutable snapshot/campaign/temporal/proposal semantics in CI.
    It is not an HTTP API, database, graph service, external feed synchronizer,
    production campaign planner or execution-authorization source.
    """

    def __init__(self, root: str | Path) -> None:
        self.root = Path(root).expanduser().resolve()
        if self.root.exists() and not self.root.is_dir():
            raise LocalKnowledgeAPIStoreError("store root must be a directory")
        self.snapshots = self.root / "snapshots"
        self.campaigns = self.root / "campaigns"
        self.temporal = self.root / "temporal"
        self.proposals = self.root / "proposals"
        for path in (self.root, self.snapshots, self.campaigns, self.temporal, self.proposals):
            path.mkdir(parents=True, exist_ok=True)
            os.chmod(path, 0o700)

    @staticmethod
    def _digest_path(path: Path) -> Path:
        return path.with_suffix(path.suffix + ".sha256")

    def _put_json(self, path: Path, value: Mapping[str, Any]) -> None:
        payload = _canonical(value)
        _atomic_create(path, payload)
        _atomic_create(self._digest_path(path), hashlib.sha256(payload).hexdigest().encode("ascii"))

    def _load_json(self, path: Path, *, label: str) -> dict[str, Any]:
        try:
            payload = path.read_bytes()
            digest = self._digest_path(path).read_text(encoding="ascii")
            if not SHA256.fullmatch(digest) or hashlib.sha256(payload).hexdigest() != digest:
                raise LocalKnowledgeAPIStoreError(f"{label} integrity verification failed")
            value = json.loads(payload)
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise LocalKnowledgeAPIStoreError(f"{label} unavailable or invalid") from exc
        if not isinstance(value, dict):
            raise LocalKnowledgeAPIStoreError(f"invalid {label} record")
        return value

    def put_snapshot(self, snapshot: Mapping[str, Any], knowledge_store: Any) -> str:
        _validate_snapshot(snapshot)
        for record_id in snapshot["source_record_ids"]:
            try:
                valid = knowledge_store.verify_record(record_id)
            except Exception as exc:
                raise LocalKnowledgeAPIStoreError("knowledge provenance verification unavailable") from exc
            if valid is not True:
                raise LocalKnowledgeAPIStoreError("snapshot provenance must exist and verify")
        snapshot_id = str(snapshot["snapshot_id"])
        self._put_json(self.snapshots / f"{snapshot_id}.json", dict(snapshot))
        return snapshot_id

    def get_snapshot(self, snapshot_id: str) -> dict[str, Any]:
        if not SNAPSHOT_ID.fullmatch(snapshot_id):
            raise LocalKnowledgeAPIStoreError("invalid snapshot id")
        snapshot = self._load_json(self.snapshots / f"{snapshot_id}.json", label="snapshot")
        _validate_snapshot(snapshot)
        return snapshot

    def verify_snapshot(self, snapshot_id: str, knowledge_store: Any | None = None) -> bool:
        try:
            snapshot = self.get_snapshot(snapshot_id)
            if knowledge_store is not None:
                return all(knowledge_store.verify_record(record_id) is True for record_id in snapshot["source_record_ids"])
            return True
        except Exception:
            return False

    def bind_campaign(self, binding: Mapping[str, Any], knowledge_store: Any | None = None) -> str:
        _validate_binding(binding)
        snapshot_id = str(binding["knowledge_snapshot_id"])
        if not self.verify_snapshot(snapshot_id, knowledge_store):
            raise LocalKnowledgeAPIStoreError("campaign binding requires a verified persisted snapshot")
        campaign_id = str(binding["campaign_id"])
        self._put_json(self.campaigns / f"{campaign_id}.json", dict(binding))
        return campaign_id

    def get_campaign_binding(self, campaign_id: str) -> dict[str, Any]:
        if not CAMPAIGN_ID.fullmatch(campaign_id):
            raise LocalKnowledgeAPIStoreError("invalid campaign id")
        binding = self._load_json(self.campaigns / f"{campaign_id}.json", label="campaign binding")
        _validate_binding(binding)
        if binding.get("campaign_id") != campaign_id:
            raise LocalKnowledgeAPIStoreError("campaign binding identity mismatch")
        return binding

    def verify_campaign_binding(self, campaign_id: str, knowledge_store: Any | None = None) -> bool:
        try:
            binding = self.get_campaign_binding(campaign_id)
            return self.verify_snapshot(str(binding["knowledge_snapshot_id"]), knowledge_store)
        except LocalKnowledgeAPIStoreError:
            return False

    def append_temporal(self, entry: Mapping[str, Any], knowledge_store: Any) -> str:
        _validate_temporal(entry)
        record_id = str(entry["source_record_id"])
        try:
            valid = knowledge_store.verify_record(record_id)
        except Exception as exc:
            raise LocalKnowledgeAPIStoreError("temporal provenance verification unavailable") from exc
        if valid is not True:
            raise LocalKnowledgeAPIStoreError("temporal entry requires verified provenance")
        entry_id = f"kte_{_digest(dict(entry))[:32]}"
        self._put_json(self.temporal / str(entry["series"]) / f"{entry_id}.json", dict(entry))
        return entry_id

    def verify_temporal(self, entry_id: str, series: str, knowledge_store: Any | None = None) -> bool:
        if not TEMPORAL_ID.fullmatch(entry_id) or series not in TEMPORAL_TYPES:
            return False
        try:
            entry = self._load_json(self.temporal / series / f"{entry_id}.json", label="temporal entry")
            _validate_temporal(entry)
            if f"kte_{_digest(entry)[:32]}" != entry_id:
                return False
            if knowledge_store is not None and knowledge_store.verify_record(str(entry["source_record_id"])) is not True:
                return False
            return True
        except Exception:
            return False

    def persist_proposal(self, proposal: Mapping[str, Any], knowledge_store: Any | None = None) -> str:
        _validate_proposal(proposal)
        campaign_id = str(proposal["campaign_id"])
        if not self.verify_campaign_binding(campaign_id, knowledge_store):
            raise LocalKnowledgeAPIStoreError("proposal requires a verified pinned campaign snapshot")
        binding = self.get_campaign_binding(campaign_id)
        if proposal.get("knowledge_snapshot_id") != binding.get("knowledge_snapshot_id"):
            raise LocalKnowledgeAPIStoreError("proposal snapshot must match the campaign's pinned snapshot")
        proposal_id = f"kpr_{_digest(dict(proposal))[:32]}"
        envelope = {
            "proposal_id": proposal_id,
            "proposal": dict(proposal),
            "execution_authority": "NONE",
            "dispatch_available": False,
        }
        self._put_json(self.proposals / f"{proposal_id}.json", envelope)
        return proposal_id

    def verify_proposal(self, proposal_id: str, knowledge_store: Any | None = None) -> bool:
        if not PROPOSAL_ID.fullmatch(proposal_id):
            return False
        try:
            envelope = self._load_json(self.proposals / f"{proposal_id}.json", label="proposal")
            if set(envelope) != {"proposal_id", "proposal", "execution_authority", "dispatch_available"}:
                return False
            if envelope.get("proposal_id") != proposal_id:
                return False
            if envelope.get("execution_authority") != "NONE" or envelope.get("dispatch_available") is not False:
                return False
            proposal = envelope.get("proposal")
            if not isinstance(proposal, Mapping):
                return False
            _validate_proposal(proposal)
            if f"kpr_{_digest(dict(proposal))[:32]}" != proposal_id:
                return False
            campaign_id = str(proposal["campaign_id"])
            if not self.verify_campaign_binding(campaign_id, knowledge_store):
                return False
            binding = self.get_campaign_binding(campaign_id)
            return proposal.get("knowledge_snapshot_id") == binding.get("knowledge_snapshot_id")
        except Exception:
            return False
