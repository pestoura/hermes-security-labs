from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
PATH = ROOT / "platform/domain-expansion/activation_evidence.py"
spec = importlib.util.spec_from_file_location("domain_activation_evidence", PATH)
assert spec and spec.loader
module = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = module
spec.loader.exec_module(module)


def _profile(domain: str, constraints: dict) -> dict:
    return {
        "profile_id": "dp_" + "a" * 32,
        "domain": domain,
        "activation_eligible": True,
        "activated": False,
        "constraints": constraints,
    }


def _cleanup(profile_id: str) -> dict:
    return {
        "profile_id": profile_id,
        "state": "VERIFIED",
        "cleanup_proof_id": "cleanup-proof-001",
        "zero_residue": True,
    }


def test_activation_requires_verified_zero_residue_cleanup_proof() -> None:
    profile = _profile("kubernetes", {"unique_cluster": True, "ephemeral_kubeconfig": True, "ttl_seconds": 600})
    cleanup = _cleanup(profile["profile_id"])
    module.validate_activation_evidence(profile=profile, cleanup_evidence=cleanup)
    cleanup["zero_residue"] = False
    with pytest.raises(module.DomainActivationEvidenceError, match="ZERO_RESIDUE_NOT_PROVEN"):
        module.validate_activation_evidence(profile=profile, cleanup_evidence=cleanup)


def test_cloud_lease_must_be_ephemeral_and_within_profile_ttl_and_budget() -> None:
    profile = _profile("cloud", {"ephemeral_credentials": True, "budget": 25.0, "ttl_seconds": 900})
    cleanup = _cleanup(profile["profile_id"])
    lease = {"profile_id": profile["profile_id"], "ephemeral": True, "budget": 20.0, "ttl_seconds": 600}
    module.validate_activation_evidence(profile=profile, cleanup_evidence=cleanup, cloud_lease=lease)
    with pytest.raises(module.DomainActivationEvidenceError, match="CLOUD_LEASE_TTL_EXCEEDS_PROFILE"):
        module.validate_activation_evidence(profile=profile, cleanup_evidence=cleanup, cloud_lease={**lease, "ttl_seconds": 1200})
    with pytest.raises(module.DomainActivationEvidenceError, match="CLOUD_LEASE_BUDGET_EXCEEDS_PROFILE"):
        module.validate_activation_evidence(profile=profile, cleanup_evidence=cleanup, cloud_lease={**lease, "budget": 30.0})


def test_external_hardware_requires_recorded_explicit_human_approval() -> None:
    profile = _profile("iot-ot", {"simulator_supported": True, "external_hardware": True, "human_approval": True})
    cleanup = _cleanup(profile["profile_id"])
    with pytest.raises(module.DomainActivationEvidenceError, match="HARDWARE_APPROVAL_REQUIRED"):
        module.validate_activation_evidence(profile=profile, cleanup_evidence=cleanup)
    approval = {
        "profile_id": profile["profile_id"],
        "decision": "APPROVE",
        "reviewed_by": "reviewer-01",
        "decision_id": "decision-001",
    }
    module.validate_activation_evidence(profile=profile, cleanup_evidence=cleanup, hardware_approval=approval)


def test_boolean_profile_claim_without_cleanup_evidence_is_not_sufficient() -> None:
    profile = _profile("mobile", {"device_lifecycle": True, "adb_scoped": True, "analysis_sidecar_bounded": True})
    assert module.activation_evidence_allowed(profile=profile, cleanup_evidence={}) is False
