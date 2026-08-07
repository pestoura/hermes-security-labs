from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import jsonschema
import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
PURPLE_DIR = ROOT / "platform" / "purple-team"

spec = importlib.util.spec_from_file_location("purple_team", PURPLE_DIR / "purple_team.py")
assert spec and spec.loader
module = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = module
spec.loader.exec_module(module)

PurpleTeamError = module.PurpleTeamError
build_resilience_exercise = module.build_resilience_exercise
record_outcome = module.record_outcome


def test_detected_outcome_requires_evidence_and_time_to_detect() -> None:
    outcome = record_outcome(
        step_id="step-1",
        state="DETECTED",
        observed=True,
        evidence_ids=["evidence-synthetic-1"],
        d3fend_refs=["D3-UAC"],
        time_to_detect_seconds=12.0,
        time_to_contain_seconds=30.0,
    )
    schema = json.loads((PURPLE_DIR / "purple-outcome.schema.json").read_text())
    jsonschema.Draft202012Validator(schema).validate(outcome)
    assert outcome["state"] == "DETECTED"
    assert outcome["time_to_detect_seconds"] == 12.0


def test_absence_of_observation_can_never_be_prevention() -> None:
    with pytest.raises(PurpleTeamError):
        record_outcome(
            step_id="step-1",
            state="PREVENTED",
            observed=False,
            evidence_ids=[],
        )
    not_observed = record_outcome(
        step_id="step-1",
        state="NOT_OBSERVED",
        observed=False,
        evidence_ids=[],
    )
    assert not_observed["state"] == "NOT_OBSERVED"


def test_prevention_requires_observation_and_evidence() -> None:
    with pytest.raises(PurpleTeamError):
        record_outcome(step_id="step-1", state="PREVENTED", observed=True, evidence_ids=[])
    prevented = record_outcome(
        step_id="step-1",
        state="PREVENTED",
        observed=True,
        evidence_ids=["evidence-synthetic-1"],
    )
    assert prevented["state"] == "PREVENTED"


def test_detected_not_actionable_is_explicit_not_success() -> None:
    outcome = record_outcome(
        step_id="step-2",
        state="DETECTED_NOT_ACTIONABLE",
        observed=True,
        evidence_ids=["evidence-synthetic-2"],
        time_to_detect_seconds=8,
    )
    assert outcome["state"] == "DETECTED_NOT_ACTIONABLE"
    assert outcome["time_to_contain_seconds"] is None


def test_negative_time_metrics_fail_closed() -> None:
    with pytest.raises(PurpleTeamError):
        record_outcome(
            step_id="step-2",
            state="DETECTED",
            observed=True,
            evidence_ids=["evidence-synthetic-2"],
            time_to_detect_seconds=-1,
        )


def test_resilience_exercise_is_plan_only() -> None:
    exercise = build_resilience_exercise(
        critical_function="synthetic customer portal",
        injects=[{"scenario": "synthetic service degradation", "expected_response": "invoke documented recovery process"}],
        recovery_criteria=["service health restored"],
        lessons_learned=["synthetic lesson"],
    )
    assert exercise["state"] == "EXERCISE_PLAN_ONLY"
    assert exercise["executable"] is False
    assert exercise["authorization_source"] == "CONTROL_PLANE_ONLY"


@pytest.mark.parametrize("forbidden", ["command", "argv", "shell", "payload", "credential", "secret", "token"])
def test_resilience_injects_reject_execution_material(forbidden: str) -> None:
    inject = {"scenario": "synthetic", "expected_response": "synthetic response"}
    inject[forbidden] = "synthetic-placeholder"
    with pytest.raises(PurpleTeamError):
        build_resilience_exercise(
            critical_function="synthetic",
            injects=[inject],
            recovery_criteria=["synthetic recovery"],
        )


def test_runtime_nonclaims_are_preserved() -> None:
    policy = yaml.safe_load((PURPLE_DIR / "purple-team-policy.yaml").read_text())
    assert policy["outcomes"]["absence_of_observation_is_prevention"] is False
    assert policy["runtime_status"] == {
        "defensive_telemetry_ingestion": "NOT_IMPLEMENTED",
        "siem_integration": "NOT_IMPLEMENTED",
        "edr_integration": "NOT_IMPLEMENTED",
        "containment_actions": "NOT_RUN",
        "adversary_emulation": "NOT_RUN",
        "resilience_exercise_execution": "NOT_RUN",
    }
