from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
ASSURANCE_DIR = ROOT / "platform" / "assurance"

spec = importlib.util.spec_from_file_location("assurance_contract", ASSURANCE_DIR / "assurance.py")
assert spec and spec.loader
module = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = module
spec.loader.exec_module(module)

AssuranceError = module.AssuranceError
FAILURE_CASES = module.FAILURE_CASES
Readiness = module.Readiness
assert_executable_step_ready = module.assert_executable_step_ready
assert_maturity_promotion = module.assert_maturity_promotion
highest_maturity = module.highest_maturity
trace_attributes = module.trace_attributes
validate_advertised_operation = module.validate_advertised_operation
validate_failure_suite = module.validate_failure_suite


def _passing_failures():
    return {name: "pass" for name in FAILURE_CASES}


def test_readiness_is_required_before_executable_step() -> None:
    with pytest.raises(AssuranceError):
        assert_executable_step_ready(None)
    with pytest.raises(AssuranceError):
        assert_executable_step_ready(Readiness("degraded", "2026-08-07T00:00:00Z", 60, 1))
    with pytest.raises(AssuranceError):
        assert_executable_step_ready(Readiness("ready", "2026-08-07T00:00:00Z", 60, 61))
    assert_executable_step_ready(Readiness("ready", "2026-08-07T00:00:00Z", 60, 1))


def test_failure_inventory_is_exact() -> None:
    assert FAILURE_CASES == {
        "restart", "invalid_json", "empty_stdout", "timeout", "network_loss",
        "disk_full", "partial_cleanup", "concurrency", "cancellation", "incompatible_version",
    }
    validate_failure_suite(_passing_failures())


def test_missing_or_failed_failure_case_blocks_suite() -> None:
    missing = _passing_failures()
    missing.pop("disk_full")
    with pytest.raises(AssuranceError):
        validate_failure_suite(missing)
    failed = _passing_failures()
    failed["timeout"] = "fail"
    with pytest.raises(AssuranceError):
        validate_failure_suite(failed)


def test_maturity_does_not_promote_without_failure_evidence() -> None:
    evidence = {"happy_path": True, "readiness": True}
    assert highest_maturity(evidence) == "M1"
    with pytest.raises(AssuranceError):
        assert_maturity_promotion("M1", "M2", evidence)


def test_complete_synthetic_evidence_reaches_m4_but_not_m5() -> None:
    evidence = {
        "happy_path": True,
        "readiness": True,
        "failure_results": _passing_failures(),
        "golden_lab": True,
        "golden_finding": True,
        "reproducibility": True,
        "false_positive_rate": True,
        "false_negative_rate": True,
        "cleanup_score": True,
    }
    assert highest_maturity(evidence) == "M4"
    with pytest.raises(AssuranceError):
        assert_maturity_promotion("M4", "M5", evidence)


def test_m5_requires_production_observation_and_retirement_readiness() -> None:
    evidence = {
        "happy_path": True,
        "readiness": True,
        "failure_results": _passing_failures(),
        "golden_lab": True,
        "golden_finding": True,
        "reproducibility": True,
        "false_positive_rate": True,
        "false_negative_rate": True,
        "cleanup_score": True,
        "production_observation": True,
        "retirement_readiness": True,
    }
    assert highest_maturity(evidence) == "M5"


def test_advertised_noop_is_rejected() -> None:
    with pytest.raises(AssuranceError):
        validate_advertised_operation({"advertised": True, "effect": "noop", "effect_evidence_required": True})
    with pytest.raises(AssuranceError):
        validate_advertised_operation({"advertised": True, "effect": "real", "effect_evidence_required": False})
    validate_advertised_operation({"advertised": True, "effect": "real", "effect_evidence_required": True})


def test_trace_attributes_require_all_four_correlations() -> None:
    attrs = trace_attributes({
        "campaign_id": "c1", "run_id": "r1", "step_id": "s1", "attempt_id": "a1"
    })
    assert set(attrs) == {
        "hexor.campaign_id", "hexor.run_id", "hexor.step_id", "hexor.attempt_id"
    }
    with pytest.raises(AssuranceError):
        trace_attributes({"campaign_id": "c1", "run_id": "r1"})


def test_runtime_assurance_operations_remain_not_run() -> None:
    policy = yaml.safe_load((ASSURANCE_DIR / "observability-maturity-policy.yaml").read_text())
    assert policy["runtime_status"] == {
        "otel_export": "NOT_RUN",
        "real_readiness_probe": "NOT_RUN",
        "chaos_execution": "NOT_RUN",
        "production_maturity_assessment": "NOT_RUN",
    }
