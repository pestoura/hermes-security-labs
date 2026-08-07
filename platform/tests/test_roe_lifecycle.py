from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
INTENT = ROOT / "docs/roadmap/epics/EPIC-28-rules-of-engagement-as-code.md"
AS_BUILT = ROOT / "docs/roadmap/EPIC-28-roe-contract-candidate-as-built.md"
README = ROOT / "platform/roe-contract/README.md"
POLICY = ROOT / "platform/roe-contract/intrusiveness-policy.yaml"


def test_concept_epic_is_implementing_and_not_final() -> None:
    """EPIC-28 must not regress to INTENT: #159/#160/#161 are on `main`."""

    text = INTENT.read_text(encoding="utf-8")

    assert "**IMPLEMENTING**" in text
    assert "**INTENT** — nothing described in this document is implemented" not in text
    assert "| INTENT | yes |" in text
    assert "| IMPLEMENTING | yes |" in text
    assert "| AS_BUILT | no |" in text
    assert "| FINAL | no |" in text


def test_concept_epic_section_14_records_real_evidence() -> None:
    tail = INTENT.read_text(encoding="utf-8").split("## 14. Implementation notes", 1)[1]

    assert "Reserved" in tail
    assert "_Not started._" not in tail
    for reference in ("/pull/159", "/pull/160", "/pull/161"):
        assert reference in tail
    assert "fix/tb1-control-plane-issued-authorization" in tail
    assert "NO_RUNTIME_CHANGE" in tail
    assert "Recorded divergence" in tail


def test_concept_epic_section_15_stays_non_final_with_runtime_not_run() -> None:
    section = INTENT.read_text(encoding="utf-8").split(
        "## 15. As-built / final architecture", 1
    )[1].split("## 16.", 1)[0]

    assert "Not final" in section
    assert "`NOT_RUN`" in section
    assert "`NOT_IMPLEMENTED`" in section


def test_authorization_receipt_docs_never_say_the_gateway_creates_authorization() -> None:
    contracts = (
        ROOT / "docs/architecture/contracts/README.md"
    ).read_text(encoding="utf-8")

    assert "the execution gateway only verifies and consumes it and never issues one" in contracts
    assert "`NOT_IMPLEMENTED`" in contracts
    assert "`NOT_RUN`" in contracts
    for forbidden in (
        "gateway creates the authorization",
        "gateway issues the authorization",
        "gateway-issued authorization",
    ):
        assert forbidden not in contracts.lower()


def test_roe_readme_documents_the_authorization_receipt_without_claiming_runtime() -> None:
    text = README.read_text(encoding="utf-8")

    assert "TB1 control-plane authorization receipt" in text
    assert "TB1 authorization receipt contract and verifier: `CANDIDATE`" in text
    assert "Hermes authorization issuance runtime: `NOT_IMPLEMENTED`" in text
    assert "Deployed validation of the authorization receipt: `NOT_RUN`" in text
    assert "implements **no operational issuer**" in text


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
