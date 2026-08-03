from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from typing import Any, Protocol

from .policy import authorise


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
) -> list[dict[str, Any]]:
    authorise(runbook, target, policy)
    context = {"target": target}
    results: list[dict[str, Any]] = []
    for step in runbook["steps"]:
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
        }
        results.append(adapter.invoke(request))
    return results
