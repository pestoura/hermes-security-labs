from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import jsonschema
import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
API_DIR = ROOT / "platform" / "knowledge-api"

spec = importlib.util.spec_from_file_location("knowledge_api", API_DIR / "knowledge_api.py")
assert spec and spec.loader
module = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = module
spec.loader.exec_module(module)

KnowledgeAPIError = module.KnowledgeAPIError
bind_campaign_snapshot = module.bind_campaign_snapshot
build_campaign_proposal = module.build_campaign_proposal
create_snapshot = module.create_snapshot
filter_by_confidence = module.filter_by_confidence
proposal_is_executable = module.proposal_is_executable
temporal_entry = module.temporal_entry
validate_query = module.validate_query

RECORD_A = "kr_" + "a" * 32
RECORD_B = "kr_" + "b" * 32


def _snapshot():
    return create_snapshot(source_record_ids=[RECORD_B, RECORD_A], created_at="2026-08-07T11:00:00Z")


def test_snapshot_is_deterministic_immutable_and_schema_valid() -> None:
    snapshot = _snapshot()
    assert snapshot["source_record_ids"] == [RECORD_A, RECORD_B]
    assert snapshot["immutable"] is True
    schema = json.loads((API_DIR / "knowledge-snapshot.schema.json").read_text())
    jsonschema.Draft202012Validator(schema).validate(snapshot)
    assert snapshot == _snapshot()


def test_query_requires_snapshot_and_bounded_minimum_confidence() -> None:
    validate_query({"type": "entity", "snapshot_id": _snapshot()["snapshot_id"], "minimum_confidence": 0.7})
    with pytest.raises(KnowledgeAPIError):
        validate_query({"type": "entity", "minimum_confidence": 0.7})
    with pytest.raises(KnowledgeAPIError):
        validate_query({"type": "entity", "snapshot_id": _snapshot()["snapshot_id"], "minimum_confidence": 1.1})


def test_confidence_filter_is_explicit_and_non_mutating() -> None:
    records = [{"id": "one", "confidence": 0.9}, {"id": "two", "confidence": 0.4}, {"id": "three"}]
    result = filter_by_confidence(records, minimum_confidence=0.8)
    assert result == [{"id": "one", "confidence": 0.9}]
    assert records[0]["id"] == "one"


def test_temporal_series_are_limited_and_append_only() -> None:
    for series in ("epss", "kev", "vex"):
        entry = temporal_entry(series=series, observed_at="2026-08-07T11:01:00Z", value={"synthetic": True}, source_record_id=RECORD_A)
        assert entry["append_only"] is True
        assert entry["source_record_id"] == RECORD_A
    with pytest.raises(KnowledgeAPIError):
        temporal_entry(series="cve", observed_at="2026-08-07T11:01:00Z", value=1, source_record_id=RECORD_A)


def test_campaign_persists_exact_knowledge_snapshot() -> None:
    snapshot_id = _snapshot()["snapshot_id"]
    binding = bind_campaign_snapshot(campaign_id="campaign-synthetic-1", snapshot_id=snapshot_id)
    assert binding == {"campaign_id": "campaign-synthetic-1", "knowledge_snapshot_id": snapshot_id}


def test_campaign_proposal_is_never_executable() -> None:
    snapshot_id = _snapshot()["snapshot_id"]
    proposal = build_campaign_proposal(
        campaign_id="campaign-synthetic-1",
        snapshot_id=snapshot_id,
        rationale="synthetic knowledge-based proposal",
        proposed_steps=[{"operation": "web.probe", "reason": "synthetic applicability evidence"}],
    )
    assert proposal["proposal_state"] == "PROPOSAL_ONLY"
    assert proposal["executable"] is False
    assert proposal["authorization_source"] == "CONTROL_PLANE_ONLY"
    assert proposal_is_executable(proposal) is False


@pytest.mark.parametrize("forbidden", ["command", "argv", "shell", "cwd", "environment", "executable", "entrypoint"])
def test_proposals_reject_execution_shaped_fields(forbidden: str) -> None:
    step = {"operation": "web.probe", "reason": "synthetic"}
    step[forbidden] = "synthetic-value"
    with pytest.raises(KnowledgeAPIError):
        build_campaign_proposal(
            campaign_id="campaign-synthetic-1",
            snapshot_id=_snapshot()["snapshot_id"],
            rationale="synthetic",
            proposed_steps=[step],
        )


def test_runtime_nonclaims_are_preserved() -> None:
    policy = yaml.safe_load((API_DIR / "knowledge-api-policy.yaml").read_text())
    assert policy["campaigns"]["proposals_executable"] is False
    assert policy["campaigns"]["authorization_source"] == "CONTROL_PLANE_ONLY"
    assert policy["runtime_status"] == {
        "http_api": "NOT_IMPLEMENTED",
        "database": "NOT_IMPLEMENTED",
        "graph_query_engine": "NOT_IMPLEMENTED",
        "external_sync": "NOT_RUN",
        "production_planner": "NOT_RUN",
        "production_temporal_ingestion": "NOT_RUN",
        "production_snapshot_store": "NOT_RUN",
        "production_campaign_binding_store": "NOT_RUN",
        "control_plane_runtime_integration": "NOT_RUN",
    }
