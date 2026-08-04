"""Regression tests for missing membership signals (issue #64)."""

from __future__ import annotations

from pathlib import Path

import pytest

from api_pentest_runbooks.catalog import load_runbooks
from evaluation import MISSING_SIGNAL, SignalError, evaluate_signals

BASE = {"target_reachable": True, "prerequisites_missing": False}


def _runbook(rid: str) -> dict:
    root = Path(__file__).resolve().parents[1]
    return next(r for r in load_runbooks(root / "runbooks") if r["metadata"]["id"] == rid)


def _criteria(rid: str) -> dict:
    return _runbook(rid)["evaluation"]


def test_missing_signal_is_singleton_falsy_and_membership_safe() -> None:
    from evaluation import _MissingSignal

    assert _MissingSignal() is MISSING_SIGNAL
    assert bool(MISSING_SIGNAL) is False
    assert not MISSING_SIGNAL
    assert len(MISSING_SIGNAL) == 0
    assert ("x" in MISSING_SIGNAL) is False
    assert ("x" not in MISSING_SIGNAL) is True
    assert MISSING_SIGNAL.__eq__(False) is True
    assert MISSING_SIGNAL.__eq__(None) is True
    assert MISSING_SIGNAL.__ne__(True) is True
    assert list(MISSING_SIGNAL) == []
    assert repr(MISSING_SIGNAL) == "MISSING_SIGNAL"


def test_missing_response_headers_membership_does_not_raise() -> None:
    criteria = {
        "vulnerable_when": ["'strict-transport-security' not in response_headers"],
        "secure_when": ["'strict-transport-security' in response_headers"],
        "inconclusive_when": [],
    }
    result = evaluate_signals(dict(BASE), criteria)
    assert result.decision == "vulnerable"


def test_hsts_runbook_with_missing_headers_and_with_dict() -> None:
    criteria = _criteria("API-TRANS-HSTS-006")

    missing = evaluate_signals(dict(BASE), criteria)
    assert missing.decision == "vulnerable"

    present = evaluate_signals(
        {**BASE, "response_headers": {"strict-transport-security": "max-age=31536000"}},
        criteria,
    )
    assert present.decision == "secure"

    empty = evaluate_signals({**BASE, "response_headers": {}}, criteria)
    assert empty.decision == "vulnerable"


def test_x_powered_by_absent_and_present() -> None:
    criteria = _criteria("API-CONFIG-SERVER-BANNER-009")

    absent = evaluate_signals({**BASE, "response_status": 200}, criteria)
    assert absent.decision == "secure"

    present = evaluate_signals(
        {**BASE, "response_status": 200, "response_headers": {"x-powered-by": "Express"}},
        criteria,
    )
    assert present.decision == "vulnerable"


def test_missing_boolean_stays_falsy_in_and_chains() -> None:
    criteria = {
        "vulnerable_when": ["auth_accepted == true and response_status == 200"],
        "secure_when": ["not auth_accepted"],
        "inconclusive_when": [],
    }
    result = evaluate_signals({**BASE, "response_status": 200}, criteria)
    assert result.decision == "secure"


def test_unknown_provided_signal_still_rejected() -> None:
    with pytest.raises(SignalError):
        evaluate_signals({**BASE, "totally_unknown_signal": True}, {"vulnerable_when": []})


def test_unknown_dotted_path_still_rejected() -> None:
    criteria = {"vulnerable_when": ["response_headers.unknown_attr == 'x'"]}
    with pytest.raises(SignalError):
        evaluate_signals({**BASE, "response_headers": {"a": "b"}}, criteria)


def test_membership_against_non_container_raises_signal_error() -> None:
    int_criteria = {"vulnerable_when": ["'x' in response_status"]}
    with pytest.raises(SignalError):
        evaluate_signals({**BASE, "response_status": 200}, int_criteria)

    bool_criteria = {"vulnerable_when": ["'x' in auth_accepted"]}
    with pytest.raises(SignalError):
        evaluate_signals({**BASE, "auth_accepted": True}, bool_criteria)


def test_map_type_mismatch_rejected() -> None:
    with pytest.raises(SignalError):
        evaluate_signals({**BASE, "response_headers": "not-a-dict"}, {"vulnerable_when": []})


def test_missing_signal_never_exposed_in_results() -> None:
    criteria = _criteria("API-TRANS-HSTS-006")
    result = evaluate_signals(dict(BASE), criteria)
    blob = " ".join(result.evaluated) + " " + " ".join(result.reasons)
    assert "MISSING_SIGNAL" not in blob
    assert all(isinstance(item, str) for item in result.evaluated + result.reasons)
