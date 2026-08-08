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


evidence = _load("evidence_plane_store_test", "evidence_plane.py")
store_module = _load("local_evidence_store_test", "local_store.py")

Correlation = evidence.Correlation
build_record = evidence.build_record
sha256_hex = evidence.sha256_hex
LocalEvidenceStore = store_module.LocalEvidenceStore
LocalEvidenceStoreError = store_module.LocalEvidenceStoreError


def _record(payload: bytes, classification: str = "raw", **overrides):
    kwargs = {
        "correlation": Correlation("campaign-1", "run-1", "step-1", "attempt-1"),
        "classification": classification,
        "producer": "synthetic-runner",
        "operation": "conformance.process.success",
        "protocol_version": "2.0",
        "payload_sha256": sha256_hex(payload),
        "payload_size": len(payload),
        "media_type": "application/json",
        "storage_ref": f"evidence://campaign-1/run-1/{classification}/result.json",
        "retention_policy_id": "default-30d",
        "retain_until": "2026-09-08T00:00:00Z",
        "created_at": "2026-08-08T00:00:00Z",
    }
    kwargs.update(overrides)
    return build_record(**kwargs)


def test_local_store_persists_and_reopens_with_integrity(tmp_path: Path) -> None:
    payload = b'{"result":"synthetic"}'
    record = _record(payload)
    store = LocalEvidenceStore(tmp_path / "evidence")
    evidence_id = store.put(record, payload)
    assert store.verify(evidence_id) is True
    reopened = LocalEvidenceStore(tmp_path / "evidence")
    assert reopened.verify(evidence_id) is True
    assert reopened.get_record(evidence_id) == record


def test_store_directories_are_owner_only(tmp_path: Path) -> None:
    store = LocalEvidenceStore(tmp_path / "evidence")
    assert store.root.stat().st_mode & 0o777 == 0o700
    assert store.objects.stat().st_mode & 0o777 == 0o700
    assert store.records.stat().st_mode & 0o777 == 0o700


def test_same_record_and_payload_are_idempotent_but_identity_mutation_is_refused(tmp_path: Path) -> None:
    payload = b"synthetic"
    record = _record(payload)
    store = LocalEvidenceStore(tmp_path / "evidence")
    store.put(record, payload)
    store.put(record, payload)
    changed = dict(record)
    changed["origin"] = dict(record["origin"])
    changed["origin"]["operation"] = "changed.operation"
    with pytest.raises(LocalEvidenceStoreError):
        store.put(changed, payload)


def test_payload_digest_and_size_are_verified_before_persistence(tmp_path: Path) -> None:
    payload = b"expected"
    record = _record(payload)
    store = LocalEvidenceStore(tmp_path / "evidence")
    with pytest.raises(LocalEvidenceStoreError):
        store.put(record, b"different")
    assert not any(store.records.glob("*.json"))


def test_noncanonical_record_shape_is_refused(tmp_path: Path) -> None:
    payload = b"synthetic"
    record = _record(payload)
    record["token"] = "synthetic-canary"
    with pytest.raises(LocalEvidenceStoreError):
        LocalEvidenceStore(tmp_path / "evidence").put(record, payload)


def test_tampered_object_fails_integrity_and_replay(tmp_path: Path) -> None:
    payload = b"synthetic"
    record = _record(payload)
    store = LocalEvidenceStore(tmp_path / "evidence")
    evidence_id = store.put(record, payload)
    digest = record["content"]["sha256"]
    (store.objects / digest[:2] / digest).write_bytes(b"tampered")
    assert store.verify(evidence_id) is False
    with pytest.raises(LocalEvidenceStoreError):
        store.replay_descriptor(evidence_id)


def test_replay_descriptor_contains_no_payload_or_storage_reference(tmp_path: Path) -> None:
    payload = b"synthetic"
    record = _record(payload)
    store = LocalEvidenceStore(tmp_path / "evidence")
    descriptor = store.replay_descriptor(store.put(record, payload))
    serialized = json.dumps(descriptor)
    assert "storage_ref" not in descriptor
    assert "payload" not in descriptor
    assert "evidence://" not in serialized
    assert descriptor["payload_sha256"] == record["content"]["sha256"]


def test_raw_and_restricted_payloads_cannot_cross_export_boundary(tmp_path: Path) -> None:
    store = LocalEvidenceStore(tmp_path / "evidence")
    for classification in ("raw", "restricted"):
        payload = f"{classification}-synthetic".encode()
        evidence_id = store.put(_record(payload, classification), payload)
        with pytest.raises(LocalEvidenceStoreError):
            store.export_payload(evidence_id)


def test_sanitized_payload_exports_only_with_verified_lineage(tmp_path: Path) -> None:
    store = LocalEvidenceStore(tmp_path / "evidence")
    raw_payload = b"raw synthetic"
    raw = _record(raw_payload, "raw")
    store.put(raw, raw_payload)
    sanitized_payload = b"sanitized synthetic"
    sanitized = _record(
        sanitized_payload,
        "sanitized",
        parent_evidence_id=raw["evidence_id"],
        redaction={
            "policy_id": "contextual-v1",
            "source_sha256": raw["content"]["sha256"],
            "removed_classes": ["raw_output"],
        },
    )
    assert store.export_payload(store.put(sanitized, sanitized_payload)) == sanitized_payload


def test_derived_evidence_requires_existing_parent_and_matching_digest(tmp_path: Path) -> None:
    store = LocalEvidenceStore(tmp_path / "evidence")
    raw_payload = b"raw synthetic"
    raw = _record(raw_payload, "raw")
    sanitized_payload = b"sanitized synthetic"
    sanitized = _record(
        sanitized_payload,
        "sanitized",
        parent_evidence_id=raw["evidence_id"],
        redaction={
            "policy_id": "contextual-v1",
            "source_sha256": raw["content"]["sha256"],
            "removed_classes": ["raw_output"],
        },
    )
    with pytest.raises(LocalEvidenceStoreError):
        store.put(sanitized, sanitized_payload)
    store.put(raw, raw_payload)
    wrong = dict(sanitized)
    wrong["redaction"] = dict(sanitized["redaction"])
    wrong["redaction"]["source_sha256"] = "0" * 64
    with pytest.raises(LocalEvidenceStoreError):
        store.put(wrong, sanitized_payload)


def test_record_file_corruption_fails_closed(tmp_path: Path) -> None:
    payload = b"synthetic"
    record = _record(payload)
    store = LocalEvidenceStore(tmp_path / "evidence")
    evidence_id = store.put(record, payload)
    (store.records / f"{evidence_id}.json").write_text("not-json", encoding="utf-8")
    assert store.verify(evidence_id) is False
    with pytest.raises(LocalEvidenceStoreError):
        store.get_record(evidence_id)
