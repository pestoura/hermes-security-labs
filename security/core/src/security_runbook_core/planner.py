from __future__ import annotations

from typing import Any


def select_runbooks(
    runbooks: list[dict[str, Any]], target: dict[str, Any], policy: dict[str, Any]
) -> list[dict[str, Any]]:
    selected: list[dict[str, Any]] = []
    target_type = target["type"]
    capabilities = set(target.get("capabilities", []))
    for runbook in runbooks:
        selectors = runbook["selectors"]
        if target_type not in selectors["target_types"]:
            continue
        if not set(selectors["capabilities"]).issubset(capabilities):
            continue
        if policy.get("production_mode") and not runbook["risk"]["production_safe"]:
            continue
        selected.append(runbook)
    return selected
