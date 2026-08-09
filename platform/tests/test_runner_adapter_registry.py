from __future__ import annotations

import copy
import importlib.util
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
MODULE_PATH = ROOT / "platform" / "runner-adapters" / "validate_registry.py"
ADAPTER_PATH = ROOT / "platform" / "runner-adapters" / "adapter-registry.yaml"
TARGET_PATH = ROOT / "platform" / "targets" / "target-registry.yaml"
OPERATION_PATH = ROOT / "platform" / "gateway-protocol" / "operation-registry.yaml"
SCENARIO_PATH = ROOT / "platform" / "scenario-registry" / "scenario-registry.yaml"
TARGET_MODULE_PATH = ROOT / "platform" / "targets" / "target_registry.py"


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


validator = _load("runner_adapter_registry_validator_test", MODULE_PATH)
target_module = _load("runner_adapter_target_registry_test", TARGET_MODULE_PATH)


def _docs():
    return (
        yaml.safe_load(ADAPTER_PATH.read_text(encoding="utf-8")),
        yaml.safe_load(TARGET_PATH.read_text(encoding="utf-8")),
        yaml.safe_load(OPERATION_PATH.read_text(encoding="utf-8")),
        yaml.safe_load(SCENARIO_PATH.read_text(encoding="utf-8")),
    )


def _findings(adapter_doc, target_doc, operation_doc, scenario_doc):
    return validator.collect_findings(
        adapter_doc=adapter_doc,
        target_doc=target_doc,
        operation_doc=operation_doc,
        scenario_doc=scenario_doc,
        target_module=target_module,
    )


def test_current_runner_adapter_registry_is_cross_registry_consistent() -> None:
    assert validator.validate_paths() == []


def test_cli_accepts_current_registry() -> None:
    assert validator.main([]) == 0


def test_unknown_target_is_rejected() -> None:
    adapter_doc, target_doc, operation_doc, scenario_doc = _docs()
    bad = copy.deepcopy(adapter_doc)
    bad["adapters"][0]["target_ids"] = ["unknown-target"]
    bad["adapters"][0]["input_contract"]["target"]["value"] = "unknown-target"
    findings = _findings(bad, target_doc, operation_doc, scenario_doc)
    assert any("not canonical" in item for item in findings)


def test_raw_hostname_target_contract_is_rejected() -> None:
    adapter_doc, target_doc, operation_doc, scenario_doc = _docs()
    bad = copy.deepcopy(adapter_doc)
    bad["adapters"][0]["input_contract"]["target"] = {
        "type": "hostname",
        "value": "webgoat-web",
    }
    findings = _findings(bad, target_doc, operation_doc, scenario_doc)
    assert any("target type must be lab-asset" in item for item in findings)


def test_blocked_target_is_not_execution_eligible() -> None:
    adapter_doc, target_doc, operation_doc, scenario_doc = _docs()
    bad_targets = copy.deepcopy(target_doc)
    for target in bad_targets["targets"]:
        if target["target_id"] == "webgoat-web":
            target["authorization_state"] = "BLOCKED"
    findings = _findings(adapter_doc, bad_targets, operation_doc, scenario_doc)
    assert any("not execution-eligible" in item for item in findings)


def test_unknown_typed_capability_is_rejected() -> None:
    adapter_doc, target_doc, operation_doc, scenario_doc = _docs()
    bad = copy.deepcopy(adapter_doc)
    bad["adapters"][0]["capabilities"] = ["web.discovery.unknown"]
    findings = _findings(bad, target_doc, operation_doc, scenario_doc)
    assert any("has no typed operation" in item for item in findings)


def test_operation_version_drift_is_rejected() -> None:
    adapter_doc, target_doc, operation_doc, scenario_doc = _docs()
    bad = copy.deepcopy(adapter_doc)
    bad["adapters"][0]["input_contract"]["operation_version"] = "9.9.9"
    findings = _findings(bad, target_doc, operation_doc, scenario_doc)
    assert any("version differs" in item for item in findings)


def test_operation_intrusiveness_drift_is_rejected() -> None:
    adapter_doc, target_doc, operation_doc, scenario_doc = _docs()
    bad = copy.deepcopy(adapter_doc)
    bad["adapters"][0]["input_contract"]["intrusiveness_level"] = "L2"
    findings = _findings(bad, target_doc, operation_doc, scenario_doc)
    assert any("intrusiveness differs" in item for item in findings)


def test_operation_must_attest_its_own_capability() -> None:
    adapter_doc, target_doc, operation_doc, scenario_doc = _docs()
    bad_ops = copy.deepcopy(operation_doc)
    for operation in bad_ops["operations"]:
        if operation["id"] == "web.discovery.headers":
            operation["required_capabilities"] = ["runtime.inventory.read"]
    findings = _findings(adapter_doc, target_doc, bad_ops, scenario_doc)
    assert any("does not attest its own capability" in item for item in findings)


def test_adapter_capabilities_must_be_covered_by_seeded_scenario() -> None:
    adapter_doc, target_doc, operation_doc, scenario_doc = _docs()
    bad_scenarios = copy.deepcopy(scenario_doc)
    for scenario in bad_scenarios["scenarios"]:
        if scenario["scenario_id"] == "webgoat-tls-transport-review":
            scenario["semantic_operations"].remove("web.discovery.tls")
    findings = _findings(adapter_doc, target_doc, operation_doc, bad_scenarios)
    assert any("no seeded scenario covers" in item for item in findings)


def test_permissive_authorization_default_is_rejected() -> None:
    adapter_doc, target_doc, operation_doc, scenario_doc = _docs()
    bad = copy.deepcopy(adapter_doc)
    bad["adapters"][0]["authorization"]["default"] = "allow"
    findings = _findings(bad, target_doc, operation_doc, scenario_doc)
    assert any("authorization default must be deny-all" in item for item in findings)


def test_runtime_ready_claim_is_rejected_before_live_acceptance() -> None:
    adapter_doc, target_doc, operation_doc, scenario_doc = _docs()
    bad = copy.deepcopy(adapter_doc)
    bad["adapters"][0]["runtime_status"] = "READY"
    findings = _findings(bad, target_doc, operation_doc, scenario_doc)
    assert any("runtime_status must remain NOT_RUN" in item for item in findings)


def test_generic_execution_enablement_is_rejected() -> None:
    adapter_doc, target_doc, operation_doc, scenario_doc = _docs()
    bad = copy.deepcopy(adapter_doc)
    bad["adapters"][0]["effect"]["generic_execution"] = True
    findings = _findings(bad, target_doc, operation_doc, scenario_doc)
    assert any("forbidden execution surface" in item for item in findings)


def test_noncanonical_handoff_source_is_rejected() -> None:
    adapter_doc, target_doc, operation_doc, scenario_doc = _docs()
    bad = copy.deepcopy(adapter_doc)
    bad["adapters"][0]["input_contract"]["source"] = "platform/other-handoff.py"
    findings = _findings(bad, target_doc, operation_doc, scenario_doc)
    assert any("canonical gateway handoff" in item for item in findings)


def test_missing_implementation_is_rejected() -> None:
    adapter_doc, target_doc, operation_doc, scenario_doc = _docs()
    bad = copy.deepcopy(adapter_doc)
    bad["adapters"][0]["implementation"] = "platform/runner-adapters/not-present.py"
    findings = _findings(bad, target_doc, operation_doc, scenario_doc)
    assert any("implementation path does not exist" in item for item in findings)
