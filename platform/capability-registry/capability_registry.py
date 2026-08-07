from __future__ import annotations

from copy import deepcopy
from typing import Any, Mapping

PROFILES = {
    "web-api",
    "devsecops",
    "ai-mcp",
    "exploitation",
    "kubernetes",
    "identity",
    "cloud",
    "mobile",
    "iot-ot",
}
PROMOTION_STATES = {"development", "candidate", "stable", "quarantined", "revoked"}


class CapabilityRegistryError(ValueError):
    """Fail-closed capability-registry contract violation."""


def validate_capability(capability: Mapping[str, Any]) -> None:
    if capability.get("profile") not in PROFILES:
        raise CapabilityRegistryError("unsupported capability profile")
    if capability.get("promotion") not in PROMOTION_STATES:
        raise CapabilityRegistryError("unsupported promotion state")
    state = capability.get("state")
    authorization = capability.get("authorization")
    compatibility = capability.get("compatibility")
    supply_chain = capability.get("supply_chain")
    if not all(isinstance(value, Mapping) for value in (state, authorization, compatibility, supply_chain)):
        raise CapabilityRegistryError("incomplete capability evidence")
    blockers = supply_chain.get("scan_blockers")
    if not isinstance(blockers, int) or isinstance(blockers, bool) or blockers < 0:
        raise CapabilityRegistryError("scan_blockers must be a non-negative integer")
    if capability.get("revoked") is True and capability.get("promotion") != "revoked":
        raise CapabilityRegistryError("revoked capability must use revoked promotion state")


def stable_gate_failures(capability: Mapping[str, Any]) -> list[str]:
    validate_capability(capability)
    failures: list[str] = []
    state = capability["state"]
    authorization = capability["authorization"]
    compatibility = capability["compatibility"]
    supply_chain = capability["supply_chain"]
    for field in ("installed", "executable", "functionally_tested"):
        if state.get(field) is not True:
            failures.append(field)
    if authorization.get("authorized") is not True or not authorization.get("policy_id"):
        failures.append("authorized")
    if compatibility.get("compatible") is not True or not compatibility.get("protocol_version"):
        failures.append("compatible")
    for field in ("sbom", "signature", "provenance"):
        if not supply_chain.get(field):
            failures.append(field)
    if supply_chain.get("scan_blockers") != 0:
        failures.append("scan_blockers")
    if capability.get("revoked") is True:
        failures.append("revoked")
    if capability.get("promotion") in {"quarantined", "revoked"}:
        failures.append("promotion_state")
    return sorted(set(failures))


def is_usable(capability: Mapping[str, Any]) -> bool:
    """Production usability is intentionally stricter than registry presence."""
    try:
        return capability.get("promotion") == "stable" and not stable_gate_failures(capability)
    except CapabilityRegistryError:
        return False


def promote(capability: Mapping[str, Any], target: str) -> dict[str, Any]:
    validate_capability(capability)
    if target not in PROMOTION_STATES:
        raise CapabilityRegistryError("unsupported promotion target")
    if capability.get("revoked") is True:
        raise CapabilityRegistryError("revoked capability cannot be promoted")
    if capability.get("promotion") == "quarantined" and target == "stable":
        raise CapabilityRegistryError("quarantined capability requires review before stable")
    promoted = deepcopy(dict(capability))
    promoted["promotion"] = target
    if target == "stable":
        failures = stable_gate_failures(promoted)
        if failures:
            raise CapabilityRegistryError(f"stable promotion gates failed: {','.join(failures)}")
    return promoted


def quarantine(capability: Mapping[str, Any], *, reason: str) -> dict[str, Any]:
    validate_capability(capability)
    if not reason.strip():
        raise CapabilityRegistryError("quarantine reason is required")
    value = deepcopy(dict(capability))
    value["promotion"] = "quarantined"
    value["quarantine_reason"] = reason
    return value


def revoke(capability: Mapping[str, Any], *, reason: str) -> dict[str, Any]:
    validate_capability(capability)
    if not reason.strip():
        raise CapabilityRegistryError("revocation reason is required")
    value = deepcopy(dict(capability))
    value["revoked"] = True
    value["promotion"] = "revoked"
    value["revocation_reason"] = reason
    return value
