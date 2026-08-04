"""Policy and contract tests for the DevSecOps pack."""

from __future__ import annotations

import pytest

from devsecops_runbooks.contracts import Decision, ExecutionRequest, ExecutionResult, Status
from devsecops_runbooks.policy import (
    ALLOWED_HANDLERS,
    PolicyViolation,
    authorise_request,
    is_implemented_handler,
)


def make_payload(**overrides):
    payload = {
        "schema_version": 1,
        "provider": "secrets",
        "action": "scan",
        "profile": "wrongsecrets-exposure",
        "target_ref": "wrongsecrets",
        "scope": "laboratory",
        "control_id": "DEVSEC-SECRETS-002",
        "arguments": {"base_url": "http://wrongsecrets:8080"},
    }
    payload.update(overrides)
    return payload


def test_request_parses_valid_payload():
    request = ExecutionRequest.from_payload(make_payload())
    assert request.handler == ("secrets", "scan")
    assert request.target_ref == "wrongsecrets"
    assert request.scope == "laboratory"
    assert request.control_id == "DEVSEC-SECRETS-002"


def test_request_accepts_target_and_scope_from_arguments():
    payload = make_payload()
    del payload["target_ref"]
    del payload["scope"]
    payload["arguments"] = {"target_ref": "wrongsecrets", "scope": "laboratory"}
    request = ExecutionRequest.from_payload(payload)
    assert request.target_ref == "wrongsecrets"


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
        authorise_request(request, {"allowed_targets": ["cicd-goat"]})
    with pytest.raises(PolicyViolation, match="execution policy"):
        authorise_request(request, {"allowed_providers": ["iac"]})


def test_secrets_scan_is_the_calibrated_handler():
    assert is_implemented_handler("secrets", "scan") is True
    uncalibrated = [pair for pair, done in ALLOWED_HANDLERS.items() if not done]
    assert uncalibrated, "catalogue must still declare uncalibrated handlers explicitly"
    for provider, action in uncalibrated:
        assert is_implemented_handler(provider, action) is False


def test_error_result_is_explicit_and_inconclusive():
    result = ExecutionResult.error("boom")
    assert result.status is Status.ERROR
    assert result.decision is Decision.INCONCLUSIVE
    assert result.to_dict()["reason"] == "boom"
