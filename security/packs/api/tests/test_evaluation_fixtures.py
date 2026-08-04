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
            "object.owner_id": "owner-1",
            "subject.id": "attacker",
            "response_status": 200,
            "target_reachable": True,
            "prerequisites_missing": False,
        }
        result = _evaluate("API-AUTHZ-BOLA-READ-001", signals)
        assert result.decision == "vulnerable"

    def test_secure_when_same_owner(self) -> None:
        signals = {
            "object.owner_id": "owner-1",
            "subject.id": "owner-1",
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


class TestSemanticSignals:
    def test_semantic_signals_are_accepted_by_evaluator(self) -> None:
        signals = {
            "entity.id": "txn-123",
            "entity.owner_id": "owner-1",
            "subject.id": "attacker",
        }
        result = evaluate_signals(
            signals,
            {
                "vulnerable_when": ["entity.id != '' and entity.owner_id != '' and entity.owner_id != subject.id"],
                "secure_when": ["entity.id == '' or entity.owner_id == '' or entity.owner_id == subject.id"],
                "inconclusive_when": ["target_reachable == false"],
            },
        )
        assert result.decision == "vulnerable"

    def test_semantic_rate_limit_signal_is_accepted(self) -> None:
        signals = {
            "rate_limit.triggered": False,
            "response_status": 200,
            "target_reachable": True,
            "prerequisites_missing": False,
        }
        result = evaluate_signals(
            signals,
            {
                "vulnerable_when": ["rate_limit.triggered == false and response_status == 200"],
                "secure_when": ["rate_limit.triggered == true"],
                "inconclusive_when": [],
            },
        )
        assert result.decision == "vulnerable"

    def test_semantic_authz_signals_are_accepted(self) -> None:
        signals = {
            "object.owner_id": "owner-1",
            "subject.id": "attacker",
            "response_status": 200,
            "target_reachable": True,
            "prerequisites_missing": False,
        }
        result = evaluate_signals(
            signals,
            {
                "vulnerable_when": ["object.owner_id != subject.id and subject.id != '' and response_status == 200"],
                "secure_when": ["object.owner_id == subject.id or subject.id == ''"],
                "inconclusive_when": [],
            },
        )
        assert result.decision == "vulnerable"


class TestRunnerMetadataFiltering:
    def test_runner_metadata_is_rejected_by_evaluate_signals(self) -> None:
        with pytest.raises(SignalError):
            evaluate_signals(
                {
                    "response_status": 200,
                    "runner_exit_code": 0,
                    "runner_status": "ok",
                    "runner_stdout": "ok",
                },
                {
                    "vulnerable_when": ["response_status == 200"],
                    "secure_when": [],
                    "inconclusive_when": [],
                },
            )

    def test_extract_runner_meta_preserves_evidence(self) -> None:
        from evaluation import extract_runner_meta
        output = {
            "status": "ok",
            "response_status": 200,
            "runner_exit_code": 0,
            "runner_status": "ok",
            "runner_stdout": "completed",
            "meta": {},
        }
        meta = extract_runner_meta(output)
        assert meta == {
            "runner_exit_code": 0,
            "runner_status": "ok",
            "runner_stdout": "completed",
        }

    def test_normalize_execution_output_excludes_runner_meta_from_functional_signals(self) -> None:
        from evaluation import normalize_execution_output
        output = {
            "status": "ok",
            "response_status": 200,
            "runner_exit_code": 0,
            "runner_status": "ok",
            "runner_stdout": "completed",
            "meta": {},
        }
        functional = normalize_execution_output("http", output)
        assert "runner_exit_code" not in functional
        assert "runner_status" not in functional
        assert "runner_stdout" not in functional
