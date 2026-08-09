from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from typing import Any, Protocol

from .policy import authorise
from .target_authorization import (
    AuthorizationRequired,
    DenyAllAuthorizer,
    TargetAuthorizationDecision,
    TargetAuthorizer,
    authorize_steps,
)


class Adapter(Protocol):
    def invoke(self, request: dict[str, Any]) -> dict[str, Any]: ...


@dataclass
class DryRunAdapter:
    def invoke(self, request: dict[str, Any]) -> dict[str, Any]:
        return {"status": "dry-run", "request": request}


def _render(value: Any, context: dict[str, Any]) -> Any:
    if isinstance(value, dict):
        return {key: _render(item, context) for key, item in value.items()}
    if isinstance(value, list):
        return [_render(item, context) for item in value]
    if isinstance(value, str) and value.startswith("{{") and value.endswith("}}"):
        current: Any = context
        for part in value[2:-2].strip().split("."):
            current = current[part]
        return current
    return value


def execute_runbook(
    runbook: dict[str, Any],
    target: dict[str, Any],
    policy: dict[str, Any],
    adapter: Adapter,
    *,
    authorizer: TargetAuthorizer | None = None,
) -> list[dict[str, Any]]:
    """Execute a runbook after a fail-closed target authorization pass.

    Authorization happens at the semantic execution boundary: every step is
    resolved and authorized against the canonical ``target_id`` BEFORE the
    adapter is invoked even once. When ``authorizer`` is omitted the default
    :class:`DenyAllAuthorizer` denies deterministically, so an unwired caller
    can never dispatch an offensive step.
    """

    authorise(runbook, target, policy)
    decisions = authorize_steps(
        runbook["steps"],
        target,
        authorizer if authorizer is not None else DenyAllAuthorizer(),
    )
    context = {"target": target}
    results: list[dict[str, Any]] = []
    for step, decision in zip(runbook["steps"], decisions, strict=True):
        request = {
            "schema_version": 1,
            "runbook_id": runbook["metadata"]["id"],
            "step_id": step["id"],
            "provider": step["provider"],
            "action": step["action"],
            "profile": step["profile"],
            "arguments": _render(deepcopy(step["arguments"]), context),
            "limits": {
                "max_actions": runbook["risk"]["max_actions"],
                "timeout_seconds": runbook["risk"]["timeout_seconds"],
            },
            "authorization": decision.as_dict(),
        }
        results.append(adapter.invoke(request))
    return results


__all__ = [
    "Adapter",
    "AuthorizationRequired",
    "DryRunAdapter",
    "TargetAuthorizationDecision",
    "execute_runbook",
]
