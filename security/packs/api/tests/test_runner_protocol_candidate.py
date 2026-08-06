from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

API_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = API_ROOT.parents[2]
PROTOCOL_ROOT = REPO_ROOT / "platform" / "runner-protocol"
SDK_SRC = PROTOCOL_ROOT / "src"
API_SRC = API_ROOT / "src"
for source in (SDK_SRC, API_SRC):
    if str(source) not in sys.path:
        sys.path.insert(0, str(source))

from api_pentest_runbooks.runner_protocol_adapter import (  # noqa: E402
    ApiRunnerProtocolCandidate,
)
from runner_protocol_v2 import validate_semantics  # noqa: E402

sys.path.insert(0, str(PROTOCOL_ROOT))
from conformance import run_conformance  # noqa: E402

CANDIDATE_PATH = API_SRC / "api_pentest_runbooks" / "runner_protocol_adapter.py"
CORRELATION = {
    "campaign_id": "11111111-1111-4111-8111-111111111111",
    "run_id": "22222222-2222-4222-8222-222222222222",
    "step_id": "33333333-3333-4333-8333-333333333333",
    "attempt_id": "44444444-4444-4444-8444-444444444444",
}


def _request(capability_id: str, authorization_ref: str = "authz/conformance/active") -> dict:
    return {
        "message_type": "runner.step.request",
        "protocol_version": "2.0.0",
        "correlation": dict(CORRELATION),
        "emitted_at": "2026-08-06T07:15:00Z",
        "authorization_ref": authorization_ref,
        "idempotency_key": "api-candidate:test:0001",
        "operation": {
            "capability_id": capability_id,
            "input": {"target_ref": "lab://conformance"},
        },
        "timeout_budget": {
            "soft_timeout_ms": 1000,
            "hard_timeout_ms": 5000,
        },
        "retry_policy": {
            "max_attempts": 2,
            "retryable_error_codes": [
                "TRANSIENT_DEPENDENCY",
                "RUNNER_UNAVAILABLE",
            ],
        },
        "cancellation_policy": {
            "mode": "cooperative_then_force",
            "grace_period_ms": 500,
        },
        "progress_mode": "optional",
    }


def _candidate_command() -> list[str]:
    return [sys.executable, str(CANDIDATE_PATH), "--conformance-only"]


def test_candidate_passes_vendor_neutral_conformance_kit() -> None:
    report = run_conformance(_candidate_command(), "api-runner-candidate")
    assert report["verdict"] == "PASS", report
    assert {case["status"] for case in report["cases"]} == {"PASS"}


def test_candidate_requires_explicit_conformance_mode() -> None:
    completed = subprocess.run(
        [sys.executable, str(CANDIDATE_PATH)],
        input="",
        text=True,
        capture_output=True,
        check=False,
    )
    assert completed.returncode == 2
    assert "--conformance-only is required" in completed.stderr


def test_candidate_refuses_non_conformance_capability_without_effect() -> None:
    candidate = ApiRunnerProtocolCandidate()
    request = _request("api.http.get")
    response = candidate.dispatch(request)

    assert candidate.effect_count == 0
    assert candidate.stats()["stats"]["ledger_entries"] == 0
    assert len(response["messages"]) == 1
    outcome = response["messages"][0]
    validate_semantics(outcome)
    assert outcome["status"] == "REFUSED"
    assert outcome["error"]["code"] == "UNSUPPORTED_CAPABILITY"
    assert outcome["error"]["retryable"] is False


def test_candidate_refuses_non_synthetic_authorization() -> None:
    candidate = ApiRunnerProtocolCandidate()
    response = candidate.dispatch(
        _request("conformance.effect.success", authorization_ref="authz/customer/real")
    )
    outcome = response["messages"][0]
    validate_semantics(outcome)
    assert outcome["status"] == "REFUSED"
    assert outcome["error"]["code"] == "AUTHORIZATION_DENIED"
    assert candidate.effect_count == 0


def test_candidate_has_no_legacy_execution_imports_or_calls() -> None:
    source = CANDIDATE_PATH.read_text(encoding="utf-8")
    forbidden = (
        "ProcessBridgeAdapter",
        "execute_runbook",
        "execute_command",
        "subprocess",
        "socket",
        "urllib",
        "requests",
    )
    for token in forbidden:
        assert token not in source


def test_candidate_uses_only_in_memory_state() -> None:
    candidate = ApiRunnerProtocolCandidate()
    assert isinstance(candidate.ledger, dict)
    assert isinstance(candidate.pending, dict)
    source = CANDIDATE_PATH.read_text(encoding="utf-8")
    assert "open(" not in source
    assert "write_text(" not in source
    assert "sqlite" not in source.lower()


def test_invalid_control_action_is_fail_closed() -> None:
    candidate = ApiRunnerProtocolCandidate()
    assert candidate.handle_control({"action": "execute"}) == {
        "transport_error": "unsupported conformance action"
    }


def test_dispatch_rejects_non_request_message() -> None:
    candidate = ApiRunnerProtocolCandidate()
    with pytest.raises(Exception):
        candidate.dispatch(
            {
                "message_type": "runner.progress",
                "protocol_version": "2.0.0",
                "correlation": dict(CORRELATION),
                "emitted_at": "2026-08-06T07:15:00Z",
                "sequence": 1,
                "state": "accepted",
            }
        )
