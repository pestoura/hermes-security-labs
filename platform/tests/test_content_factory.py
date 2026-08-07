from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import jsonschema
import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
FACTORY_DIR = ROOT / "platform" / "content-factory"

spec = importlib.util.spec_from_file_location("content_factory", FACTORY_DIR / "content_factory.py")
assert spec and spec.loader
module = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = module
spec.loader.exec_module(module)

ContentFactoryError = module.ContentFactoryError
build_candidate = module.build_candidate
incremental_events = module.incremental_events
promote = module.promote
promotion_failures = module.promotion_failures
record_human_review = module.record_human_review


def _metrics(**overrides):
    values = {
        "coverage_delta": 0.1,
        "positive_control": True,
        "negative_control": True,
        "reproducibility": 0.99,
        "false_positive_rate": 0.01,
        "false_negative_rate": 0.02,
        "cost_delta": 10.0,
        "staleness_days": 2,
    }
    values.update(overrides)
    return values


def _candidate(**overrides):
    values = {
        "kind": "runbook",
        "source_events": ["source-event-1"],
        "reuse_strategy": "binding",
        "metrics": _metrics(),
    }
    values.update(overrides)
    return build_candidate(**values)


def test_incremental_sync_represents_only_differences() -> None:
    assert incremental_events(previous=["a", "b"], current=["b", "c"]) == [
        {"event": "added", "item": "c"},
        {"event": "removed", "item": "a"},
    ]


def test_candidate_is_non_executable_and_schema_valid() -> None:
    candidate = _candidate(learning_proposal=True)
    assert candidate["lifecycle"] == "PROPOSED"
    assert candidate["auto_merge"] is False
    assert candidate["learning_proposal"] is True
    schema = json.loads((FACTORY_DIR / "content-candidate.schema.json").read_text())
    schema_view = dict(candidate)
    schema_view.pop("learning_proposal")
    jsonschema.Draft202012Validator(schema).validate(schema_view)


def test_human_review_is_required_before_promotion() -> None:
    candidate = _candidate()
    assert "human_review" in promotion_failures(candidate, target="LAB_VALIDATED")
    reviewed = record_human_review(candidate, reviewer="synthetic-reviewer")
    promoted = promote(reviewed, target="LAB_VALIDATED")
    assert promoted["lifecycle"] == "LAB_VALIDATED"
    assert promoted["auto_merge"] is False


def test_controls_are_required_above_lab_validated() -> None:
    reviewed = record_human_review(_candidate(metrics=_metrics(positive_control=False)), reviewer="synthetic-reviewer")
    assert "positive_control" in promotion_failures(reviewed, target="CANDIDATE")
    with pytest.raises(ContentFactoryError):
        promote(reviewed, target="CANDIDATE")


def test_duplicate_candidate_is_blocked_automatically() -> None:
    reviewed = record_human_review(_candidate(duplicate_of="cc_existing"), reviewer="synthetic-reviewer")
    assert "duplicate" in promotion_failures(reviewed, target="LAB_VALIDATED")
    with pytest.raises(ContentFactoryError):
        promote(reviewed, target="LAB_VALIDATED")


@pytest.mark.parametrize(
    ("override", "failure"),
    [
        ({"coverage_delta": -0.01}, "coverage_regression"),
        ({"reproducibility": 0.8}, "reproducibility"),
        ({"false_positive_rate": 0.2}, "false_positive_rate"),
        ({"false_negative_rate": 0.2}, "false_negative_rate"),
        ({"cost_delta": 101.0}, "cost"),
        ({"staleness_days": 31}, "staleness"),
    ],
)
def test_stable_promotion_blocks_quality_degradation(override: dict, failure: str) -> None:
    reviewed = record_human_review(_candidate(metrics=_metrics(**override)), reviewer="synthetic-reviewer")
    assert failure in promotion_failures(reviewed, target="STABLE")


def test_stable_promotion_succeeds_only_with_all_gates() -> None:
    reviewed = record_human_review(_candidate(), reviewer="synthetic-reviewer")
    stable = promote(reviewed, target="STABLE")
    assert stable["lifecycle"] == "STABLE"
    assert stable["auto_merge"] is False


def test_runtime_nonclaims_are_preserved() -> None:
    policy = yaml.safe_load((FACTORY_DIR / "promotion-policy.yaml").read_text())
    assert policy["learning_proposals"]["auto_merge"] is False
    assert policy["promotion"]["coverage_regression_allowed"] is False
    assert policy["runtime_status"] == {
        "source_sync": "NOT_RUN",
        "candidate_generation_model": "NOT_RUN",
        "lab_execution": "NOT_RUN",
        "runtime_image_build": "NOT_RUN",
        "detection_deployment": "NOT_RUN",
        "autonomous_merge": "NOT_RUN",
    }
