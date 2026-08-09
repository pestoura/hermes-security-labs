"""Negative controls for the core semantic execution boundary (Lane G).

Proves that the adapter (the thing that would touch a target) is never invoked
when the target authorization decision denies.
"""

from __future__ import annotations

from typing import Any

import pytest

from security_runbook_core.executor import execute_runbook
from security_runbook_core.target_authorization import (
    AuthorizationRequired,
    CallableAuthorizer,
    DenyAllAuthorizer,
    TargetAuthorizationDecision,
    authorize_steps,
    canonical_target_id,
    step_operation_id,
)

RUNBOOK = {
    "metadata": {"id": "TEST-001"},
    "risk": {"destructive": False, "max_actions": 1, "timeout_seconds": 10},
    "steps": [
        {
            "id": "primary",
            "provider": "test",
            "action": "web_vulnerability_scan",
            "profile": "baseline",
            "arguments": {"target_ref": "{{ target.ref }}"},
        }
    ],
}

POLICY = {
    "allowed_targets": ["lab"],
    "allowed_providers": ["test"],
    "allow_destructive": False,
    "max_actions_per_runbook": 10,
}

TARGET = {"ref": "lab", "target_id": "lab-target"}


class AdapterSpy:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def invoke(self, request: dict[str, Any]) -> dict[str, Any]:
        self.calls.append(request)
        return {"status": "invoked"}


class StaticAuthorizer:
    def __init__(self, allowed: bool, reason_code: str) -> None:
        self.allowed = allowed
        self.reason_code = reason_code
        self.seen: list[tuple[Any, Any, str]] = []

    def authorize(self, target_id, operation_id, *, operation_class="OFFENSIVE"):
        self.seen.append((target_id, operation_id, operation_class))
        return TargetAuthorizationDecision(
            target_id=target_id,
            operation_id=operation_id,
            allowed=self.allowed,
            reason_code=self.reason_code,
            operation_class=operation_class,
        )


# --------------------------------------------------------------------------
# adapter is never reached on denial
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "reason_code",
    [
        "AUTHORIZATION_STATE_DENIED",
        "TARGET_UNKNOWN",
        "TARGET_LIFECYCLE_RETIRED",
        "OPERATION_OUT_OF_SCOPE",
        "GENERIC_EXECUTION_FORBIDDEN",
    ],
)
def test_adapter_is_never_invoked_when_authorization_denies(reason_code: str) -> None:
    adapter = AdapterSpy()
    authorizer = StaticAuthorizer(allowed=False, reason_code=reason_code)
    with pytest.raises(AuthorizationRequired) as excinfo:
        execute_runbook(RUNBOOK, TARGET, POLICY, adapter, authorizer=authorizer)
    assert adapter.calls == []
    assert excinfo.value.decision.reason_code == reason_code


def test_default_authorizer_denies_and_never_invokes_the_adapter() -> None:
    adapter = AdapterSpy()
    with pytest.raises(AuthorizationRequired) as excinfo:
        execute_runbook(RUNBOOK, TARGET, POLICY, adapter)
    assert adapter.calls == []
    assert excinfo.value.decision.reason_code == "AUTHORIZER_NOT_CONFIGURED"


def test_target_without_canonical_target_id_denies_before_dispatch() -> None:
    adapter = AdapterSpy()
    authorizer = StaticAuthorizer(allowed=True, reason_code="ALLOW_OFFENSIVE_OPERATION")
    with pytest.raises(AuthorizationRequired) as excinfo:
        execute_runbook(
            RUNBOOK,
            {"ref": "lab"},
            POLICY,
            adapter,
            authorizer=authorizer,
        )
    assert adapter.calls == []
    assert authorizer.seen == []
    assert excinfo.value.decision.reason_code == "TARGET_ID_MISSING"


@pytest.mark.parametrize(
    "raw_target_id",
    ["http://lab-target:3000/", "10.0.0.5", "lab target", " lab-target", "lab-target/path"],
)
def test_raw_locators_are_never_an_execution_authority(raw_target_id: str) -> None:
    adapter = AdapterSpy()
    authorizer = StaticAuthorizer(allowed=True, reason_code="ALLOW_OFFENSIVE_OPERATION")
    with pytest.raises(AuthorizationRequired):
        execute_runbook(
            RUNBOOK,
            {"ref": "lab", "target_id": raw_target_id},
            POLICY,
            adapter,
            authorizer=authorizer,
        )
    assert adapter.calls == []
    assert authorizer.seen == []


def test_multi_step_runbook_authorizes_every_step_before_any_dispatch() -> None:
    runbook = {
        **RUNBOOK,
        "risk": {"destructive": False, "max_actions": 2, "timeout_seconds": 10},
        "steps": [
            RUNBOOK["steps"][0],
            {
                "id": "secondary",
                "provider": "test",
                "action": "manual_exploitation",
                "profile": "baseline",
                "arguments": {},
            },
        ],
    }

    class SecondStepDenies:
        def __init__(self) -> None:
            self.calls = 0

        def authorize(self, target_id, operation_id, *, operation_class="OFFENSIVE"):
            self.calls += 1
            allowed = operation_id == "web_vulnerability_scan"
            return TargetAuthorizationDecision(
                target_id=target_id,
                operation_id=operation_id,
                allowed=allowed,
                reason_code=(
                    "ALLOW_OFFENSIVE_OPERATION" if allowed else "OPERATION_OUT_OF_SCOPE"
                ),
                operation_class=operation_class,
            )

    adapter = AdapterSpy()
    authorizer = SecondStepDenies()
    with pytest.raises(AuthorizationRequired):
        execute_runbook(runbook, TARGET, POLICY, adapter, authorizer=authorizer)
    # The first step is allowed, but nothing is dispatched because the whole
    # runbook is authorized up front.
    assert adapter.calls == []
    assert authorizer.calls == 2


def test_step_without_typed_operation_denies() -> None:
    runbook = {
        **RUNBOOK,
        "steps": [{"id": "primary", "provider": "test", "profile": "baseline", "arguments": {}}],
    }
    adapter = AdapterSpy()
    with pytest.raises(AuthorizationRequired) as excinfo:
        execute_runbook(
            runbook,
            TARGET,
            POLICY,
            adapter,
            authorizer=StaticAuthorizer(True, "ALLOW_OFFENSIVE_OPERATION"),
        )
    assert adapter.calls == []
    assert excinfo.value.decision.reason_code == "OPERATION_ID_MISSING"


# --------------------------------------------------------------------------
# helpers and audit shape
# --------------------------------------------------------------------------


def test_canonical_target_id_rejects_locators() -> None:
    assert canonical_target_id({"target_id": "lab-target"}) == "lab-target"
    assert canonical_target_id("lab-target") == "lab-target"
    for bad in (None, "", "  ", "http://x/", "host:80", "a@b", "a b", {"ref": "lab"}):
        assert canonical_target_id(bad) is None


def test_step_operation_id_prefers_explicit_operation_id() -> None:
    assert step_operation_id({"operation_id": "web.discovery.headers", "action": "x"}) == (
        "web.discovery.headers"
    )
    assert step_operation_id({"action": "discovery"}) == "discovery"
    assert step_operation_id({}) is None


def test_deny_all_authorizer_is_the_safe_default() -> None:
    decision = DenyAllAuthorizer().authorize("lab-target", "discovery")
    assert decision.allowed is False
    assert decision.reason_code == "AUTHORIZER_NOT_CONFIGURED"


def test_callable_authorizer_fails_closed_on_a_malformed_response() -> None:
    authorizer = CallableAuthorizer(lambda *_a, **_k: object())
    decision = authorizer.authorize("lab-target", "discovery")
    assert decision.allowed is False
    assert decision.reason_code == "AUTHORIZER_RESPONSE_INVALID"


def test_callable_authorizer_accepts_a_platform_style_mapping() -> None:
    authorizer = CallableAuthorizer(
        lambda *_a, **_k: {
            "target_id": "lab-target",
            "operation_id": "discovery",
            "allowed": True,
            "reason_code": "ALLOW_OFFENSIVE_OPERATION",
        }
    )
    decision = authorizer.authorize("lab-target", "discovery")
    assert decision.allowed is True
    assert decision.as_dict()["reason_code"] == "ALLOW_OFFENSIVE_OPERATION"


def test_safety_operations_are_classified_as_safety() -> None:
    authorizer = StaticAuthorizer(allowed=True, reason_code="ALLOW_SAFETY_OPERATION")
    authorize_steps(
        [{"id": "teardown", "operation_id": "lab.lifecycle.destroy"}],
        TARGET,
        authorizer,
    )
    assert authorizer.seen[0][2] == "SAFETY"


def test_decision_payload_has_no_raw_locator() -> None:
    decision = TargetAuthorizationDecision(
        target_id="lab-target",
        operation_id="discovery",
        allowed=False,
        reason_code="AUTHORIZATION_STATE_DENIED",
    )
    payload = decision.as_dict()
    assert payload["allowed"] is False
    assert "://" not in str(payload)
