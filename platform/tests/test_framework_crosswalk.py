from __future__ import annotations

import copy
import importlib.util
import json
import sys
from pathlib import Path

import jsonschema
import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
CROSSWALK_DIR = ROOT / "platform" / "framework-crosswalk"

spec = importlib.util.spec_from_file_location("framework_crosswalk", CROSSWALK_DIR / "crosswalk.py")
assert spec and spec.loader
module = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = module
spec.loader.exec_module(module)

CrosswalkError = module.CrosswalkError
CANONICAL_PHASES = module.CANONICAL_PHASES
coverage_summary = module.coverage_summary
snapshot_digest = module.snapshot_digest
validate_crosswalk = module.validate_crosswalk
validate_methodology = module.validate_methodology


def _load_yaml(name: str) -> dict:
    return yaml.safe_load((CROSSWALK_DIR / name).read_text(encoding="utf-8"))


def _methodology() -> dict:
    return _load_yaml("methodology.yaml")


def _crosswalk() -> dict:
    return _load_yaml("framework-crosswalk.yaml")


def test_methodology_and_crosswalk_validate_against_strict_schemas() -> None:
    methodology_schema = json.loads((CROSSWALK_DIR / "methodology.schema.json").read_text(encoding="utf-8"))
    crosswalk_schema = json.loads((CROSSWALK_DIR / "framework-crosswalk.schema.json").read_text(encoding="utf-8"))
    jsonschema.Draft202012Validator(methodology_schema).validate(_methodology())
    jsonschema.Draft202012Validator(crosswalk_schema).validate(_crosswalk())


def test_canonical_methodology_has_fixed_order_and_explicit_authority_modes() -> None:
    methodology = validate_methodology(_methodology())
    assert tuple(phase["phase_id"] for phase in methodology["phases"]) == CANONICAL_PHASES
    assert methodology["phases"][0]["authorization_mode"] == "CONTROL_PLANE_ONLY"
    assert methodology["phases"][0]["execution_possible"] is False
    for phase in methodology["phases"]:
        if phase["execution_possible"]:
            assert phase["authorization_mode"] == "AUTHORIZED_EXECUTION"
            assert "active_authorization" in phase["required_inputs"]


def test_methodology_fails_closed_if_execution_phase_loses_authorization_input() -> None:
    methodology = _methodology()
    validate_phase = next(phase for phase in methodology["phases"] if phase["phase_id"] == "validate")
    validate_phase["required_inputs"].remove("active_authorization")
    with pytest.raises(CrosswalkError, match="active_authorization"):
        validate_methodology(methodology)


def test_crosswalk_requires_versioned_sources_relations_confidence_and_rationale() -> None:
    dataset = validate_crosswalk(_crosswalk(), _methodology())
    assert {framework["framework_id"] for framework in dataset["frameworks"]} == {
        "nist-sp-800-115",
        "owasp-wstg",
    }
    assert all(framework["framework_version"] for framework in dataset["frameworks"])
    assert all(framework["source_status"] == "manually_reviewed" for framework in dataset["frameworks"])
    assert all(mapping["relation"] in {"aligned_with", "supports", "informed_by", "overlaps"} for mapping in dataset["mappings"])
    assert all(mapping["advisory_only"] is True for mapping in dataset["mappings"])
    assert all(mapping["rationale"] for mapping in dataset["mappings"])


def test_crosswalk_confidence_band_mismatch_fails_closed() -> None:
    dataset = _crosswalk()
    dataset["mappings"][0]["confidence"] = "high"
    dataset["mappings"][0]["confidence_score"] = 0.50
    with pytest.raises(CrosswalkError, match="confidence"):
        validate_crosswalk(dataset, _methodology())


def test_unknown_framework_and_hidden_execution_authority_fail_closed() -> None:
    dataset = _crosswalk()
    dataset["mappings"][0]["framework_id"] = "unknown-framework"
    with pytest.raises(CrosswalkError, match="unknown framework"):
        validate_crosswalk(dataset, _methodology())

    dataset = _crosswalk()
    dataset["authorization_ref"] = "forbidden"
    with pytest.raises(CrosswalkError, match="execution authority"):
        validate_crosswalk(dataset, _methodology())


def test_mapping_claim_language_is_restricted_to_advisory_alignment() -> None:
    dataset = _crosswalk()
    dataset["mappings"][0]["rationale"] = "This mapping is certified by an external authority."
    with pytest.raises(CrosswalkError, match="certification or compliance"):
        validate_crosswalk(dataset, _methodology())


def test_coverage_summary_exposes_gaps_instead_of_forcing_mappings() -> None:
    summary = coverage_summary(_crosswalk(), _methodology())
    assert summary["phase_count"] == 7
    assert summary["framework_count"] == 2
    assert summary["mapped_phase_count_by_framework"]["nist-sp-800-115"] == 7
    assert summary["gaps_by_framework"]["nist-sp-800-115"] == []
    assert set(summary["gaps_by_framework"]["owasp-wstg"]) == {"assess_impact", "remediate_retest"}
    assert summary["claim_semantics"] == "advisory_alignment_only"


def test_snapshot_digest_is_deterministic_under_record_reordering() -> None:
    dataset = _crosswalk()
    digest = snapshot_digest(dataset, _methodology())
    reordered = copy.deepcopy(dataset)
    reordered["frameworks"].reverse()
    reordered["mappings"].reverse()
    assert snapshot_digest(reordered, _methodology()) == digest
    assert len(digest) == 64


def test_external_sync_consumers_and_execution_effect_are_not_claimed() -> None:
    dataset = validate_crosswalk(_crosswalk(), _methodology())
    assert dataset["runtime_status"] == {
        "authoritative_external_sync": "NOT_RUN",
        "automatic_framework_updates": "NOT_IMPLEMENTED",
        "planner_consumer_integration": "NOT_IMPLEMENTED",
        "reporting_consumer_integration": "NOT_IMPLEMENTED",
        "execution_effect": "NONE",
    }
    methodology = validate_methodology(_methodology())
    assert methodology["runtime_status"] == {
        "external_framework_sync": "NOT_RUN",
        "planner_integration": "NOT_IMPLEMENTED",
        "reporting_integration": "NOT_IMPLEMENTED",
        "execution_authority": "CONTROL_PLANE_ONLY",
    }
