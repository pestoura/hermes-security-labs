from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PATH = ROOT / "platform/content-factories/content_lifecycle.py"
spec = importlib.util.spec_from_file_location("content_lifecycle", PATH)
assert spec and spec.loader
lifecycle = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = lifecycle
spec.loader.exec_module(lifecycle)


def _decision(current: str, target: str, **overrides):
    args = dict(
        current_state=current,
        target_state=target,
        fingerprint="sha256:synthetic",
        active_fingerprints=[],
        positive_control_passed=True,
        negative_control_passed=True,
        human_review_id="review-001",
        pr_approval_id="pr-approval-001",
    )
    args.update(overrides)
    return lifecycle.evaluate_promotion(**args)


def test_duplicate_is_blocked_automatically() -> None:
    result = _decision(
        "TRIAGED",
        "GENERATED",
        active_fingerprints=["sha256:synthetic"],
    )
    assert result.allowed is False
    assert result.next_state == "DUPLICATE"
    assert result.codes == ("DUPLICATE_BLOCKED",)


def test_content_without_positive_and_negative_controls_cannot_pass_lab_validated() -> None:
    result = _decision(
        "LAB_VALIDATED",
        "REVIEWED",
        negative_control_passed=False,
    )
    assert result.allowed is False
    assert result.codes == ("LAB_CONTROLS_INCOMPLETE",)


def test_candidate_requires_recorded_human_review() -> None:
    result = _decision("REVIEWED", "CANDIDATE", human_review_id=None)
    assert result.allowed is False
    assert result.codes == ("HUMAN_REVIEW_REQUIRED",)


def test_acceptance_requires_explicit_pr_approval() -> None:
    result = _decision("CANDIDATE", "ACCEPTED", pr_approval_id=None)
    assert result.allowed is False
    assert result.codes == ("PR_APPROVAL_REQUIRED",)


def test_green_sequential_transition_is_allowed() -> None:
    result = _decision("REVIEWED", "CANDIDATE")
    assert result.allowed is True
    assert result.next_state == "CANDIDATE"
