from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from typing import Any, Iterable, Mapping

LAB_TYPES = {"fixture", "single-service", "multi-service", "attack-path", "kubernetes", "vm", "identity", "cloud-sandbox", "external-hardware"}
STATES = {"VULNERABLE", "MITIGATED", "FIXED"}
MATURITY = {"L0", "L1", "L2", "L3", "L4", "L5"}


class LabRegistryError(ValueError):
    """Fail-closed Lab Registry v2 contract violation."""


def _digest(value: Mapping[str, Any]) -> str:
    raw = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()
    return hashlib.sha256(raw).hexdigest()


def build_manifest(
    *,
    family: str,
    variant: str,
    lab_type: str,
    states: Mapping[str, Mapping[str, str]],
    cpu_limit: float,
    memory_mb: int,
    ttl_seconds: int,
    egress_allowlist: Iterable[str],
    reset_seed: str,
    maturity: str,
    generated_or_untrusted: bool,
    isolated_build: bool,
    required_capabilities: Iterable[str] | None = None,
) -> dict[str, Any]:
    if not family or not variant or lab_type not in LAB_TYPES:
        raise LabRegistryError("family, variant and supported lab type are required")
    if set(states) != STATES:
        raise LabRegistryError("every lab family must define VULNERABLE, MITIGATED and FIXED states")
    normalized_states: dict[str, dict[str, str]] = {}
    for state, controls in states.items():
        positive = controls.get("positive_control")
        negative = controls.get("negative_control")
        if not positive or not negative:
            raise LabRegistryError("every state requires positive and negative controls")
        normalized_states[state] = {"positive_control": positive, "negative_control": negative}
    if isinstance(cpu_limit, bool) or not isinstance(cpu_limit, (int, float)) or cpu_limit <= 0:
        raise LabRegistryError("cpu limit must be positive")
    if isinstance(memory_mb, bool) or not isinstance(memory_mb, int) or memory_mb < 64:
        raise LabRegistryError("memory limit is too small")
    if isinstance(ttl_seconds, bool) or not isinstance(ttl_seconds, int) or ttl_seconds < 60:
        raise LabRegistryError("TTL must be at least 60 seconds")
    if not reset_seed or maturity not in MATURITY:
        raise LabRegistryError("reset seed and supported maturity are required")
    if generated_or_untrusted and not isolated_build:
        raise LabRegistryError("generated or untrusted labs require isolated build")
    seed = {"family": family, "variant": variant, "lab_type": lab_type, "states": normalized_states, "reset_seed": reset_seed}
    return {
        "schema_version": "2.0",
        "lab_id": f"lab_{_digest(seed)[:32]}",
        "family": family,
        "variant": variant,
        "lab_type": lab_type,
        "states": normalized_states,
        "isolation": {"privileged": False, "host_network": False, "docker_socket": False, "host_mounts": False},
        "resources": {"cpu_limit": float(cpu_limit), "memory_mb": memory_mb},
        "ttl_seconds": ttl_seconds,
        "egress": {"default": "deny", "allowlist": sorted(set(egress_allowlist))},
        "reset_seed": reset_seed,
        "reset_fingerprint": reset_fingerprint(family=family, variant=variant, reset_seed=reset_seed),
        "maturity": maturity,
        "cleanup_proof_required": True,
        "generated_or_untrusted": generated_or_untrusted,
        "isolated_build": isolated_build,
        "required_capabilities": sorted(set(required_capabilities or [])),
    }


def reset_fingerprint(*, family: str, variant: str, reset_seed: str) -> str:
    if not family or not variant or not reset_seed:
        raise LabRegistryError("deterministic reset requires family, variant and reset seed")
    return _digest({"family": family, "variant": variant, "reset_seed": reset_seed})


def validate_isolation(manifest: Mapping[str, Any]) -> bool:
    isolation = manifest.get("isolation")
    if not isinstance(isolation, Mapping):
        return False
    return all(isolation.get(field) is False for field in ("privileged", "host_network", "docker_socket", "host_mounts"))


def select_lab(
    manifests: Iterable[Mapping[str, Any]],
    *,
    family: str,
    state: str,
    lab_type: str | None = None,
    available_capabilities: Iterable[str] | None = None,
) -> dict[str, Any]:
    if state not in STATES:
        raise LabRegistryError("unsupported lab state")
    available = set(available_capabilities or [])
    candidates: list[dict[str, Any]] = []
    for manifest in manifests:
        if manifest.get("family") != family:
            continue
        if state not in manifest.get("states", {}):
            continue
        if lab_type and manifest.get("lab_type") != lab_type:
            continue
        if not validate_isolation(manifest):
            continue
        required = set(manifest.get("required_capabilities", []))
        if not required.issubset(available):
            continue
        candidates.append(deepcopy(dict(manifest)))
    if not candidates:
        raise LabRegistryError("no compatible lab candidate")
    candidates.sort(key=lambda item: (item.get("maturity", "L0"), item.get("variant", "")), reverse=True)
    selected = candidates[0]
    selected["selected_state"] = state
    return selected
