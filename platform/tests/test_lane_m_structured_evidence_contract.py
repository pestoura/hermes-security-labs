from __future__ import annotations

import importlib.util
import json
import sys
from copy import deepcopy
from pathlib import Path

import jsonschema
import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
SCENARIO_DIR = ROOT / "scenario-registry"
SCENARIO_PATH = SCENARIO_DIR / "scenario-registry.yaml"
SCHEMA_PATH = SCENARIO_DIR / "scenario-registry.schema.json"
CONTRACT_PATH = SCENARIO_DIR / "evidence_contract.py"
COMPOSER_PATH = SCENARIO_DIR / "scenario_plan.py"
POLICY_PATH = ROOT / "evidence-plane" / "evidence-policy.yaml"


def _load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def _yaml(path: Path):
    return yaml.safe_load(path.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def contract():
    return _load_module("lane_m_evidence_contract_tests", CONTRACT_PATH)


@pytest.fixture(scope="module")
def composer():
    return _load_module("lane_m_scenario_plan_tests", COMPOSER_PATH)


def test_registry_schema_accepts_structured_evidence_and_rejects_legacy_free_text():
    registry = _yaml(SCENARIO_PATH)
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    jsonschema.validate(registry, schema)

    legacy = deepcopy(registry)
    legacy["scenarios"][0]["evidence_requirements"] = ["legacy free-text evidence"]
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(legacy, schema)


def test_all_seeded_scenarios_match_canonical_evidence_plane_policy(contract):
    registry = _yaml(SCENARIO_PATH)
    policy = _yaml(POLICY_PATH)

    assert contract.validate_registry_document(registry, policy=policy) == []
    for scenario in registry["scenarios"]:
        normalized = contract.validate_contract(
            scenario["evidence_requirements"],
            policy=policy,
        )
        assert normalized["evidence_plane_schema_version"] == policy["schema_version"]
        assert normalized["correlation"]["required_ids"] == policy["required_correlation_ids"]
        assert normalized["integrity"]["digest"] == policy["required_integrity"]["digest"]
        assert {item["classification"] for item in normalized["expected"]} <= set(
            policy["classifications"]
        )


@pytest.mark.parametrize(
    "scenario_id,scenario_specific_type",
    [
        ("webgoat-tls-transport-review", "structured_result"),
        ("dvwa-sql-injection-screening", "structured_result"),
        ("juice-shop-lab-lifecycle-stop", "reset_attestation"),
    ],
)
def test_composer_embeds_validated_structured_contract(
    composer,
    scenario_id,
    scenario_specific_type,
):
    result = composer.compose_scenario_plan(scenario_id)

    assert result.ok is True
    evidence = result.as_dict()["plan"]["evidence"]
    assert evidence["structure_state"] == "STRUCTURED_EVIDENCE_CONTRACT"
    structured = evidence["scenario_contract"]
    assert structured["integrity"]["digest"] == "sha256"
    assert structured["correlation"]["required_ids"] == [
        "campaign_id",
        "run_id",
        "step_id",
        "attempt_id",
    ]
    by_type = {item["evidence_type"]: item for item in structured["expected"]}
    assert by_type["execution_manifest"]["projection"] == "record"
    assert by_type["execution_manifest"]["classification"] == "restricted"
    assert by_type["execution_summary"]["projection"] == "record"
    assert by_type["execution_summary"]["classification"] == "summary"
    assert by_type[scenario_specific_type]["projection"] == "payload"
    assert by_type[scenario_specific_type]["classification"] == "raw"


@pytest.mark.parametrize(
    "mutation,expected_fragment",
    [
        ("correlation", "exactly match Evidence Plane policy"),
        ("classification", "unsupported evidence classification"),
        ("digest", "does not match Evidence Plane policy"),
        ("evidence_type", "unsupported evidence_type"),
        ("schema_version", "does not match Evidence Plane policy"),
        ("mandatory", "missing mandatory Evidence Plane projections"),
    ],
)
def test_contract_drift_fails_closed(contract, mutation, expected_fragment):
    requirements = deepcopy(_yaml(SCENARIO_PATH)["scenarios"][0]["evidence_requirements"])
    if mutation == "correlation":
        requirements["correlation"]["required_ids"].pop()
    elif mutation == "classification":
        requirements["expected"][0]["classification"] = "customer"
    elif mutation == "digest":
        requirements["integrity"]["digest"] = "sha512"
    elif mutation == "evidence_type":
        requirements["expected"][2]["evidence_type"] = "arbitrary_blob"
    elif mutation == "schema_version":
        requirements["evidence_plane_schema_version"] = "999.0"
    elif mutation == "mandatory":
        requirements["expected"] = [
            item
            for item in requirements["expected"]
            if item["evidence_type"] != "execution_summary"
        ]

    with pytest.raises(contract.EvidenceContractError, match=expected_fragment):
        contract.validate_contract(requirements)


def test_composer_rejects_policy_drift_as_missing_evidence_contract(composer):
    scenarios = deepcopy(_yaml(SCENARIO_PATH))
    scenarios["scenarios"][0]["evidence_requirements"]["integrity"]["digest"] = "sha512"

    result = composer.compose_scenario_plan(
        scenarios["scenarios"][0]["scenario_id"],
        scenario_doc=scenarios,
    )

    assert result.ok is False
    assert result.reason_code == "MISSING_EVIDENCE_CONTRACT"


def test_contract_only_declares_evidence_and_never_claims_runtime_observation(contract):
    registry = _yaml(SCENARIO_PATH)
    normalized = contract.validate_contract(registry["scenarios"][0]["evidence_requirements"])

    encoded = json.dumps(normalized, sort_keys=True)
    assert "runtime_observed" not in encoded
    assert "evidence_id" not in encoded
    assert "storage_ref" not in encoded
    assert "payload_sha256" not in encoded
