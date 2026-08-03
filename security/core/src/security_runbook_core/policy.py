from __future__ import annotations

from typing import Any


class PolicyViolation(RuntimeError):
    """Raised when execution violates the selected policy."""


def authorise(runbook: dict[str, Any], target: dict[str, Any], policy: dict[str, Any]) -> None:
    if target["ref"] not in policy["allowed_targets"]:
        raise PolicyViolation(f"target {target['ref']!r} is not allowlisted")
    risk = runbook["risk"]
    if risk["destructive"] and not policy.get("allow_destructive", False):
        raise PolicyViolation("destructive runbook blocked")
    allowed = set(policy["allowed_providers"])
    for step in runbook["steps"]:
        if step["provider"] not in allowed:
            raise PolicyViolation(f"provider {step['provider']!r} is not allowed")
    if risk["max_actions"] > policy["max_actions_per_runbook"]:
        raise PolicyViolation("runbook action budget exceeds policy")
