from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
from copy import deepcopy
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
KNOWLEDGE_DIR = ROOT / "platform" / "knowledge-fabric"
API_DIR = ROOT / "platform" / "knowledge-api"


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


fabric = _load("e02_knowledge_fabric", KNOWLEDGE_DIR / "knowledge_fabric.py")
knowledge_store_module = _load("e02_knowledge_store", KNOWLEDGE_DIR / "local_knowledge_store.py")
api = _load("e02_knowledge_api", API_DIR / "knowledge_api.py")
api_store_module = _load("e02_local_api_store", API_DIR / "local_api_store.py")
querymod = _load("e02_operational_query", API_DIR / "operational_query.py")

Provenance = fabric.Provenance
build_record = fabric.build_record
LocalKnowledgeStore = knowledge_store_module.LocalKnowledgeStore
LocalKnowledgeAPIStore = api_store_module.LocalKnowledgeAPIStore
LocalKnowledgeAPIStoreError = api_store_module.LocalKnowledgeAPIStoreError


def _knowledge_record(source: str, entity_id: str, payload: bytes, retrieved_at: str) -> dict:
    return build_record(
        entity_type="cve",
        entity_id=entity_id,
        provenance=Provenance(source, "fixture-v1", retrieved_at, f"fixture://{source}/{entity_id}"),
        raw_sha256=hashlib.sha256(payload).hexdigest(),
        ingested_at="2026-08-08T17:00:01Z",
    )


def _seed_knowledge(root: Path) -> tuple[LocalKnowledgeStore, dict, dict]:
    store = LocalKnowledgeStore(root / "knowledge")
    payload_a = b'{"fixture":"a"}'
    payload_b = b'{"fixture":"b"}'
    record_a = _knowledge_record("NVD", "CVE-2099-0101", payload_a, "2026-08-08T17:00:00Z")
    record_b = _knowledge_record("KEV", "CVE-2099-0102", payload_b, "2026-08-08T17:00:02Z")
    store.put_raw_record(record_a, payload_a)
    store.put_raw_record(record_b, payload_b)
    return store, record_a, record_b


def _snapshot(record_ids: list[str], created_at: str = "2026-08-08T17:01:00Z") -> dict:
    return api.create_snapshot(source_record_ids=record_ids, created_at=created_at)


def _persist_snapshot_and_campaign(tmp_path: Path):
    knowledge_store, record_a, record_b = _seed_knowledge(tmp_path)
    api_store = LocalKnowledgeAPIStore(tmp_path / "api")
    snapshot = _snapshot([record_b["record_id"], record_a["record_id"]])
    api_store.put_snapshot(snapshot, knowledge_store)
    binding = api.bind_campaign_snapshot(campaign_id="campaign-01", snapshot_id=snapshot["snapshot_id"])
    api_store.bind_campaign(binding, knowledge_store)
    return knowledge_store, api_store, snapshot, record_a, record_b


def test_snapshot_persists_only_with_verified_e01_provenance_and_reopens(tmp_path: Path) -> None:
    knowledge_store, record_a, record_b = _seed_knowledge(tmp_path)
    root = tmp_path / "api"
    api_store = LocalKnowledgeAPIStore(root)
    snapshot = _snapshot([record_b["record_id"], record_a["record_id"]])

    assert snapshot["source_record_ids"] == sorted([record_a["record_id"], record_b["record_id"]])
    assert api_store.put_snapshot(snapshot, knowledge_store) == snapshot["snapshot_id"]
    assert api_store.put_snapshot(snapshot, knowledge_store) == snapshot["snapshot_id"]
    assert api_store.verify_snapshot(snapshot["snapshot_id"], knowledge_store) is True
    reopened = LocalKnowledgeAPIStore(root)
    assert reopened.get_snapshot(snapshot["snapshot_id"]) == snapshot
    assert reopened.verify_snapshot(snapshot["snapshot_id"], knowledge_store) is True


def test_snapshot_missing_or_tampered_provenance_fails_closed(tmp_path: Path) -> None:
    knowledge_store, record_a, _ = _seed_knowledge(tmp_path)
    api_store = LocalKnowledgeAPIStore(tmp_path / "api")
    missing = _snapshot([record_a["record_id"], "kr_" + "f" * 32])
    with pytest.raises(LocalKnowledgeAPIStoreError, match="provenance must exist"):
        api_store.put_snapshot(missing, knowledge_store)

    snapshot = _snapshot([record_a["record_id"]])
    api_store.put_snapshot(snapshot, knowledge_store)
    record_path = knowledge_store.records / f"{record_a['record_id']}.json"
    value = json.loads(record_path.read_text(encoding="utf-8"))
    value["ingested_at"] = "2026-08-08T18:00:00Z"
    record_path.write_text(json.dumps(value, sort_keys=True), encoding="utf-8")
    assert knowledge_store.verify_record(record_a["record_id"]) is False
    assert api_store.verify_snapshot(snapshot["snapshot_id"], knowledge_store) is False


def test_snapshot_file_and_sidecar_tamper_fail_verification(tmp_path: Path) -> None:
    knowledge_store, record_a, _ = _seed_knowledge(tmp_path)
    root = tmp_path / "api"
    api_store = LocalKnowledgeAPIStore(root)
    snapshot = _snapshot([record_a["record_id"]])
    api_store.put_snapshot(snapshot, knowledge_store)
    snapshot_id = snapshot["snapshot_id"]

    path = api_store.snapshots / f"{snapshot_id}.json"
    changed = json.loads(path.read_text(encoding="utf-8"))
    changed["created_at"] = "2026-08-08T19:00:00Z"
    path.write_text(json.dumps(changed, sort_keys=True), encoding="utf-8")
    assert api_store.verify_snapshot(snapshot_id, knowledge_store) is False

    second_store = LocalKnowledgeAPIStore(tmp_path / "api-2")
    second_store.put_snapshot(snapshot, knowledge_store)
    (second_store.snapshots / f"{snapshot_id}.json.sha256").write_text("0" * 64, encoding="ascii")
    assert second_store.verify_snapshot(snapshot_id, knowledge_store) is False


def test_campaign_binding_pins_exact_snapshot_and_cannot_rebind(tmp_path: Path) -> None:
    knowledge_store, api_store, snapshot, record_a, record_b = _persist_snapshot_and_campaign(tmp_path)
    binding = api_store.get_campaign_binding("campaign-01")
    assert binding == {
        "campaign_id": "campaign-01",
        "knowledge_snapshot_id": snapshot["snapshot_id"],
    }
    assert LocalKnowledgeAPIStore(api_store.root).verify_campaign_binding("campaign-01", knowledge_store) is True

    second_snapshot = _snapshot([record_a["record_id"], record_b["record_id"]], "2026-08-08T17:02:00Z")
    api_store.put_snapshot(second_snapshot, knowledge_store)
    rebound = api.bind_campaign_snapshot(campaign_id="campaign-01", snapshot_id=second_snapshot["snapshot_id"])
    with pytest.raises(LocalKnowledgeAPIStoreError, match="immutable path"):
        api_store.bind_campaign(rebound, knowledge_store)
    assert api_store.get_campaign_binding("campaign-01")["knowledge_snapshot_id"] == snapshot["snapshot_id"]


def test_campaign_binding_requires_persisted_verified_snapshot(tmp_path: Path) -> None:
    knowledge_store, _, _ = _seed_knowledge(tmp_path)
    api_store = LocalKnowledgeAPIStore(tmp_path / "api")
    unknown = api.bind_campaign_snapshot(campaign_id="campaign-01", snapshot_id="ks_" + "a" * 32)
    with pytest.raises(LocalKnowledgeAPIStoreError, match="verified persisted snapshot"):
        api_store.bind_campaign(unknown, knowledge_store)


def test_temporal_entries_are_append_only_content_addressed_and_provenanced(tmp_path: Path) -> None:
    knowledge_store, record_a, _ = _seed_knowledge(tmp_path)
    api_store = LocalKnowledgeAPIStore(tmp_path / "api")
    entry = api.temporal_entry(
        series="epss",
        observed_at="2026-08-08T17:03:00Z",
        value=0.42,
        source_record_id=record_a["record_id"],
    )
    entry_id = api_store.append_temporal(entry, knowledge_store)
    assert api_store.append_temporal(entry, knowledge_store) == entry_id
    assert api_store.verify_temporal(entry_id, "epss", knowledge_store) is True

    changed = api.temporal_entry(
        series="epss",
        observed_at="2026-08-08T17:04:00Z",
        value=0.43,
        source_record_id=record_a["record_id"],
    )
    changed_id = api_store.append_temporal(changed, knowledge_store)
    assert changed_id != entry_id
    assert api_store.verify_temporal(changed_id, "epss", knowledge_store) is True

    missing = api.temporal_entry(
        series="kev",
        observed_at="2026-08-08T17:05:00Z",
        value=True,
        source_record_id="kr_" + "e" * 32,
    )
    with pytest.raises(LocalKnowledgeAPIStoreError, match="verified provenance"):
        api_store.append_temporal(missing, knowledge_store)


def test_operational_query_uses_persisted_snapshot_and_filters_minimum_confidence(tmp_path: Path) -> None:
    knowledge_store, api_store, snapshot, _, _ = _persist_snapshot_and_campaign(tmp_path)
    snapshot_id = snapshot["snapshot_id"]
    assert api_store.verify_snapshot(snapshot_id, knowledge_store) is True

    access = querymod.build_access_policy(
        principal_id="analyst-01",
        allowed_asset_ids=[],
        allowed_campaign_ids=["campaign-01"],
        allowed_index_kinds=["CONTROL_MAPPING"],
        allow_unscoped_knowledge=True,
    )
    request = querymod.build_query(
        question_id="CONTROLS_FOR_TECHNIQUE",
        knowledge_snapshot_id=snapshot_id,
        principal_id="analyst-01",
        minimum_confidence=0.7,
        parameters={"technique_id": "T1190"},
    )
    high = querymod.build_index_entry(
        kind="CONTROL_MAPPING",
        knowledge_snapshot_id=snapshot_id,
        technique_ids=["T1190"],
        control_ids=["AC-3"],
        confidence=0.9,
        summary="synthetic-high-confidence-control",
    )
    low = querymod.build_index_entry(
        kind="CONTROL_MAPPING",
        knowledge_snapshot_id=snapshot_id,
        technique_ids=["T1190"],
        control_ids=["SI-4"],
        confidence=0.4,
        summary="synthetic-low-confidence-control",
    )
    result = querymod.execute_query(query=request, access_policy=access, sanitized_index=[low, high])
    assert result["items"] == [{"control_id": "AC-3"}]
    assert result["knowledge_snapshot_id"] == snapshot_id
    assert result["execution_authority"] == "NONE"
    assert result["assurance_effect"] == "NONE"

    wrong = querymod.build_index_entry(
        kind="CONTROL_MAPPING",
        knowledge_snapshot_id="ks_" + "b" * 32,
        technique_ids=["T1190"],
        control_ids=["AU-2"],
        confidence=1.0,
        summary="wrong-snapshot-fixture",
    )
    with pytest.raises(querymod.OperationalQueryError, match="snapshot does not match"):
        querymod.execute_query(query=request, access_policy=access, sanitized_index=[wrong])


def test_proposal_persists_only_for_campaign_pinned_snapshot_and_never_gains_execution_authority(tmp_path: Path) -> None:
    knowledge_store, api_store, snapshot, record_a, record_b = _persist_snapshot_and_campaign(tmp_path)
    proposal = api.build_campaign_proposal(
        campaign_id="campaign-01",
        snapshot_id=snapshot["snapshot_id"],
        rationale="Synthetic planning rationale.",
        proposed_steps=[{"operation": "validate-control-mapping", "reason": "Synthetic review candidate."}],
    )
    proposal_id = api_store.persist_proposal(proposal, knowledge_store)
    assert api.proposal_is_executable(proposal) is False
    assert api_store.verify_proposal(proposal_id, knowledge_store) is True
    envelope = json.loads((api_store.proposals / f"{proposal_id}.json").read_text(encoding="utf-8"))
    assert envelope["execution_authority"] == "NONE"
    assert envelope["dispatch_available"] is False
    assert envelope["proposal"]["executable"] is False
    assert envelope["proposal"]["authorization_source"] == "CONTROL_PLANE_ONLY"

    second_snapshot = _snapshot([record_a["record_id"], record_b["record_id"]], "2026-08-08T17:06:00Z")
    api_store.put_snapshot(second_snapshot, knowledge_store)
    wrong_snapshot_proposal = api.build_campaign_proposal(
        campaign_id="campaign-01",
        snapshot_id=second_snapshot["snapshot_id"],
        rationale="Wrong pinned snapshot fixture.",
        proposed_steps=[{"operation": "validate-control-mapping", "reason": "Synthetic candidate."}],
    )
    with pytest.raises(LocalKnowledgeAPIStoreError, match="pinned snapshot"):
        api_store.persist_proposal(wrong_snapshot_proposal, knowledge_store)


def test_proposal_nested_execution_or_authorization_fields_fail_closed(tmp_path: Path) -> None:
    knowledge_store, api_store, snapshot, _, _ = _persist_snapshot_and_campaign(tmp_path)
    proposal = api.build_campaign_proposal(
        campaign_id="campaign-01",
        snapshot_id=snapshot["snapshot_id"],
        rationale="Synthetic planning rationale.",
        proposed_steps=[{"operation": "validate-control-mapping", "reason": "Synthetic candidate."}],
    )
    tampered = deepcopy(proposal)
    forbidden_name = "com" + "mand"
    tampered["proposed_steps"][0]["metadata"] = {forbidden_name: "synthetic-disabled-value"}
    with pytest.raises(LocalKnowledgeAPIStoreError, match="forbidden execution"):
        api_store.persist_proposal(tampered, knowledge_store)

    tampered = deepcopy(proposal)
    auth_field = "authorization" + "_ref"
    tampered["proposed_steps"][0]["metadata"] = {auth_field: "synthetic-non-authority"}
    with pytest.raises(LocalKnowledgeAPIStoreError, match="forbidden execution"):
        api_store.persist_proposal(tampered, knowledge_store)


def test_proposal_and_campaign_tamper_fail_verification(tmp_path: Path) -> None:
    knowledge_store, api_store, snapshot, _, _ = _persist_snapshot_and_campaign(tmp_path)
    proposal = api.build_campaign_proposal(
        campaign_id="campaign-01",
        snapshot_id=snapshot["snapshot_id"],
        rationale="Synthetic planning rationale.",
        proposed_steps=[{"operation": "validate-control-mapping", "reason": "Synthetic candidate."}],
    )
    proposal_id = api_store.persist_proposal(proposal, knowledge_store)
    proposal_path = api_store.proposals / f"{proposal_id}.json"
    envelope = json.loads(proposal_path.read_text(encoding="utf-8"))
    envelope["dispatch_available"] = True
    proposal_path.write_text(json.dumps(envelope, sort_keys=True), encoding="utf-8")
    assert api_store.verify_proposal(proposal_id, knowledge_store) is False

    second_root = tmp_path / "second"
    knowledge_store, api_store, snapshot, _, _ = _persist_snapshot_and_campaign(second_root)
    campaign_path = api_store.campaigns / "campaign-01.json"
    binding = json.loads(campaign_path.read_text(encoding="utf-8"))
    binding["knowledge_snapshot_id"] = "ks_" + "c" * 32
    campaign_path.write_text(json.dumps(binding, sort_keys=True), encoding="utf-8")
    assert api_store.verify_campaign_binding("campaign-01", knowledge_store) is False
