"""Contract tests for the Lane F scenario + tool registries.

These tests assert the fail-closed guarantees required by the task:
  * no generic_execution / command / shell entries;
  * every scenario binds to a known environment and an execution-eligible target_id;
  * every scenario semantic operation maps to the typed operation registry;
  * every tool maps to exactly one typed operation;
  * generic_execution remains forbidden;
  * negative cases (missing target, unknown op, forbidden field, bogus runbook) are rejected.
"""

from __future__ import annotations

import importlib.util
import sys
from copy import deepcopy
from pathlib import Path

import pytest
import yaml

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
SCENARIO_DIR = ROOT / "platform" / "scenario-registry"
TARGETS_DIR = ROOT / "platform" / "targets"
OPERATION_REGISTRY = ROOT / "platform" / "gateway-protocol" / "operation-registry.yaml"

SCENARIO_YAML = SCENARIO_DIR / "scenario-registry.yaml"
TOOL_YAML = SCENARIO_DIR / "tool-registry.yaml"

MODULE_PATH = SCENARIO_DIR / "validate_registries.py"


def _load_validator():
    spec = importlib.util.spec_from_file_location("hermes_lane_f_validator", MODULE_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def validator():
    return _load_validator()


@pytest.fixture(scope="module")
def target_module():
    spec = importlib.util.spec_from_file_location(
        "hermes_lane_f_target_registry", TARGETS_DIR / "target_registry.py"
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def docs():
    return (
        yaml.safe_load(SCENARIO_YAML.read_text(encoding="utf-8")),
        yaml.safe_load(TOOL_YAML.read_text(encoding="utf-8")),
        yaml.safe_load(OPERATION_REGISTRY.read_text(encoding="utf-8")),
    )


def test_registries_pass_contract(validator, docs, target_module):
    scenario_doc, tool_doc, op_doc = docs
    op_ids = {op["id"] for op in op_doc.get("operations", [])}
    findings = validator.collect_findings(
        scenario_doc=scenario_doc,
        tool_doc=tool_doc,
        target_module=target_module,
        op_ids=op_ids,
    )
    assert findings == [], f"unexpected findings: {findings}"


def test_generic_execution_forbidden(validator, docs):
    scenario_doc, tool_doc, _ = docs
    assert scenario_doc["contract"]["forbidden_fields"]
    assert "generic_execution" in scenario_doc["contract"]["forbidden_fields"]
    assert tool_doc["contract"]["forbidden_execution"] == "generic_execution"


def test_no_forbidden_command_shell_fields(validator, docs):
    scenario_doc, tool_doc, _ = docs
    hits = validator._walk_forbidden(scenario_doc, validator.FORBIDDEN_SCENARIO_FIELDS)
    assert hits == [], f"forbidden fields present: {hits}"
    # tool registry must never declare command/shell either
    hits_tool = validator._walk_forbidden(tool_doc, validator.FORBIDDEN_SCENARIO_FIELDS)
    assert hits_tool == [], f"forbidden fields present in tool registry: {hits_tool}"


def test_scenarios_bind_known_environment_and_eligible_target(validator, docs, target_module):
    scenario_doc, _, _ = docs
    known_env = target_module.known_environment_ids()
    registry = target_module.load_registry()
    for scenario in scenario_doc["scenarios"]:
        assert scenario["environment_id"] in known_env
        decision = target_module.resolve_execution_eligibility(
            scenario["required_authorization"]["target_id"], registry
        )
        assert decision.eligible, scenario["scenario_id"]


def test_scenario_operations_map_to_operation_registry(docs):
    scenario_doc, _, op_doc = docs
    op_ids = {op["id"] for op in op_doc.get("operations", [])}
    for scenario in scenario_doc["scenarios"]:
        for op in scenario["semantic_operations"]:
            assert op in op_ids, f"{scenario['scenario_id']} -> {op}"


def test_tool_mappings_resolve_to_operations(docs):
    scenario_doc, tool_doc, op_doc = docs
    op_ids = {op["id"] for op in op_doc.get("operations", [])}
    scenario_ids = {s["scenario_id"] for s in scenario_doc["scenarios"]}
    for tool in tool_doc["tools"]:
        mapped = tool["mapped_operation"]
        if mapped == "UNMAPPED":
            continue
        assert mapped in op_ids, tool["tool_id"]
        for ref in tool.get("scenario_refs", []):
            if ref:
                assert ref in scenario_ids, tool["tool_id"]


def test_ready_tools_only_for_implemented_candidate(docs):
    _, tool_doc, _ = docs
    for tool in tool_doc["tools"]:
        if tool["availability"] == "READY":
            assert tool["mapped_operation"] == "system.health.read", tool["tool_id"]


# ----- negative tests -------------------------------------------------


def test_rejects_unknown_target_id(validator, docs, target_module):
    scenario_doc, tool_doc, op_doc = docs
    bad = deepcopy(scenario_doc)
    bad["scenarios"][0]["required_authorization"]["target_id"] = "does-not-exist"
    op_ids = {op["id"] for op in op_doc.get("operations", [])}
    findings = validator.collect_findings(
        scenario_doc=bad, tool_doc=tool_doc, target_module=target_module, op_ids=op_ids
    )
    assert any("does-not-exist" in f for f in findings)


def test_rejects_unknown_semantic_operation(validator, docs, target_module):
    scenario_doc, tool_doc, op_doc = docs
    bad = deepcopy(scenario_doc)
    bad["scenarios"][0]["semantic_operations"][-1] = "operation.not.declared"
    op_ids = {op["id"] for op in op_doc.get("operations", [])}
    findings = validator.collect_findings(
        scenario_doc=bad, tool_doc=tool_doc, target_module=target_module, op_ids=op_ids
    )
    assert any("operation.not.declared" in f for f in findings)


def test_rejects_forbidden_command_field(validator, docs, target_module):
    scenario_doc, tool_doc, op_doc = docs
    bad = deepcopy(scenario_doc)
    bad["scenarios"][0]["steps"][0]["command"] = "echo pwn"
    op_ids = {op["id"] for op in op_doc.get("operations", [])}
    findings = validator.collect_findings(
        scenario_doc=bad, tool_doc=tool_doc, target_module=target_module, op_ids=op_ids
    )
    assert any("command" in f for f in findings)


def test_rejects_bogus_runbook_ref(validator, docs, target_module):
    scenario_doc, tool_doc, op_doc = docs
    bad = deepcopy(scenario_doc)
    bad["scenarios"][0]["steps"][1]["runbook_ref"] = "security/packs/api/runbooks/does-not-exist.yaml"
    op_ids = {op["id"] for op in op_doc.get("operations", [])}
    findings = validator.collect_findings(
        scenario_doc=bad, tool_doc=tool_doc, target_module=target_module, op_ids=op_ids
    )
    assert any("does-not-exist.yaml" in f for f in findings)


def test_rejects_tool_mapped_to_unknown_operation(validator, docs, target_module):
    scenario_doc, tool_doc, op_doc = docs
    bad = deepcopy(tool_doc)
    bad["tools"][0]["mapped_operation"] = "operation.not.declared"
    op_ids = {op["id"] for op in op_doc.get("operations", [])}
    findings = validator.collect_findings(
        scenario_doc=scenario_doc, tool_doc=bad, target_module=target_module, op_ids=op_ids
    )
    assert any("operation.not.declared" in f for f in findings)


def test_rejects_duplicate_scenario_id(validator, docs, target_module):
    scenario_doc, tool_doc, op_doc = docs
    bad = deepcopy(scenario_doc)
    bad["scenarios"].append(deepcopy(bad["scenarios"][0]))
    op_ids = {op["id"] for op in op_doc.get("operations", [])}
    findings = validator.collect_findings(
        scenario_doc=bad, tool_doc=tool_doc, target_module=target_module, op_ids=op_ids
    )
    assert any("duplicate scenario_id" in f for f in findings)


def test_cli_reports_failure_on_bad_doc(tmp_path, validator, docs, target_module):
    bad_yaml = tmp_path / "scenario-bad.yaml"
    bad = deepcopy(docs[0])
    bad["scenarios"][0]["required_authorization"]["target_id"] = "nope"
    bad_yaml.write_text(yaml.safe_dump(bad), encoding="utf-8")
    rc = validator.main(["--scenario", str(bad_yaml), "--tool", str(TOOL_YAML)])
    assert rc == 1
