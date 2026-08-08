from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
EVIDENCE_DIR = ROOT / "platform" / "evidence-plane"


def _load(name: str, filename: str):
    spec = importlib.util.spec_from_file_location(name, EVIDENCE_DIR / filename)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


evidence = _load("evidence_plane_redaction_test", "evidence_plane.py")
store_module = _load("local_evidence_store_redaction_test", "local_store.py")
redaction_module = _load("structured_redaction_test", "redaction.py")

Correlation = evidence.Correlation
build_record = evidence.build_record
sha256_hex = evidence.sha256_hex
LocalEvidenceStore = store_module.LocalEvidenceStore
RedactionError = redaction_module.RedactionError
redact_structured_payload = redaction_module.redact_structured_payload


def _source(fields: list[dict]) -> bytes:
    return json.dumps(
        {"schema_version": "1.0", "fields": fields},
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _raw_record(payload: bytes):
    return build_record(
        correlation=Correlation("campaign-1", "run-1", "step-1", "attempt-1"),
        classification="raw",
        producer="synthetic-runner",
        operation="synthetic.redaction.fixture",
        protocol_version="2.0",
        payload_sha256=sha256_hex(payload),
        payload_size=len(payload),
        media_type="application/json",
        storage_ref="evidence://campaign-1/run-1/raw/redaction-fixture.json",
        retention_policy_id="default-30d",
        retain_until="2026-09-08T00:00:00Z",
        created_at="2026-08-08T00:00:00Z",
    )


def _sanitized_record(raw: dict, payload: bytes, redaction: dict):
    return build_record(
        correlation=Correlation("campaign-1", "run-1", "step-1", "attempt-1"),
        classification="sanitized",
        producer="evidence-redactor",
        operation="synthetic.redaction.fixture",
        protocol_version="2.0",
        payload_sha256=sha256_hex(payload),
        payload_size=len(payload),
        media_type="application/json",
        storage_ref="evidence://campaign-1/run-1/sanitized/redaction-fixture.json",
        retention_policy_id="default-30d",
        retain_until="2026-09-08T00:00:00Z",
        parent_evidence_id=raw["evidence_id"],
        redaction=redaction,
        created_at="2026-08-08T00:00:01Z",
    )


def test_sensitive_classes_are_removed_and_safe_fields_are_deterministic() -> None:
    payload = _source([
        {"name": "severity", "classification": "public", "value": "high"},
        {"name": "token_value", "classification": "token", "value": "CANARY-TOKEN"},
        {"name": "status", "classification": "operational", "value": "observed"},
        {"name": "cookie_value", "classification": "cookie", "value": "CANARY-COOKIE"},
        {"name": "credential_value", "classification": "credential", "value": "CANARY-CREDENTIAL"},
    ])
    sanitized, metadata = redact_structured_payload(payload)
    decoded = json.loads(sanitized)
    assert decoded == {
        "schema_version": "1.0",
        "fields": [
            {"name": "severity", "value": "high"},
            {"name": "status", "value": "observed"},
        ],
    }
    assert b"CANARY" not in sanitized
    assert metadata["removed_classes"] == ["cookie", "credential", "token"]
    assert metadata["source_sha256"] == sha256_hex(payload)


@pytest.mark.parametrize("field_name", ["token", "access_token", "session_cookie", "user_password", "api_key"])
def test_sensitive_name_override_removes_mislabeled_public_field(field_name: str) -> None:
    payload = _source([
        {"name": field_name, "classification": "public", "value": "CANARY-MISLABEL"},
        {"name": "status", "classification": "public", "value": "safe"},
    ])
    sanitized, metadata = redact_structured_payload(payload)
    assert b"CANARY-MISLABEL" not in sanitized
    assert json.loads(sanitized)["fields"] == [{"name": "status", "value": "safe"}]
    assert metadata["removed_classes"] == ["sensitive_name_override"]


def test_sensitive_nested_key_in_retained_field_fails_closed() -> None:
    payload = _source([
        {"name": "details", "classification": "public", "value": {"access_token": "CANARY"}},
    ])
    with pytest.raises(RedactionError):
        redact_structured_payload(payload)


def test_unknown_classification_and_shape_fail_closed() -> None:
    with pytest.raises(RedactionError):
        redact_structured_payload(_source([
            {"name": "field", "classification": "unknown", "value": "x"},
        ]))
    with pytest.raises(RedactionError):
        redact_structured_payload(b'{"schema_version":"1.0","fields":[],"extra":true}')


def test_duplicate_fields_fail_closed() -> None:
    with pytest.raises(RedactionError):
        redact_structured_payload(_source([
            {"name": "status", "classification": "public", "value": "a"},
            {"name": "status", "classification": "public", "value": "b"},
        ]))


def test_redaction_integrates_with_local_store_lineage_and_export(tmp_path: Path) -> None:
    raw_payload = _source([
        {"name": "status", "classification": "public", "value": "observed"},
        {"name": "password", "classification": "public", "value": "CANARY-PASSWORD"},
        {"name": "raw_result", "classification": "raw_output", "value": "CANARY-RAW"},
    ])
    raw = _raw_record(raw_payload)
    store = LocalEvidenceStore(tmp_path / "evidence")
    store.put(raw, raw_payload)

    sanitized_payload, metadata = redact_structured_payload(raw_payload)
    sanitized = _sanitized_record(raw, sanitized_payload, metadata)
    sanitized_id = store.put(sanitized, sanitized_payload)

    assert store.verify(raw["evidence_id"]) is True
    assert store.verify(sanitized_id) is True
    assert store.export_payload(sanitized_id) == sanitized_payload
    assert b"CANARY" not in sanitized_payload
    assert sanitized["parent_evidence_id"] == raw["evidence_id"]
    assert sanitized["redaction"]["source_sha256"] == raw["content"]["sha256"]


def test_redaction_is_byte_deterministic_for_same_source() -> None:
    payload = _source([
        {"name": "zeta", "classification": "public", "value": 2},
        {"name": "alpha", "classification": "operational", "value": 1},
    ])
    first_payload, first_metadata = redact_structured_payload(payload)
    second_payload, second_metadata = redact_structured_payload(payload)
    assert first_payload == second_payload
    assert first_metadata == second_metadata
