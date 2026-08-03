from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from api_pentest_runbooks.evaluator import EvaluationError, evaluate, validate_expression
from api_pentest_runbooks.signals import normalize_handler_output

ROOT = Path(__file__).resolve().parents[1]
FIXTURE_ROOT = ROOT / "tests" / "fixtures"


def _load_runbook(rid: str) -> dict:
    from api_pentest_runbooks.catalog import load_runbooks
    return next(r for r in load_runbooks(ROOT / "runbooks") if r["metadata"]["id"] == rid)


def _output(handler: str, profile: str, **kwargs: object) -> dict[str, object]:
    output: dict[str, object] = {"status": "completed", "status_code": 200, "headers": {}, "body_sample": "", "stdout": "", "stderr": ""}
    output.update(kwargs)
    return normalize_handler_output(handler, profile, output)


def test_jwt_audience_regression_vulnerable() -> None:
    runbook = _load_runbook("API-AUTH-JWT-AUDIENCE-008")
    signals = {"jwt.claims.aud": None, "target_reachable": True, "prerequisites_missing": False}
    assert any(evaluate(rule, signals, "authentication") for rule in runbook["evaluation"]["vulnerable_when"])


def test_jwt_audience_regression_secure() -> None:
    runbook = _load_runbook("API-AUTH-JWT-AUDIENCE-008")
    signals = {"jwt.claims.aud": "hex0r-api", "jwt.signature.valid": True, "target_reachable": True, "prerequisites_missing": False}
    assert all(evaluate(rule, signals, "authentication") for rule in runbook["evaluation"]["secure_when"])


def test_jwt_audience_regression_inconclusive_when_unreachable() -> None:
    runbook = _load_runbook("API-AUTH-JWT-AUDIENCE-008")
    signals = {"jwt.claims.aud": None, "target_reachable": False, "prerequisites_missing": False}
    assert any(evaluate(rule, signals, "authentication") for rule in runbook["evaluation"]["inconclusive_when"])


def test_missing_auth_regression_vulnerable() -> None:
    runbook = _load_runbook("API-AUTH-MISSING-001")
    signals = {"auth.accepted": False, "response_status": 200, "target_reachable": True, "prerequisites_missing": False}
    assert any(evaluate(rule, signals, "authentication") for rule in runbook["evaluation"]["vulnerable_when"])


def test_missing_auth_regression_secure() -> None:
    runbook = _load_runbook("API-AUTH-MISSING-001")
    signals = {"auth.accepted": True, "response_status": 401, "target_reachable": True, "prerequisites_missing": False}
    assert any(evaluate(rule, signals, "authentication") for rule in runbook["evaluation"]["secure_when"])


def test_basic_transport_regression_vulnerable() -> None:
    runbook = _load_runbook("API-AUTH-BASIC-TRANSPORT-016")
    signals = {"auth.scheme": "basic", "request.redirect_target": "http://insecure.example.com", "target_reachable": True, "prerequisites_missing": False}
    assert any(evaluate(rule, signals, "authentication") for rule in runbook["evaluation"]["vulnerable_when"])


def test_basic_transport_regression_secure() -> None:
    runbook = _load_runbook("API-AUTH-BASIC-TRANSPORT-016")
    signals = {"request.redirect_target": "https://secure.example.com", "target_reachable": True, "prerequisites_missing": False}
    assert any(evaluate(rule, signals, "authentication") for rule in runbook["evaluation"]["secure_when"])


def test_empty_expression_raises() -> None:
    with pytest.raises(EvaluationError):
        validate_expression("", "authentication")


def test_unknown_variable_raises() -> None:
    with pytest.raises(EvaluationError):
        validate_expression("workflow_status in {'failed'}", "authentication")


def test_irrelevant_header_variable_raises() -> None:
    with pytest.raises(EvaluationError):
        validate_expression("headers['x-powered-by'] == 'nginx'", "authentication")


def test_signal_family_isolation() -> None:
    auth_runbook = _load_runbook("API-AUTH-JWT-AUDIENCE-008")
    authz_signals = {"object.owner_id": "other", "subject.id": "me", "target_reachable": True, "prerequisites_missing": False}
    for rule in auth_runbook["evaluation"]["vulnerable_when"]:
        with pytest.raises(EvaluationError):
            evaluate(rule, authz_signals, "authorization")
