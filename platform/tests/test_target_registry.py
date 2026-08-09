"""Contract tests for the canonical target registry (Lane B).

The registry is fail closed: offensive execution eligibility resolves True only
for LAB_ONLY and AUTHORIZED_TEST_TARGET, and target_id is the only execution
authority.
"""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from copy import deepcopy
from pathlib import Path

import jsonschema
import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
TARGETS_DIR = ROOT / "platform" / "targets"
MODULE_PATH = TARGETS_DIR / "target_registry.py"
REGISTRY_PATH = TARGETS_DIR / "target-registry.yaml"
SCHEMA_PATH = TARGETS_DIR / "target-registry.schema.json"

spec = importlib.util.spec_from_file_location("hermes_target_registry", MODULE_PATH)
assert spec and spec.loader
target_registry = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = target_registry
spec.loader.exec_module(target_registry)

AUTHORIZATION_STATES = target_registry.AUTHORIZATION_STATES
OFFENSIVE_EXECUTION_STATES = target_registry.OFFENSIVE_EXECUTION_STATES
TargetRegistryError = target_registry.TargetRegistryError


@pytest.fixture(scope="module")
def document() -> dict:
    return target_registry.load_registry()


def _mutated(document: dict, **overrides) -> dict:
    clone = deepcopy(document)
    clone["targets"][0].update(overrides)
    return clone


# --------------------------------------------------------------------------
# schema and structural contract
# --------------------------------------------------------------------------


def test_registry_validates_against_its_json_schema(document: dict) -> None:
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    jsonschema.validate(instance=document, schema=schema)


def test_registry_declares_the_fail_closed_contract(document: dict) -> None:
    contract = document["contract"]
    assert contract["canonical_authority"] == "target_id"
    assert contract["fail_closed"] is True
    assert set(contract["offensive_execution_states"]) == set(OFFENSIVE_EXECUTION_STATES)


def test_registry_has_no_contract_violations(document: dict) -> None:
    assert target_registry.validate_registry(document) == []


def test_target_ids_are_unique(document: dict) -> None:
    ids = [entry["target_id"] for entry in target_registry.targets(document)]
    assert len(ids) == len(set(ids))


def test_every_target_declares_the_required_fields(document: dict) -> None:
    required = {
        "target_id",
        "environment_id",
        "kind",
        "identity",
        "authorization_state",
        "lifecycle",
        "health",
        "scope",
    }
    for entry in target_registry.targets(document):
        assert required.issubset(entry), f"{entry.get('target_id')} is missing required fields"


def test_authorization_states_are_within_the_enum(document: dict) -> None:
    for entry in target_registry.targets(document):
        assert entry["authorization_state"] in AUTHORIZATION_STATES


# --------------------------------------------------------------------------
# no external targets
# --------------------------------------------------------------------------


def test_no_external_or_public_targets_are_committed(document: dict) -> None:
    for entry in target_registry.targets(document):
        assert entry["authorization_state"] != "EXTERNAL"
        assert entry["identity"]["reachability"] in {"lab-internal", "loopback"}


def test_identities_are_not_raw_urls(document: dict) -> None:
    for entry in target_registry.targets(document):
        hostname = entry["identity"]["hostname"]
        assert "://" not in hostname
        assert "/" not in hostname


def test_registry_rejects_a_committed_external_target(document: dict) -> None:
    broken = _mutated(document, authorization_state="EXTERNAL")
    assert any("EXTERNAL" in problem for problem in target_registry.validate_registry(broken))


# --------------------------------------------------------------------------
# orphan checks
# --------------------------------------------------------------------------


def test_every_environment_id_matches_a_known_environment(document: dict) -> None:
    assert target_registry.orphan_targets(document) == []


def test_known_environment_ids_include_the_executable_docker_labs() -> None:
    known = target_registry.known_environment_ids()
    for env_id in ("juice-shop", "webgoat", "dvwa", "vampi", "wrongsecrets"):
        assert env_id in known


def test_orphan_environment_id_is_reported(document: dict) -> None:
    broken = _mutated(document, environment_id="environment-that-does-not-exist")
    violations = target_registry.orphan_targets(broken)
    assert violations and "not a known environment" in violations[0]


def test_targets_only_reference_docker_environments(document: dict) -> None:
    manifests = {}
    for path in sorted((ROOT / "platform" / "environments").rglob("*.yaml")):
        if path.name in {"compose.yaml", "compose-effective.yaml"}:
            continue
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        if isinstance(data, dict) and isinstance(data.get("id"), str):
            manifests[data["id"]] = data
    for entry in target_registry.targets(document):
        manifest = manifests[entry["environment_id"]]
        assert manifest.get("runtime") == "docker"


# --------------------------------------------------------------------------
# resolver: safety invariant
# --------------------------------------------------------------------------


def test_every_committed_target_is_execution_eligible(document: dict) -> None:
    for entry in target_registry.targets(document):
        decision = target_registry.resolve_execution_eligibility(entry["target_id"], document)
        assert decision.eligible is True
        assert decision.authorization_state in OFFENSIVE_EXECUTION_STATES


@pytest.mark.parametrize("state", ["LAB_ONLY", "AUTHORIZED_TEST_TARGET"])
def test_authorized_states_resolve_true(document: dict, state: str) -> None:
    mutated = _mutated(document, authorization_state=state)
    target_id = mutated["targets"][0]["target_id"]
    assert target_registry.resolve_execution_eligibility(target_id, mutated).eligible is True


@pytest.mark.parametrize("state", ["UNVERIFIED", "BLOCKED", "EXTERNAL"])
def test_unauthorized_states_fail_closed(document: dict, state: str) -> None:
    mutated = _mutated(document, authorization_state=state)
    target_id = mutated["targets"][0]["target_id"]
    decision = target_registry.resolve_execution_eligibility(target_id, mutated)
    assert decision.eligible is False
    assert state in decision.reason


@pytest.mark.parametrize("state", [None, "", "lab_only", "AUTHORISED", 42, ["LAB_ONLY"]])
def test_unknown_or_malformed_states_fail_closed(document: dict, state) -> None:
    mutated = _mutated(document, authorization_state=state)
    target_id = mutated["targets"][0]["target_id"]
    decision = target_registry.resolve_execution_eligibility(target_id, mutated)
    assert decision.eligible is False


def test_missing_authorization_state_fails_closed(document: dict) -> None:
    mutated = deepcopy(document)
    mutated["targets"][0].pop("authorization_state")
    target_id = mutated["targets"][0]["target_id"]
    decision = target_registry.resolve_execution_eligibility(target_id, mutated)
    assert decision.eligible is False
    assert "authorization_state" in decision.reason


def test_retired_lifecycle_fails_closed(document: dict) -> None:
    mutated = _mutated(document, lifecycle="RETIRED")
    target_id = mutated["targets"][0]["target_id"]
    decision = target_registry.resolve_execution_eligibility(target_id, mutated)
    assert decision.eligible is False
    assert "RETIRED" in decision.reason


def test_empty_scope_fails_closed(document: dict) -> None:
    mutated = _mutated(document, scope={"allowed_operations": []})
    target_id = mutated["targets"][0]["target_id"]
    decision = target_registry.resolve_execution_eligibility(target_id, mutated)
    assert decision.eligible is False


# --------------------------------------------------------------------------
# resolver: target_id is the only execution authority
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "candidate",
    [
        "http://juice-shop:3000/",
        "https://127.0.0.1:3000",
        "127.0.0.1:3000",
        "juice-shop:3000",
        "user@juice-shop",
        "juice shop",
    ],
)
def test_raw_locators_are_never_an_execution_authority(document: dict, candidate: str) -> None:
    decision = target_registry.resolve_execution_eligibility(candidate, document)
    assert decision.eligible is False
    assert "authority" in decision.reason or "not present" in decision.reason


@pytest.mark.parametrize("candidate", [None, "", "   ", 0, 1, [], {}, object()])
def test_missing_or_non_string_target_ids_fail_closed(document: dict, candidate) -> None:
    decision = target_registry.resolve_execution_eligibility(candidate, document)
    assert decision.eligible is False


def test_unknown_target_id_fails_closed(document: dict) -> None:
    decision = target_registry.resolve_execution_eligibility("not-a-registered-target", document)
    assert decision.eligible is False
    assert "not present" in decision.reason


def test_resolve_target_returns_none_for_unknown_ids(document: dict) -> None:
    assert target_registry.resolve_target("not-a-registered-target", document) is None
    assert target_registry.resolve_target(None, document) is None


def test_resolve_target_returns_the_entry(document: dict) -> None:
    entry = target_registry.resolve_target("juice-shop-web", document)
    assert entry is not None
    assert entry["environment_id"] == "juice-shop"


# --------------------------------------------------------------------------
# resolver: scope enforcement and helpers
# --------------------------------------------------------------------------


def test_operation_outside_declared_scope_fails_closed(document: dict) -> None:
    decision = target_registry.resolve_execution_eligibility(
        "juice-shop-web", document, operation="supply_chain_review"
    )
    assert decision.eligible is False
    assert "outside the declared scope" in decision.reason


def test_operation_inside_declared_scope_resolves_true(document: dict) -> None:
    decision = target_registry.resolve_execution_eligibility(
        "juice-shop-web", document, operation="web_vulnerability_scan"
    )
    assert decision.eligible is True


def test_decision_is_deterministic(document: dict) -> None:
    first = target_registry.resolve_execution_eligibility("juice-shop-web", document).as_dict()
    second = target_registry.resolve_execution_eligibility("juice-shop-web", document).as_dict()
    assert first == second


def test_eligible_target_ids_matches_the_committed_registry(document: dict) -> None:
    ids = target_registry.eligible_target_ids(document)
    assert ids == sorted(entry["target_id"] for entry in target_registry.targets(document))


def test_targets_for_environment_filters_correctly(document: dict) -> None:
    webgoat = target_registry.targets_for_environment("webgoat", document)
    assert {entry["target_id"] for entry in webgoat} == {"webgoat-web", "webgoat-webwolf"}
    assert target_registry.targets_for_environment("unknown-environment", document) == []


# --------------------------------------------------------------------------
# loader failure modes
# --------------------------------------------------------------------------


def test_missing_registry_file_raises(tmp_path: Path) -> None:
    with pytest.raises(TargetRegistryError):
        target_registry.load_registry(tmp_path / "absent.yaml")


def test_invalid_registry_document_raises(tmp_path: Path) -> None:
    broken = tmp_path / "registry.yaml"
    broken.write_text("schema_version: '9.9'\ntargets: []\n", encoding="utf-8")
    with pytest.raises(TargetRegistryError):
        target_registry.load_registry(broken)


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------


def _run_cli(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(MODULE_PATH), *args],
        capture_output=True,
        text=True,
        check=False,
    )


def test_cli_validate_is_green() -> None:
    result = _run_cli("validate")
    assert result.returncode == 0, result.stderr
    assert result.stdout.startswith("OK targets=")
    assert "orphans=0" in result.stdout


def test_cli_list_emits_json_rows() -> None:
    result = _run_cli("list")
    assert result.returncode == 0, result.stderr
    rows = json.loads(result.stdout)
    assert rows and all(row["offensive_execution_eligible"] is True for row in rows)


def test_cli_resolve_exit_codes() -> None:
    allowed = _run_cli("resolve", "juice-shop-web")
    assert allowed.returncode == 0
    assert json.loads(allowed.stdout)["eligible"] is True

    denied = _run_cli("resolve", "http://juice-shop:3000/")
    assert denied.returncode == 2
    assert json.loads(denied.stdout)["eligible"] is False


def test_cli_validate_rejects_an_orphan_registry(tmp_path: Path) -> None:
    document = yaml.safe_load(REGISTRY_PATH.read_text(encoding="utf-8"))
    document["targets"][0]["environment_id"] = "environment-that-does-not-exist"
    candidate = tmp_path / "registry.yaml"
    candidate.write_text(yaml.safe_dump(document, sort_keys=False), encoding="utf-8")
    result = _run_cli("--registry", str(candidate), "validate")
    assert result.returncode == 1
    assert "not a known environment" in result.stderr


# --------------------------------------------------------------------------
# lane boundary
# --------------------------------------------------------------------------


def test_lane_does_not_wire_the_resolver_into_lab_lifecycle() -> None:
    lifecycle_dir = ROOT / "platform" / "lab-lifecycle"
    for path in lifecycle_dir.glob("*.py"):
        text = path.read_text(encoding="utf-8")
        assert "target_registry" not in text, f"{path.name} must not import the target registry in this lane"


def test_registry_evidence_paths_exist(document: dict) -> None:
    for entry in target_registry.targets(document):
        evidence = entry.get("evidence") or {}
        for key in ("manifest_path", "compose_path"):
            value = evidence.get(key)
            if value:
                assert (ROOT / value).is_file(), f"{entry['target_id']}: missing {value}"
