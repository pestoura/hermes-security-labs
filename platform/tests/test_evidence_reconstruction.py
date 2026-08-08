from __future__ import annotations

import hashlib
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


evidence = _load("evidence_reconstruction_contract_test", "evidence_plane.py")
store_module = _load("evidence_reconstruction_store_test", "local_store.py")
safe_persistence = _load("evidence_reconstruction_ingress_test", "safe_persistence.py")
reconstruction = _load("evidence_reconstruction_test", "reconstruction.py")

Correlation = evidence.Correlation
build_record = evidence.build_record
sha256_hex = evidence.sha256_hex
LocalEvidenceStore = store_module.LocalEvidenceStore
ReconstructionError = reconstruction.ReconstructionError
reconstruct_verified_result = reconstruction.reconstruct_verified_result
persist_structured_sanitized = safe_persistence.persist_structured_sanitized

SOURCE = json.dumps(
    {
        "schema_version": "1.0",
        "fields": [
            {"name": "finding_id", "classification": "operational", "value": "finding-synthetic-1"},
            {"name": "access_token", "classification": "public", "value": "SYNTHETIC_TOKEN_CANARY"},
            {"name": "session_cookie", "classification": "cookie", "value": "SYNTHETIC_COOKIE_CANARY"},
            {"name": "raw_result", "classification": "raw_output", "value": "SYNTHETIC_RAW_CANARY"},
        ],
    },
    sort_keys=True,
).encode()


def _persist(store: LocalEvidenceStore) -> dict[str, str | bool]:
    return persist_structured_sanitized(
        store=store,
        source_payload=SOURCE,
        correlation=Correlation("campaign-1", "run-1", "step-1", "attempt-1"),
        operation="controlled.synthetic.observation",
        source_created_at="2026-08-08T16:00:00Z",
        sanitized_created_at="2026-08-08T16:00:01Z",
        retain_until="2026-09-08T16:00:00Z",
    )


def _receipt_digest(receipt: dict) -> str:
    unsigned = dict(receipt)
    unsigned.pop("receipt_sha256")
    encoded = json.dumps(unsigned, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()
    return hashlib.sha256(encoded).hexdigest()


def test_verified_result_reconstruction_is_deterministic_across_reopen(tmp_path: Path) -> None:
    root = tmp_path / "evidence"
    store = LocalEvidenceStore(root)
    persisted = _persist(store)
    evidence_id = str(persisted["sanitized_evidence_id"])

    payload, receipt = reconstruct_verified_result(store, evidence_id)
    reopened_payload, reopened_receipt = reconstruct_verified_result(LocalEvidenceStore(root), evidence_id)

    assert payload == reopened_payload
    assert receipt == reopened_receipt
    assert json.loads(payload) == {
        "schema_version": "1.0",
        "fields": [{"name": "finding_id", "value": "finding-synthetic-1"}],
    }
    assert receipt["mode"] == "verified_stored_result_reconstruction"
    assert receipt["execution_replayed"] is False
    assert receipt["authorization_replayed"] is False
    assert receipt["receipt_sha256"] == _receipt_digest(receipt)

    serialized = payload + json.dumps(receipt, sort_keys=True).encode()
    for canary in (b"SYNTHETIC_TOKEN_CANARY", b"SYNTHETIC_COOKIE_CANARY", b"SYNTHETIC_RAW_CANARY"):
        assert canary not in serialized
    assert b"storage_ref" not in serialized
    assert b"evidence://" not in serialized


def test_restricted_source_manifest_is_not_reconstructable_as_a_result(tmp_path: Path) -> None:
    store = LocalEvidenceStore(tmp_path / "evidence")
    persisted = _persist(store)
    with pytest.raises(ReconstructionError, match="sanitized or summary"):
        reconstruct_verified_result(store, str(persisted["manifest_evidence_id"]))


def test_payload_tamper_fails_reconstruction(tmp_path: Path) -> None:
    store = LocalEvidenceStore(tmp_path / "evidence")
    persisted = _persist(store)
    evidence_id = str(persisted["sanitized_evidence_id"])
    record = store.get_record(evidence_id)
    digest = record["content"]["sha256"]
    (store.objects / digest[:2] / digest).write_bytes(b"tampered")

    assert store.verify(evidence_id) is False
    with pytest.raises(ReconstructionError, match="integrity"):
        reconstruct_verified_result(store, evidence_id)


def test_record_metadata_tamper_is_detected_by_canonical_sidecar(tmp_path: Path) -> None:
    store = LocalEvidenceStore(tmp_path / "evidence")
    persisted = _persist(store)
    evidence_id = str(persisted["sanitized_evidence_id"])
    path = store.records / f"{evidence_id}.json"
    record = json.loads(path.read_text())
    record["origin"]["operation"] = "tampered.operation"
    path.write_text(json.dumps(record, sort_keys=True), encoding="utf-8")

    assert store.verify(evidence_id) is False
    with pytest.raises(ReconstructionError, match="integrity"):
        reconstruct_verified_result(store, evidence_id)


def test_record_digest_sidecar_tamper_fails_closed(tmp_path: Path) -> None:
    store = LocalEvidenceStore(tmp_path / "evidence")
    persisted = _persist(store)
    evidence_id = str(persisted["sanitized_evidence_id"])
    (store.records / f"{evidence_id}.sha256").write_text("0" * 64, encoding="ascii")

    assert store.verify(evidence_id) is False
    with pytest.raises(ReconstructionError, match="integrity"):
        reconstruct_verified_result(store, evidence_id)


def test_parent_record_tamper_invalidates_child_reconstruction(tmp_path: Path) -> None:
    store = LocalEvidenceStore(tmp_path / "evidence")
    persisted = _persist(store)
    child_id = str(persisted["sanitized_evidence_id"])
    parent_id = str(persisted["manifest_evidence_id"])
    parent_path = store.records / f"{parent_id}.json"
    parent = json.loads(parent_path.read_text())
    parent["retention"]["legal_hold"] = True
    parent_path.write_text(json.dumps(parent, sort_keys=True), encoding="utf-8")

    assert store.verify(parent_id) is False
    assert store.verify(child_id) is False
    with pytest.raises(ReconstructionError, match="integrity"):
        reconstruct_verified_result(store, child_id)


def test_missing_record_fails_closed(tmp_path: Path) -> None:
    store = LocalEvidenceStore(tmp_path / "evidence")
    with pytest.raises(ReconstructionError, match="unavailable"):
        reconstruct_verified_result(store, "ev_" + "0" * 32)


def test_invalid_redaction_policy_identity_is_refused_at_reconstruction(tmp_path: Path) -> None:
    store = LocalEvidenceStore(tmp_path / "evidence")
    correlation = Correlation("campaign-1", "run-1", "step-1", "attempt-1")
    parent_payload = b'{"source":"synthetic"}'
    parent = build_record(
        correlation=correlation,
        classification="restricted",
        producer="synthetic-ingress",
        operation="controlled.synthetic.observation",
        protocol_version="2.0",
        payload_sha256=sha256_hex(parent_payload),
        payload_size=len(parent_payload),
        media_type="application/json",
        storage_ref="evidence://campaign-1/run-1/restricted/manifest.json",
        retention_policy_id="default-30d",
        retain_until="2026-09-08T16:00:00Z",
        created_at="2026-08-08T16:00:00Z",
    )
    store.put(parent, parent_payload)

    child_payload = b'{"result":"sanitized"}'
    child = build_record(
        correlation=correlation,
        classification="sanitized",
        producer="synthetic-redactor",
        operation="controlled.synthetic.observation",
        protocol_version="2.0",
        payload_sha256=sha256_hex(child_payload),
        payload_size=len(child_payload),
        media_type="application/json",
        storage_ref="evidence://campaign-1/run-1/sanitized/result.json",
        retention_policy_id="default-30d",
        retain_until="2026-09-08T16:00:00Z",
        parent_evidence_id=parent["evidence_id"],
        redaction={"policy_id": "invalid policy id", "source_sha256": parent["content"]["sha256"]},
        created_at="2026-08-08T16:00:01Z",
    )
    store.put(child, child_payload)

    with pytest.raises(ReconstructionError, match="policy identity"):
        reconstruct_verified_result(store, child["evidence_id"])
