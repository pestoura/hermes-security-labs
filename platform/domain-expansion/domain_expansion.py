from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from typing import Any, Mapping

DOMAINS = {"kubernetes", "identity", "cloud", "mobile", "iot-ot"}


class DomainExpansionError(ValueError):
    """Fail-closed domain-expansion contract violation."""


def _digest(value: Mapping[str, Any]) -> str:
    raw = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()
    return hashlib.sha256(raw).hexdigest()


def build_profile(*, domain: str, cleanup_demonstrated: bool, constraints: Mapping[str, Any]) -> dict[str, Any]:
    if domain not in DOMAINS:
        raise DomainExpansionError("unsupported expansion domain")
    normalized = deepcopy(dict(constraints))
    _validate_constraints(domain, normalized)
    eligible = cleanup_demonstrated is True and _domain_specific_eligible(domain, normalized)
    seed = {"domain": domain, "cleanup_demonstrated": cleanup_demonstrated, "constraints": normalized}
    return {
        "schema_version": "1.0",
        "profile_id": f"dp_{_digest(seed)[:32]}",
        "domain": domain,
        "cleanup_demonstrated": cleanup_demonstrated,
        "constraints": normalized,
        "activation_eligible": eligible,
        "activated": False,
    }


def _validate_constraints(domain: str, constraints: Mapping[str, Any]) -> None:
    required: dict[str, set[str]] = {
        "kubernetes": {"unique_cluster", "ephemeral_kubeconfig", "ttl_seconds"},
        "identity": {"snapshot_required", "rollback_required", "resource_budget"},
        "cloud": {"ephemeral_credentials", "budget", "ttl_seconds"},
        "mobile": {"device_lifecycle", "adb_scoped", "analysis_sidecar_bounded"},
        "iot-ot": {"simulator_supported", "external_hardware", "human_approval"},
    }
    if set(constraints) != required[domain]:
        raise DomainExpansionError("domain constraints do not match canonical profile")
    if domain in {"kubernetes", "cloud"}:
        ttl = constraints["ttl_seconds"]
        if isinstance(ttl, bool) or not isinstance(ttl, int) or ttl < 60:
            raise DomainExpansionError("TTL must be at least 60 seconds")
    if domain == "identity":
        budget = constraints["resource_budget"]
        if isinstance(budget, bool) or not isinstance(budget, (int, float)) or budget <= 0:
            raise DomainExpansionError("identity resource budget must be positive")
    if domain == "cloud":
        budget = constraints["budget"]
        if isinstance(budget, bool) or not isinstance(budget, (int, float)) or budget <= 0:
            raise DomainExpansionError("cloud budget must be positive")


def _domain_specific_eligible(domain: str, constraints: Mapping[str, Any]) -> bool:
    if domain == "kubernetes":
        return constraints["unique_cluster"] is True and constraints["ephemeral_kubeconfig"] is True
    if domain == "identity":
        return constraints["snapshot_required"] is True and constraints["rollback_required"] is True
    if domain == "cloud":
        return constraints["ephemeral_credentials"] is True
    if domain == "mobile":
        return all(constraints[field] is True for field in ("device_lifecycle", "adb_scoped", "analysis_sidecar_bounded"))
    if domain == "iot-ot":
        if constraints["external_hardware"] is True:
            return constraints["human_approval"] is True
        return constraints["simulator_supported"] is True
    return False


def activation_eligible(profile: Mapping[str, Any]) -> bool:
    return profile.get("activation_eligible") is True and profile.get("activated") is False


def require_hardware_approval(profile: Mapping[str, Any]) -> bool:
    if profile.get("domain") != "iot-ot":
        return False
    constraints = profile.get("constraints", {})
    return constraints.get("external_hardware") is True and constraints.get("human_approval") is not True
