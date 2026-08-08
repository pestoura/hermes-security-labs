from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
FACTORY_DIR = ROOT / "platform/content-factory"


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


factory = _load("content_factory_controlled_ci", FACTORY_DIR / "content_factory.py")
ledger_module = _load("content_review_ledger_controlled_ci", FACTORY_DIR / "review_ledger.py")


def _candidate():
    return factory.build_candidate(
        kind="runbook",
        source_events=["controlled-ci-source"],
        reuse_strategy="variant",
        metrics={
            "coverage_delta": 1,
            "positive_control": True,
            "negative_control": True,
            "reproducibility": 1.0,
            "false_positive_rate": 0.0,
            "false_negative_rate": 0.0,
            "cost_delta": 0.0,
            "staleness_days": 0,
        },
    )


def test_controlled_local_promotion_requires_immutable_human_review_receipt(tmp_path: Path) -> None:
    ledger = ledger_module.LocalReviewLedger(tmp_path / "ledger")
    candidate = _candidate()
    registered = ledger.register(candidate)
    assert registered["result"] == "REGISTERED"
    review = ledger.record_review(
        candidate["candidate_id"],
        reviewer="controlled-reviewer",
        decision="APPROVE",
        rationale="controlled CI promotion evidence",
        reviewed_at="2026-08-08T22:40:00Z",
    )
    assert ledger.verify_review(review["review_receipt_id"]) is True
    promotion = ledger.promote(
        candidate["candidate_id"],
        target="STABLE",
        review_receipt_id=review["review_receipt_id"],
    )
    assert promotion["result"] == "PROMOTION_ELIGIBLE"
    assert promotion["auto_merge"] is False
    assert promotion["execution_authority"] == "NONE"
    assert ledger.verify_promotion(promotion["promotion_receipt_id"]) is True


def test_duplicate_candidate_is_blocked_before_promotion(tmp_path: Path) -> None:
    ledger = ledger_module.LocalReviewLedger(tmp_path / "ledger")
    candidate = _candidate()
    assert ledger.register(candidate)["result"] == "REGISTERED"
    duplicate = ledger.register(candidate)
    assert duplicate["result"] == "BLOCKED_DUPLICATE"
    assert duplicate["auto_merge"] is False
