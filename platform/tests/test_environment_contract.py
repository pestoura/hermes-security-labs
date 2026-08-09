"""Fail-closed guarantees for the canonical environment contract.

The contract lives in ``platform/schemas/lab-manifest.schema.json`` and is enforced
by ``platform/scripts/labctl.py``. These tests pin the executable/catalog-only split
and prove that an executable manifest missing authorization_state, network or
readiness FAILS validation instead of silently passing.
"""

from __future__ import annotations

import copy
import importlib.util
import json
import sys
from pathlib import Path

import jsonschema
import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
PLATFORM = ROOT / "platform"
SCHEMA_PATH = PLATFORM / "schemas" / "lab-manifest.schema.json"
ENVIRONMENTS = PLATFORM / "environments"

spec = importlib.util.spec_from_file_location("labctl", PLATFORM / "scripts" / "labctl.py")
assert spec and spec.loader
labctl = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = labctl
spec.loader.exec_module(labctl)

EXECUTABLE_MANIFESTS = sorted(ENVIRONMENTS.rglob("manifest.yaml"))


@pytest.fixture(scope="module")
def schema() -> dict:
    return json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def validator(schema: dict) -> jsonschema.Draft7Validator:
    jsonschema.Draft7Validator.check_schema(schema)
    return jsonschema.Draft7Validator(schema)


def _load(path: Path) -> dict:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert isinstance(data, dict)
    return data


def _manifest(data: dict, path: Path = Path("platform/environments/test/manifest.yaml")):
    return labctl.Manifest(env_id=str(data.get("id", "test")), path=PLATFORM / "environments" / "test" / "manifest.yaml", data=data)


def _reference() -> dict:
    return _load(ENVIRONMENTS / "web-api" / "dvwa" / "manifest.yaml")


def test_twelve_directory_manifests_are_migrated() -> None:
    assert len(EXECUTABLE_MANIFESTS) == 12
    for path in EXECUTABLE_MANIFESTS:
        data = _load(path)
        assert data.get("execution_class") == "executable", path
        assert data.get("schema_version") == labctl.CONTRACT_SCHEMA_VERSION, path


@pytest.mark.parametrize("path", EXECUTABLE_MANIFESTS, ids=lambda p: p.parent.name)
def test_executable_manifest_satisfies_the_contract(path: Path, validator) -> None:
    data = _load(path)
    assert list(validator.iter_errors(data)) == []
    assert labctl.contract_errors(_manifest(data)) == []
    assert data["authorization_state"] in labctl.RUNNABLE_AUTHORIZATION_STATES
    assert data["network"]["egress"]["default"] == "deny"
    assert data["network"]["ingress"]["scope"] in labctl.INGRESS_SCOPES
    assert data["readiness"]["timeout_seconds"] > 0
    assert data["persistence"]["evidence"]["retention_days"] >= 0
    assert data["reset_strategy"]["mode"] in {"script", "recreate", "redeploy", "not-supported"}


def test_flat_catalogue_yaml_is_not_marked_executable() -> None:
    flat = [
        path
        for path in ENVIRONMENTS.rglob("*.yaml")
        if path.name not in {"manifest.yaml", "compose.yaml", "compose-effective.yaml"}
    ]
    assert flat, "expected flat catalogue manifests to still exist"
    for path in flat:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            continue
        assert data.get("execution_class") != "executable", path


def test_catalog_only_manifest_is_not_held_to_the_executable_contract() -> None:
    data = {"id": "catalogue-lab", "name": "x", "category": "web-api", "runtime": "docker", "status": "PLANNED", "resources": {}, "lifecycle": ["start"]}
    assert labctl.contract_errors(_manifest(data)) == []


@pytest.mark.parametrize("field", ["authorization_state", "network", "readiness", "liveness", "reset_strategy", "persistence", "backend", "schema_version"])
def test_executable_manifest_missing_contract_field_fails(field: str, validator) -> None:
    data = _reference()
    data.pop(field)
    assert list(validator.iter_errors(data)), f"schema accepted manifest without {field}"
    errors = labctl.contract_errors(_manifest(data))
    assert any(field in error for error in errors), errors


def test_unknown_execution_class_fails_closed(validator) -> None:
    data = _reference()
    data["execution_class"] = "maybe-executable"
    assert list(validator.iter_errors(data))
    assert labctl.contract_errors(_manifest(data))


def test_invalid_authorization_state_fails(validator) -> None:
    data = _reference()
    data["authorization_state"] = "PROBABLY_FINE"
    assert list(validator.iter_errors(data))
    assert labctl.contract_errors(_manifest(data))


@pytest.mark.parametrize("state", ["UNVERIFIED", "BLOCKED", "EXTERNAL"])
def test_non_runnable_authorization_states_are_declarable_but_not_runnable(state: str, validator) -> None:
    data = _reference()
    data["authorization_state"] = state
    assert list(validator.iter_errors(data)) == []
    assert labctl.contract_errors(_manifest(data)) == []
    assert state not in labctl.RUNNABLE_AUTHORIZATION_STATES


def test_egress_default_allow_is_rejected(validator) -> None:
    data = _reference()
    data["network"]["egress"]["default"] = "allow"
    assert list(validator.iter_errors(data))
    assert labctl.contract_errors(_manifest(data))


def test_unenforced_egress_without_residual_risk_is_rejected(validator) -> None:
    data = _reference()
    data["network"]["egress"].pop("residual_risk")
    assert list(validator.iter_errors(data))
    assert labctl.contract_errors(_manifest(data))


def test_ingress_without_scope_is_rejected(validator) -> None:
    data = _reference()
    data["network"]["ingress"].pop("scope")
    assert list(validator.iter_errors(data))
    assert labctl.contract_errors(_manifest(data))


def test_unknown_ingress_scope_is_rejected(validator) -> None:
    data = _reference()
    data["network"]["ingress"]["scope"] = "internet"
    assert list(validator.iter_errors(data))
    assert labctl.contract_errors(_manifest(data))


@pytest.mark.parametrize("field", ["probe", "timeout_seconds", "success_criteria"])
def test_partial_readiness_is_rejected(field: str, validator) -> None:
    data = _reference()
    data["readiness"].pop(field)
    assert list(validator.iter_errors(data))
    assert labctl.contract_errors(_manifest(data))


def test_executable_manifest_requires_cpu_and_memory_limits(validator) -> None:
    data = _reference()
    data["resources"] = {"disk": "3G"}
    assert list(validator.iter_errors(data))


def test_unknown_contract_subkeys_are_rejected(validator) -> None:
    data = _reference()
    data["network"]["egress"]["bypass"] = True
    assert list(validator.iter_errors(data))


def test_reference_manifest_is_unchanged_by_the_negative_cases() -> None:
    first = _reference()
    second = copy.deepcopy(first)
    assert first == second
