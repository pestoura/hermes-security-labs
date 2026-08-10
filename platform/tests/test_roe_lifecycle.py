from __future__ import annotations

import json
from pathlib import Path

import jsonschema
import yaml

ROOT = Path(__file__).resolve().parents[2]
ROE_DIR = ROOT / "platform" / "roe-contract"
AUTH_DIR = ROOT / "platform" / "authorization-contract"
README = ROE_DIR / "README.md"
AUTH_README = AUTH_DIR / "README.md"
POLICY = ROE_DIR / "intrusiveness-policy.yaml"
SCHEMA = ROE_DIR / "roe-contract.schema.json"
EXAMPLE = ROE_DIR / "examples" / "roe-contract.example.json"


def test_roe_schema_and_example_validate() -> None:
    schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
    document = json.loads(EXAMPLE.read_text(encoding="utf-8"))
    jsonschema.Draft202012Validator(schema).validate(document)


def test_roe_readme_names_canonical_verifier_components() -> None:
    text = README.read_text(encoding="utf-8")

    for path in (
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


def test_tb1_authorization_contract_never_claims_live_runtime_issuance() -> None:
    text = AUTH_README.read_text(encoding="utf-8")

    assert "Hermes is the only execution-authorization authority" in text
    assert "Hermes receipt issuance boundary: `IMPLEMENTED / GREEN-REPO-CANDIDATE`" in text
    assert "production signer binding/private-key custody: `NOT_CONFIGURED / NOT_RUN`" in text
    assert "live Hermes receipt issuance: `NOT_RUN`" in text
    assert "deployed authorization trust store: `NOT_RUN`" in text
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
