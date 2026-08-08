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


evidence = _load("safe_persistence_contract_test", "evidence_plane.py")
store_module = _load("safe_persistence_store_test", "local_store.py")
pipeline_module = _load("safe_persistence_pipeline_test", "safe_persistence.py")

Correlation = evidence.Correlation
LocalEvidenceStore = store_module.LocalEvidenceStore
LocalEvidenceStoreError = store_module.LocalEvidenceStoreError
SafePersistenceError = pipeline_module.SafePersistenceError
persist_structured_sanitized = pipeline_module.persist_structured_sanitized
sha256_hex = evidence.sha256_hex


def _source() -> bytes:
    return json.dumps(
        {
            "schema_version": "1.0",
            "fields": [
                {"name": "status", "classification": "public", "value": "observed"},
                {"name": "access_token", "classification": "public", "value": "CANARY-ACCESS-TOKEN"},
                {"name": "session_cookie", "classification": "cookie", "value": "CANARY-COOKIE"},
                {"name": "credential_value", "classification": "credential", "value": "CANARY-CREDENTIAL"},
                {"name": "raw_result", "classification": "raw_output", "value": "CANARY-RAW-OUTPUT"},
            ],
        },
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _persist(store: LocalEvidenceStore, source: bytes):
    return persist_structured_sanitized(
        store=store,
        source_payload=source,
        correlation=Correlation("campaign-1", "run-1", "step-1", "attempt-1"),
        operation="synthetic.safe-persistence.fixture",
        source_created_at="2026-08-08T00:00:00Z",
        sanitized_created_at="2026-08-08T00:00:01Z",
        retain_until="2026-09-08T00:00:00Z",
    )


def _persisted_bytes(root: Path) -> bytes:
    return b"\n".join(path.read_bytes() for path in sorted(root.rglob("*")) if path.is_file())


def test_sensitive_source_bytes_are_never_persisted(tmp_path: Path) -> None:
    source = _source()
    store = LocalEvidenceStore(tmp_path / "evidence")
    result = _persist(store, source)

    persisted = _persisted_bytes(store.root)
    for canary in (
        b"CANARY-ACCESS-TOKEN",
        b"CANARY-COOKIE",
        b"CANARY-CREDENTIAL",
        b"CANARY-RAW-OUTPUT",
    ):
        assert canary not in persisted
    assert source not in persisted
    assert result["source_material_persisted"] is False
    assert result["source_material_sha256"] == sha256_hex(source)


def test_only_safe_manifest_and_sanitized_payload_are_persisted(tmp_path: Path) -> None:
    source = _source()
    store = LocalEvidenceStore(tmp_path / "evidence")
    result = _persist(store, source)

    records = sorted(store.records.glob("*.json"))
    objects = sorted(path for path in store.objects.rglob("*") if path.is_file())
    assert len(records) == 2
    assert len(objects) == 2

    manifest = store.get_record(result["manifest_evidence_id"])
    sanitized = store.get_record(result["sanitized_evidence_id"])
    assert manifest["classification"] == "restricted"
    assert sanitized["classification"] == "sanitized"
    assert sanitized["parent_evidence_id"] == manifest["evidence_id"]
    assert sanitized["redaction"]["source_sha256"] == manifest["content"]["sha256"]
    assert sanitized["redaction"]["source_material_sha256"] == sha256_hex(source)
    assert sanitized["redaction"]["source_material_persistence"] == "NOT_PERSISTED"


def test_manifest_is_non_exportable_and_sanitized_derivative_is_exportable(tmp_path: Path) -> None:
    store = LocalEvidenceStore(tmp_path / "evidence")
    result = _persist(store, _source())

    with pytest.raises(LocalEvidenceStoreError):
        store.export_payload(result["manifest_evidence_id"])
    exported = store.export_payload(result["sanitized_evidence_id"])
    assert json.loads(exported) == {
        "schema_version": "1.0",
        "fields": [{"name": "status", "value": "observed"}],
    }


def test_repeated_identical_ingress_is_content_and_record_idempotent(tmp_path: Path) -> None:
    source = _source()
    store = LocalEvidenceStore(tmp_path / "evidence")
    first = _persist(store, source)
    second = _persist(store, source)

    assert first == second
    assert len(list(store.records.glob("*.json"))) == 2
    assert len([path for path in store.objects.rglob("*") if path.is_file()]) == 2


def test_invalid_source_fails_before_any_persistence(tmp_path: Path) -> None:
    store = LocalEvidenceStore(tmp_path / "evidence")
    invalid = b'{"schema_version":"1.0","fields":[{"name":"status","classification":"unknown","value":"x"}]}'

    with pytest.raises(SafePersistenceError):
        _persist(store, invalid)
    assert not list(store.records.glob("*.json"))
    assert not [path for path in store.objects.rglob("*") if path.is_file()]


def test_sensitive_nested_key_fails_before_any_persistence(tmp_path: Path) -> None:
    store = LocalEvidenceStore(tmp_path / "evidence")
    source = json.dumps(
        {
            "schema_version": "1.0",
            "fields": [
                {"name": "details", "classification": "public", "value": {"access_token": "CANARY"}},
            ],
        },
        separators=(",", ":"),
    ).encode()

    with pytest.raises(SafePersistenceError):
        _persist(store, source)
    assert not list(store.records.glob("*.json"))
    assert not [path for path in store.objects.rglob("*") if path.is_file()]


def test_tamper_after_safe_persistence_still_fails_closed(tmp_path: Path) -> None:
    store = LocalEvidenceStore(tmp_path / "evidence")
    result = _persist(store, _source())
    sanitized = store.get_record(result["sanitized_evidence_id"])
    digest = sanitized["content"]["sha256"]
    (store.objects / digest[:2] / digest).write_bytes(b"tampered")

    assert store.verify(result["sanitized_evidence_id"]) is False
    with pytest.raises(LocalEvidenceStoreError):
        store.export_payload(result["sanitized_evidence_id"])
