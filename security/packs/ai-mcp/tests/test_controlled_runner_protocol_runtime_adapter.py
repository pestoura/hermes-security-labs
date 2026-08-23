from __future__ import annotations

import copy
import importlib
import json
import sys
from pathlib import Path
from typing import Any

PACK_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = PACK_ROOT.parents[2]
SDK_SRC = REPO_ROOT / "platform" / "runner-protocol" / "src"
PACK_SRC = PACK_ROOT / "src"
for source in (SDK_SRC, PACK_SRC):
    if str(source) not in sys.path:
        sys.path.insert(0, str(source))

from ai_mcp_runbooks.dispatch import dispatch  # noqa: E402
from ai_mcp_runbooks.execution import HttpResponse  # noqa: E402
from ai_mcp_runbooks.runner_protocol_projection import CAPABILITY_ID  # noqa: E402
from runner_protocol_v2 import SQLiteIdempotencyLedger, validate_semantics  # noqa: E402

MODULE = PACK_SRC / "ai_mcp_runbooks" / "runtime_runner_protocol_adapter.py"
CORRELATION = {
    "campaign_id": "11111111-1111-4111-8111-111111111111",
    "run_id": "22222222-2222-4222-8222-222222222222",
    "step_id": "33333333-3333-4333-8333-333333333333",
    "attempt_id": "44444444-4444-4444-8444-444444444444",
}


def _request(*, action: str = "conversation-test", key: str = "idem:ai-mcp:runtime:0001") -> dict[str, Any]:
    message = {
        "message_type": "runner.step.request",
        "protocol_version": "2.0.0",
        "correlation": copy.deepcopy(CORRELATION),
        "emitted_at": "2026-08-23T01:30:00Z",
        "authorization_ref": "authz/campaign/ai-mcp-controlled",
        "idempotency_key": key,
        "operation": {
            "capability_id": CAPABILITY_ID,
            "input": {
                "schema_version": 1,
                "provider": "agent",
                "action": action,
                "profile": "promptme-direct-injection",
                "target_ref": "promptme",
                "scope": "laboratory",
                "control_id": "AIMCP-DIRECTPROMPTINJECTION-001",
                "arguments": {"base_url": "http://target:8080"},
            },
        },
        "timeout_budget": {"soft_timeout_ms": 1000, "hard_timeout_ms": 5000},
        "retry_policy": {"max_attempts": 1, "retryable_error_codes": []},
        "cancellation_policy": {"mode": "cooperative", "grace_period_ms": 500},
    }
    validate_semantics(message)
    return message


class MemoryTransport:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []

    def request(self, url: str, method: str = "GET", payload=None, timeout: int = 10):
        self.calls.append((method, url))
        if url.endswith("/health"):
            return HttpResponse(url, 200, json.dumps({"status": "ok", "lab": "promptme", "mode": "prompt"}))
        if url.endswith("/api/meta"):
            return HttpResponse(
                url,
                200,
                json.dumps({"lab": "promptme", "mode": "prompt", "real_secrets": False}),
            )
        if url.endswith("/api/chat"):
            prompt = (payload or {}).get("prompt", "")
            detected = any(
                token in prompt.lower()
                for token in ("ignore previous", "system override", "reveal", "exfiltrate")
            )
            return HttpResponse(
                url,
                200,
                json.dumps(
                    {
                        "injection_detected": detected,
                        "vulnerable_response": (
                            "SENSITIVE_SYNTHETIC_MARKER" if detected else "No override detected."
                        ),
                        "real_secret_present": False,
                    }
                ),
            )
        return HttpResponse(url, 404, "{}")


def _module():
    assert MODULE.exists(), "controlled runtime adapter is not implemented yet"
    importlib.invalidate_caches()
    return importlib.import_module("ai_mcp_runbooks.runtime_runner_protocol_adapter")


def _outcome(response: dict[str, Any]) -> dict[str, Any]:
    messages = response.get("messages")
    assert isinstance(messages, list), response
    terminal = next(
        message
        for message in messages
        if isinstance(message, dict) and message.get("message_type") == "runner.outcome"
    )
    validate_semantics(terminal)
    return terminal


def test_controlled_runtime_executes_real_dispatch_with_injected_transport_and_replays(tmp_path: Path) -> None:
    module = _module()
    transport = MemoryTransport()
    calls = 0

    def executor(payload: dict[str, Any]) -> dict[str, Any]:
        nonlocal calls
        calls += 1
        return dispatch(payload, transport=transport)

    database = tmp_path / "runtime.sqlite3"
    adapter = module.ControlledAiMcpRunnerProtocolAdapter(
        durable_ledger=SQLiteIdempotencyLedger(database),
        executor=executor,
    )
    request = _request()
    first = _outcome(adapter.dispatch(request))

    assert first["status"] == "PASS"
    assert first["output"]["runtime_status"] == "ok"
    assert first["output"]["runtime_decision"] == "vulnerable"
    assert adapter.effect_count == 1
    assert calls == 1
    assert len(transport.calls) >= 3
    serialized = json.dumps(first, sort_keys=True)
    assert "SENSITIVE_SYNTHETIC_MARKER" not in serialized

    restarted = module.ControlledAiMcpRunnerProtocolAdapter(
        durable_ledger=SQLiteIdempotencyLedger(database),
        executor=executor,
    )
    replay = _outcome(restarted.dispatch(copy.deepcopy(request)))
    assert replay["status"] == "PASS"
    assert replay["output"] == first["output"]
    assert replay["evidence_refs"] == first["evidence_refs"]
    assert calls == 1
    assert restarted.effect_count == 0


def test_missing_executor_refuses_before_ledger_claim(tmp_path: Path) -> None:
    module = _module()
    database = tmp_path / "disabled.sqlite3"
    ledger = SQLiteIdempotencyLedger(database)
    adapter = module.ControlledAiMcpRunnerProtocolAdapter(durable_ledger=ledger)

    outcome = _outcome(adapter.dispatch(_request(key="idem:ai-mcp:runtime:0002")))
    assert outcome["status"] == "REFUSED"
    assert outcome["error"]["code"] == "RUNNER_UNAVAILABLE"
    assert outcome["error"]["category"] == "compatibility"
    assert adapter.effect_count == 0
    assert ledger.count() == 0


def test_uncalibrated_handler_refuses_without_executor_or_ledger_effect(tmp_path: Path) -> None:
    module = _module()
    database = tmp_path / "uncalibrated.sqlite3"
    ledger = SQLiteIdempotencyLedger(database)
    called = False

    def executor(payload: dict[str, Any]) -> dict[str, Any]:
        nonlocal called
        called = True
        return dispatch(payload, transport=MemoryTransport())

    adapter = module.ControlledAiMcpRunnerProtocolAdapter(
        durable_ledger=ledger,
        executor=executor,
    )
    outcome = _outcome(adapter.dispatch(_request(action="discover", key="idem:ai-mcp:runtime:0003")))
    assert outcome["status"] == "REFUSED"
    assert outcome["error"]["code"] == "UNSUPPORTED_CAPABILITY"
    assert called is False
    assert adapter.effect_count == 0
    assert ledger.count() == 0


def test_executor_exception_is_normalized_and_durable(tmp_path: Path) -> None:
    module = _module()
    database = tmp_path / "error.sqlite3"
    calls = 0

    def executor(payload: dict[str, Any]) -> dict[str, Any]:
        nonlocal calls
        calls += 1
        raise RuntimeError("/secret/path TOKEN=never-return-this")

    adapter = module.ControlledAiMcpRunnerProtocolAdapter(
        durable_ledger=SQLiteIdempotencyLedger(database),
        executor=executor,
    )
    request = _request(key="idem:ai-mcp:runtime:0004")
    first = _outcome(adapter.dispatch(request))
    serialized = json.dumps(first, sort_keys=True)

    assert first["status"] == "ERROR"
    assert first["error"]["code"] == "EXECUTION_FAILED"
    assert "/secret/path" not in serialized
    assert "never-return-this" not in serialized
    assert calls == 1
    restarted = module.ControlledAiMcpRunnerProtocolAdapter(
        durable_ledger=SQLiteIdempotencyLedger(database),
        executor=executor,
    )
    replay = _outcome(restarted.dispatch(copy.deepcopy(request)))
    assert replay["status"] == "ERROR"
    assert replay["evidence_refs"] == first["evidence_refs"]
    assert calls == 1


def test_adapter_source_has_no_network_subprocess_or_default_runtime_executor() -> None:
    module = _module()
    source = MODULE.read_text(encoding="utf-8")
    assert "import subprocess" not in source
    assert "import urllib" not in source
    assert "import requests" not in source
    assert "CurlCommandTransport" not in source
    assert "LocalHttpTransport" not in source
    assert "from ai_mcp_runbooks.dispatch import dispatch" not in source
    assert module.DEFAULT_EXECUTOR is None


def test_idempotency_conflict_refuses_before_second_effect(tmp_path: Path) -> None:
    module = _module()
    calls = 0

    def executor(payload: dict[str, Any]) -> dict[str, Any]:
        nonlocal calls
        calls += 1
        return dispatch(payload, transport=MemoryTransport())

    adapter = module.ControlledAiMcpRunnerProtocolAdapter(
        durable_ledger=SQLiteIdempotencyLedger(tmp_path / "conflict.sqlite3"),
        executor=executor,
    )
    first = _request(key="idem:ai-mcp:runtime:0005")
    assert _outcome(adapter.dispatch(first))["status"] == "PASS"

    conflicting = copy.deepcopy(first)
    conflicting["operation"]["input"]["arguments"]["variant"] = "different"
    validate_semantics(conflicting)
    conflict = _outcome(adapter.dispatch(conflicting))
    assert conflict["status"] == "REFUSED"
    assert conflict["error"]["code"] == "IDEMPOTENCY_CONFLICT"
    assert calls == 1


def test_durable_completion_failure_returns_inconclusive_after_effect(tmp_path: Path) -> None:
    module = _module()
    backing = SQLiteIdempotencyLedger(tmp_path / "completion-fail.sqlite3")

    class FailingCompleteLedger:
        def claim(self, *args, **kwargs):
            return backing.claim(*args, **kwargs)

        def complete(self, *args, **kwargs):
            raise module.LedgerError("synthetic completion failure")

    adapter = module.ControlledAiMcpRunnerProtocolAdapter(
        durable_ledger=FailingCompleteLedger(),
        executor=lambda payload: dispatch(payload, transport=MemoryTransport()),
    )
    outcome = _outcome(
        adapter.dispatch(_request(key="idem:ai-mcp:runtime:0006"))
    )
    assert outcome["status"] == "INCONCLUSIVE"
    assert outcome["error"]["code"] == "INTERNAL_ERROR"
    assert outcome["evidence_refs"][0]["kind"] == "protocol"
    assert adapter.effect_count == 1
    assert backing.count() == 1
