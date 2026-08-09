import pytest

from security_runbook_core.executor import DryRunAdapter, execute_runbook
from security_runbook_core.policy import PolicyViolation
from security_runbook_core.target_authorization import (
    AuthorizationRequired,
    TargetAuthorizationDecision,
)

RUNBOOK = {
    "metadata": {"id": "TEST-001"},
    "risk": {"destructive": False, "max_actions": 1, "timeout_seconds": 10},
    "steps": [
        {
            "id": "primary",
            "provider": "test",
            "action": "inspect",
            "profile": "baseline",
            "arguments": {"target_ref": "{{ target.ref }}"},
        }
    ],
}

TARGET = {"ref": "lab", "target_id": "lab-target"}

POLICY = {
    "allowed_targets": ["lab"],
    "allowed_providers": ["test"],
    "allow_destructive": False,
    "max_actions_per_runbook": 10,
}


class AllowAuthorizer:
    def authorize(self, target_id, operation_id, *, operation_class="OFFENSIVE"):
        return TargetAuthorizationDecision(
            target_id=target_id,
            operation_id=operation_id,
            allowed=True,
            reason_code="ALLOW_OFFENSIVE_OPERATION",
            operation_class=operation_class,
        )


def test_dry_run_is_typed() -> None:
    result = execute_runbook(RUNBOOK, TARGET, POLICY, DryRunAdapter(), authorizer=AllowAuthorizer())
    assert result[0]["request"]["arguments"]["target_ref"] == "lab"
    assert result[0]["request"]["authorization"]["allowed"] is True
    assert result[0]["request"]["authorization"]["target_id"] == "lab-target"


def test_scope_is_enforced() -> None:
    policy = dict(POLICY, allowed_targets=[])
    with pytest.raises(PolicyViolation):
        execute_runbook(RUNBOOK, TARGET, policy, DryRunAdapter(), authorizer=AllowAuthorizer())


def test_execution_is_denied_without_an_authorizer() -> None:
    with pytest.raises(AuthorizationRequired):
        execute_runbook(RUNBOOK, TARGET, POLICY, DryRunAdapter())
