"""Positive and negative tests for the EPIC-02 source-of-truth contract."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "platform" / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import validate_source_of_truth as source_of_truth  # noqa: E402

REGISTRY = ROOT / "platform" / "registry.yaml"
SCHEMA = ROOT / "platform" / "schemas" / "runtime-profile.schema.json"


def test_repository_source_of_truth_is_valid() -> None:
    assert source_of_truth.validate_repository() == []


def test_registry_declares_fail_safe_tristate_drift() -> None:
    registry = yaml.safe_load(REGISTRY.read_text(encoding="utf-8"))
    drift = registry["source_of_truth"]["drift"]
    assert set(drift["states"]) == {"IN_SYNC", "DRIFT_DETECTED", "UNKNOWN"}
    assert drift["missing_observation"] == "UNKNOWN"
    assert drift["unparsable_observation"] == "UNKNOWN"
    assert drift["unverifiable_observation"] == "UNKNOWN"
    assert drift["automatic_reconciliation"] == "forbidden"


def test_observed_state_is_explicitly_non_authoritative() -> None:
    registry = yaml.safe_load(REGISTRY.read_text(encoding="utf-8"))
    classes = {
        item["class"]
        for item in registry["source_of_truth"]["non_authoritative"]
    }
    assert {
        "applied-deployment-state",
        "host-runtime-state",
        "issue-tracking",
        "generated-output",
    }.issubset(classes)


def test_runtime_ids_and_manifests_are_one_to_one() -> None:
    registry = yaml.safe_load(REGISTRY.read_text(encoding="utf-8"))
    entries = registry["runtimes"]
    ids = [item["id"] for item in entries]
    manifests = [item["manifest"] for item in entries]
    assert len(ids) == len(set(ids))
    assert len(manifests) == len(set(manifests))
    assert set((ROOT / "platform" / "runtimes").glob("*.yaml")) == {
        ROOT / "platform" / manifest for manifest in manifests
    }


def test_environment_runtime_references_resolve() -> None:
    registry = yaml.safe_load(REGISTRY.read_text(encoding="utf-8"))
    runtime_ids = {item["id"] for item in registry["runtimes"]}
    environments, errors = source_of_truth.discover_environment_runtimes()
    assert errors == []
    unresolved = {
        env_id: runtime_id
        for env_id, runtime_id in environments.items()
        if runtime_id not in runtime_ids
    }
    assert unresolved == {}


def test_profile_id_mismatch_is_rejected(tmp_path: Path) -> None:
    schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
    profile = yaml.safe_load(
        (ROOT / "platform" / "runtimes" / "docker.yaml").read_text(encoding="utf-8")
    )
    profile["id"] = "other-runtime"
    path = tmp_path / "docker.yaml"
    path.write_text(yaml.safe_dump(profile), encoding="utf-8")
    errors = source_of_truth.validate_runtime_profile(
        path,
        schema,
        expected_id="docker",
        statuses={"CURRENT"},
    )
    assert any("does not match registry id" in error for error in errors)


def test_pinned_release_without_digest_is_rejected(tmp_path: Path) -> None:
    schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
    profile = yaml.safe_load(
        (ROOT / "platform" / "runtimes" / "docker.yaml").read_text(encoding="utf-8")
    )
    profile["release_identity"] = {
        "digest_scope": "runtime-release",
        "environment_override": "forbidden",
        "current_state": "PINNED",
    }
    path = tmp_path / "docker.yaml"
    path.write_text(yaml.safe_dump(profile), encoding="utf-8")
    errors = source_of_truth.validate_runtime_profile(
        path,
        schema,
        expected_id="docker",
        statuses={"CURRENT"},
    )
    assert any("digest" in error for error in errors)


def test_environment_digest_override_is_forbidden() -> None:
    registry = yaml.safe_load(REGISTRY.read_text(encoding="utf-8"))
    release = registry["source_of_truth"]["release_identity"]
    assert release["image_digest_scope"] == "runtime-release"
    assert release["environment_digest_override"] == "forbidden"
    assert release["missing_required_digest"] == "UNKNOWN"
