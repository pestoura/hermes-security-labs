from __future__ import annotations

import importlib
import json
import sys
import threading
import time
from pathlib import Path
from typing import Any

PACK_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = PACK_ROOT.parents[2]
PACK_SRC = PACK_ROOT / "src"
SDK_SRC = REPO_ROOT / "platform" / "runner-protocol" / "src"
for source in (PACK_SRC, SDK_SRC):
    if str(source) not in sys.path:
        sys.path.insert(0, str(source))

from runner_protocol_v2 import SQLiteIdempotencyLedger, validate_semantics  # noqa: E402

HANG_WORKER = Path(__file__).parent / "fixtures" / "supervised_runtime_hang_worker.py"
LIVE_BASE_URL = "http://127.0.0.1:8210"
CORRELATION = {
    "campaign_id": "11111111-1111-4111-8111-111111111111",
    "run_id": "22222222-2222-4222-8222-222222222222",
    "step_id": "33333333-3333-4333-8333-333333333333",
    "attempt_id": "44444444-4444-4444-8444-444444444444",
}


def _request(*, key: str = "idem:ai-mcp:cancellation:0001") -> dict[str, Any]:
    message = {
        "message_type": "runner.step.request",
        "protocol_version": "2.0.0",
        "correlation": dict(CORRELATION),
        "emitted_at": "2026-08-24T09:00:00Z",
        "authorization_ref": "authz/test-only/promptme-cancellation",
        "idempotency_key": key,
        "operation": {
            "capability_id": "ai-mcp.runtime.handler-invoke",
            "input": {
                "schema_version": 1,
                "provider": "agent",
                "action": "conversation-test",
                "profile": "promptme-direct-injection",
                "target_ref": "promptme",
                "scope": "laboratory",
                "arguments": {"base_url": LIVE_BASE_URL},
            },
        },
        "timeout_budget": {"soft_timeout_ms": 100, "hard_timeout_ms": 5_000},
        "retry_policy": {"max_attempts": 1, "retryable_error_codes": []},
        "cancellation_policy": {"mode": "cooperative_then_force", "grace_period_ms": 50},
    }
    validate_semantics(message)
    return message


def _cancellation_request(correlation: dict[str, str] | None = None) -> dict[str, Any]:
    message = {
        "message_type": "runner.cancellation.request",
        "protocol_version": "2.0.0",
        "correlation": dict(correlation or CORRELATION),
        "emitted_at": "2026-08-24T09:00:01Z",
        "reason": "operator",
        "requested_by": "gateway",
    }
    validate_semantics(message)
    return message


def _candidate(tmp_path: Path):
    module = importlib.import_module("ai_mcp_runbooks.supervised_promptme_runtime_adapter")
    return module.SupervisedPromptMeAiMcpRunnerCandidate(
        durable_ledger=SQLiteIdempotencyLedger(tmp_path / "cancellation.sqlite3"),
        working_directory=tmp_path,
        worker_path=HANG_WORKER,
    )


def _terminal(response: dict[str, Any]) -> dict[str, Any]:
    messages = response.get("messages")
    assert isinstance(messages, list)
    terminal = next(item for item in messages if item.get("message_type") == "runner.outcome")
    validate_semantics(terminal)
    return terminal


def _wait_until_active(candidate: Any, timeout_seconds: float = 2.0) -> None:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        if candidate.stats().get("active_processes") == 1:
            return
        time.sleep(0.01)
    raise AssertionError("supervised PromptMe process did not become cancellable")


def test_runner_cancellation_request_stops_active_supervised_process_and_persists_terminal(
    tmp_path: Path,
) -> None:
    candidate = _candidate(tmp_path)
    assert hasattr(candidate, "cancel"), "PromptMe candidate does not handle runner.cancellation.request"

    request = _request()
    result_box: dict[str, Any] = {}
    thread = threading.Thread(
        target=lambda: result_box.setdefault("dispatch", candidate.dispatch(request)),
        name="chg097-promptme-dispatch",
        daemon=False,
    )
    thread.start()
    _wait_until_active(candidate)

    cancellation = candidate.cancel(_cancellation_request())
    thread.join(timeout=3)
    assert not thread.is_alive(), "cancel must complete the supervised process within bounded cleanup"

    messages = cancellation.get("messages")
    assert isinstance(messages, list)
    ack = next(item for item in messages if item.get("message_type") == "runner.cancellation.ack")
    terminal = next(item for item in messages if item.get("message_type") == "runner.outcome")
    validate_semantics(ack)
    validate_semantics(terminal)
    assert ack["status"] == "accepted"
    assert terminal["status"] == "CANCELLED"
    assert terminal["error"]["code"] == "CANCELLED"
    assert terminal["output"]["supervision"]["status"] == "CANCELLED"
    assert terminal["output"]["supervision"]["force_killed"] is True

    dispatch_terminal = _terminal(result_box["dispatch"])
    assert dispatch_terminal["status"] == "CANCELLED"
    assert candidate.stats() == {
        "effect_count": 1,
        "ledger_entries": 1,
        "active_processes": 0,
    }

    restarted = _candidate(tmp_path)
    replay = _terminal(restarted.dispatch(request))
    assert replay["status"] == "CANCELLED"
    assert restarted.stats()["effect_count"] == 0
    assert restarted.stats()["ledger_entries"] == 1


def test_cancellation_for_unknown_correlation_is_acknowledged_not_found(tmp_path: Path) -> None:
    candidate = _candidate(tmp_path)
    assert hasattr(candidate, "cancel"), "PromptMe candidate does not handle runner.cancellation.request"
    unknown = dict(CORRELATION)
    unknown["attempt_id"] = "55555555-5555-4555-8555-555555555555"
    response = candidate.cancel(_cancellation_request(unknown))
    messages = response.get("messages")
    assert isinstance(messages, list) and len(messages) == 1
    ack = messages[0]
    validate_semantics(ack)
    assert ack["message_type"] == "runner.cancellation.ack"
    assert ack["status"] == "not_found"
    assert candidate.stats()["ledger_entries"] == 0
    assert candidate.stats()["effect_count"] == 0
