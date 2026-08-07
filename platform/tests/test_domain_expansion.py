from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import jsonschema
import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
DOMAIN_DIR = ROOT / "platform" / "domain-expansion"

spec = importlib.util.spec_from_file_location("domain_expansion", DOMAIN_DIR / "domain_expansion.py")
assert spec and spec.loader
module = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = module
spec.loader.exec_module(module)

DomainExpansionError = module.DomainExpansionError
activation_eligible = module.activation_eligible
build_profile = module.build_profile
require_hardware_approval = module.require_hardware_approval


def test_no_domain_is_eligible_without_cleanup_demonstration() -> None:
    profile = build_profile(
        domain="kubernetes",
        cleanup_demonstrated=False,
        constraints={"unique_cluster": True, "ephemeral_kubeconfig": True, "ttl_seconds": 600},
    )
    assert profile["activation_eligible"] is False
    assert activation_eligible(profile) is False


def test_kubernetes_requires_unique_cluster_ephemeral_kubeconfig_and_ttl() -> None:
    profile = build_profile(
        domain="kubernetes",
        cleanup_demonstrated=True,
        constraints={"unique_cluster": True, "ephemeral_kubeconfig": True, "ttl_seconds": 600},
    )
    assert activation_eligible(profile) is True
    assert profile["activated"] is False
    schema = json.loads((DOMAIN_DIR / "domain-profile.schema.json").read_text())
    jsonschema.Draft202012Validator(schema).validate(profile)


def test_identity_requires_snapshot_rollback_and_budget() -> None:
    profile = build_profile(
        domain="identity",
        cleanup_demonstrated=True,
        constraints={"snapshot_required": True, "rollback_required": True, "resource_budget": 2.0},
    )
    assert profile["activation_eligible"] is True
    with pytest.raises(DomainExpansionError):
        build_profile(
            domain="identity",
            cleanup_demonstrated=True,
            constraints={"snapshot_required": True, "rollback_required": True, "resource_budget": 0},
        )


def test_cloud_requires_ephemeral_credentials_budget_and_ttl() -> None:
    profile = build_profile(
        domain="cloud",
        cleanup_demonstrated=True,
        constraints={"ephemeral_credentials": True, "budget": 5.0, "ttl_seconds": 900},
    )
    assert profile["activation_eligible"] is True
    assert profile["constraints"]["ephemeral_credentials"] is True
    with pytest.raises(DomainExpansionError):
        build_profile(
            domain="cloud",
            cleanup_demonstrated=True,
            constraints={"ephemeral_credentials": True, "budget": 0, "ttl_seconds": 900},
        )


def test_mobile_requires_bounded_device_lifecycle() -> None:
    profile = build_profile(
        domain="mobile",
        cleanup_demonstrated=True,
        constraints={"device_lifecycle": True, "adb_scoped": True, "analysis_sidecar_bounded": True},
    )
    assert profile["activation_eligible"] is True


def test_external_iot_hardware_requires_explicit_human_approval() -> None:
    blocked = build_profile(
        domain="iot-ot",
        cleanup_demonstrated=True,
        constraints={"simulator_supported": True, "external_hardware": True, "human_approval": False},
    )
    assert blocked["activation_eligible"] is False
    assert require_hardware_approval(blocked) is True
    approved = build_profile(
        domain="iot-ot",
        cleanup_demonstrated=True,
        constraints={"simulator_supported": True, "external_hardware": True, "human_approval": True},
    )
    assert approved["activation_eligible"] is True
    assert require_hardware_approval(approved) is False


def test_simulator_only_iot_profile_does_not_require_hardware_approval() -> None:
    profile = build_profile(
        domain="iot-ot",
        cleanup_demonstrated=True,
        constraints={"simulator_supported": True, "external_hardware": False, "human_approval": False},
    )
    assert profile["activation_eligible"] is True
    assert require_hardware_approval(profile) is False


def test_runtime_nonclaims_are_preserved() -> None:
    policy = yaml.safe_load((DOMAIN_DIR / "domain-policy.yaml").read_text())
    assert policy["activation"]["contract_eligibility_is_not_runtime_activation"] is True
    assert policy["iot_ot"]["external_hardware_requires_human_approval"] is True
    assert policy["runtime_status"] == {
        "kubernetes": "NOT_RUN",
        "identity": "NOT_RUN",
        "cloud": "NOT_RUN",
        "mobile": "NOT_RUN",
        "iot_ot": "NOT_RUN",
        "external_hardware": "NOT_RUN",
    }
