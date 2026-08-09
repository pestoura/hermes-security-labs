"""Canonical Lane F scenario + tool registry validator.

Read-only contract checks. The validator:
  * validates both registries against their JSON Schemas;
  * forbids generic_execution / command / shell / argv / cwd / script entries;
  * cross-references every scenario to a known environment_id and a registered,
    eligible target_id (target registry resolver, fail-closed);
  * cross-references every scenario semantic operation to the typed operation
    registry;
  * cross-references every scenario step.runbook_ref to a committed file;
  * cross-references every tool to exactly one typed semantic operation
    (UNMAPPED is explicit and flagged);
  * cross-references scenario_refs in tools back to scenarios;
  * asserts generic_execution is forbidden in both registries.

It does NOT execute anything. It does NOT write state. It returns a non-zero
exit code on the first batch of findings via pytest (assertions) and as a CLI.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from copy import deepcopy
from pathlib import Path
from typing import Any, Mapping

import jsonschema
import yaml

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
SCENARIO_DIR = HERE
TARGETS_DIR = ROOT / "platform" / "targets"
OPERATION_REGISTRY = ROOT / "platform" / "gateway-protocol" / "operation-registry.yaml"

SCENARIO_SCHEMA = SCENARIO_DIR / "scenario-registry.schema.json"
TOOL_SCHEMA = SCENARIO_DIR / "tool-registry.schema.json"
SCENARIO_REGISTRY = SCENARIO_DIR / "scenario-registry.yaml"
TOOL_REGISTRY = SCENARIO_DIR / "tool-registry.yaml"

FORBIDDEN_SCENARIO_FIELDS = [
    "command",
    "shell",
    "cmd",
    "exec",
    "argv",
    "cwd",
    "script",
    "run",
    "generic_execution",
]


def _load_target_registry_module() -> Any:
    spec = importlib.util.spec_from_file_location(
        "hermes_lane_f_target_registry", TARGETS_DIR / "target_registry.py"
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _walk_forbidden(node: Any, forbidden: list[str], path: str = "") -> list[str]:
    findings: list[str] = []
    if isinstance(node, Mapping):
        for key, value in node.items():
            if isinstance(key, str) and key in forbidden:
                findings.append(f"{path}.{key}" if path else key)
            findings.extend(_walk_forbidden(value, forbidden, f"{path}.{key}" if path else str(key)))
    elif isinstance(node, list):
        for index, value in enumerate(node):
            findings.extend(_walk_forbidden(value, forbidden, f"{path}[{index}]"))
    return findings


def load_doc(path: Path) -> dict[str, Any]:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def operation_ids(registry_yaml: Mapping[str, Any]) -> set[str]:
    return {op["id"] for op in registry_yaml.get("operations", []) if isinstance(op, Mapping)}


def _deep_merge(base: Mapping[str, Any], override: Mapping[str, Any]) -> dict[str, Any]:
    out = deepcopy(dict(base))
    for key, value in override.items():
        if isinstance(value, Mapping) and isinstance(out.get(key), Mapping):
            out[key] = _deep_merge(out[key], value)
        else:
            out[key] = value
    return out


def collect_findings(
    *,
    scenario_doc: Mapping[str, Any],
    tool_doc: Mapping[str, Any],
    target_module: Any,
    op_ids: set[str],
) -> list[str]:
    """Return a list of human-readable contract violations (empty == clean)."""

    findings: list[str] = []

    # generic_execution forbidden in both registries.
    if scenario_doc.get("contract", {}).get("forbidden_fields") and "generic_execution" not in scenario_doc[
        "contract"
    ].get("forbidden_fields", []):
        findings.append("scenario contract missing generic_execution in forbidden_fields")
    if tool_doc.get("contract", {}).get("forbidden_execution") != "generic_execution":
        findings.append("tool contract must forbid generic_execution")

    # JSON Schema validation.
    scenario_schema = json.loads(SCENARIO_SCHEMA.read_text(encoding="utf-8"))
    tool_schema = json.loads(TOOL_SCHEMA.read_text(encoding="utf-8"))
    try:
        jsonschema.validate(scenario_doc, scenario_schema)
    except jsonschema.ValidationError as exc:  # pragma: no cover - schema guards
        findings.append(f"scenario-registry.yaml schema violation: {exc.message}")
    try:
        jsonschema.validate(tool_doc, tool_schema)
    except jsonschema.ValidationError as exc:  # pragma: no cover - schema guards
        findings.append(f"tool-registry.yaml schema violation: {exc.message}")

    # forbidden arbitrary command/shell fields anywhere in scenario registry.
    forbidden_hits = _walk_forbidden(scenario_doc, FORBIDDEN_SCENARIO_FIELDS)
    for hit in forbidden_hits:
        findings.append(f"scenario registry contains forbidden field '{hit}'")

    # scenario -> environment / target / operation / runbook
    target_registry = target_module.load_registry()
    known_env = target_module.known_environment_ids()
    scenario_ids: set[str] = set()
    for scenario in scenario_doc.get("scenarios", []):
        sid = scenario.get("scenario_id")
        if sid in scenario_ids:
            findings.append(f"duplicate scenario_id '{sid}'")
        scenario_ids.add(sid)

        env_id = scenario.get("environment_id")
        if env_id not in known_env:
            findings.append(f"scenario '{sid}': environment_id '{env_id}' is not a known environment")

        auth = scenario.get("required_authorization") or {}
        target_id = auth.get("target_id")
        decision = target_module.resolve_execution_eligibility(target_id, target_registry)
        if not decision.eligible:
            findings.append(
                f"scenario '{sid}': target_id '{target_id}' not execution-eligible "
                f"(reason: {decision.reason})"
            )

        for op in scenario.get("semantic_operations", []):
            if op not in op_ids:
                findings.append(f"scenario '{sid}': semantic operation '{op}' not in operation-registry")

        for step in scenario.get("steps", []):
            if "operation" in step and step["operation"] not in op_ids:
                findings.append(
                    f"scenario '{sid}': step operation '{step['operation']}' not in operation-registry"
                )
            ref = step.get("runbook_ref")
            if ref:
                if not (ROOT / ref).is_file():
                    findings.append(f"scenario '{sid}': runbook_ref '{ref}' does not exist")

    # tool -> operation mapping + scenario_refs back-reference
    tool_op_ids = operation_ids(load_doc(OPERATION_REGISTRY))
    scenario_id_set = scenario_ids
    for tool in tool_doc.get("tools", []):
        mapped = tool.get("mapped_operation")
        if mapped == "UNMAPPED":
            if tool.get("availability") == "READY":
                findings.append(
                    f"tool '{tool.get('tool_id')}': UNMAPPED tool must not claim availability READY"
                )
            if tool.get("scenario_refs"):
                findings.append(
                    f"tool '{tool.get('tool_id')}': UNMAPPED tool must not reference scenarios"
                )
            continue
        if mapped not in tool_op_ids:
            findings.append(f"tool '{tool.get('tool_id')}': mapped_operation '{mapped}' not in operation-registry")
        if tool.get("availability") == "READY" and mapped != "system.health.read":
            findings.append(
                f"tool '{tool.get('tool_id')}': availability READY requires a live candidate effect "
                f"(only system.health.read is implemented)"
            )
        for ref in tool.get("scenario_refs", []):
            if ref and ref not in scenario_id_set:
                findings.append(f"tool '{tool.get('tool_id')}': scenario_ref '{ref}' not in scenario registry")

    return findings


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate Lane F scenario + tool registries")
    parser.add_argument("--scenario", default=str(SCENARIO_REGISTRY))
    parser.add_argument("--tool", default=str(TOOL_REGISTRY))
    args = parser.parse_args(argv)

    target_module = _load_target_registry_module()
    op_yaml = load_doc(OPERATION_REGISTRY)
    op_ids = operation_ids(op_yaml)

    scenario_doc = load_doc(Path(args.scenario))
    tool_doc = load_doc(Path(args.tool))

    findings = collect_findings(
        scenario_doc=scenario_doc,
        tool_doc=tool_doc,
        target_module=target_module,
        op_ids=op_ids,
    )

    if findings:
        for line in findings:
            print(f"FAIL: {line}")
        return 1
    print("LANE_F_REGISTRY_OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
