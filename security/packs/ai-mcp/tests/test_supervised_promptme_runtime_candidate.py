from __future__ import annotations

import importlib
import json
import sys
from pathlib import Path
from typing import Any

import pytest

PACK_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = PACK_ROOT.parents[2]
PACK_SRC = PACK_ROOT / "src"
SDK_SRC = REPO_ROOT / "platform" / "runner-protocol" / "src"
for source in (PACK_SRC, SDK_SRC):
    if str(source) not in sys.path:
        sys.path.insert(0, str(source))

from ai_mcp_runbooks.execution import HttpResponse  # noqa: E402
from runner_protocol_v2 import (  # noqa: E402
    SQLiteIdempotencyLedger,
    SupervisionUnavailableError,
    validate_semantics,
)

MODULE = PACK_SRC / "ai_mcp_runbooks" / "supervised_promptme_runtime_adapter.py"
WORKER_MODULE = "ai_mcp_runbooks.supervised_promptme_runtime_worker"
RESULT_WORKER = Path(__file__).parent / "fixtures" / "supervised_runtime_result_worker.py"
HANG_WORKER = Path(__file__).parent / "fixtures" / "supervised_runtime_hang_worker.py"
LIVE_BASE_URL = "http://127.0.0.1:8210"
CORRELATION = {
    "campaign_id": "11111111-1111-4111-8111-111111111111",
    "run_id": "22222222-2222-4222-8222-222222222222",
    "step_id": "33333333-3333-4333-8333-333333333333",
    "attempt_id": "44444444-4444-4444-8444-444444444444",
}


def _request(*, key: str = "idem:ai-mcp:supervised:0001", hard_timeout_ms: int = 2000,
             target_ref: str = "promptme", base_url: str = LIVE_BASE_URL) -> dict[str, Any]:
    message = {
        "message_type": "runner.step.request",
        "protocol_version": "2.0.0",
        "correlation": dict(CORRELATION),
        "emitted_at": "2026-08-23T04:30:00Z",
        "authorization_ref": "authz/test-only/promptme-supervised",
        "idempotency_key": key,
        "operation": {
            "capability_id": "ai-mcp.runtime.handler-invoke",
            "input": {
                "schema_version": 1,
                "provider": "agent",
                "action": "conversation-test",
                "profile": "promptme-direct-injection",
                "target_ref": target_ref,
                "scope": "laboratory",
                "arguments": {"base_url": base_url},
            },
        },
        "timeout_budget": {"soft_timeout_ms": 100, "hard_timeout_ms": hard_timeout_ms},
        "retry_policy": {"max_attempts": 1, "retryable_error_codes": []},
        "cancellation_policy": {"mode": "cooperative_then_force", "grace_period_ms": 50},
    }
    validate_semantics(message)
    return message


def _candidate_class():
    assert MODULE.exists(), "supervised PromptMe runtime candidate is not implemented yet"
    module = importlib.import_module("ai_mcp_runbooks.supervised_promptme_runtime_adapter")
    return module.SupervisedPromptMeAiMcpRunnerCandidate


def _outcome(response: dict[str, Any]) -> dict[str, Any]:
    messages = response.get("messages")
    assert isinstance(messages, list)
    terminal = next(item for item in messages if item.get("message_type") == "runner.outcome")
    validate_semantics(terminal)
    return terminal


class MemoryTransport:
    def request(self, url: str, method: str = "GET", payload: Any = None, timeout: int = 10):
        if url.endswith("/health"):
            return HttpResponse(url, 200, json.dumps({"status": "ok", "lab": "promptme", "mode": "prompt"}))
        if url.endswith("/api/meta"):
            return HttpResponse(url, 200, json.dumps({"lab": "promptme", "mode": "prompt", "real_secrets": False}))
        if url.endswith("/api/chat"):
            prompt = str((payload or {}).get("prompt", ""))
            detected = "ignore previous" in prompt.lower()
            body = {
                "injection_detected": detected,
                "vulnerable_response": "PROMPTME_SYNTHETIC_MARKER" if detected else "clean",
                "real_secret_present": False,
            }
            return HttpResponse(url, 200, json.dumps(body))
        return HttpResponse(url, 404, json.dumps({"error": "not found"}))


def test_fixed_worker_executes_calibrated_dispatch_and_sanitizes() -> None:
    worker = importlib.import_module(WORKER_MODULE)
    result = worker.execute_fixed_promptme(transport=MemoryTransport())
    assert result["status"] == "ok"
    assert result["decision"] == "vulnerable"
    serialized = json.dumps(result, sort_keys=True)
    assert "PROMPTME_SYNTHETIC_MARKER" not in serialized
    assert "ignore previous" not in serialized


def test_supervised_candidate_success_and_durable_replay(tmp_path: Path) -> None:
    candidate_class = _candidate_class()
    ledger_path = tmp_path / "runtime.sqlite3"
    request = _request()
    candidate = candidate_class(
        durable_ledger=SQLiteIdempotencyLedger(ledger_path),
        working_directory=tmp_path,
        worker_path=RESULT_WORKER,
    )
    first = _outcome(candidate.dispatch(request))
    assert first["status"] == "PASS"
    assert first["output"]["runtime_status"] == "ok"
    assert first["output"]["runtime_decision"] == "vulnerable"
    assert first["output"]["supervision"]["status"] == "EXITED"
    assert candidate.effect_count == 1

    replay_request = json.loads(json.dumps(request))
    replay_request["correlation"]["attempt_id"] = "55555555-5555-4555-8555-555555555555"
    replay_request["emitted_at"] = "2026-08-23T04:30:01Z"
    restarted = candidate_class(
        durable_ledger=SQLiteIdempotencyLedger(ledger_path),
        working_directory=tmp_path,
        worker_path=RESULT_WORKER,
    )
    replay = _outcome(restarted.dispatch(replay_request))
    assert replay["status"] == "PASS"
    assert replay["output"] == first["output"]
    assert restarted.effect_count == 0
    assert restarted.stats()["ledger_entries"] == 1


def test_hard_timeout_is_terminal_and_replays_without_second_spawn(tmp_path: Path) -> None:
    candidate_class = _candidate_class()
    ledger_path = tmp_path / "timeout.sqlite3"
    request = _request(key="idem:ai-mcp:supervised:timeout", hard_timeout_ms=250)
    candidate = candidate_class(
        durable_ledger=SQLiteIdempotencyLedger(ledger_path),
        working_directory=tmp_path,
        worker_path=HANG_WORKER,
    )
    timed_out = _outcome(candidate.dispatch(request))
    assert timed_out["status"] == "TIMED_OUT"
    assert timed_out["error"]["code"] == "TIMEOUT_HARD"
    assert timed_out["output"]["supervision"]["status"] == "TIMED_OUT"
    assert candidate.effect_count == 1

    restarted = candidate_class(
        durable_ledger=SQLiteIdempotencyLedger(ledger_path),
        working_directory=tmp_path,
        worker_path=HANG_WORKER,
    )
    replay = _outcome(restarted.dispatch(request))
    assert replay["status"] == "TIMED_OUT"
    assert restarted.effect_count == 0


@pytest.mark.parametrize(
    ("target_ref", "base_url"),
    [("llmforge", LIVE_BASE_URL), ("promptme", "http://target:8080")],
)
def test_fixed_lab_boundary_refuses_request_variation_before_effect(
    tmp_path: Path, target_ref: str, base_url: str
) -> None:
    candidate_class = _candidate_class()
    ledger = SQLiteIdempotencyLedger(tmp_path / "refusal.sqlite3")
    candidate = candidate_class(
        durable_ledger=ledger,
        working_directory=tmp_path,
        worker_path=RESULT_WORKER,
    )
    outcome = _outcome(candidate.dispatch(_request(target_ref=target_ref, base_url=base_url)))
    assert outcome["status"] == "REFUSED"
    assert candidate.effect_count == 0
    assert candidate.stats()["ledger_entries"] == 0


def test_candidate_source_has_no_shell_or_request_controlled_command_surface() -> None:
    assert MODULE.is_file(), "supervised runtime candidate is missing"
    source = MODULE.read_text(encoding="utf-8")
    assert "subprocess" not in source
    assert "shell=True" not in source
    assert "operation.input['argv']" not in source
    assert 'operation.input["argv"]' not in source
    assert "request.get('argv')" not in source
    assert 'request.get("argv")' not in source


class UnavailableSupervisor:
    def run(self, _spec):
        raise SupervisionUnavailableError("synthetic unavailable detail must not escape")


def test_supervisor_unavailable_fails_closed_after_claim(tmp_path: Path) -> None:
    candidate_class = _candidate_class()
    candidate = candidate_class(
        durable_ledger=SQLiteIdempotencyLedger(tmp_path / "unavailable.sqlite3"),
        working_directory=tmp_path,
        worker_path=RESULT_WORKER,
        supervisor=UnavailableSupervisor(),
    )
    outcome = _outcome(candidate.dispatch(_request(key="idem:ai-mcp:supervised:unavailable")))
    assert outcome["status"] == "INCONCLUSIVE"
    assert outcome["error"]["code"] == "INTERNAL_ERROR"
    assert "synthetic unavailable detail" not in json.dumps(outcome)
    assert candidate.effect_count == 0
    assert candidate.stats()["ledger_entries"] == 1
