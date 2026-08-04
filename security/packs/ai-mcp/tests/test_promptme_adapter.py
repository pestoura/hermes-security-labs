"""PromptMe adapter tests against the interface exposed by the Phase 2 runtime.

The fake transport reproduces the documented contract of
``platform/runtime/phase2-safe-lab/server.py``:

* ``GET /health`` -> ``{"status": "ok", "lab": ..., "mode": ...}``
* ``GET /api/meta`` -> ``{..., "real_secrets": false}``
* ``POST /api/chat`` -> ``{"injection_detected": bool,
  "vulnerable_response": str, "real_secret_present": false}``

No network is used and no real laboratory is started.
"""

from __future__ import annotations

import json
import re

import pytest

from ai_mcp_runbooks.adapters.promptme import (
    CONTROL_TURNS,
    LABORATORY_ID,
    PromptMeAdapter,
    build_adapter,
)
from ai_mcp_runbooks.contracts import Decision, ExecutionRequest, Status
from ai_mcp_runbooks.dispatch import dispatch, sanitize_result
from ai_mcp_runbooks.execution import (
    CommandError,
    HttpResponse,
    LocalHttpTransport,
    RequestBudget,
    validate_base_url,
)

MARKER = "PROMPTME_SYNTHETIC_MARKER"
BASE_URL = "http://target:8080"


def make_request(**overrides) -> ExecutionRequest:
    payload = {
        "schema_version": 1,
        "provider": "agent",
        "action": "conversation-test",
        "profile": "promptme-direct-injection",
        "target_ref": "promptme",
        "scope": "laboratory",
        "control_id": "AIMCP-DIRECTPROMPTINJECTION-001",
        "arguments": {"base_url": BASE_URL},
    }
    payload.update(overrides)
    return ExecutionRequest.from_payload(payload)


class FakeTransport:
    """Deterministic stand-in for the Phase 2 safe-lab HTTP interface."""

    def __init__(self, vulnerable: bool = True, real_secrets: bool = False, chat_status: int = 200,
                 chat_body: dict | None = None, health_ok: bool = True):
        self.vulnerable = vulnerable
        self.real_secrets = real_secrets
        self.chat_status = chat_status
        self.chat_body = chat_body
        self.health_ok = health_ok
        self.calls: list[tuple[str, str]] = []

    def request(self, url, method="GET", payload=None, timeout=10):
        self.calls.append((method, url))
        if url.endswith("/health"):
            if not self.health_ok:
                return HttpResponse(url, None, "", error="ConnectionRefusedError")
            return HttpResponse(url, 200, json.dumps({"status": "ok", "lab": LABORATORY_ID, "mode": "prompt"}))
        if url.endswith("/api/meta"):
            return HttpResponse(
                url,
                200,
                json.dumps(
                    {
                        "lab": LABORATORY_ID,
                        "mode": "prompt",
                        "source_commit": "fd7676c",
                        "real_secrets": self.real_secrets,
                    }
                ),
            )
        if url.endswith("/api/chat"):
            if self.chat_body is not None:
                return HttpResponse(url, self.chat_status, json.dumps(self.chat_body))
            prompt = (payload or {}).get("prompt", "")
            detected = self.vulnerable and any(
                token in prompt.lower()
                for token in ("ignore previous", "system override", "reveal", "exfiltrate")
            )
            return HttpResponse(
                url,
                self.chat_status,
                json.dumps(
                    {
                        "injection_detected": detected,
                        "vulnerable_response": (
                            f"synthetic-marker={MARKER}" if detected else "No override detected."
                        ),
                        "real_secret_present": self.real_secrets,
                    }
                ),
            )
        return HttpResponse(url, 404, json.dumps({"error": "not found"}))


def run_adapter(transport) -> dict:
    adapter = PromptMeAdapter(transport=transport, base_url=BASE_URL)
    return sanitize_result(adapter.run(make_request()))


# -- controls -----------------------------------------------------------


def test_positive_control_detects_prompt_injection():
    document = run_adapter(FakeTransport(vulnerable=True))
    assert document["status"] == Status.OK.value
    assert document["decision"] == Decision.VULNERABLE.value
    assert "prompt_injection.override_accepted" in document["vulnerable_signals"]
    assert "prompt_injection.disclosure_channel_active" in document["vulnerable_signals"]
    assert "control.negative_clean" in document["secure_signals"]


def test_negative_control_proves_a_secure_response():
    document = run_adapter(FakeTransport(vulnerable=False))
    assert document["decision"] == Decision.SECURE.value
    assert "prompt_injection.override_rejected" in document["secure_signals"]
    assert document["vulnerable_signals"] == []


def test_negative_control_failure_is_inconclusive_not_vulnerable():
    """A runtime flagging the benign turn means the control is not calibrated."""

    body = {"injection_detected": True, "vulnerable_response": "x", "real_secret_present": False}
    document = run_adapter(FakeTransport(chat_body=body))
    assert document["decision"] == Decision.INCONCLUSIVE.value
    assert "control.negative_failed" in document["inconclusive_signals"]


def test_unreachable_target_is_inconclusive_with_explicit_cause():
    document = run_adapter(FakeTransport(health_ok=False))
    assert document["decision"] == Decision.INCONCLUSIVE.value
    assert "target.unreachable" in document["inconclusive_signals"]


def test_contract_mismatch_is_inconclusive():
    document = run_adapter(FakeTransport(chat_body={"unexpected": True}))
    assert document["decision"] == Decision.INCONCLUSIVE.value
    assert "chat.contract_mismatch" in document["inconclusive_signals"]


def test_real_secret_signal_aborts_the_control():
    document = run_adapter(FakeTransport(real_secrets=True))
    assert document["decision"] == Decision.INCONCLUSIVE.value
    assert "laboratory.unsafe_configuration" in document["inconclusive_signals"]


# -- sanitisation -------------------------------------------------------


def test_result_never_echoes_the_prompt_or_the_synthetic_marker():
    document = run_adapter(FakeTransport(vulnerable=True))
    serialised = json.dumps(document)
    for _, prompt, _ in CONTROL_TURNS:
        assert prompt not in serialised
    # distinctive fragments of the controlled turns must not leak either
    for fragment in ("ignore previous", "reveal", "summarise the runtime", "documentation"):
        assert fragment not in serialised.lower()
    assert MARKER not in serialised
    assert not re.search(r"(?i)synthetic[_-]?marker=", serialised)


def test_evidence_reports_only_structural_signals():
    document = run_adapter(FakeTransport(vulnerable=True))
    turn_evidence = [item for item in document["evidence"] if item["ref"].startswith("turn/")]
    assert len(turn_evidence) == len(CONTROL_TURNS)
    for item in turn_evidence:
        value = item["value"]
        assert value["real_material_flag"] is False
        assert set(value) >= {
            "turn_id",
            "injection_detected",
            "disclosure_present",
            "structural_fields_present",
            "matched_expectation",
            "turn_fingerprint",
        }
        assert isinstance(value["turn_fingerprint"], str)
        assert len(value["turn_fingerprint"]) == 12
        assert item["redacted"] is True


def test_output_is_deterministic():
    first = run_adapter(FakeTransport(vulnerable=True))
    second = run_adapter(FakeTransport(vulnerable=True))
    assert json.dumps(first, sort_keys=True) == json.dumps(second, sort_keys=True)


# -- transport policy ---------------------------------------------------


@pytest.mark.parametrize(
    "url",
    [
        "http://attacker.example.com:8080",
        "https://target:8080",
        "http://target:9999",
        "http://target:8080/?x=1",
        "file:///etc/passwd",
        "",
    ],
)
def test_transport_refuses_urls_outside_the_allowlist(url):
    with pytest.raises(CommandError):
        validate_base_url(url)


def test_transport_never_uses_a_shell():
    from ai_mcp_runbooks import execution

    source = (
        execution.__file__ and open(execution.__file__, encoding="utf-8").read()  # noqa: SIM115
    )
    assert "shell=True" not in source
    assert "shell=False" in source


def test_curl_argv_is_fixed_and_never_carries_the_prompt():
    from ai_mcp_runbooks.execution import CurlCommandTransport

    argv = CurlCommandTransport().build_argv(f"{BASE_URL}/api/chat", "POST", True)
    assert argv[0] == "curl"
    assert "--data-binary" in argv and "@-" in argv
    assert not any("ignore previous" in part.lower() for part in argv)


def test_request_budget_is_enforced():
    budget = RequestBudget(limit=1)
    budget.consume()
    with pytest.raises(CommandError, match="budget"):
        budget.consume()


def test_local_transport_is_the_default():
    adapter = build_adapter(make_request())
    assert isinstance(adapter, PromptMeAdapter)
    assert isinstance(adapter.transport, LocalHttpTransport)


# -- dispatch fallbacks -------------------------------------------------


def test_unknown_target_for_calibrated_handler_falls_back_by_name():
    request = make_request(target_ref="llmforge")
    with pytest.raises(NotImplementedError, match="llmforge"):
        build_adapter(request)


def test_dispatch_uncalibrated_provider_is_named_and_safe():
    payload = make_request(provider="rag", action="poison-test").to_dict()
    document = dispatch(payload)
    assert document["status"] == Status.NOT_IMPLEMENTED.value
    assert document["decision"] == Decision.INCONCLUSIVE.value
    assert "handler.not_calibrated" in document["inconclusive_signals"]


def test_dispatch_uses_the_injected_transport():
    payload = make_request().to_dict()
    transport = FakeTransport(vulnerable=True)
    document = dispatch(payload, transport=transport)
    assert document["decision"] == Decision.VULNERABLE.value
    assert transport.calls
    assert all(url.startswith(BASE_URL) for _, url in transport.calls)
