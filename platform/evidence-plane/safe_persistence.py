from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent


def _load_sibling(name: str, filename: str):
    module_name = f"_evidence_safe_persistence_{name}"
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


evidence = _load_sibling("contract", "evidence_plane.py")
redaction = _load_sibling("redaction", "redaction.py")

Correlation = evidence.Correlation
build_record = evidence.build_record
sha256_hex = evidence.sha256_hex
redact_structured_payload = redaction.redact_structured_payload


class SafePersistenceError(ValueError):
    """Fail-closed ingress-to-persistence error."""


def _canonical_bytes(value: dict[str, Any]) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")


def persist_structured_sanitized(
    *,
    store: Any,
    source_payload: bytes,
    correlation: Any,
    operation: str,
    source_created_at: str,
    sanitized_created_at: str,
    retention_policy_id: str = "default-30d",
    retain_until: str | None = None,
    protocol_version: str = "2.0",
    knowledge_snapshot: str | None = None,
) -> dict[str, Any]:
    """Redact structured source bytes in memory before any Evidence Plane persistence.

    The original source payload is never passed to the store. Only a digest-only restricted
    manifest and the sanitized derivative are persisted. This is a controlled local reference
    boundary, not a production transport, DLP engine, encryption or publication workflow.
    """
    if not isinstance(source_payload, bytes):
        raise SafePersistenceError("source_payload must be bytes")
    if not isinstance(operation, str) or not operation or len(operation) > 128:
        raise SafePersistenceError("operation must be a bounded non-empty string")

    # Redaction must succeed before the first store write.
    try:
        sanitized_payload, redaction_metadata = redact_structured_payload(source_payload)
    except Exception as exc:
        raise SafePersistenceError("structured redaction failed before persistence") from exc

    source_material_sha256 = sha256_hex(source_payload)
    manifest_payload = _canonical_bytes(
        {
            "schema_version": "1.0",
            "source_material_sha256": source_material_sha256,
            "source_material_persistence": "NOT_PERSISTED",
            "redaction_policy_id": redaction_metadata["policy_id"],
        }
    )
    manifest_sha256 = sha256_hex(manifest_payload)

    manifest_record = build_record(
        correlation=correlation,
        classification="restricted",
        producer="evidence-safe-ingress",
        operation=operation,
        protocol_version=protocol_version,
        payload_sha256=manifest_sha256,
        payload_size=len(manifest_payload),
        media_type="application/json",
        storage_ref=f"evidence://{correlation.campaign_id}/{correlation.run_id}/restricted/source-manifest.json",
        retention_policy_id=retention_policy_id,
        retain_until=retain_until,
        knowledge_snapshot=knowledge_snapshot,
        created_at=source_created_at,
    )

    derived_redaction = {
        "policy_id": redaction_metadata["policy_id"],
        "source_sha256": manifest_sha256,
        "source_material_sha256": source_material_sha256,
        "source_material_persistence": "NOT_PERSISTED",
        "removed_classes": redaction_metadata["removed_classes"],
        "removed_fields": redaction_metadata["removed_fields"],
        "retained_fields": redaction_metadata["retained_fields"],
        "mode": redaction_metadata["mode"],
    }
    sanitized_record = build_record(
        correlation=correlation,
        classification="sanitized",
        producer="evidence-redactor",
        operation=operation,
        protocol_version=protocol_version,
        payload_sha256=sha256_hex(sanitized_payload),
        payload_size=len(sanitized_payload),
        media_type="application/json",
        storage_ref=f"evidence://{correlation.campaign_id}/{correlation.run_id}/sanitized/result.json",
        retention_policy_id=retention_policy_id,
        retain_until=retain_until,
        knowledge_snapshot=knowledge_snapshot,
        parent_evidence_id=manifest_record["evidence_id"],
        redaction=derived_redaction,
        created_at=sanitized_created_at,
    )

    try:
        manifest_id = store.put(manifest_record, manifest_payload)
        sanitized_id = store.put(sanitized_record, sanitized_payload)
    except Exception as exc:
        raise SafePersistenceError("safe persistence failed") from exc

    return {
        "manifest_evidence_id": manifest_id,
        "sanitized_evidence_id": sanitized_id,
        "source_material_sha256": source_material_sha256,
        "sanitized_sha256": sanitized_record["content"]["sha256"],
        "source_material_persisted": False,
    }
