import pytest

from security_runbook_core.executor import DryRunAdapter, execute_runbook
from security_runbook_core.policy import PolicyViolation

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


def test_dry_run_is_typed() -> None:
    policy = {
        "allowed_targets": ["lab"],
        "allowed_providers": ["test"],
        "allow_destructive": False,
        "max_actions_per_runbook": 10,
    }
    result = execute_runbook(RUNBOOK, {"ref": "lab"}, policy, DryRunAdapter())
    assert result[0]["request"]["arguments"]["target_ref"] == "lab"


def test_scope_is_enforced() -> None:
    policy = {
        "allowed_targets": [],
        "allowed_providers": ["test"],
        "allow_destructive": False,
        "max_actions_per_runbook": 10,
    }
    with pytest.raises(PolicyViolation):
        execute_runbook(RUNBOOK, {"ref": "lab"}, policy, DryRunAdapter())
