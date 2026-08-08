from __future__ import annotations

import hashlib
import json
import os
import re
from pathlib import Path
from typing import Any, Mapping

SHA256 = re.compile(r"^[a-f0-9]{64}$")
RECORD_ID = re.compile(r"^kr_[a-f0-9]{32}$")
RELATION_ID = re.compile(r"^rel_[a-f0-9]{32}$")
CONFLICT_ID = re.compile(r"^cf_[a-f0-9]{32}$")
RESOLUTION_ID = re.compile(r"^cr_[a-f0-9]{32}$")

RECORD_KEYS = {
    "schema_version",
    "record_id",
    "entity",
    "source",
    "ingested_at",
    "raw_sha256",
    "immutable_raw",
}
ENTITY_KEYS = {"type", "id"}
SOURCE_KEYS = {"name", "version", "retrieved_at", "locator"}
RELATION_KEYS = {"relation", "from", "to", "confidence", "provenance_record_ids", "rationale"}
CONFLICT_KEYS = {"key", "status", "assertions", "selected_assertion"}
RESOLVED_CONFLICT_KEYS = CONFLICT_KEYS | {"precedence_policy_id"}
ASSERTION_KEYS = {"source_record_id", "value"}


class LocalKnowledgeStoreError(ValueError):
    """Fail-closed local Knowledge Fabric persistence violation."""


def _canonical(value: Mapping[str, Any]) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")


def _sha(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _exact_mapping(value: Any, expected: set[str], *, name: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping) or set(value) != expected:
        raise LocalKnowledgeStoreError(f"invalid {name} shape")
    return value


def _bounded_text(value: Any, *, name: str, maximum: int = 2048) -> str:
    if not isinstance(value, str) or not value or len(value) > maximum:
        raise LocalKnowledgeStoreError(f"invalid {name}")
    return value


def _atomic_create(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    os.chmod(path.parent, 0o700)
    try:
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:
        if path.read_bytes() != payload:
            raise LocalKnowledgeStoreError(f"immutable path already contains different content: {path.name}")
        return
    try:
        with os.fdopen(fd, "wb", closefd=True) as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
    except Exception:
        path.unlink(missing_ok=True)
        raise


def _record_identity(record: Mapping[str, Any]) -> str:
    entity = _exact_mapping(record.get("entity"), ENTITY_KEYS, name="record entity")
    source = _exact_mapping(record.get("source"), SOURCE_KEYS, name="record source")
    seed = {
        "entity_type": entity.get("type"),
        "entity_id": entity.get("id"),
        "source": dict(source),
        "raw_sha256": record.get("raw_sha256"),
    }
    return f"kr_{_sha(_canonical(seed))[:32]}"


def _validate_record(record: Mapping[str, Any], raw_payload: bytes | None = None) -> None:
    _exact_mapping(record, RECORD_KEYS, name="knowledge record")
    entity = _exact_mapping(record["entity"], ENTITY_KEYS, name="record entity")
    source = _exact_mapping(record["source"], SOURCE_KEYS, name="record source")
    _bounded_text(entity.get("type"), name="entity type", maximum=64)
    _bounded_text(entity.get("id"), name="entity id", maximum=256)
    for key in SOURCE_KEYS:
        _bounded_text(source.get(key), name=f"source {key}", maximum=2048)
    _bounded_text(record.get("ingested_at"), name="ingested_at", maximum=128)
    digest = record.get("raw_sha256")
    if not isinstance(digest, str) or not SHA256.fullmatch(digest):
        raise LocalKnowledgeStoreError("invalid raw_sha256")
    if record.get("immutable_raw") is not True:
        raise LocalKnowledgeStoreError("raw knowledge must be immutable")
    record_id = record.get("record_id")
    if not isinstance(record_id, str) or not RECORD_ID.fullmatch(record_id):
        raise LocalKnowledgeStoreError("invalid record_id")
    if record_id != _record_identity(record):
        raise LocalKnowledgeStoreError("record identity does not match canonical provenance")
    if raw_payload is not None and _sha(raw_payload) != digest:
        raise LocalKnowledgeStoreError("raw payload digest mismatch")


def _validate_relation(relation: Mapping[str, Any]) -> None:
    _exact_mapping(relation, RELATION_KEYS, name="relation")
    for key in ("relation", "from", "to", "rationale"):
        _bounded_text(relation.get(key), name=f"relation {key}")
    confidence = relation.get("confidence")
    if isinstance(confidence, bool) or not isinstance(confidence, (int, float)) or not 0.0 <= confidence <= 1.0:
        raise LocalKnowledgeStoreError("invalid relation confidence")
    provenance = relation.get("provenance_record_ids")
    if not isinstance(provenance, list) or not provenance or provenance != sorted(set(provenance)):
        raise LocalKnowledgeStoreError("relation requires unique sorted provenance")
    if any(not isinstance(item, str) or not RECORD_ID.fullmatch(item) for item in provenance):
        raise LocalKnowledgeStoreError("invalid relation provenance record id")


def _validate_assertions(assertions: Any) -> list[Mapping[str, Any]]:
    if not isinstance(assertions, list) or len(assertions) < 2:
        raise LocalKnowledgeStoreError("conflict requires at least two assertions")
    validated: list[Mapping[str, Any]] = []
    source_ids: list[str] = []
    for assertion in assertions:
        value = _exact_mapping(assertion, ASSERTION_KEYS, name="conflict assertion")
        source_id = value.get("source_record_id")
        if not isinstance(source_id, str) or not RECORD_ID.fullmatch(source_id):
            raise LocalKnowledgeStoreError("invalid conflict provenance record id")
        source_ids.append(source_id)
        validated.append(value)
    if len(set(source_ids)) != len(source_ids):
        raise LocalKnowledgeStoreError("conflict assertions require distinct provenance")
    return validated


class LocalKnowledgeStore:
    """Controlled local store proving E-01 integrity semantics in CI.

    It is not a production graph database, external feed synchronizer, TAXII client or
    authorization source. Filesystem immutability here means create-only/content-addressed
    behaviour with integrity sidecars; it is not a WORM/storage-administrator threat claim.
    """

    def __init__(self, root: str | Path) -> None:
        self.root = Path(root).expanduser().resolve()
        if self.root.exists() and not self.root.is_dir():
            raise LocalKnowledgeStoreError("store root must be a directory")
        self.raw = self.root / "raw" / "sha256"
        self.records = self.root / "records"
        self.relations = self.root / "relations"
        self.conflicts = self.root / "conflicts"
        self.resolutions = self.root / "resolutions"
        for path in (self.root, self.raw, self.records, self.relations, self.conflicts, self.resolutions):
            path.mkdir(parents=True, exist_ok=True)
            os.chmod(path, 0o700)

    @staticmethod
    def _json_digest_path(path: Path) -> Path:
        return path.with_suffix(path.suffix + ".sha256")

    def _put_json(self, path: Path, value: Mapping[str, Any]) -> None:
        payload = _canonical(value)
        _atomic_create(path, payload)
        _atomic_create(self._json_digest_path(path), _sha(payload).encode("ascii"))

    def _verify_json(self, path: Path) -> bool:
        try:
            payload = path.read_bytes()
            digest = self._json_digest_path(path).read_text(encoding="ascii")
        except (OSError, UnicodeError):
            return False
        return bool(SHA256.fullmatch(digest)) and _sha(payload) == digest

    def put_raw_record(self, record: Mapping[str, Any], raw_payload: bytes) -> str:
        _validate_record(record, raw_payload)
        record_id = str(record["record_id"])
        digest = str(record["raw_sha256"])
        _atomic_create(self.raw / digest[:2] / digest, raw_payload)
        self._put_json(self.records / f"{record_id}.json", record)
        return record_id

    def get_record(self, record_id: str) -> dict[str, Any]:
        if not RECORD_ID.fullmatch(record_id):
            raise LocalKnowledgeStoreError("invalid record_id")
        path = self.records / f"{record_id}.json"
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise LocalKnowledgeStoreError("knowledge record unavailable") from exc
        if not isinstance(value, dict) or value.get("record_id") != record_id:
            raise LocalKnowledgeStoreError("knowledge record identity mismatch")
        _validate_record(value)
        return value

    def verify_record(self, record_id: str) -> bool:
        try:
            record = self.get_record(record_id)
            path = self.records / f"{record_id}.json"
            if not self._verify_json(path):
                return False
            digest = record["raw_sha256"]
            raw_payload = (self.raw / digest[:2] / digest).read_bytes()
            return _sha(raw_payload) == digest
        except (LocalKnowledgeStoreError, OSError):
            return False

    def publish_relation(self, relation: Mapping[str, Any]) -> str:
        _validate_relation(relation)
        provenance = relation["provenance_record_ids"]
        if any(not self.verify_record(record_id) for record_id in provenance):
            raise LocalKnowledgeStoreError("relation provenance must exist and verify before publication")
        canonical = dict(relation)
        relation_id = f"rel_{_sha(_canonical(canonical))[:32]}"
        envelope = {"relation_id": relation_id, "relation": canonical, "execution_authority": "NONE"}
        self._put_json(self.relations / f"{relation_id}.json", envelope)
        return relation_id

    def verify_relation(self, relation_id: str) -> bool:
        if not RELATION_ID.fullmatch(relation_id):
            return False
        path = self.relations / f"{relation_id}.json"
        if not self._verify_json(path):
            return False
        try:
            envelope = json.loads(path.read_text(encoding="utf-8"))
            if set(envelope) != {"relation_id", "relation", "execution_authority"}:
                return False
            if envelope.get("relation_id") != relation_id or envelope.get("execution_authority") != "NONE":
                return False
            relation = envelope.get("relation")
            if not isinstance(relation, Mapping):
                return False
            _validate_relation(relation)
            expected = f"rel_{_sha(_canonical(dict(relation)))[:32]}"
            if expected != relation_id:
                return False
            return all(self.verify_record(record_id) for record_id in relation["provenance_record_ids"])
        except (OSError, json.JSONDecodeError, LocalKnowledgeStoreError):
            return False

    def persist_conflict(self, conflict: Mapping[str, Any]) -> str:
        _exact_mapping(conflict, CONFLICT_KEYS, name="unresolved conflict")
        _bounded_text(conflict.get("key"), name="conflict key")
        if conflict.get("status") != "unresolved" or conflict.get("selected_assertion") is not None:
            raise LocalKnowledgeStoreError("conflicts must be persisted unresolved")
        assertions = _validate_assertions(conflict.get("assertions"))
        if any(not self.verify_record(str(item["source_record_id"])) for item in assertions):
            raise LocalKnowledgeStoreError("conflict provenance must exist and verify")
        canonical = dict(conflict)
        conflict_id = f"cf_{_sha(_canonical(canonical))[:32]}"
        envelope = {"conflict_id": conflict_id, "conflict": canonical, "automatic_resolution": False}
        self._put_json(self.conflicts / f"{conflict_id}.json", envelope)
        return conflict_id

    def get_conflict(self, conflict_id: str) -> dict[str, Any]:
        if not CONFLICT_ID.fullmatch(conflict_id):
            raise LocalKnowledgeStoreError("invalid conflict_id")
        path = self.conflicts / f"{conflict_id}.json"
        try:
            envelope = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise LocalKnowledgeStoreError("conflict unavailable") from exc
        if not isinstance(envelope, dict) or envelope.get("conflict_id") != conflict_id:
            raise LocalKnowledgeStoreError("conflict identity mismatch")
        conflict = envelope.get("conflict")
        if not isinstance(conflict, dict):
            raise LocalKnowledgeStoreError("invalid conflict envelope")
        return conflict

    def verify_conflict(self, conflict_id: str) -> bool:
        if not CONFLICT_ID.fullmatch(conflict_id):
            return False
        path = self.conflicts / f"{conflict_id}.json"
        if not self._verify_json(path):
            return False
        try:
            envelope = json.loads(path.read_text(encoding="utf-8"))
            if set(envelope) != {"conflict_id", "conflict", "automatic_resolution"}:
                return False
            if envelope.get("conflict_id") != conflict_id or envelope.get("automatic_resolution") is not False:
                return False
            conflict = envelope.get("conflict")
            if not isinstance(conflict, Mapping):
                return False
            _exact_mapping(conflict, CONFLICT_KEYS, name="unresolved conflict")
            if conflict.get("status") != "unresolved" or conflict.get("selected_assertion") is not None:
                return False
            assertions = _validate_assertions(conflict.get("assertions"))
            expected = f"cf_{_sha(_canonical(dict(conflict)))[:32]}"
            return expected == conflict_id and all(
                self.verify_record(str(item["source_record_id"])) for item in assertions
            )
        except (OSError, json.JSONDecodeError, LocalKnowledgeStoreError):
            return False

    def record_resolution(self, conflict_id: str, resolved_conflict: Mapping[str, Any]) -> str:
        if not self.verify_conflict(conflict_id):
            raise LocalKnowledgeStoreError("persisted unresolved conflict must verify before resolution")
        _exact_mapping(resolved_conflict, RESOLVED_CONFLICT_KEYS, name="resolved conflict")
        original = self.get_conflict(conflict_id)
        if resolved_conflict.get("status") != "resolved":
            raise LocalKnowledgeStoreError("resolution must be explicit")
        if resolved_conflict.get("key") != original.get("key") or resolved_conflict.get("assertions") != original.get("assertions"):
            raise LocalKnowledgeStoreError("resolution cannot rewrite conflict history")
        selected = resolved_conflict.get("selected_assertion")
        assertions = _validate_assertions(resolved_conflict.get("assertions"))
        candidates = {item["source_record_id"] for item in assertions}
        if selected not in candidates:
            raise LocalKnowledgeStoreError("resolution must select an existing assertion")
        policy_id = _bounded_text(resolved_conflict.get("precedence_policy_id"), name="precedence policy id", maximum=256)
        envelope = {
            "conflict_id": conflict_id,
            "selected_assertion": selected,
            "precedence_policy_id": policy_id,
            "historical_rewrite": False,
            "automatic_resolution": False,
            "execution_authority": "NONE",
        }
        resolution_id = f"cr_{_sha(_canonical(envelope))[:32]}"
        value = {"resolution_id": resolution_id, **envelope}
        self._put_json(self.resolutions / f"{resolution_id}.json", value)
        return resolution_id

    def verify_resolution(self, resolution_id: str) -> bool:
        if not RESOLUTION_ID.fullmatch(resolution_id):
            return False
        path = self.resolutions / f"{resolution_id}.json"
        if not self._verify_json(path):
            return False
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
            required = {
                "resolution_id",
                "conflict_id",
                "selected_assertion",
                "precedence_policy_id",
                "historical_rewrite",
                "automatic_resolution",
                "execution_authority",
            }
            if not isinstance(value, dict) or set(value) != required:
                return False
            if value.get("resolution_id") != resolution_id:
                return False
            if value.get("historical_rewrite") is not False or value.get("automatic_resolution") is not False:
                return False
            if value.get("execution_authority") != "NONE":
                return False
            if not self.verify_conflict(value.get("conflict_id", "")):
                return False
            conflict = self.get_conflict(value["conflict_id"])
            candidates = {item["source_record_id"] for item in _validate_assertions(conflict["assertions"])}
            if value.get("selected_assertion") not in candidates:
                return False
            identity = {key: value[key] for key in required if key != "resolution_id"}
            return f"cr_{_sha(_canonical(identity))[:32]}" == resolution_id
        except (OSError, json.JSONDecodeError, LocalKnowledgeStoreError):
            return False
