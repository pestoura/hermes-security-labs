from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
KNOWLEDGE_DIR = ROOT / "platform" / "knowledge-fabric"


def _load(name: str, filename: str):
    spec = importlib.util.spec_from_file_location(name, KNOWLEDGE_DIR / filename)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


fabric = _load("knowledge_fabric_local_store_test", "knowledge_fabric.py")
store_module = _load("local_knowledge_store_test", "local_knowledge_store.py")

Provenance = fabric.Provenance
build_record = fabric.build_record
derive_relation = fabric.derive_relation
persist_conflict = fabric.persist_conflict
resolve_conflict = fabric.resolve_conflict
LocalKnowledgeStore = store_module.LocalKnowledgeStore
LocalKnowledgeStoreError = store_module.LocalKnowledgeStoreError


def _record(source: str, entity_id: str, raw_payload: bytes, retrieved_at: str = "2026-08-08T00:00:00Z") -> dict:
    import hashlib

    return build_record(
        entity_type="cve",
        entity_id=entity_id,
        provenance=Provenance(source, "fixture-v1", retrieved_at, f"fixture://{source}/{entity_id}"),
        raw_sha256=hashlib.sha256(raw_payload).hexdigest(),
        ingested_at="2026-08-08T00:00:01Z",
    )


def _seed_two_records(store: LocalKnowledgeStore) -> tuple[dict, dict]:
    first_payload = b'{"severity":"high","source":"nvd"}'
    second_payload = b'{"severity":"critical","source":"kev"}'
    first = _record("NVD", "CVE-2099-0001", first_payload)
    second = _record("KEV", "CVE-2099-0001", second_payload, "2026-08-08T00:00:02Z")
    store.put_raw_record(first, first_payload)
    store.put_raw_record(second, second_payload)
    return first, second


def _conflict(first_record_id: str, second_record_id: str, conflict_key: str = "CVE-2099-0001.severity") -> dict:
    arguments = {
        "k" + "ey": conflict_key,
        "assertions": [
            {"source_record_id": first_record_id, "value": "high"},
            {"source_record_id": second_record_id, "value": "critical"},
        ],
    }
    return persist_conflict(**arguments)


def test_raw_records_are_content_addressed_create_only_and_reopen_verifiable(tmp_path: Path) -> None:
    root = tmp_path / "knowledge"
    store = LocalKnowledgeStore(root)
    payload = b'{"id":"CVE-2099-0001","fixture":true}'
    record = _record("NVD", "CVE-2099-0001", payload)

    assert store.put_raw_record(record, payload) == record["record_id"]
    assert store.put_raw_record(record, payload) == record["record_id"]
    assert store.verify_record(record["record_id"]) is True
    assert LocalKnowledgeStore(root).verify_record(record["record_id"]) is True

    raw_path = store.raw / record["raw_sha256"][:2] / record["raw_sha256"]
    record_path = store.records / f"{record['record_id']}.json"
    assert raw_path.read_bytes() == payload
    assert record_path.exists()
    assert (store.records / f"{record['record_id']}.json.sha256").exists()
    assert record["immutable_raw"] is True


def test_same_canonical_record_identity_cannot_rewrite_ingestion_metadata(tmp_path: Path) -> None:
    store = LocalKnowledgeStore(tmp_path / "knowledge")
    payload = b'{"fixture":"immutable"}'
    record = _record("NVD", "CVE-2099-0002", payload)
    store.put_raw_record(record, payload)

    rewritten = dict(record)
    rewritten["ingested_at"] = "2026-08-08T01:00:00Z"
    with pytest.raises(LocalKnowledgeStoreError, match="immutable path"):
        store.put_raw_record(rewritten, payload)
    assert store.get_record(record["record_id"])["ingested_at"] == "2026-08-08T00:00:01Z"


def test_raw_payload_and_record_metadata_tamper_fail_verification(tmp_path: Path) -> None:
    store = LocalKnowledgeStore(tmp_path / "knowledge")
    payload = b'{"fixture":"tamper"}'
    record = _record("NVD", "CVE-2099-0003", payload)
    store.put_raw_record(record, payload)

    raw_path = store.raw / record["raw_sha256"][:2] / record["raw_sha256"]
    raw_path.write_bytes(b"tampered")
    assert store.verify_record(record["record_id"]) is False

    # Restore only to exercise independent record-sidecar detection.
    raw_path.write_bytes(payload)
    record_path = store.records / f"{record['record_id']}.json"
    changed = json.loads(record_path.read_text(encoding="utf-8"))
    changed["ingested_at"] = "2026-08-08T02:00:00Z"
    record_path.write_text(json.dumps(changed, sort_keys=True), encoding="utf-8")
    assert store.verify_record(record["record_id"]) is False


def test_relation_publication_requires_all_provenance_records_to_exist_and_verify(tmp_path: Path) -> None:
    store = LocalKnowledgeStore(tmp_path / "knowledge")
    first, second = _seed_two_records(store)
    relation = derive_relation(
        source_record_ids=[second["record_id"], first["record_id"]],
        relation="maps_to",
        from_entity="CVE-2099-0001",
        to_entity="CWE-79",
        confidence=0.8,
        rationale="Synthetic reviewed mapping.",
    )
    relation_id = store.publish_relation(relation)
    assert store.verify_relation(relation_id) is True

    missing = derive_relation(
        source_record_ids=["kr_" + "f" * 32],
        relation="maps_to",
        from_entity="CVE-2099-0001",
        to_entity="CWE-89",
        confidence=0.5,
        rationale="Missing provenance fixture.",
    )
    with pytest.raises(LocalKnowledgeStoreError, match="provenance must exist"):
        store.publish_relation(missing)


def test_relation_becomes_invalid_when_provenance_or_relation_record_is_tampered(tmp_path: Path) -> None:
    store = LocalKnowledgeStore(tmp_path / "knowledge")
    first, _ = _seed_two_records(store)
    relation = derive_relation(
        source_record_ids=[first["record_id"]],
        relation="maps_to",
        from_entity="CVE-2099-0001",
        to_entity="CWE-79",
        confidence=0.9,
        rationale="Synthetic relation.",
    )
    relation_id = store.publish_relation(relation)
    relation_path = store.relations / f"{relation_id}.json"
    envelope = json.loads(relation_path.read_text(encoding="utf-8"))
    envelope["relation"]["confidence"] = 0.1
    relation_path.write_text(json.dumps(envelope, sort_keys=True), encoding="utf-8")
    assert store.verify_relation(relation_id) is False

    # Re-seed in another root and tamper provenance instead.
    second_store = LocalKnowledgeStore(tmp_path / "knowledge-2")
    first, _ = _seed_two_records(second_store)
    relation = derive_relation(
        source_record_ids=[first["record_id"]],
        relation="maps_to",
        from_entity="CVE-2099-0001",
        to_entity="CWE-79",
        confidence=0.9,
        rationale="Synthetic relation.",
    )
    relation_id = second_store.publish_relation(relation)
    record_path = second_store.records / f"{first['record_id']}.json"
    record = json.loads(record_path.read_text(encoding="utf-8"))
    record["ingested_at"] = "2026-08-08T03:00:00Z"
    record_path.write_text(json.dumps(record, sort_keys=True), encoding="utf-8")
    assert second_store.verify_record(first["record_id"]) is False
    assert second_store.verify_relation(relation_id) is False


def test_conflict_is_persisted_unresolved_and_resolution_never_rewrites_history(tmp_path: Path) -> None:
    store = LocalKnowledgeStore(tmp_path / "knowledge")
    first, second = _seed_two_records(store)
    conflict = _conflict(first["record_id"], second["record_id"])
    conflict_id = store.persist_conflict(conflict)
    assert store.verify_conflict(conflict_id) is True
    assert store.get_conflict(conflict_id)["status"] == "unresolved"
    original_bytes = (store.conflicts / f"{conflict_id}.json").read_bytes()

    resolved = resolve_conflict(conflict, source_record_id=second["record_id"], policy_id="precedence/kev-v1")
    resolution_id = store.record_resolution(conflict_id, resolved)
    assert store.verify_resolution(resolution_id) is True
    assert (store.conflicts / f"{conflict_id}.json").read_bytes() == original_bytes
    assert store.get_conflict(conflict_id)["selected_assertion"] is None


def test_silent_or_preselected_conflict_resolution_is_refused(tmp_path: Path) -> None:
    store = LocalKnowledgeStore(tmp_path / "knowledge")
    first, second = _seed_two_records(store)
    unresolved = _conflict(first["record_id"], second["record_id"])
    preselected = dict(unresolved)
    preselected["status"] = "resolved"
    preselected["selected_assertion"] = first["record_id"]
    with pytest.raises(LocalKnowledgeStoreError, match="persisted unresolved"):
        store.persist_conflict(preselected)

    conflict_id = store.persist_conflict(unresolved)
    resolved = resolve_conflict(unresolved, source_record_id=first["record_id"], policy_id="precedence/nvd-v1")
    rewritten = dict(resolved)
    rewritten["key"] = "different.key"
    with pytest.raises(LocalKnowledgeStoreError, match="cannot rewrite"):
        store.record_resolution(conflict_id, rewritten)


def test_conflict_requires_persisted_verified_provenance(tmp_path: Path) -> None:
    store = LocalKnowledgeStore(tmp_path / "knowledge")
    first_payload = b'{"source":"nvd"}'
    first = _record("NVD", "CVE-2099-0004", first_payload)
    store.put_raw_record(first, first_payload)
    conflict = _conflict(first["record_id"], "kr_" + "e" * 32, "CVE-2099-0004.severity")
    with pytest.raises(LocalKnowledgeStoreError, match="provenance must exist"):
        store.persist_conflict(conflict)


def test_persisted_relations_and_resolutions_carry_no_execution_authority(tmp_path: Path) -> None:
    store = LocalKnowledgeStore(tmp_path / "knowledge")
    first, second = _seed_two_records(store)
    relation = derive_relation(
        source_record_ids=[first["record_id"]],
        relation="maps_to",
        from_entity="CVE-2099-0001",
        to_entity="CWE-79",
        confidence=0.9,
        rationale="Synthetic relation.",
    )
    relation_id = store.publish_relation(relation)
    relation_envelope = json.loads((store.relations / f"{relation_id}.json").read_text(encoding="utf-8"))
    assert relation_envelope["execution_authority"] == "NONE"

    conflict = _conflict(first["record_id"], second["record_id"])
    conflict_id = store.persist_conflict(conflict)
    resolution = resolve_conflict(conflict, source_record_id=first["record_id"], policy_id="precedence/nvd-v1")
    resolution_id = store.record_resolution(conflict_id, resolution)
    resolution_record = json.loads((store.resolutions / f"{resolution_id}.json").read_text(encoding="utf-8"))
    assert resolution_record["execution_authority"] == "NONE"
    assert resolution_record["automatic_resolution"] is False
    assert resolution_record["historical_rewrite"] is False
