from __future__ import annotations

import hashlib
import json
import os
import re
from pathlib import Path
from typing import Any, Mapping

SHA256 = re.compile(r"^[a-f0-9]{64}$")
EVIDENCE_ID = re.compile(r"^ev_[a-f0-9]{32}$")
CLASSIFICATIONS = {"raw", "restricted", "sanitized", "summary"}
EXPORTABLE_CLASSIFICATIONS = {"sanitized", "summary"}
RECORD_KEYS = {
    "schema_version",
    "evidence_id",
    "classification",
    "correlation",
    "origin",
    "content",
    "retention",
    "parent_evidence_id",
    "redaction",
    "created_at",
}
CORRELATION_KEYS = {"campaign_id", "run_id", "step_id", "attempt_id"}
ORIGIN_KEYS = {"producer", "operation", "protocol_version", "knowledge_snapshot"}
CONTENT_KEYS = {"sha256", "size_bytes", "media_type", "storage_ref"}
RETENTION_KEYS = {"policy_id", "retain_until", "legal_hold"}


class LocalEvidenceStoreError(ValueError):
    """Fail-closed local evidence-store violation."""


def _canonical_json(value: Mapping[str, Any]) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _exact_mapping(value: Any, expected: set[str], *, name: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping) or set(value) != expected:
        raise LocalEvidenceStoreError(f"invalid {name} shape")
    return value


def _validate_record_shape(record: Mapping[str, Any]) -> None:
    _exact_mapping(record, RECORD_KEYS, name="record")
    _exact_mapping(record.get("correlation"), CORRELATION_KEYS, name="correlation")
    _exact_mapping(record.get("origin"), ORIGIN_KEYS, name="origin")
    _exact_mapping(record.get("content"), CONTENT_KEYS, name="content")
    _exact_mapping(record.get("retention"), RETENTION_KEYS, name="retention")


def _atomic_create(path: Path, payload: bytes, *, mode: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    os.chmod(path.parent, 0o700)
    try:
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, mode)
    except FileExistsError:
        if path.read_bytes() != payload:
            raise LocalEvidenceStoreError(f"immutable path already exists with different content: {path.name}")
        return
    try:
        with os.fdopen(fd, "wb", closefd=True) as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
    except Exception:
        path.unlink(missing_ok=True)
        raise


class LocalEvidenceStore:
    """Local reference persistence boundary for controlled CI evidence.

    This store intentionally does not claim encryption, WORM semantics, object-storage
    durability, retention deletion, customer export or production readiness. Record
    sidecars detect accidental or single-file metadata tampering; they are not a claim
    of protection against an actor with write access to the complete store.
    """

    def __init__(self, root: str | Path) -> None:
        self.root = Path(root).expanduser().resolve()
        if self.root.exists() and not self.root.is_dir():
            raise LocalEvidenceStoreError("store root must be a directory")
        self.objects = self.root / "objects" / "sha256"
        self.records = self.root / "records"
        for path in (self.root, self.root / "objects", self.objects, self.records):
            path.mkdir(parents=True, exist_ok=True)
            os.chmod(path, 0o700)

    def _record_path(self, evidence_id: str) -> Path:
        return self.records / f"{evidence_id}.json"

    def _record_digest_path(self, evidence_id: str) -> Path:
        return self.records / f"{evidence_id}.sha256"

    def put(self, record: Mapping[str, Any], payload: bytes) -> str:
        _validate_record_shape(record)
        evidence_id = record.get("evidence_id")
        classification = record.get("classification")
        content = record["content"]
        if not isinstance(evidence_id, str) or not EVIDENCE_ID.fullmatch(evidence_id):
            raise LocalEvidenceStoreError("invalid evidence_id")
        if classification not in CLASSIFICATIONS:
            raise LocalEvidenceStoreError("invalid classification")

        digest = content.get("sha256")
        size = content.get("size_bytes")
        storage_ref = content.get("storage_ref")
        if not isinstance(digest, str) or not SHA256.fullmatch(digest):
            raise LocalEvidenceStoreError("invalid content digest")
        if digest != _sha256(payload):
            raise LocalEvidenceStoreError("payload digest mismatch")
        if size != len(payload):
            raise LocalEvidenceStoreError("payload size mismatch")
        if not isinstance(storage_ref, str) or not storage_ref.startswith("evidence://"):
            raise LocalEvidenceStoreError("invalid storage_ref")

        if classification in EXPORTABLE_CLASSIFICATIONS:
            parent_id = record.get("parent_evidence_id")
            redaction = record.get("redaction")
            if not isinstance(parent_id, str) or not EVIDENCE_ID.fullmatch(parent_id):
                raise LocalEvidenceStoreError("derived evidence requires valid parent")
            if not isinstance(redaction, Mapping):
                raise LocalEvidenceStoreError("derived evidence requires redaction metadata")
            parent = self.get_record(parent_id)
            parent_content = parent.get("content")
            if not isinstance(parent_content, Mapping):
                raise LocalEvidenceStoreError("parent content unavailable")
            if redaction.get("source_sha256") != parent_content.get("sha256"):
                raise LocalEvidenceStoreError("derived evidence source digest does not match parent")
            if not self.verify(parent_id):
                raise LocalEvidenceStoreError("parent evidence integrity verification failed")
        elif record.get("parent_evidence_id") is not None or record.get("redaction") is not None:
            raise LocalEvidenceStoreError("raw/restricted evidence cannot claim derived lineage")

        object_path = self.objects / digest[:2] / digest
        record_path = self._record_path(evidence_id)
        record_payload = _canonical_json(record)
        record_digest = _sha256(record_payload).encode("ascii")
        _atomic_create(object_path, payload, mode=0o600)
        _atomic_create(record_path, record_payload, mode=0o600)
        _atomic_create(self._record_digest_path(evidence_id), record_digest, mode=0o600)
        return evidence_id

    def get_record(self, evidence_id: str) -> dict[str, Any]:
        if not EVIDENCE_ID.fullmatch(evidence_id):
            raise LocalEvidenceStoreError("invalid evidence_id")
        path = self._record_path(evidence_id)
        try:
            record = json.loads(path.read_bytes())
        except (OSError, json.JSONDecodeError) as exc:
            raise LocalEvidenceStoreError("record unavailable or invalid") from exc
        if not isinstance(record, dict) or record.get("evidence_id") != evidence_id:
            raise LocalEvidenceStoreError("record identity mismatch")
        _validate_record_shape(record)
        return record

    def verify(self, evidence_id: str) -> bool:
        try:
            record = self.get_record(evidence_id)
            record_digest = self._record_digest_path(evidence_id).read_text(encoding="ascii")
            if not SHA256.fullmatch(record_digest):
                return False
            if _sha256(_canonical_json(record)) != record_digest:
                return False

            content = record["content"]
            digest = content.get("sha256")
            size = content.get("size_bytes")
            if not isinstance(digest, str) or not SHA256.fullmatch(digest):
                return False
            payload = (self.objects / digest[:2] / digest).read_bytes()
            if len(payload) != size or _sha256(payload) != digest:
                return False
            if record.get("classification") in EXPORTABLE_CLASSIFICATIONS:
                parent_id = record.get("parent_evidence_id")
                redaction = record.get("redaction")
                if not isinstance(parent_id, str) or not isinstance(redaction, Mapping):
                    return False
                parent = self.get_record(parent_id)
                if redaction.get("source_sha256") != parent["content"].get("sha256"):
                    return False
                if not self.verify(parent_id):
                    return False
            return True
        except (LocalEvidenceStoreError, OSError, UnicodeError):
            return False

    def replay_descriptor(self, evidence_id: str) -> dict[str, Any]:
        if not self.verify(evidence_id):
            raise LocalEvidenceStoreError("evidence integrity verification failed")
        record = self.get_record(evidence_id)
        origin = record["origin"]
        correlation = record["correlation"]
        content = record["content"]
        return {
            "schema_version": record.get("schema_version"),
            "evidence_id": evidence_id,
            "correlation": dict(correlation),
            "producer": origin.get("producer"),
            "operation": origin.get("operation"),
            "protocol_version": origin.get("protocol_version"),
            "knowledge_snapshot": origin.get("knowledge_snapshot"),
            "payload_sha256": content.get("sha256"),
        }

    def export_payload(self, evidence_id: str) -> bytes:
        if not self.verify(evidence_id):
            raise LocalEvidenceStoreError("evidence integrity verification failed")
        record = self.get_record(evidence_id)
        if record.get("classification") not in EXPORTABLE_CLASSIFICATIONS:
            raise LocalEvidenceStoreError("classification is not exportable")
        digest = record["content"]["sha256"]
        return (self.objects / digest[:2] / digest).read_bytes()
