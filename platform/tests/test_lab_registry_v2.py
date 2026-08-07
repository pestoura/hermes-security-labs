from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import jsonschema
import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
LAB_DIR = ROOT / "platform" / "lab-registry-v2"

spec = importlib.util.spec_from_file_location("lab_registry_v2", LAB_DIR / "lab_registry.py")
assert spec and spec.loader
module = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = module
spec.loader.exec_module(module)

LabRegistryError = module.LabRegistryError
build_manifest = module.build_manifest
reset_fingerprint = module.reset_fingerprint
select_lab = module.select_lab
validate_isolation = module.validate_isolation


def _states():
    return {
        "VULNERABLE": {"positive_control": "synthetic vulnerable finding", "negative_control": "synthetic unrelated control"},
        "MITIGATED": {"positive_control": "synthetic mitigation observed", "negative_control": "synthetic vulnerable behavior absent"},
        "FIXED": {"positive_control": "synthetic fixed behavior", "negative_control": "synthetic vulnerability absent"},
    }


def _manifest(**overrides):
    values = {
        "family": "synthetic-web-family",
        "variant": "v1",
        "lab_type": "single-service",
        "states": _states(),
        "cpu_limit": 1.0,
        "memory_mb": 256,
        "ttl_seconds": 600,
        "egress_allowlist": [],
        "reset_seed": "synthetic-seed-v1",
        "maturity": "L2",
        "generated_or_untrusted": False,
        "isolated_build": True,
        "required_capabilities": ["web-api"],
    }
    values.update(overrides)
    return build_manifest(**values)


def test_manifest_requires_all_three_states_and_controls() -> None:
    manifest = _manifest()
    assert set(manifest["states"]) == {"VULNERABLE", "MITIGATED", "FIXED"}
    for state in manifest["states"].values():
        assert state["positive_control"]
        assert state["negative_control"]
    schema = json.loads((LAB_DIR / "lab-manifest.schema.json").read_text())
    jsonschema.Draft202012Validator(schema).validate(manifest)


def test_isolation_forbids_privileged_host_network_socket_and_mounts() -> None:
    manifest = _manifest()
    assert validate_isolation(manifest) is True
    assert manifest["isolation"] == {
        "privileged": False,
        "host_network": False,
        "docker_socket": False,
        "host_mounts": False,
    }
    broken = dict(manifest)
    broken["isolation"] = dict(manifest["isolation"], privileged=True)
    assert validate_isolation(broken) is False


def test_egress_is_default_deny_with_explicit_allowlist() -> None:
    manifest = _manifest(egress_allowlist=["synthetic.example:443"])
    assert manifest["egress"]["default"] == "deny"
    assert manifest["egress"]["allowlist"] == ["synthetic.example:443"]


def test_generated_or_untrusted_lab_requires_isolated_build() -> None:
    with pytest.raises(LabRegistryError):
        _manifest(generated_or_untrusted=True, isolated_build=False)
    manifest = _manifest(generated_or_untrusted=True, isolated_build=True)
    assert manifest["isolated_build"] is True


def test_reset_fingerprint_is_deterministic() -> None:
    first = reset_fingerprint(family="synthetic-web-family", variant="v1", reset_seed="synthetic-seed-v1")
    second = reset_fingerprint(family="synthetic-web-family", variant="v1", reset_seed="synthetic-seed-v1")
    assert first == second
    assert first == _manifest()["reset_fingerprint"]


def test_selection_is_capability_and_state_aware() -> None:
    low = _manifest(variant="v1", maturity="L1")
    high = _manifest(variant="v2", maturity="L3")
    selected = select_lab(
        [low, high],
        family="synthetic-web-family",
        state="VULNERABLE",
        available_capabilities=["web-api"],
    )
    assert selected["variant"] == "v2"
    assert selected["selected_state"] == "VULNERABLE"
    with pytest.raises(LabRegistryError):
        select_lab([high], family="synthetic-web-family", state="VULNERABLE", available_capabilities=[])


def test_cleanup_proof_and_runtime_nonclaims_are_preserved() -> None:
    manifest = _manifest()
    assert manifest["cleanup_proof_required"] is True
    policy = yaml.safe_load((LAB_DIR / "lab-policy.yaml").read_text())
    assert policy["isolation"]["egress_default"] == "deny"
    assert policy["runtime_status"] == {
        "container_labs": "NOT_RUN",
        "vm_labs": "NOT_RUN",
        "kubernetes_labs": "NOT_RUN",
        "cloud_sandboxes": "NOT_RUN",
        "external_hardware": "NOT_RUN",
        "deterministic_reset_observed": "NOT_RUN",
        "cleanup_proof_observed": "NOT_RUN",
    }
