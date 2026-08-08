from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
FACTORY_DIR = ROOT / "platform" / "content-factory"


def _load(name: str, filename: str):
    spec = importlib.util.spec_from_file_location(name, FACTORY_DIR / filename)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


factory = _load("h01_factory_test", "content_factory.py")
ledger_module = _load("h01_review_ledger_test", "review_ledger.py")
LocalReviewLedger = ledger_module.LocalReviewLedger
ReviewLedgerError = ledger_module.ReviewLedgerError


def _metrics(**overrides):
    value = {
        "coverage_delta": 0.1,
        "positive_control": True,
        "negative_control": True,
        "reproducibility": 0.99,
        "false_positive_rate": 0.01,
        "false_negative_rate": 0.02,
        "cost_delta": 10.0,
        "staleness_days": 2,
    }
    value.update(overrides)
    return value


def _candidate(**overrides):
    value = {
        "kind": "runbook",
        "source_events": ["synthetic-source-event"],
        "reuse_strategy": "binding",
        "metrics": _metrics(),
    }
    value.update(overrides)
    return factory.build_candidate(**value)


def test_second_semantically_identical_submission_is_marked_and_blocked(tmp_path: Path) -> None:
    ledger = LocalReviewLedger(tmp_path / "ledger")
    candidate = _candidate()
    first = ledger.register(candidate)
    second = ledger.register(candidate)
    assert first["result"] == "REGISTERED"
    assert second["result"] == "BLOCKED_DUPLICATE"
    assert second["duplicate_of"] == candidate["candidate_id"]
    assert second["auto_merge"] is False
    assert second["execution_authority"] == "NONE"
    assert len(list(ledger.duplicates.glob("*.json"))) == 1


def test_caller_cannot_preapprove_or_claim_duplicate_state(tmp_path: Path) -> None:
    ledger = LocalReviewLedger(tmp_path / "ledger")
    candidate = _candidate()
    candidate["human_reviewed"] = True
    with pytest.raises(ReviewLedgerError):
        ledger.register(candidate)

    candidate = _candidate()
    candidate["duplicate_of"] = "cc_attacker_controlled"
    with pytest.raises(ReviewLedgerError):
        ledger.register(candidate)


def test_promotion_requires_persisted_approved_review_bound_to_exact_candidate(tmp_path: Path) -> None:
    ledger = LocalReviewLedger(tmp_path / "ledger")
    candidate = _candidate()
    ledger.register(candidate)
    review = ledger.record_review(
        candidate["candidate_id"],
        reviewer="synthetic-reviewer",
        decision="APPROVE",
        rationale="Controlled synthetic review approved for test promotion.",
        reviewed_at="2026-08-08T21:30:00Z",
    )
    assert ledger.verify_review(review["review_receipt_id"]) is True
    promotion = ledger.promote(
        candidate["candidate_id"], target="CANDIDATE", review_receipt_id=review["review_receipt_id"]
    )
    assert promotion["result"] == "PROMOTION_ELIGIBLE"
    assert promotion["auto_merge"] is False
    assert promotion["execution_authority"] == "NONE"


def test_rejected_review_cannot_promote(tmp_path: Path) -> None:
    ledger = LocalReviewLedger(tmp_path / "ledger")
    candidate = _candidate()
    ledger.register(candidate)
    review = ledger.record_review(
        candidate["candidate_id"],
        reviewer="synthetic-reviewer",
        decision="REJECT",
        rationale="Synthetic rejection exercises the fail-closed path.",
        reviewed_at="2026-08-08T21:31:00Z",
    )
    with pytest.raises(ReviewLedgerError):
        ledger.promote(candidate["candidate_id"], target="LAB_VALIDATED", review_receipt_id=review["review_receipt_id"])


def test_missing_positive_or_negative_control_cannot_exceed_lab_validated(tmp_path: Path) -> None:
    for metric in ("positive_control", "negative_control"):
        ledger = LocalReviewLedger(tmp_path / metric)
        candidate = _candidate(metrics=_metrics(**{metric: False}))
        ledger.register(candidate)
        review = ledger.record_review(
            candidate["candidate_id"],
            reviewer="synthetic-reviewer",
            decision="APPROVE",
            rationale="Approval does not override technical content gates.",
            reviewed_at="2026-08-08T21:32:00Z",
        )
        with pytest.raises(ReviewLedgerError):
            ledger.promote(candidate["candidate_id"], target="CANDIDATE", review_receipt_id=review["review_receipt_id"])


def test_candidate_tamper_breaks_review_binding(tmp_path: Path) -> None:
    ledger = LocalReviewLedger(tmp_path / "ledger")
    candidate = _candidate()
    ledger.register(candidate)
    review = ledger.record_review(
        candidate["candidate_id"],
        reviewer="synthetic-reviewer",
        decision="APPROVE",
        rationale="Synthetic approval.",
        reviewed_at="2026-08-08T21:33:00Z",
    )
    path = ledger.candidates / f"{candidate['candidate_id']}.json"
    mutated = json.loads(path.read_text())
    mutated["metrics"]["coverage_delta"] = 0.9
    path.write_text(json.dumps(mutated), encoding="utf-8")
    assert ledger.verify_review(review["review_receipt_id"]) is False
    with pytest.raises(ReviewLedgerError):
        ledger.promote(candidate["candidate_id"], target="CANDIDATE", review_receipt_id=review["review_receipt_id"])


def test_review_receipt_tamper_fails_closed(tmp_path: Path) -> None:
    ledger = LocalReviewLedger(tmp_path / "ledger")
    candidate = _candidate()
    ledger.register(candidate)
    review = ledger.record_review(
        candidate["candidate_id"],
        reviewer="synthetic-reviewer",
        decision="REJECT",
        rationale="Initial rejection.",
        reviewed_at="2026-08-08T21:34:00Z",
    )
    path = ledger.reviews / f"{review['review_receipt_id']}.json"
    mutated = json.loads(path.read_text())
    mutated["decision"] = "APPROVE"
    path.write_text(json.dumps(mutated), encoding="utf-8")
    assert ledger.verify_review(review["review_receipt_id"]) is False
    with pytest.raises(ReviewLedgerError):
        ledger.promote(candidate["candidate_id"], target="LAB_VALIDATED", review_receipt_id=review["review_receipt_id"])


def test_ledger_paths_are_owner_only(tmp_path: Path) -> None:
    ledger = LocalReviewLedger(tmp_path / "ledger")
    for path in (ledger.root, ledger.candidates, ledger.reviews, ledger.promotions, ledger.duplicates):
        assert path.stat().st_mode & 0o777 == 0o700
