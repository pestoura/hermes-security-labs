from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
EPIC = ROOT / "docs/roadmap/epics/EPIC-28-rules-of-engagement-as-code.md"
AS_BUILT = ROOT / "docs/roadmap/EPIC-28-roe-contract-candidate-as-built.md"
README = ROOT / "platform/roe-contract/README.md"
POLICY = ROOT / "platform/roe-contract/intrusiveness-policy.yaml"
AUTH_README = ROOT / "platform/authorization-contract/README.md"


def test_concept_epic_is_implementing_but_not_final() -> None:
    text = EPIC.read_text(encoding="utf-8")

    assert "**IMPLEMENTING**" in text
    assert "| IMPLEMENTING | yes |" in text
    assert "| AS_BUILT | no |" in text
    assert "| FINAL | no |" in text
    assert "PR #159" in text
    assert "PR #160" in text
    assert "PR #161" in text
    assert "NO_RUNTIME_CHANGE" in text


def test_concept_epic_records_control_plane_as_only_authority() -> None:
    text = EPIC.read_text(encoding="utf-8")

    assert "Hermes/control plane is the sole execution authorization authority" in text
    assert "execution plane may recompute a reference only as an integrity check" in text
    assert "separate trust purposes/domains" in text
    assert "Hermes operational TB1 receipt issuance: `NOT_IMPLEMENTED` / `NOT_RUN`" in text


def test_supplementary_record_never_claims_final_or_runtime_enforcement() -> None:
    text = AS_BUILT.read_text(encoding="utf-8")
    normalized = text.lower()

    assert "AS_BUILT — contract candidate" in text
    assert "| FINAL | no |" in text
    assert "production/deployed trust-store and signing operations: `not_run`" in normalized
    assert "deployed gateway enforcement: `not_run`" in normalized
    assert "cancellation request transport/dispatch: `not_implemented` / `not_run`" in normalized
    assert "runtime changes: `no_runtime_change`" in normalized


def test_supplementary_record_references_every_contract_component() -> None:
    text = AS_BUILT.read_text(encoding="utf-8")

    for path in (
        "roe-contract.schema.json",
        "roe-step-request.schema.json",
        "intrusiveness-policy.yaml",
        "roe_contract.py",
        "test_roe_contract.py",
        "trust_store.py",
        "kill_switch.py",
        "admission.py",
        "kill_switch_cancellation.py",
    ):
        assert path in text


def test_roe_readme_preserves_unimplemented_production_boundaries() -> None:
    text = README.read_text(encoding="utf-8")

    assert "Gateway enforcement: `NOT_RUN`" in text
    assert "trust-store integration: `NOT_IMPLEMENTED`" in text
    assert "Production signature verification: `NOT_RUN`" in text
    assert "Runtime changes: `NO_RUNTIME_CHANGE`" in text


def test_tb1_authorization_contract_distinguishes_repo_issuer_from_live_runtime() -> None:
    text = AUTH_README.read_text(encoding="utf-8")

    assert "Hermes is the only execution-authorization authority" in text
    assert "Hermes receipt issuance boundary: `IMPLEMENTED / GREEN-REPO-CANDIDATE`" in text
    assert "production signer binding/private-key custody: `NOT_CONFIGURED / NOT_RUN`" in text
    assert "deployed authorization trust store: `NOT_RUN`" in text
    assert "live Hermes receipt issuance: `NOT_RUN`" in text
    assert "deployed gateway validation: `NOT_RUN`" in text
    assert "runtime changes: `NO_RUNTIME_CHANGE`" in text


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
