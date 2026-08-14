"""Provider-neutral assurance-profile evaluation contract for first L1 lab promotion.

The module turns the accepted ADR-0011 decision (Option B) into repository-only,
machine-checkable evidence about *which* assurance requirement set applies to a
lab promotion decision. It deliberately performs no runtime mutation, selects no
signer/supplier/provider, and never promotes anything.

Fail-closed rule (mirrors ADR-0004 fail-safe evaluation):
- an absent, invalid or unparsable `assurance_profile` resolves to PROD;
- PROD is never weaker than the current production-equivalent behaviour;
- LAB_L1 MAY omit ONLY the external production WORM backend and the multi-tenant
  production tenant-isolation gates. It MUST NOT relax signer/trust, SO_PEERCRED
  negative test + audit, evidence integrity + hash-chain, PRE/POST packages,
  mandatory reset, or request-bound HITL.
- `promotion_allowed` is always False here; live promotion remains a separate,
  explicitly request-bound human decision path (ADR-0008).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

import yaml
from jsonschema import Draft7Validator

_SCHEMA_PATH = None


def _schema_path() -> Any:
    global _SCHEMA_PATH
    if _SCHEMA_PATH is None:
        from pathlib import Path

        # Resides next to the runtime-profile.schema.json, under platform/schemas.
        _SCHEMA_PATH = Path(__file__).resolve().parent.parent / "schemas" / "assurance-profile.schema.json"
    return _SCHEMA_PATH


PROFILES = ("LAB_L1", "PROD")
# Machine-readable projection of the ADR-0011 Option B requirement table.
# `prod_value` is the value REQUIRED under PROD (every control on; no auto-supplier).
# LAB_L1 is allowed to set only the controls in _LAB_L1_OMISSIBLE to False.
_REQUIREMENTS: dict[str, tuple[str, bool]] = {
    "requires_external_signer": ("external signer", True),
    "requires_purpose_bound_trust_store": ("purpose-bound public trust store", True),
    "requires_non_exportable_private_key": ("non-exportable private key", True),
    "requires_explicit_trust_store": ("explicit trust store", True),
    "requires_so_peerccred_with_audit": ("enabled SO_PEERCRED identity mapping + audit", True),
    "requires_audit_sink": ("audit sink", True),
    "requires_tamper_evident_evidence": ("tamper-evident content-addressed evidence", True),
    "requires_hash_chain": ("append-only hash chain / sealed packages", True),
    "requires_pre_promotion_package": ("PRE_PROMOTION evidence package", True),
    "requires_post_effect_package": ("POST_EFFECT evidence package", True),
    "requires_mandatory_reset": ("mandatory reset / zero-residue", True),
    "requires_request_bound_hitl": ("request-bound human-in-the-loop decision", True),
    "allows_automatic_supplier_choice": ("automatic supplier/provider choice", False),
    "requires_external_worm_backend": ("external production WORM/durable evidence backend", True),
    "requires_tenant_isolation": ("production tenant-isolation / cross-tenant negatives", True),
}

# Requirement keys that LAB_L1 is explicitly allowed to omit (set False). PROD keeps them True.
_LAB_L1_OMISSIBLE = {"requires_external_worm_backend", "requires_tenant_isolation"}

PROD = "PROD"
LAB_L1 = "LAB_L1"


def _required_by_profile(profile: str) -> dict[str, bool]:
    required: dict[str, bool] = {}
    for key, (_label, prod_value) in _REQUIREMENTS.items():
        if profile == LAB_L1 and key in _LAB_L1_OMISSIBLE:
            required[key] = False
        else:
            required[key] = prod_value
    return required


class AssuranceProfileError(ValueError):
    """Fail-closed profile evaluation violation."""


@dataclass(frozen=True)
class AssuranceProfileEvaluation:
    raw_profile: str | None
    resolved_profile: str
    requires_external_worm_backend: bool
    requires_tenant_isolation: bool
    promotion_allowed: bool
    failures: tuple[str, ...]

    def as_dict(self) -> dict[str, Any]:
        return {
            "raw_profile": self.raw_profile,
            "resolved_profile": self.resolved_profile,
            "requires_external_worm_backend": self.requires_external_worm_backend,
            "requires_tenant_isolation": self.requires_tenant_isolation,
            "promotion_allowed": self.promotion_allowed,
            "failures": list(self.failures),
        }


def _evaluate_requirements(profile: str) -> dict[str, bool]:
    out: dict[str, bool] = {}
    for key, (_label, prod_value) in _REQUIREMENTS.items():
        if profile == LAB_L1 and key in _LAB_L1_OMISSIBLE:
            out[key] = False
        else:
            out[key] = prod_value
    return out


def resolve_profile(raw: Any) -> str:
    """Fail-closed profile resolution: absent/invalid -> PROD."""
    if raw in PROFILES:
        return raw  # type: ignore[return-value]
    return PROD


def validate_profile_document(document: Mapping[str, Any]) -> AssuranceProfileEvaluation:
    """Validate a profile declaration and fail closed on any inconsistency."""
    raw = document.get("assurance_profile")
    resolved = resolve_profile(raw)
    requirements = _required_by_profile(resolved)
    failures: list[str] = []

    if raw not in PROFILES:
        failures.append(
            f"invalid or missing assurance_profile {raw!r}; failing closed to PROD"
        )

    # Compare declared evaluation against the required-by-profile contract.
    declared = document.get("evaluation") or {}
    for key, expected in requirements.items():
        got = declared.get(key)
        if got != expected:
            failures.append(
                f"{resolved} requirement {key} expected {expected}, got {got!r}"
            )

    return AssuranceProfileEvaluation(
        raw_profile=raw if isinstance(raw, str) else None,
        resolved_profile=resolved,
        requires_external_worm_backend=bool(requirements["requires_external_worm_backend"]),
        requires_tenant_isolation=bool(requirements["requires_tenant_isolation"]),
        promotion_allowed=False,
        failures=tuple(failures),
    )


def load_profile(path: Any) -> AssuranceProfileEvaluation:
    """Load and validate a profile YAML/JSON declaration from a path."""
    from pathlib import Path

    data = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    if not isinstance(data, Mapping):
        raise AssuranceProfileError("assurance profile document must be a mapping")
    return validate_profile_document(data)


def validate_profile_schema(document: Mapping[str, Any]) -> None:
    """Validate against platform/schemas/assurance-profile.schema.json (draft-07)."""
    schema = yaml.safe_load(_schema_path().read_text(encoding="utf-8"))
    errors = sorted(Draft7Validator(schema).iter_errors(document), key=lambda e: e.path)
    if errors:
        raise AssuranceProfileError(
            "schema violation: " + "; ".join(e.message for e in errors)
        )
