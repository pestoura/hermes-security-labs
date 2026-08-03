"""Fixture-driven evaluator tests for API signal criteria."""

from __future__ import annotations

from pathlib import Path

import pytest

from api_pentest_runbooks.catalog import load_runbooks
from evaluation import (
    EvaluationResult,
    SignalError,
    evaluate_signals,
)

ROOT = Path(__file__).resolve().parents[1]
FIXTURE_ROOT = ROOT / "fixtures"


def _load(rid: str) -> dict:
    return next(r for r in load_runbooks(ROOT / "runbooks") if r["metadata"]["id"] == rid)


def _evaluate(rid: str, signals: dict[str, object]) -> EvaluationResult:
    runbook = _load(rid)
    return evaluate_signals(signals, runbook["evaluation"])


class TestMissingAuth:
    def test_vulnerable_when_no_auth_and_200(self) -> None:
        signals = {
            "auth_accepted": False,
            "response_status": 200,
            "target_reachable": True,
            "prerequisites_missing": False,
        }
        result = _evaluate("API-AUTH-MISSING-001", signals)
        assert result.decision == "vulnerable"

    def test_secure_when_401(self) -> None:
        signals = {
            "auth_accepted": False,
            "response_status": 401,
            "target_reachable": True,
            "prerequisites_missing": False,
        }
        result = _evaluate("API-AUTH-MISSING-001", signals)
        assert result.decision == "secure"

    def test_secure_when_auth_accepted(self) -> None:
        signals = {
            "auth_accepted": True,
            "response_status": 200,
            "target_reachable": True,
            "prerequisites_missing": False,
        }
        result = _evaluate("API-AUTH-MISSING-001", signals)
        assert result.decision == "secure"

    def test_inconclusive_when_unreachable(self) -> None:
        signals = {
            "auth_accepted": False,
            "response_status": 0,
            "target_reachable": False,
            "prerequisites_missing": False,
        }
        result = _evaluate("API-AUTH-MISSING-001", signals)
        assert result.decision == "inconclusive"


class TestBasicTransport:
    def test_missing_producer_is_explicit_inconclusive(self) -> None:
        runbook = _load("API-AUTH-BASIC-TRANSPORT-016")
        assert not any(runbook["evaluation"]["vulnerable_when"])
        assert not any(runbook["evaluation"]["secure_when"])
        assert any("family_signal_producer_required" in item for item in runbook["evaluation"]["inconclusive_when"])

    def test_evaluator_returns_inconclusive_without_required_signals(self) -> None:
        runbook = _load("API-AUTH-BASIC-TRANSPORT-016")
        result = evaluate_signals(
            {
                "auth_scheme": "basic",
                "request_redirect_target": "http://insecure.example.com",
                "target_reachable": True,
                "prerequisites_missing": False,
            },
            runbook["evaluation"],
        )
        assert result.decision == "inconclusive"


class TestJwtAudience:
    def test_vulnerable_when_audience_missing(self) -> None:
        signals = {
            "jwt_claims_aud": None,
            "jwt_signature_valid": False,
            "target_reachable": True,
            "prerequisites_missing": False,
        }
        result = _evaluate("API-AUTH-JWT-AUDIENCE-008", signals)
        assert result.decision == "vulnerable"

    def test_secure_when_valid_audience_and_signature(self) -> None:
        signals = {
            "jwt_claims_aud": "hex0r-api",
            "jwt_signature_valid": True,
            "target_reachable": True,
            "prerequisites_missing": False,
        }
        result = _evaluate("API-AUTH-JWT-AUDIENCE-008", signals)
        assert result.decision == "secure"

    def test_inconclusive_when_prerequisites_missing(self) -> None:
        signals = {
            "jwt_claims_aud": "hex0r-api",
            "jwt_signature_valid": False,
            "target_reachable": False,
            "prerequisites_missing": True,
        }
        result = _evaluate("API-AUTH-JWT-AUDIENCE-008", signals)
        assert result.decision == "inconclusive"


class TestBola:
    def test_vulnerable_when_owner_mismatch(self) -> None:
        signals = {
            "object_owner_id": "owner-1",
            "subject_id": "attacker",
            "response_status": 200,
            "target_reachable": True,
            "prerequisites_missing": False,
        }
        result = _evaluate("API-AUTHZ-BOLA-READ-001", signals)
        assert result.decision == "vulnerable"

    def test_secure_when_same_owner(self) -> None:
        signals = {
            "object_owner_id": "owner-1",
            "subject_id": "owner-1",
            "response_status": 200,
            "target_reachable": True,
            "prerequisites_missing": False,
        }
        result = _evaluate("API-AUTHZ-BOLA-READ-001", signals)
        assert result.decision == "secure"


class TestEvaluatorSafety:
    def test_unknown_signal_rejected(self) -> None:
        with pytest.raises(SignalError):
            evaluate_signals({"unknown_signal": True}, {"vulnerable_when": ["unknown_signal == true"], "secure_when": [], "inconclusive_when": []})

    def test_type_mismatch_rejected(self) -> None:
        with pytest.raises(SignalError):
            evaluate_signals(
                {"response_status": "200"},
                {"vulnerable_when": ["response_status == 200"], "secure_when": [], "inconclusive_when": []},
            )

    def test_criteria_without_producer_is_inconclusive(self) -> None:
        runbook = _load("API-AUTH-MFA-ENFORCEMENT-021")
        assert not any(runbook["evaluation"]["vulnerable_when"])
        assert not any(runbook["evaluation"]["secure_when"])
        assert any("family_signal_producer_required" in item for item in runbook["evaluation"]["inconclusive_when"])
