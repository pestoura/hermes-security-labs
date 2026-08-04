"""Policy and contract tests for the AI/MCP pack."""

from __future__ import annotations

import pytest

from ai_mcp_runbooks.contracts import Decision, ExecutionRequest, ExecutionResult, Status
from ai_mcp_runbooks.policy import (
    ALLOWED_HANDLERS,
    ALLOWED_TARGETS,
    PolicyViolation,
    authorise_request,
    is_implemented_handler,
)


def make_payload(**overrides):
    payload = {
        "schema_version": 1,
        "provider": "agent",
        "action": "conversation-test",
        "profile": "promptme-direct-injection",
        "target_ref": "promptme",
        "scope": "laboratory",
        "control_id": "AIMCP-DIRECTPROMPTINJECTION-001",
        "arguments": {"base_url": "http://target:8080"},
    }
    payload.update(overrides)
    return payload


def test_request_parses_valid_payload():
    request = ExecutionRequest.from_payload(make_payload())
    assert request.handler == ("agent", "conversation-test")
    assert request.target_ref == "promptme"
    assert request.scope == "laboratory"
    assert request.control_id == "AIMCP-DIRECTPROMPTINJECTION-001"


def test_request_accepts_target_and_scope_from_arguments():
    payload = make_payload()
    del payload["target_ref"]
    del payload["scope"]
    payload["arguments"] = {"target_ref": "promptme", "scope": "laboratory"}
    request = ExecutionRequest.from_payload(payload)
    assert request.target_ref == "promptme"
    assert request.scope == "laboratory"


@pytest.mark.parametrize(
    "payload",
    [
        "not-an-object",
        {},
        make_payload(provider=""),
        make_payload(action=None),
        make_payload(profile="   "),
        make_payload(schema_version=99),
    ],
)
def test_request_rejects_malformed_payloads(payload):
    with pytest.raises(ValueError):
        ExecutionRequest.from_payload(payload)


def test_request_rejects_non_object_arguments():
    with pytest.raises(ValueError):
        ExecutionRequest.from_payload(make_payload(arguments=["a"]))


def test_request_rejects_missing_target_and_scope():
    payload = make_payload()
    del payload["target_ref"]
    payload["arguments"] = {}
    with pytest.raises(ValueError, match="target_ref"):
        ExecutionRequest.from_payload(payload)


def test_authorise_accepts_calibrated_request():
    authorise_request(ExecutionRequest.from_payload(make_payload()))


def test_authorise_rejects_unknown_handler():
    request = ExecutionRequest.from_payload(make_payload(provider="shell", action="exec"))
    with pytest.raises(PolicyViolation, match="allowed catalogue"):
        authorise_request(request)


def test_authorise_rejects_invalid_scope():
    request = ExecutionRequest.from_payload(make_payload(scope="production"))
    with pytest.raises(PolicyViolation, match="scope"):
        authorise_request(request)


def test_authorise_rejects_target_outside_allowlist():
    request = ExecutionRequest.from_payload(make_payload(target_ref="example.com"))
    with pytest.raises(PolicyViolation, match="allowlist"):
        authorise_request(request)


def test_execution_policy_can_narrow_but_not_widen():
    request = ExecutionRequest.from_payload(make_payload())
    with pytest.raises(PolicyViolation, match="execution policy"):
        authorise_request(request, {"allowed_targets": ["llmforge"]})
    with pytest.raises(PolicyViolation, match="execution policy"):
        authorise_request(request, {"allowed_providers": ["mcp"]})


def test_payload_cannot_widen_the_target_allowlist():
    payload = make_payload(target_ref="attacker.example.com")
    payload["arguments"]["allowed_targets"] = ["attacker.example.com"]
    request = ExecutionRequest.from_payload(payload)
    with pytest.raises(PolicyViolation):
        authorise_request(request)
    assert "attacker.example.com" not in ALLOWED_TARGETS


def test_production_mode_is_refused():
    request = ExecutionRequest.from_payload(make_payload())
    with pytest.raises(PolicyViolation, match="production_mode"):
        authorise_request(request, {"production_mode": True})


def test_conversation_test_is_the_calibrated_handler():
    assert is_implemented_handler("agent", "conversation-test") is True
    uncalibrated = [pair for pair, done in ALLOWED_HANDLERS.items() if not done]
    assert uncalibrated, "catalogue must still declare uncalibrated handlers explicitly"
    for provider, action in uncalibrated:
        assert is_implemented_handler(provider, action) is False


def test_error_result_is_explicit_and_inconclusive():
    result = ExecutionResult.error("boom")
    assert result.status is Status.ERROR
    assert result.decision is Decision.INCONCLUSIVE
    assert result.to_dict()["reason"] == "boom"
