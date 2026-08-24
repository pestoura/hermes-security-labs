from __future__ import annotations

import importlib
from dataclasses import replace
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

from runner_protocol_v2 import (  # noqa: E402
    SQLiteIdempotencyLedger,
    SupervisedProcessResult,
    validate_semantics,
)

HANG_WORKER = Path(__file__).parent / "fixtures" / "supervised_runtime_hang_worker.py"
RESULT_WORKER = Path(__file__).parent / "fixtures" / "supervised_runtime_result_worker.py"
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


class BlockingClaimLedger:
    def __init__(self, delegate: SQLiteIdempotencyLedger) -> None:
        self.delegate = delegate
        self.claim_entered = threading.Event()
        self.release_claim = threading.Event()

    def claim(self, key: str, fingerprint: str):
        self.claim_entered.set()
        if not self.release_claim.wait(2):
            raise AssertionError("test did not release blocked ledger claim")
        return self.delegate.claim(key, fingerprint)

    def complete(self, key: str, fingerprint: str, outcome: dict[str, Any]):
        return self.delegate.complete(key, fingerprint, outcome)

    def count(self) -> int:
        return self.delegate.count()

def test_cancellation_cannot_be_lost_between_durable_claim_and_pending_publication(
    tmp_path: Path,
) -> None:
    module = importlib.import_module("ai_mcp_runbooks.supervised_promptme_runtime_adapter")
    ledger = BlockingClaimLedger(SQLiteIdempotencyLedger(tmp_path / "claim-race.sqlite3"))
    candidate = module.SupervisedPromptMeAiMcpRunnerCandidate(
        durable_ledger=ledger,
        working_directory=tmp_path,
        worker_path=HANG_WORKER,
    )
    request = _request(key="idem:ai-mcp:cancellation:claim-race")
    dispatch_box: dict[str, Any] = {}
    cancel_box: dict[str, Any] = {}
    dispatch_thread = threading.Thread(
        target=lambda: dispatch_box.setdefault("response", candidate.dispatch(request)),
        daemon=False,
    )
    dispatch_thread.start()
    assert ledger.claim_entered.wait(1), "dispatch did not enter durable claim"
    cancel_thread = threading.Thread(
        target=lambda: cancel_box.setdefault(
            "response", candidate.cancel(_cancellation_request())
        ),
        daemon=False,
    )
    cancel_thread.start()
    time.sleep(0.05)
    assert cancel_thread.is_alive(), (
        "cancellation returned before a successful durable claim could publish "
        "its cancellable pending execution"
    )

    ledger.release_claim.set()
    cancel_thread.join(timeout=3)
    dispatch_thread.join(timeout=3)
    assert not cancel_thread.is_alive()
    assert not dispatch_thread.is_alive()

    cancel_messages = cancel_box["response"]["messages"]
    assert cancel_messages[0]["message_type"] == "runner.cancellation.ack"
    assert cancel_messages[0]["status"] == "accepted"
    assert _terminal(cancel_box["response"])["status"] == "CANCELLED"
    assert _terminal(dispatch_box["response"])["status"] == "CANCELLED"
    assert candidate.stats()["active_processes"] == 0
    assert candidate.stats()["ledger_entries"] == 1


class DelayedCancellationSupervisor:
    def run(self, _spec, *, cancellation=None):
        assert cancellation is not None
        assert cancellation.wait(1), "test cancellation was not delivered"
        time.sleep(1.15)
        return SupervisedProcessResult(
            status="CANCELLED",
            returncode=None,
            stdout=b"",
            stderr=b"",
            stdout_truncated=False,
            stderr_truncated=False,
            force_killed=True,
            residue_cleaned=False,
            cleanup_failed=False,
            duration_ms=1_150,
            root_pid=12345,
        )

def test_accepted_cancellation_waits_long_enough_for_bounded_cleanup_terminal(
    tmp_path: Path,
) -> None:
    module = importlib.import_module("ai_mcp_runbooks.supervised_promptme_runtime_adapter")

    class ShortCleanupCandidate(module.SupervisedPromptMeAiMcpRunnerCandidate):
        def _spec(self, request: dict[str, Any]):
            return replace(
                super()._spec(request),
                termination_grace_ms=0,
                cleanup_timeout_ms=100,
            )

    candidate = ShortCleanupCandidate(
        durable_ledger=SQLiteIdempotencyLedger(tmp_path / "slow-cleanup.sqlite3"),
        working_directory=tmp_path,
        worker_path=HANG_WORKER,
        supervisor=DelayedCancellationSupervisor(),
    )
    request = _request(key="idem:ai-mcp:cancellation:bounded-cleanup")
    dispatch_box: dict[str, Any] = {}
    thread = threading.Thread(
        target=lambda: dispatch_box.setdefault("response", candidate.dispatch(request)),
        daemon=False,
    )
    thread.start()
    _wait_until_active(candidate)
    response = candidate.cancel(_cancellation_request())
    thread.join(timeout=2)
    assert not thread.is_alive()
    messages = response["messages"]
    assert [item["message_type"] for item in messages] == [
        "runner.cancellation.ack",
        "runner.outcome",
    ]
    assert messages[0]["status"] == "accepted"
    assert _terminal(response)["status"] == "CANCELLED"
    assert _terminal(dispatch_box["response"])["status"] == "CANCELLED"


class BlockingCompleteLedger:
    def __init__(self, delegate: SQLiteIdempotencyLedger) -> None:
        self.delegate = delegate
        self.complete_entered = threading.Event()
        self.release_complete = threading.Event()

    def claim(self, key: str, fingerprint: str):
        return self.delegate.claim(key, fingerprint)

    def complete(self, key: str, fingerprint: str, outcome: dict[str, Any]):
        self.complete_entered.set()
        if not self.release_complete.wait(2):
            raise AssertionError("test did not release blocked ledger completion")
        return self.delegate.complete(key, fingerprint, outcome)

    def count(self) -> int:
        return self.delegate.count()

def test_late_cancellation_during_terminal_commit_is_not_accepted(
    tmp_path: Path,
) -> None:
    module = importlib.import_module("ai_mcp_runbooks.supervised_promptme_runtime_adapter")
    ledger = BlockingCompleteLedger(SQLiteIdempotencyLedger(tmp_path / "late-cancel.sqlite3"))
    candidate = module.SupervisedPromptMeAiMcpRunnerCandidate(
        durable_ledger=ledger,
        working_directory=tmp_path,
        worker_path=RESULT_WORKER,
    )
    request = _request(key="idem:ai-mcp:cancellation:late")
    dispatch_box: dict[str, Any] = {}
    cancel_box: dict[str, Any] = {}
    dispatch_thread = threading.Thread(
        target=lambda: dispatch_box.setdefault("response", candidate.dispatch(request)),
        daemon=False,
    )
    dispatch_thread.start()
    assert ledger.complete_entered.wait(2), "dispatch did not reach durable terminal commit"

    cancel_thread = threading.Thread(
        target=lambda: cancel_box.setdefault(
            "response", candidate.cancel(_cancellation_request())
        ),
        daemon=False,
    )
    cancel_thread.start()
    time.sleep(0.05)
    ledger.release_complete.set()
    cancel_thread.join(timeout=2)
    dispatch_thread.join(timeout=2)
    assert not cancel_thread.is_alive()
    assert not dispatch_thread.is_alive()

    messages = cancel_box["response"]["messages"]
    assert len(messages) == 1
    assert messages[0]["message_type"] == "runner.cancellation.ack"
    assert messages[0]["status"] == "not_found"
    assert _terminal(dispatch_box["response"])["status"] == "PASS"
    assert candidate.stats() == {
        "effect_count": 1,
        "ledger_entries": 1,
        "active_processes": 0,
    }
