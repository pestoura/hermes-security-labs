"""Evidence-backed activation gate for SVP2-L-01 domain expansion."""
from __future__ import annotations

from typing import Any, Mapping


class DomainActivationEvidenceError(ValueError):
    pass


def validate_activation_evidence(
    *,
    profile: Mapping[str, Any],
    cleanup_evidence: Mapping[str, Any],
    cloud_lease: Mapping[str, Any] | None = None,
    hardware_approval: Mapping[str, Any] | None = None,
) -> None:
    profile_id = profile.get("profile_id")
    domain = profile.get("domain")
    constraints = profile.get("constraints")
    if not isinstance(profile_id, str) or not profile_id.startswith("dp_"):
        raise DomainActivationEvidenceError("PROFILE_ID_INVALID")
    if profile.get("activation_eligible") is not True or profile.get("activated") is not False:
        raise DomainActivationEvidenceError("PROFILE_NOT_ACTIVATION_ELIGIBLE")
    if not isinstance(constraints, Mapping):
        raise DomainActivationEvidenceError("PROFILE_CONSTRAINTS_REQUIRED")

    if cleanup_evidence.get("profile_id") != profile_id:
        raise DomainActivationEvidenceError("CLEANUP_PROFILE_MISMATCH")
    if cleanup_evidence.get("state") != "VERIFIED":
        raise DomainActivationEvidenceError("CLEANUP_NOT_VERIFIED")
    if not cleanup_evidence.get("cleanup_proof_id"):
        raise DomainActivationEvidenceError("CLEANUP_PROOF_REQUIRED")
    if cleanup_evidence.get("zero_residue") is not True:
        raise DomainActivationEvidenceError("ZERO_RESIDUE_NOT_PROVEN")

    if domain == "cloud":
        if not isinstance(cloud_lease, Mapping):
            raise DomainActivationEvidenceError("CLOUD_LEASE_EVIDENCE_REQUIRED")
        if cloud_lease.get("profile_id") != profile_id or cloud_lease.get("ephemeral") is not True:
            raise DomainActivationEvidenceError("CLOUD_LEASE_NOT_EPHEMERAL")
        lease_ttl = cloud_lease.get("ttl_seconds")
        lease_budget = cloud_lease.get("budget")
        if isinstance(lease_ttl, bool) or not isinstance(lease_ttl, int) or lease_ttl <= 0:
            raise DomainActivationEvidenceError("CLOUD_LEASE_TTL_INVALID")
        if lease_ttl > constraints.get("ttl_seconds", 0):
            raise DomainActivationEvidenceError("CLOUD_LEASE_TTL_EXCEEDS_PROFILE")
        if isinstance(lease_budget, bool) or not isinstance(lease_budget, (int, float)) or lease_budget <= 0:
            raise DomainActivationEvidenceError("CLOUD_LEASE_BUDGET_INVALID")
        if float(lease_budget) > float(constraints.get("budget", 0)):
            raise DomainActivationEvidenceError("CLOUD_LEASE_BUDGET_EXCEEDS_PROFILE")

    if domain == "iot-ot" and constraints.get("external_hardware") is True:
        if not isinstance(hardware_approval, Mapping):
            raise DomainActivationEvidenceError("HARDWARE_APPROVAL_REQUIRED")
        if hardware_approval.get("profile_id") != profile_id:
            raise DomainActivationEvidenceError("HARDWARE_APPROVAL_PROFILE_MISMATCH")
        if hardware_approval.get("decision") != "APPROVE" or not hardware_approval.get("reviewed_by"):
            raise DomainActivationEvidenceError("EXPLICIT_HARDWARE_APPROVAL_REQUIRED")
        if not hardware_approval.get("decision_id"):
            raise DomainActivationEvidenceError("HARDWARE_APPROVAL_DECISION_ID_REQUIRED")


def activation_evidence_allowed(**kwargs: Any) -> bool:
    try:
        validate_activation_evidence(**kwargs)
        return True
    except DomainActivationEvidenceError:
        return False
