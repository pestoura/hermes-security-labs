from __future__ import annotations

import ast
import importlib.util
import json
import sys
from copy import deepcopy
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "scenario-registry" / "scenario_plan.py"
SCENARIO_PATH = ROOT / "scenario-registry" / "scenario-registry.yaml"
TOOL_PATH = ROOT / "scenario-registry" / "tool-registry.yaml"
OPERATION_PATH = ROOT / "gateway-protocol" / "operation-registry.yaml"
TARGET_PATH = ROOT / "targets" / "target-registry.yaml"
WEBGOAT_MANIFEST = ROOT / "environments" / "web-api" / "webgoat" / "manifest.yaml"


def _load_module():
    spec = importlib.util.spec_from_file_location("lane_k_scenario_plan_tests", MODULE_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _yaml(path: Path):
    return yaml.safe_load(path.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def composer():
    return _load_module()


@pytest.mark.parametrize(
    "scenario_id,expected_profile",
    [
        ("webgoat-tls-transport-review", "normal"),
        ("dvwa-sql-injection-screening", "controlled"),
        ("juice-shop-lab-lifecycle-stop", "controlled"),
    ],
)
def test_seeded_scenarios_compose_inert_plans(composer, scenario_id, expected_profile):
    result = composer.compose_scenario_plan(scenario_id)

    assert result.ok is True
    assert result.reason_code == "PLAN_READY"
    payload = result.as_dict()
    json.dumps(payload)
    plan = payload["plan"]
    assert plan["mode"] == "DRY_RUN"
    assert plan["gateway_profile"] == expected_profile
    assert plan["target"]["target_id"]
    assert plan["target"]["authorization"]["eligible"] is True
    assert plan["backend"]["backend_type"] == "DOCKER"
    assert plan["backend_plan"]["operation"] == "status"
    assert plan["execution"]["permitted"] is False
    assert plan["reset_cleanup_proof"]["runtime_known_state_proof_required"] is True


def test_unknown_scenario_fails_closed(composer):
    result = composer.compose_scenario_plan("does-not-exist")
    assert (result.ok, result.reason_code) == (False, "UNKNOWN_SCENARIO")


def test_invalid_target_fails_closed(composer):
    scenarios = deepcopy(_yaml(SCENARIO_PATH))
    scenarios["scenarios"][0]["required_authorization"]["target_id"] = "missing-target"

    result = composer.compose_scenario_plan(
        scenarios["scenarios"][0]["scenario_id"],
        scenario_doc=scenarios,
    )
    assert (result.ok, result.reason_code) == (False, "UNKNOWN_TARGET")


def test_unauthorized_target_fails_closed(composer):
    target_doc = deepcopy(_yaml(TARGET_PATH))
    for target in target_doc["targets"]:
        if target["target_id"] == "webgoat-web":
            target["authorization_state"] = "BLOCKED"

    result = composer.compose_scenario_plan(
        "webgoat-tls-transport-review",
        target_doc=target_doc,
    )
    assert (result.ok, result.reason_code) == (False, "UNAUTHORIZED_TARGET")


def test_unauthorized_semantic_operation_fails_closed(composer):
    operation_doc = deepcopy(_yaml(OPERATION_PATH))
    for profile in operation_doc["profiles"].values():
        profile["operations"] = [
            op for op in profile["operations"] if op != "web.discovery.tls"
        ]

    result = composer.compose_scenario_plan(
        "webgoat-tls-transport-review",
        operation_doc=operation_doc,
    )
    assert (result.ok, result.reason_code) == (
        False,
        "UNAUTHORIZED_SEMANTIC_OPERATION",
    )


def test_missing_operation_reference_fails_closed(composer):
    scenarios = deepcopy(_yaml(SCENARIO_PATH))
    scenario = scenarios["scenarios"][0]
    scenario["semantic_operations"].append("web.discovery.nonexistent")

    result = composer.compose_scenario_plan(
        scenario["scenario_id"],
        scenario_doc=scenarios,
    )
    assert (result.ok, result.reason_code) == (False, "MISSING_OPERATION_REFERENCE")


def test_missing_tool_reference_fails_closed(composer):
    tool_doc = deepcopy(_yaml(TOOL_PATH))
    tool_doc["tools"] = [
        tool
        for tool in tool_doc["tools"]
        if tool.get("mapped_operation") != "web.discovery.tls"
    ]

    result = composer.compose_scenario_plan(
        "webgoat-tls-transport-review",
        tool_doc=tool_doc,
    )
    assert (result.ok, result.reason_code) == (False, "MISSING_TOOL_REFERENCE")


def test_unsupported_backend_fails_closed(composer):
    manifest = deepcopy(_yaml(WEBGOAT_MANIFEST))
    manifest["backend"] = "kind"

    result = composer.compose_scenario_plan(
        "webgoat-tls-transport-review",
        manifests={"webgoat": manifest},
    )
    assert (result.ok, result.reason_code) == (False, "UNSUPPORTED_BACKEND")


@pytest.mark.parametrize(
    "mutation,expected",
    [
        ("lifecycle", "MISSING_LIFECYCLE_CONTRACT"),
        ("readiness", "MISSING_READINESS_CONTRACT"),
        ("evidence", "MISSING_EVIDENCE_CONTRACT"),
        ("reset", "MISSING_RESET_PROOF"),
    ],
)
def test_missing_environment_contracts_fail_closed(composer, mutation, expected):
    manifest = deepcopy(_yaml(WEBGOAT_MANIFEST))
    if mutation == "lifecycle":
        manifest.pop("lifecycle")
    elif mutation == "readiness":
        manifest.pop("readiness")
    elif mutation == "evidence":
        manifest["persistence"].pop("evidence")
    elif mutation == "reset":
        manifest.pop("reset_strategy")

    result = composer.compose_scenario_plan(
        "webgoat-tls-transport-review",
        manifests={"webgoat": manifest},
    )
    assert (result.ok, result.reason_code) == (False, expected)


def test_ambiguous_scenario_resolution_fails_closed(composer):
    scenarios = deepcopy(_yaml(SCENARIO_PATH))
    scenarios["scenarios"].append(deepcopy(scenarios["scenarios"][0]))

    result = composer.compose_scenario_plan(
        scenarios["scenarios"][0]["scenario_id"],
        scenario_doc=scenarios,
    )
    assert (result.ok, result.reason_code) == (
        False,
        "AMBIGUOUS_REGISTRY_RESOLUTION",
    )


def test_composer_source_has_no_execution_or_network_primitives():
    tree = ast.parse(MODULE_PATH.read_text(encoding="utf-8"))
    forbidden_imports = {"subprocess", "socket", "requests", "httpx", "urllib"}
    imported = set()
    called_names = set()

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module.split(".")[0])
        elif isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name):
                called_names.add(node.func.id)
            elif isinstance(node.func, ast.Attribute):
                called_names.add(node.func.attr)

    assert imported.isdisjoint(forbidden_imports)
    assert {"system", "popen", "Popen", "run", "check_call", "check_output"}.isdisjoint(
        called_names
    )
