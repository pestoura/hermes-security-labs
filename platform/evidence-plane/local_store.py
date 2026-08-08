from __future__ import annotations

import hashlib
import json
import os
import re
from pathlib import Path
from typing import Any, Mapping

SHA256 = re.compile(r"^[a-f0-9]{64}$")
EVIDENCE_ID = re.compile(r"^ev_[a-f0-9]{32}$")
EXPORTABLE_CLASSIFICATIONS = {"sanitized", "summary"}


class LocalEvidenceStoreError(ValueError):
    """Fail-closed local evidence-store violation."""


def _canonical_json(value: Mapping[str, Any]) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _atomic_create(path: Path, payload: bytes, *, mode: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
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
    """Repository-local reference persistence boundary for controlled CI evidence.

    This store is intentionally local and does not claim encryption, WORM semantics,
    object-storage durability, retention deletion, customer export or production readiness.
    """

    def __init__(self, root: str | Path) -> None:
        self.root = Path(root).expanduser().resolve()
        if self.root.exists() and not self.root.is_dir():
            raise LocalEvidenceStoreError("store root must be a directory")
        self.objects = self.root / "objects" / "sha256"
        self.records = self.root / "records"
        self.root.mkdir(parents=True, exist_ok=True)
        os.chmod(self.root, 0o700)

    def put(self, record: Mapping[str, Any], payload: bytes) -> str:
        evidence_id = record.get("evidence_id")
        classification = record.get("classification")
        content = record.get("content")
        if not isinstance(evidence_id, str) or not EVIDENCE_ID.fullmatch(evidence_id):
            raise LocalEvidenceStoreError("invalid evidence_id")
        if classification not in {"raw", "restricted", "sanitized", "summary"}:
            raise LocalEvidenceStoreError("invalid classification")
        if not isinstance(content, Mapping):
            raise LocalEvidenceStoreError("missing content metadata")

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

        object_path = self.objects / digest[:2] / digest
        record_path = self.records / f"{evidence_id}.json"
        _atomic_create(object_path, payload, mode=0o600)
        _atomic_create(record_path, _canonical_json(record), mode=0o600)
        return evidence_id

    def get_record(self, evidence_id: str) -> dict[str, Any]:
        if not EVIDENCE_ID.fullmatch(evidence_id):
            raise LocalEvidenceStoreError("invalid evidence_id")
        path = self.records / f"{evidence_id}.json"
        try:
            raw = path.read_bytes()
            record = json.loads(raw)
        except (OSError, json.JSONDecodeError) as exc:
            raise LocalEvidenceStoreError("record unavailable or invalid") from exc
        if not isinstance(record, dict) or record.get("evidence_id") != evidence_id:
            raise LocalEvidenceStoreError("record identity mismatch")
        return record

    def verify(self, evidence_id: str) -> bool:
        try:
            record = self.get_record(evidence_id)
            content = record.get("content")
            if not isinstance(content, Mapping):
                return False
            digest = content.get("sha256")
            size = content.get("size_bytes")
            if not isinstance(digest, str) or not SHA256.fullmatch(digest):
                return False
            payload = (self.objects / digest[:2] / digest).read_bytes()
            return len(payload) == size and _sha256(payload) == digest
        except (LocalEvidenceStoreError, OSError):
            return False

    def replay_descriptor(self, evidence_id: str) -> dict[str, Any]:
        if not self.verify(evidence_id):
            raise LocalEvidenceStoreError("evidence integrity verification failed")
        record = self.get_record(evidence_id)
        origin = record.get("origin")
        correlation = record.get("correlation")
        content = record.get("content")
        if not all(isinstance(item, Mapping) for item in (origin, correlation, content)):
            raise LocalEvidenceStoreError("incomplete evidence record")
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
        if not record.get("parent_evidence_id") or not record.get("redaction"):
            raise LocalEvidenceStoreError("derived evidence lineage is required for export")
        content = record["content"]
        digest = content["sha256"]
        return (self.objects / digest[:2] / digest).read_bytes()
