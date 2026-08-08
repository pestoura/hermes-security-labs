from __future__ import annotations

import importlib.util
import json
import sys
from copy import deepcopy
from pathlib import Path

import jsonschema
import pytest


ROOT = Path(__file__).resolve().parents[2]
MODULE_PATH = ROOT / "platform/knowledge-api/campaign_planner.py"
SCHEMA_DIR = ROOT / "platform/knowledge-api"

spec = importlib.util.spec_from_file_location("campaign_planner_contract", MODULE_PATH)
assert spec and spec.loader
planner = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = planner
spec.loader.exec_module(planner)


def rid(ch: str) -> str:
    return "kr_" + ch * 32


def context(**overrides):
    values = {
        "campaign_id": "campaign-001",
        "knowledge_snapshot_id": "ks_" + "a" * 32,
        "capability_registry_version": "registry-2026.08.08",
        "roe_contract_id": "roe-contract-001",
        "roe_contract_payload_sha256": "b" * 64,
        "asset_ids": ["asset-api-01", "asset-web-01"],
        "threat_technique_ids": ["T1190", "T1059.004"],
        "vulnerability_ids": ["CVE-2026-12345"],
        "allowed_capability_ids": ["cap-http", "cap-observe"],
        "max_intrusiveness_level": "L2",
        "minimum_confidence": 0.7,
    }
    values.update(overrides)
    return planner.build_planning_context(**values)


def candidate(name: str, **overrides):
    values = {
        "operation_id": f"operation-{name}",
        "capability_id": "cap-http",
        "intrusiveness_level": "L1",
        "asset_ids": ["asset-web-01"],
        "technique_ids": ["T1190"],
        "vulnerability_ids": [],
        "knowledge_record_ids": [rid("c")],
        "confidence": 0.9,
        "rationale": f"candidate {name} matches supplied threat context",
    }
    values.update(overrides)
    return planner.build_candidate(**values)


def schema(name: str):
    return json.loads((SCHEMA_DIR / name).read_text(encoding="utf-8"))


def test_context_and_candidate_validate_against_schemas() -> None:
    ctx = context()
    cand = candidate("one")
    jsonschema.validate(ctx, schema("campaign-planning-context.schema.json"))
    jsonschema.validate(cand, schema("campaign-plan-candidate.schema.json"))


def test_identical_inputs_yield_identical_plan_independent_of_candidate_order() -> None:
    ctx = context()
    first = candidate("first", confidence=0.85)
    second = candidate(
        "second",
        capability_id="cap-observe",
        intrusiveness_level="L0",
        technique_ids=["T1059.004"],
        confidence=0.95,
        knowledge_record_ids=[rid("d")],
    )
    plan_a = planner.derive_plan(context=ctx, candidates=[first, second])
    plan_b = planner.derive_plan(context=ctx, candidates=[second, first])
    assert plan_a == plan_b
    assert [step["candidate_id"] for step in plan_a["selected_steps"]] == [
        second["candidate_id"],
        first["candidate_id"],
    ]
    jsonschema.validate(plan_a, schema("campaign-plan.schema.json"))


def test_planning_filters_record_deterministic_exclusion_reasons() -> None:
    ctx = context()
    valid = candidate("valid")
    disallowed = candidate("capability", capability_id="cap-other", knowledge_record_ids=[rid("d")])
    intrusive = candidate("intrusive", intrusiveness_level="L3", knowledge_record_ids=[rid("e")])
    out_of_scope = candidate("scope", asset_ids=["asset-other"], knowledge_record_ids=[rid("f")])
    low_conf = candidate("confidence", confidence=0.3, knowledge_record_ids=[rid("1")])
    no_match = candidate(
        "threat",
        technique_ids=["T1021"],
        vulnerability_ids=[],
        knowledge_record_ids=[rid("2")],
    )

    plan = planner.derive_plan(
        context=ctx,
        candidates=[no_match, low_conf, intrusive, valid, out_of_scope, disallowed],
    )
    assert [item["candidate_id"] for item in plan["selected_steps"]] == [valid["candidate_id"]]
    excluded = {item["candidate_id"]: item["reasons"] for item in plan["excluded_candidates"]}
    assert excluded[disallowed["candidate_id"]] == ["CAPABILITY_NOT_ALLOWED_BY_PLANNING_CONTEXT"]
    assert excluded[intrusive["candidate_id"]] == ["INTRUSIVENESS_ABOVE_PLANNING_CEILING"]
    assert excluded[out_of_scope["candidate_id"]] == ["ASSET_OUTSIDE_PLANNING_SCOPE"]
    assert excluded[low_conf["candidate_id"]] == ["CONFIDENCE_BELOW_PLANNING_MINIMUM"]
    assert excluded[no_match["candidate_id"]] == ["NO_THREAT_CONTEXT_MATCH"]


def test_context_and_candidate_tampering_fail_closed() -> None:
    ctx = context()
    tampered_ctx = deepcopy(ctx)
    tampered_ctx["asset_ids"] = ["asset-other"]
    with pytest.raises(planner.CampaignPlannerError, match="context id"):
        planner.derive_plan(context=tampered_ctx, candidates=[])

    cand = candidate("tamper")
    tampered_candidate = deepcopy(cand)
    tampered_candidate["rationale"] = "changed after candidate identity was issued"
    with pytest.raises(planner.CampaignPlannerError, match="candidate id"):
        planner.derive_plan(context=ctx, candidates=[tampered_candidate])


def test_execution_authorization_and_secret_shaped_fields_fail_closed() -> None:
    ctx = context()
    ctx_with_receipt = deepcopy(ctx)
    ctx_with_receipt["authorization_receipt"] = {"status": "ALLOW"}
    with pytest.raises(planner.CampaignPlannerError):
        planner.derive_plan(context=ctx_with_receipt, candidates=[])

    cand = candidate("forbidden")
    cand_with_command = deepcopy(cand)
    cand_with_command["command"] = "do-not-accept"
    with pytest.raises(planner.CampaignPlannerError):
        planner.derive_plan(context=ctx, candidates=[cand_with_command])


def test_plan_is_proposal_only_and_never_authorizes_execution() -> None:
    plan = planner.derive_plan(context=context(), candidates=[candidate("one")])
    encoded = json.dumps(plan, sort_keys=True)
    assert plan["proposal_state"] == "PROPOSAL_ONLY"
    assert plan["executable"] is False
    assert plan["planning_constraints_are_authorization"] is False
    assert plan["authorization_effect"] == "NONE"
    assert plan["requires_fresh_authorization"] is True
    assert plan["execution_authority"] == "CONTROL_PLANE_ONLY"
    assert planner.proposal_is_executable(plan) is False
    for forbidden in ("command", "argv", "shell", "credential", "secret", "authorization_receipt"):
        assert f'"{forbidden}"' not in encoded


def test_duplicate_candidates_fail_closed() -> None:
    cand = candidate("duplicate")
    with pytest.raises(planner.CampaignPlannerError, match="candidate ids must be unique"):
        planner.derive_plan(context=context(), candidates=[cand, cand])


def test_diff_is_deterministic_and_proposal_only() -> None:
    ctx = context()
    first = candidate("first")
    second = candidate("second", knowledge_record_ids=[rid("d")], confidence=0.95)
    previous = planner.derive_plan(context=ctx, candidates=[first])
    current = planner.derive_plan(context=ctx, candidates=[first, second])
    diff_a = planner.diff_plans(previous=previous, current=current)
    diff_b = planner.diff_plans(previous=deepcopy(previous), current=deepcopy(current))
    assert diff_a == diff_b
    assert diff_a["added_candidate_ids"] == [second["candidate_id"]]
    assert diff_a["removed_candidate_ids"] == []
    assert diff_a["effect"] == "PROPOSAL_DIFF_ONLY"
    assert diff_a["authorization_effect"] == "NONE"
    assert diff_a["execution_authority"] == "CONTROL_PLANE_ONLY"
    jsonschema.validate(diff_a, schema("campaign-plan-diff.schema.json"))


def test_diff_refuses_different_campaigns() -> None:
    previous = planner.derive_plan(context=context(campaign_id="campaign-a"), candidates=[candidate("first")])
    current = planner.derive_plan(context=context(campaign_id="campaign-b"), candidates=[candidate("first")])
    with pytest.raises(planner.CampaignPlannerError, match="same campaign"):
        planner.diff_plans(previous=previous, current=current)


def test_plan_tampering_cannot_be_used_as_a_valid_diff_input() -> None:
    ctx = context()
    base = planner.derive_plan(context=ctx, candidates=[candidate("first")])
    tampered = deepcopy(base)
    tampered["selected_steps"][0]["selection_reason"] = "tampered"
    with pytest.raises(planner.CampaignPlannerError, match="plan id"):
        planner.diff_plans(previous=base, current=tampered)
