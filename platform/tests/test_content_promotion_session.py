from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
FACTORY_PATH = ROOT / "platform/content-factory/content_factory.py"
SESSION_PATH = ROOT / "platform/content-factory/promotion_session.py"


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


factory = _load("content_factory_for_session_test", FACTORY_PATH)
session = _load("content_promotion_session_test", SESSION_PATH)


def _candidate() -> dict:
    return factory.build_candidate(
        kind="runbook",
        source_events=["feed:example:1"],
        reuse_strategy="variant",
        metrics={
            "coverage_delta": 1,
            "positive_control": True,
            "negative_control": True,
            "reproducibility": 1.0,
            "false_positive_rate": 0.0,
            "false_negative_rate": 0.0,
            "cost_delta": 0,
            "staleness_days": 0,
        },
    )


def test_controlled_session_produces_verified_non_executable_receipts(tmp_path: Path) -> None:
    result = session.run_controlled_session(
        ledger_root=tmp_path,
        candidate=_candidate(),
        reviewer="human-reviewer",
        rationale="positive and negative controls verified",
        reviewed_at="2026-08-08T22:15:00Z",
    )
    assert result["registration_result"] == "REGISTERED"
    assert result["promotion_result"] == "PROMOTION_ELIGIBLE"
    assert result["target"] == "CANDIDATE"
    assert result["auto_merge"] is False
    assert result["deployment_performed"] is False
    assert result["execution_authority"] == "NONE"


def test_duplicate_candidate_fails_closed(tmp_path: Path) -> None:
    candidate = _candidate()
    session.run_controlled_session(
        ledger_root=tmp_path,
        candidate=candidate,
        reviewer="human-reviewer",
        rationale="first review",
        reviewed_at="2026-08-08T22:15:00Z",
    )
    with pytest.raises(session.PromotionSessionError, match="fresh record"):
        session.run_controlled_session(
            ledger_root=tmp_path,
            candidate=candidate,
            reviewer="human-reviewer",
            rationale="duplicate review",
            reviewed_at="2026-08-08T22:16:00Z",
        )


def test_session_refuses_stable_or_implicit_deployment(tmp_path: Path) -> None:
    with pytest.raises(session.PromotionSessionError, match="LAB_VALIDATED or CANDIDATE"):
        session.run_controlled_session(
            ledger_root=tmp_path,
            candidate=_candidate(),
            reviewer="human-reviewer",
            rationale="reviewed",
            reviewed_at="2026-08-08T22:15:00Z",
            target="STABLE",
        )
