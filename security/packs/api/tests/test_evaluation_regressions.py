"""Regression tests for API evaluation criteria fixes introduced in issue #64."""

from __future__ import annotations

from api_pentest_runbooks.adapter import DryRunAdapter
from api_pentest_runbooks.catalog import load_runbooks
from api_pentest_runbooks.executor import execute_runbook
from api_pentest_runbooks.planner import applicable
from evaluation import evaluate_signals


def _load(rid: str) -> dict:
    from pathlib import Path
    root = Path(__file__).resolve().parents[1]
    return next(r for r in load_runbooks(root / "runbooks") if r["metadata"]["id"] == rid)


def _run(rid: str, target: dict | None = None) -> dict:
    if target is None:
        target = {"base_url": "http://localhost", "ref": "lab"}
    policy = {
        "allowed_targets": ["lab"],
        "allowed_providers": ["kali"],
        "allow_destructive": False,
        "max_actions_per_runbook": 10,
        "scope": {"allowed_hosts": ["localhost"], "allowed_cidrs": []},
        "execution": {"allowed_intrusiveness": ["medium"], "allow_destructive": False},
    }
    result = execute_runbook(_load(rid), target, {}, policy, DryRunAdapter())
    return result[0]


def test_jwt_audience_regression_family_isolation() -> None:
    runbook = _load("API-AUTH-JWT-AUDIENCE-008")
    assert runbook["metadata"]["category"] == "authentication"
    assert any("jwt_claims_aud" in item for item in runbook["evaluation"]["vulnerable_when"])
    assert any("jwt_claims_aud" in item for item in runbook["evaluation"]["secure_when"])
    assert not any("workflow_status" in item for item in runbook["evaluation"]["vulnerable_when"])
    assert not any("x-powered-by" in item for item in runbook["evaluation"]["vulnerable_when"])
    assert not any("x-content-type-options" in item for item in runbook["evaluation"]["vulnerable_when"])


def test_jwt_audience_dry_run_does_not_cross_authorization_family() -> None:
    outcome = _run("API-AUTH-JWT-AUDIENCE-008")
    assert outcome["status"] == "dry-run"
    assert "mcp_call" in outcome


def test_jwt_audience_selected_only_for_jwt_targets() -> None:
    runbook = _load("API-AUTH-JWT-AUDIENCE-008")
    assert applicable(runbook, {"api_type": "rest", "auth_type": "jwt", "capabilities": ["token_capture"]}) is True
    assert applicable(runbook, {"api_type": "rest", "auth_type": "any", "capabilities": []}) is False


def test_missing_auth_regression_uses_auth_signals() -> None:
    runbook = _load("API-AUTH-MISSING-001")
    assert runbook["metadata"]["category"] == "authentication"
    assert any("auth_accepted" in item for item in runbook["evaluation"]["vulnerable_when"])
    assert any("response_status" in item for item in runbook["evaluation"]["vulnerable_when"])
    assert not any("x-powered-by" in item for item in runbook["evaluation"]["vulnerable_when"])
    assert not any("workflow_status" in item for item in runbook["evaluation"]["secure_when"])


def test_missing_auth_fixture_vulnerable_when_no_auth_and_200() -> None:
    outcome = _run("API-AUTH-MISSING-001")
    assert outcome["status"] == "dry-run"


def test_basic_transport_regression_uses_redirect_signals() -> None:
    runbook = _load("API-AUTH-BASIC-TRANSPORT-016")
    assert runbook["metadata"]["category"] == "authentication"
    assert any("family_signal_producer_required" in item for item in runbook["evaluation"]["inconclusive_when"])
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


def test_basic_transport_fixture_secure_when_https_or_no_redirect() -> None:
    outcome = _run("API-AUTH-BASIC-TRANSPORT-016")
    assert outcome["status"] == "dry-run"
