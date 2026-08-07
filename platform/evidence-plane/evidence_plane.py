from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Mapping

SCHEMA_VERSION = "2.0"
CLASSIFICATIONS = {"raw", "restricted", "sanitized", "summary"}
SECRET_KEYS = {
    "authorization",
    "cookie",
    "credential",
    "password",
    "secret",
    "token",
    "api_key",
    "private_key",
    "stdout",
    "stderr",
    "command",
    "argv",
}
SAFE_ID = re.compile(r"^[A-Za-z0-9._:-]{1,128}$")


class EvidenceError(ValueError):
    """Fail-closed evidence contract violation."""


@dataclass(frozen=True)
class Correlation:
    campaign_id: str
    run_id: str
    step_id: str
    attempt_id: str

    def as_dict(self) -> dict[str, str]:
        values = {
            "campaign_id": self.campaign_id,
            "run_id": self.run_id,
            "step_id": self.step_id,
            "attempt_id": self.attempt_id,
        }
        for name, value in values.items():
            if not SAFE_ID.fullmatch(value):
                raise EvidenceError(f"invalid correlation identifier: {name}")
        return values


def sha256_hex(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def canonical_digest(value: Mapping[str, Any]) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()
    return sha256_hex(encoded)


def _assert_safe_mapping(value: Mapping[str, Any], *, path: str = "metadata") -> None:
    for key, item in value.items():
        normalized = key.lower().replace("-", "_")
        if normalized in SECRET_KEYS:
            raise EvidenceError(f"secret-bearing or raw-output field forbidden at {path}.{key}")
        if isinstance(item, Mapping):
            _assert_safe_mapping(item, path=f"{path}.{key}")
        elif isinstance(item, list):
            for index, member in enumerate(item):
                if isinstance(member, Mapping):
                    _assert_safe_mapping(member, path=f"{path}.{key}[{index}]")


def build_record(
    *,
    correlation: Correlation,
    classification: str,
    producer: str,
    operation: str,
    protocol_version: str,
    payload_sha256: str,
    payload_size: int,
    media_type: str,
    storage_ref: str,
    retention_policy_id: str,
    retain_until: str,
    legal_hold: bool = False,
    knowledge_snapshot: str | None = None,
    parent_evidence_id: str | None = None,
    redaction: Mapping[str, Any] | None = None,
    metadata: Mapping[str, Any] | None = None,
    created_at: str | None = None,
) -> dict[str, Any]:
    if classification not in CLASSIFICATIONS:
        raise EvidenceError("unsupported evidence classification")
    if not re.fullmatch(r"[a-f0-9]{64}", payload_sha256):
        raise EvidenceError("payload_sha256 must be lowercase sha256")
    if payload_size < 0:
        raise EvidenceError("payload_size cannot be negative")
    if not storage_ref.startswith("evidence://"):
        raise EvidenceError("storage_ref must use evidence://")
    if metadata:
        _assert_safe_mapping(metadata)

    if classification in {"sanitized", "summary"}:
        if not parent_evidence_id or not redaction:
            raise EvidenceError("derived evidence requires parent and redaction metadata")
        _assert_safe_mapping(redaction, path="redaction")
        source_sha = redaction.get("source_sha256")
        if not isinstance(source_sha, str) or not re.fullmatch(r"[a-f0-9]{64}", source_sha):
            raise EvidenceError("redaction source_sha256 is required")
    elif redaction is not None:
        raise EvidenceError("raw/restricted evidence cannot claim redaction")

    timestamp = created_at or datetime.now(UTC).isoformat().replace("+00:00", "Z")
    seed = {
        "classification": classification,
        "correlation": correlation.as_dict(),
        "producer": producer,
        "operation": operation,
        "payload_sha256": payload_sha256,
        "created_at": timestamp,
    }
    record: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "evidence_id": f"ev_{canonical_digest(seed)[:32]}",
        "classification": classification,
        "correlation": correlation.as_dict(),
        "origin": {
            "producer": producer,
            "operation": operation,
            "protocol_version": protocol_version,
            "knowledge_snapshot": knowledge_snapshot,
        },
        "content": {
            "sha256": payload_sha256,
            "size_bytes": payload_size,
            "media_type": media_type,
            "storage_ref": storage_ref,
        },
        "retention": {
            "policy_id": retention_policy_id,
            "retain_until": retain_until,
            "legal_hold": legal_hold,
        },
        "parent_evidence_id": parent_evidence_id,
        "redaction": dict(redaction) if redaction else None,
        "created_at": timestamp,
    }
    return record


def exportable(record: Mapping[str, Any]) -> bool:
    """Only derived, sanitized evidence may cross the sharing boundary by default."""
    return record.get("classification") in {"sanitized", "summary"} and bool(
        record.get("parent_evidence_id") and record.get("redaction")
    )


def verify_chain(records: list[Mapping[str, Any]]) -> bool:
    """Verify parent references, derivation lineage and digest shape without opening payloads."""
    by_id = {record.get("evidence_id"): record for record in records}
    if len(by_id) != len(records) or None in by_id:
        return False
    for record in records:
        classification = record.get("classification")
        content = record.get("content")
        if classification not in CLASSIFICATIONS or not isinstance(content, Mapping):
            return False
        digest = content.get("sha256")
        if not isinstance(digest, str) or not re.fullmatch(r"[a-f0-9]{64}", digest):
            return False
        if classification in {"sanitized", "summary"}:
            parent_id = record.get("parent_evidence_id")
            parent = by_id.get(parent_id)
            redaction = record.get("redaction")
            if not parent or not isinstance(redaction, Mapping):
                return False
            if redaction.get("source_sha256") != parent.get("content", {}).get("sha256"):
                return False
    return True


def replay_descriptor(record: Mapping[str, Any]) -> dict[str, Any]:
    """Return the minimum deterministic replay descriptor; never returns raw payload data."""
    origin = record.get("origin")
    correlation = record.get("correlation")
    content = record.get("content")
    if not all(isinstance(value, Mapping) for value in (origin, correlation, content)):
        raise EvidenceError("incomplete evidence record")
    return {
        "schema_version": SCHEMA_VERSION,
        "evidence_id": record.get("evidence_id"),
        "correlation": dict(correlation),
        "producer": origin.get("producer"),
        "operation": origin.get("operation"),
        "protocol_version": origin.get("protocol_version"),
        "knowledge_snapshot": origin.get("knowledge_snapshot"),
        "payload_sha256": content.get("sha256"),
    }
