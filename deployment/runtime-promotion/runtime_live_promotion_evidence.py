#!/usr/bin/env python3
"""Fail-closed verifier for phased live-promotion evidence packages.

The package aggregates content-addressed evidence references for one exact
WebGoat L1 candidate. It does not collect evidence, run a target operation,
change policy, update the validation campaign or grant promotion authority.

PRE_PROMOTION packages prove that machine/runtime prerequisites are assembled
for explicit Human-in-the-Loop review. POST_EFFECT packages bind the approved
promotion decision, the effective minimum policy set and the one bounded live
effect/persistence/reset acceptance. Both phases remain evidence only.

The required gate contract is resolved from the accepted assurance profile
(``platform/assurance/current-assurance-profile.yaml`` / ADR-0011 Option B):

- LAB_L1 requires the common signer/trust/peer/evidence-integrity controls but
  may omit only the external production WORM backend and production tenant-
  isolation gates;
- PROD requires those two additional gates;
- an absent, invalid or internally inconsistent profile fails closed to PROD;
- when ``requires_hash_chain`` is true, ``HASH_CHAIN_SEAL`` is required for both
  phases and is verified with the frozen Evidence Plane seal primitive.

For backward evidence compatibility, LAB_L1 packages may still carry the two
PROD-only gates. They are optional under LAB_L1: an absent/NOT_RUN optional gate
does not block completion, while a supplied FAIL or unverified optional gate
still blocks. PROD never treats them as optional.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

import jsonschema
import yaml

ROOT = Path(__file__).resolve().parents[2]
HERE = ROOT / "deployment" / "runtime-promotion"
SCHEMA_PATH = HERE / "live-promotion-evidence-package.schema.json"
DEFAULT_PACKAGE = HERE / "templates" / "live-promotion-evidence-package.example.yaml"
DEFAULT_CAMPAIGN = ROOT / "validation" / "VAL-HSL-RUNNER-L1-LIVE-PROMOTION.yaml"
ASSURANCE_PROFILE_PATH = ROOT / "platform" / "assurance" / "current-assurance-profile.yaml"
ASSURANCE_PROFILE_MODULE_PATH = ROOT / "platform" / "assurance" / "assurance_profile.py"
EVIDENCE_CHAIN_SCHEMA_PATH = ROOT / "platform" / "schemas" / "evidence-chain.schema.json"

EXPECTED_CANDIDATE = {
    "environment_id": "webgoat",
    "adapter_id": "webgoat-l1",
    "capability_id": "web.discovery.headers",
    "intrusiveness_level": "L1",
}

COMMON_PRE_PROMOTION_GATES = frozenset(
    {
        "GATEWAY_ADMISSION_REOBSERVATION",
        "BRIDGE_REVISION_REOBSERVATION",
        "HOST_IDENTITY_SOCKET_TRUST",
        "USER_NAMESPACE_MAPPING",
        "SIGNER_PROVIDER_ATTESTATION",
        "RECEIPT_DELIVERY",
        "UNAUTHORIZED_PEER_NEGATIVE",
    }
)
PROD_ONLY_PRE_PROMOTION_GATES = frozenset(
    {
        "EVIDENCE_BACKEND_CONTROLS",
        "EVIDENCE_TENANT_ISOLATION",
    }
)
# Historical/accepted superset retained for callers and previously assembled
# packages. The verifier below resolves the actual required subset by profile.
PRE_PROMOTION_GATES = COMMON_PRE_PROMOTION_GATES | PROD_ONLY_PRE_PROMOTION_GATES
POST_EFFECT_GATES = frozenset(
    {
        "HITL_PROMOTION_DECISION",
        "PROMOTED_POLICY_SET",
        "LIVE_RUNNER_OUTCOME_PERSISTENCE",
        "LIVE_DISPATCH_AUDIT_PERSISTENCE",
        "WEBGOAT_L1_EFFECT_RESET",
    }
)
REQUIRED_GATES = {
    "PRE_PROMOTION": PRE_PROMOTION_GATES,
    "POST_EFFECT": POST_EFFECT_GATES,
}

HASH_CHAIN_SEAL_GATE = "HASH_CHAIN_SEAL"
LAB_L1 = "LAB_L1"
PROD = "PROD"

_SEAL_MODULE = None
_ASSURANCE_MODULE = None


class LiveEvidencePackageError(ValueError):
    """Stable fail-closed live evidence package error."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


class EvidenceVerifier(Protocol):
    """Verify custody/integrity of one referenced evidence result artifact."""

    def verify(self, evidence_ref: str, sha256: str) -> bool:
        ...


class DenyAllEvidenceVerifier:
    """Default boundary: evidence references are never trusted implicitly."""

    def verify(self, evidence_ref: str, sha256: str) -> bool:
        del evidence_ref, sha256
        return False


@dataclass(frozen=True)
class LiveEvidencePackageResult:
    phase: str
    package_valid: bool
    package_complete: bool
    promotion_allowed: bool
    recommendation: str
    next_review: str
    blockers: tuple[str, ...]
    verified_evidence_count: int
    required_gate_count: int

    def as_dict(self) -> dict[str, Any]:
        return {
            "phase": self.phase,
            "package_valid": self.package_valid,
            "package_complete": self.package_complete,
            "promotion_allowed": self.promotion_allowed,
            "recommendation": self.recommendation,
            "next_review": self.next_review,
            "blockers": list(self.blockers),
            "verified_evidence_count": self.verified_evidence_count,
            "required_gate_count": self.required_gate_count,
        }


def _load_json(path: Path, code: str) -> dict[str, Any]:
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, UnicodeDecodeError) as exc:
        raise LiveEvidencePackageError(code, f"cannot load {path.name}") from exc
    if not isinstance(document, dict):
        raise LiveEvidencePackageError(code, f"{path.name} must contain an object")
    return document


def _load_yaml(path: Path, code: str) -> dict[str, Any]:
    try:
        document = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError, UnicodeDecodeError) as exc:
        raise LiveEvidencePackageError(code, f"cannot load {path.name}") from exc
    if not isinstance(document, dict):
        raise LiveEvidencePackageError(code, f"{path.name} must contain an object")
    return document


def _validate_schema(package: Mapping[str, Any]) -> None:
    schema = _load_json(SCHEMA_PATH, "PACKAGE_SCHEMA_UNAVAILABLE")
    validator = jsonschema.Draft202012Validator(
        schema, format_checker=jsonschema.FormatChecker()
    )
    errors = sorted(validator.iter_errors(package), key=lambda error: list(error.path))
    if errors:
        first = errors[0]
        location = ".".join(str(part) for part in first.path) or "<root>"
        raise LiveEvidencePackageError(
            "PACKAGE_INVALID", f"{location}: {first.message}"
        )


def load_package(path: Path = DEFAULT_PACKAGE) -> dict[str, Any]:
    package = _load_yaml(path, "PACKAGE_UNREADABLE")
    _validate_schema(package)
    return package


def load_campaign(path: Path = DEFAULT_CAMPAIGN) -> dict[str, Any]:
    return _load_yaml(path, "CAMPAIGN_UNREADABLE")


def _load_assurance_profile_module():
    """Load the canonical ADR-0011 evaluator instead of duplicating its rules."""
    global _ASSURANCE_MODULE
    if _ASSURANCE_MODULE is not None:
        return _ASSURANCE_MODULE
    spec = importlib.util.spec_from_file_location(
        "_hsl_live_assurance_profile", ASSURANCE_PROFILE_MODULE_PATH
    )
    if not spec or not spec.loader:
        raise RuntimeError("cannot load canonical assurance-profile evaluator")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    _ASSURANCE_MODULE = module
    return module


def _resolve_assurance() -> tuple[str, bool]:
    """Resolve the accepted profile, failing closed to PROD on any inconsistency."""
    try:
        document = yaml.safe_load(
            ASSURANCE_PROFILE_PATH.read_text(encoding="utf-8")
        )
        if not isinstance(document, Mapping):
            return (PROD, True)

        assurance = _load_assurance_profile_module()
        assurance.validate_profile_schema(document)
        evaluation = assurance.validate_profile_document(document)
        if evaluation.failures:
            return (PROD, True)

        declared = document.get("evaluation")
        if not isinstance(declared, Mapping):
            return (PROD, True)
        requires_hash_chain = declared.get("requires_hash_chain")
        if not isinstance(requires_hash_chain, bool):
            return (PROD, True)

        resolved = str(evaluation.resolved_profile)
        if resolved not in (LAB_L1, PROD):
            return (PROD, True)
        return (resolved, requires_hash_chain)
    except Exception:  # noqa: BLE001 - profile defects must only strengthen gates
        return (PROD, True)


def profile_required_gate_ids(
    phase: str,
    assurance_profile: str,
    requires_hash_chain: bool = True,
) -> frozenset[str]:
    """Return the true mandatory gate set for one explicit assurance profile."""
    if phase not in REQUIRED_GATES:
        raise LiveEvidencePackageError("PACKAGE_INVALID", f"unsupported phase {phase}")

    # Explicit invalid profile is also fail-closed to PROD.
    resolved = assurance_profile if assurance_profile in (LAB_L1, PROD) else PROD
    if phase == "PRE_PROMOTION":
        base = set(COMMON_PRE_PROMOTION_GATES)
        if resolved == PROD:
            base.update(PROD_ONLY_PRE_PROMOTION_GATES)
    else:
        base = set(POST_EFFECT_GATES)

    if requires_hash_chain:
        base.add(HASH_CHAIN_SEAL_GATE)
    return frozenset(base)


def profile_optional_gate_ids(phase: str, assurance_profile: str) -> frozenset[str]:
    """Return accepted-but-not-required gates for backward-compatible LAB evidence."""
    resolved = assurance_profile if assurance_profile in (LAB_L1, PROD) else PROD
    if phase == "PRE_PROMOTION" and resolved == LAB_L1:
        return PROD_ONLY_PRE_PROMOTION_GATES
    return frozenset()


def _expected_gate_ids(phase: str, requires_hash_chain: bool) -> frozenset[str]:
    """Backward-compatible accepted gate superset used by historical callers.

    New profile-aware code must use ``profile_required_gate_ids``. Keeping this
    superset avoids invalidating already-assembled LAB_L1 evidence packages that
    carried the two PROD-only gates before CHG-HSL-066.
    """
    base = set(REQUIRED_GATES[phase])
    if requires_hash_chain:
        base.add(HASH_CHAIN_SEAL_GATE)
    return frozenset(base)


def required_gate_ids(phase: str, requires_hash_chain: bool = True) -> frozenset[str]:
    """Legacy public projection of the accepted gate superset (compatibility)."""
    return _expected_gate_ids(phase, requires_hash_chain)


def _load_evidence_chain_seal_module():
    """Load the frozen LAB_L1 evidence-chain seal primitive standalone (no package)."""
    global _SEAL_MODULE
    if _SEAL_MODULE is not None:
        return _SEAL_MODULE
    path = ROOT / "platform" / "evidence-plane" / "seal.py"
    spec = importlib.util.spec_from_file_location("_hsl_live_hash_seal", path)
    if not spec or not spec.loader:
        raise LiveEvidencePackageError(
            "CHAIN_SEAL_PRIMITIVE_UNAVAILABLE",
            "cannot load frozen evidence-chain seal primitive",
        )
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    _SEAL_MODULE = module
    return module


def _verify_hash_chain_seal_gate(
    package: Mapping[str, Any], gate: Mapping[str, Any]
) -> bool:
    """Verify the HASH_CHAIN_SEAL gate against the frozen chain+seal primitive.

    Fail-closed: any schema violation, tamper condition, or digest-binding
    mismatch returns False. The seal is self-verifying (no external verifier),
    so a valid sealed document passes regardless of the delegated evidence
    verifier.
    """
    document = package.get("evidence_chain_document")
    if not isinstance(document, Mapping):
        return False
    try:
        schema = _load_json(EVIDENCE_CHAIN_SCHEMA_PATH, "CHAIN_SCHEMA_UNAVAILABLE")
    except LiveEvidencePackageError:
        return False
    validator = jsonschema.Draft202012Validator(
        schema, format_checker=jsonschema.FormatChecker()
    )
    if list(validator.iter_errors(document)):
        return False
    try:
        seal_module = _load_evidence_chain_seal_module()
        result = seal_module.verify_seal(document)
    except Exception:  # noqa: BLE001 - primitive internals do not cross boundary
        return False
    if not isinstance(result, Mapping) or not result.get("verified"):
        return False
    if str(gate.get("evidence_sha256")) != str(result.get("chain_state_digest_sha256")):
        return False
    return True


def _campaign_candidate_commit(campaign: Mapping[str, Any]) -> str:
    candidate = campaign.get("candidate")
    if not isinstance(candidate, Mapping):
        raise LiveEvidencePackageError(
            "CAMPAIGN_INVALID", "campaign candidate must be an object"
        )
    commit = candidate.get("commit")
    if not isinstance(commit, str) or len(commit) != 40:
        raise LiveEvidencePackageError(
            "CAMPAIGN_INVALID", "campaign candidate commit must be an exact SHA"
        )
    return commit


def _gate_map(package: Mapping[str, Any]) -> dict[str, Mapping[str, Any]]:
    gates = package["gates"]
    if not isinstance(gates, list):
        raise LiveEvidencePackageError("PACKAGE_INVALID", "gates must be a list")
    result: dict[str, Mapping[str, Any]] = {}
    for gate in gates:
        if not isinstance(gate, Mapping):
            raise LiveEvidencePackageError("PACKAGE_INVALID", "gate must be an object")
        gate_id = str(gate["gate_id"])
        if gate_id in result:
            raise LiveEvidencePackageError(
                "PACKAGE_INVALID", f"duplicate gate identifier {gate_id}"
            )
        result[gate_id] = gate
    return result


def verify_live_evidence_package(
    package: Mapping[str, Any],
    campaign: Mapping[str, Any],
    *,
    evidence_verifier: EvidenceVerifier | None = None,
) -> LiveEvidencePackageResult:
    """Verify a phased evidence package without converting evidence to approval."""

    if not isinstance(package, Mapping):
        raise LiveEvidencePackageError("PACKAGE_INVALID", "package must be an object")
    _validate_schema(package)

    phase = str(package["phase"])
    assurance_profile, requires_hash_chain = _resolve_assurance()
    required_gates = profile_required_gate_ids(
        phase, assurance_profile, requires_hash_chain
    )
    optional_gates = profile_optional_gate_ids(phase, assurance_profile)
    allowed_gates = required_gates | optional_gates

    gates = _gate_map(package)
    actual_gate_ids = frozenset(gates)
    missing = sorted(required_gates - actual_gate_ids)
    extra = sorted(actual_gate_ids - allowed_gates)
    if missing or extra:
        raise LiveEvidencePackageError(
            "PACKAGE_GATE_SET_INVALID",
            f"gate set mismatch missing={missing} extra={extra}",
        )

    candidate = package["candidate"]
    if not isinstance(candidate, Mapping):
        raise LiveEvidencePackageError("PACKAGE_INVALID", "candidate must be an object")
    for field, expected in EXPECTED_CANDIDATE.items():
        if candidate.get(field) != expected:
            raise LiveEvidencePackageError(
                "PACKAGE_CANDIDATE_MISMATCH", f"candidate {field} is not canonical"
            )

    package_status = str(package["package_status"])
    if package_status == "NOT_RUN":
        if any(gate["result"] != "NOT_RUN" for gate in gates.values()):
            raise LiveEvidencePackageError(
                "PACKAGE_INVALID", "NOT_RUN package cannot contain executed gates"
            )
    else:
        campaign_commit = _campaign_candidate_commit(campaign)
        if candidate.get("repository_commit") != campaign_commit:
            raise LiveEvidencePackageError(
                "PACKAGE_CANDIDATE_MISMATCH",
                "assembled package is not bound to the campaign candidate commit",
            )

    verifier = evidence_verifier or DenyAllEvidenceVerifier()
    blockers: list[str] = []
    verified_count = 0

    # Evaluate every supplied allowed gate. Optional LAB_L1 gates are ignored only
    # when explicitly NOT_RUN; supplied evidence can only tighten the outcome.
    for gate_id in sorted(actual_gate_ids):
        gate = gates[gate_id]
        gate_result = str(gate["result"])
        is_optional = gate_id in optional_gates

        if gate_result == "NOT_RUN":
            if not is_optional:
                blockers.append(f"{gate_id}:NOT_RUN")
            continue

        if gate_id == HASH_CHAIN_SEAL_GATE:
            verified = _verify_hash_chain_seal_gate(package, gate)
        else:
            evidence_ref = str(gate["evidence_ref"])
            evidence_sha = str(gate["evidence_sha256"])
            verified = False
            try:
                verified = bool(verifier.verify(evidence_ref, evidence_sha))
            except Exception:  # noqa: BLE001 - verifier internals do not cross boundary
                verified = False

        if verified:
            verified_count += 1
        else:
            blockers.append(f"{gate_id}:EVIDENCE_UNVERIFIED")

        if gate_result != "PASS":
            blockers.append(f"{gate_id}:{gate_result}")

    complete = package_status == "ASSEMBLED" and not blockers
    if complete and phase == "PRE_PROMOTION":
        next_review = "HUMAN_PROMOTION_REVIEW_REQUIRED"
    elif complete:
        next_review = "CAMPAIGN_ACCEPTANCE_REVIEW_REQUIRED"
    else:
        next_review = "EVIDENCE_COLLECTION_REQUIRED"

    # Compatibility: count all supplied allowed gates. For a minimal LAB_L1
    # package this equals the true required count; historical superset packages
    # continue to report their evaluated gate count without being invalidated.
    evaluated_gate_count = len(actual_gate_ids)

    return LiveEvidencePackageResult(
        phase=phase,
        package_valid=True,
        package_complete=complete,
        promotion_allowed=False,
        recommendation="HOLD",
        next_review=next_review,
        blockers=tuple(blockers),
        verified_evidence_count=verified_count,
        required_gate_count=evaluated_gate_count,
    )


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--package", type=Path, default=DEFAULT_PACKAGE)
    parser.add_argument("--campaign", type=Path, default=DEFAULT_CAMPAIGN)
    parser.add_argument("--json", action="store_true")
    parser.add_argument("command", choices=("check",))
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        result = verify_live_evidence_package(
            load_package(args.package), load_campaign(args.campaign)
        )
    except LiveEvidencePackageError as exc:
        payload = {
            "package_valid": False,
            "package_complete": False,
            "promotion_allowed": False,
            "recommendation": "HOLD",
            "code": exc.code,
            "error": str(exc),
        }
        if args.json:
            print(json.dumps(payload, sort_keys=True))
        else:
            print(f"FAIL-CLOSED [{exc.code}] {exc}")
        return 2

    if args.json:
        print(json.dumps(result.as_dict(), sort_keys=True))
    else:
        print(
            f"phase={result.phase} package_complete={str(result.package_complete).lower()} "
            f"promotion_allowed=false recommendation={result.recommendation} "
            f"next_review={result.next_review}"
        )
        for blocker in result.blockers:
            print(f"- {blocker}")
    return 0 if result.package_complete else 2


if __name__ == "__main__":
    raise SystemExit(main())
