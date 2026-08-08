from __future__ import annotations

import hashlib
import json
from typing import Any

RECONSTRUCTABLE_CLASSIFICATIONS = {"sanitized", "summary"}


class ReconstructionError(ValueError):
    """Fail-closed stored-result reconstruction violation."""


def _canonical_bytes(value: dict[str, Any]) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")


def reconstruct_verified_result(store: Any, evidence_id: str) -> tuple[bytes, dict[str, Any]]:
    """Reconstruct an exact verified stored derivative, not the original execution.

    The function proves that a sanitized/summary result can be deterministically recovered
    from its Evidence Plane record and verified lineage. It never re-executes a runner,
    security tool, target interaction or authorization decision.
    """
    try:
        record = store.get_record(evidence_id)
    except Exception as exc:
        raise ReconstructionError("evidence record is unavailable") from exc

    if record.get("classification") not in RECONSTRUCTABLE_CLASSIFICATIONS:
        raise ReconstructionError("only sanitized or summary evidence is reconstructable")
    if not store.verify(evidence_id):
        raise ReconstructionError("evidence or lineage integrity verification failed")

    parent_id = record.get("parent_evidence_id")
    redaction = record.get("redaction")
    if not isinstance(parent_id, str) or not isinstance(redaction, dict):
        raise ReconstructionError("derived lineage is required")
    if not store.verify(parent_id):
        raise ReconstructionError("parent evidence integrity verification failed")

    try:
        payload = store.export_payload(evidence_id)
        descriptor = store.replay_descriptor(evidence_id)
        parent = store.get_record(parent_id)
    except Exception as exc:
        raise ReconstructionError("verified derivative could not be reconstructed") from exc

    content = record.get("content")
    parent_content = parent.get("content")
    if not isinstance(content, dict) or not isinstance(parent_content, dict):
        raise ReconstructionError("content metadata is incomplete")
    if hashlib.sha256(payload).hexdigest() != content.get("sha256"):
        raise ReconstructionError("reconstructed payload digest mismatch")

    receipt = {
        "schema_version": "1.0",
        "mode": "verified_stored_result_reconstruction",
        "execution_replayed": False,
        "evidence_id": evidence_id,
        "parent_evidence_id": parent_id,
        "correlation": descriptor["correlation"],
        "producer": descriptor["producer"],
        "operation": descriptor["operation"],
        "protocol_version": descriptor["protocol_version"],
        "knowledge_snapshot": descriptor["knowledge_snapshot"],
        "payload_sha256": content["sha256"],
        "payload_size": content["size_bytes"],
        "parent_payload_sha256": parent_content["sha256"],
        "redaction_policy_id": redaction.get("policy_id"),
    }
    receipt["receipt_sha256"] = hashlib.sha256(_canonical_bytes(receipt)).hexdigest()
    return payload, receipt
