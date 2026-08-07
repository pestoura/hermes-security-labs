from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
INTENT = ROOT / "docs/roadmap/epics/EPIC-28-rules-of-engagement-as-code.md"
AS_BUILT = ROOT / "docs/roadmap/EPIC-28-roe-contract-candidate-as-built.md"
README = ROOT / "platform/roe-contract/README.md"
POLICY = ROOT / "platform/roe-contract/intrusiveness-policy.yaml"


def test_concept_epic_remains_intent_with_reserved_lifecycle_sections() -> None:
    text = INTENT.read_text(encoding="utf-8")

    assert "**INTENT**" in text
    tail = text.split("## 14. Implementation notes", 1)[1]
    assert "Reserved" in tail
    assert "| FINAL | no |" in text


def test_supplementary_record_never_claims_final_or_runtime_enforcement() -> None:
    text = AS_BUILT.read_text(encoding="utf-8")

    assert "AS_BUILT — contract candidate" in text
    assert "| FINAL | no |" in text
    assert "production trust-store integration: `NOT_IMPLEMENTED`" in text
    assert "gateway enforcement: `NOT_RUN`" in text
    assert "runtime changes: `NO_RUNTIME_CHANGE`" in text


def test_supplementary_record_references_every_contract_component() -> None:
    text = AS_BUILT.read_text(encoding="utf-8")

    for path in (
        "roe-contract.schema.json",
        "roe-step-request.schema.json",
        "intrusiveness-policy.yaml",
        "roe_contract.py",
        "test_roe_contract.py",
    ):
        assert path in text


def test_roe_readme_preserves_unimplemented_production_boundaries() -> None:
    text = README.read_text(encoding="utf-8")

    assert "Gateway enforcement: `NOT_RUN`" in text
    assert "trust-store integration: `NOT_IMPLEMENTED`" in text
    assert "Production signature verification: `NOT_RUN`" in text
    assert "Runtime changes: `NO_RUNTIME_CHANGE`" in text


def test_intrusiveness_policy_inventory_and_l4_separation_are_fixed() -> None:
    policy = yaml.safe_load(POLICY.read_text(encoding="utf-8"))

    assert tuple(policy["levels"]) == ("L0", "L1", "L2", "L3", "L4")
    assert policy["levels"]["L4"] == {
        "name": "high_impact",
        "minimum_step_approvals": 2,
        "distinct_approval_sides": 2,
        "rollback_plan_required": True,
    }
    assert policy["active_campaign_state"] == "RUNNING"
    assert policy["kill_switch_transition"]["to"] == "STOPPING"
