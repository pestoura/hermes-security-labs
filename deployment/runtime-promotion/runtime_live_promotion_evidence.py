#!/usr/bin/env python3
"""Fail-closed verifier for phased live-promotion evidence packages.

The package aggregates content-addressed evidence references for one exact
WebGoat L1 candidate. It does not collect evidence, run a target operation,
change policy, update the validation campaign or grant promotion authority.

PRE_PROMOTION packages prove that machine/runtime prerequisites are assembled
for explicit Human-in-the-Loop review. POST_EFFECT packages bind the approved
promotion decision, the effective minimum policy set and the one bounded live
effect/persistence/reset acceptance. Both phases remain evidence only.

Gate composition is resolved from the ACCEPTED assurance profile (ADR-0011
Option B, `platform/assurance/assurance_profile.py`), never hardcoded per phase:

- PROD requires every gate, including the external WORM/durable evidence-backend
  gate and the production tenant-isolation gate;
- LAB_L1 may omit ONLY those two gates (`requires_external_worm_backend: false`,
  `requires_tenant_isolation: false`). They remain ACCEPTED-but-optional inputs:
  if present and executed they are still verified and a FAIL still blocks.
- an absent/invalid/unparsable profile declaration fails closed to PROD, so a
  broken profile document can never remove a required gate.

Phase 2 (deliberately NOT wired here) will bind the frozen evidence hash-chain
seal interface to a dedicated gate; see `PHASE2_SEAL_GATE_HOOK`.
"""

from __future__ import annotations

import argparse
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
ASSURANCE_DIR = ROOT / "platform" / "assurance"
DEFAULT_ASSURANCE_PROFILE = ASSURANCE_DIR / "current-assurance-profile.yaml"

if str(ASSURANCE_DIR) not in sys.path:
    sys.path.insert(0, str(ASSURANCE_DIR))

from assurance_profile import (  # noqa: E402
    LAB_L1,
    PROD,
    AssuranceProfileEvaluation,
    validate_profile_document,
)

EXPECTED_CANDIDATE = {
    "environment_id": "webgoat",
    "adapter_id": "webgoat-l1",
    "capability_id": "web.discovery.headers",
    "intrusiveness_level": "L1",
}

PHASES = ("PRE_PROMOTION", "POST_EFFECT")
# Profiles this verifier composes gate sets for (ADR-0011 Option B).
SUPPORTED_ASSURANCE_PROFILES = (LAB_L1, PROD)

# Gates required under every assurance profile (PROD baseline, never relaxed).
BASE_PRE_PROMOTION_GATES = frozenset(
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
BASE_POST_EFFECT_GATES = frozenset(
    {
        "HITL_PROMOTION_DECISION",
        "PROMOTED_POLICY_SET",
        "LIVE_RUNNER_OUTCOME_PERSISTENCE",
        "LIVE_DISPATCH_AUDIT_PERSISTENCE",
        "WEBGOAT_L1_EFFECT_RESET",
    }
)

# Gates whose requirement is conditioned on one assurance-profile requirement key.
# LAB_L1 sets both keys False (ADR-0011 Option B); PROD keeps both True.
PROFILE_CONDITIONAL_GATES: dict[str, tuple[str, str]] = {
    "EVIDENCE_BACKEND_CONTROLS": ("PRE_PROMOTION", "requires_external_worm_backend"),
    "EVIDENCE_TENANT_ISOLATION": ("PRE_PROMOTION", "requires_tenant_isolation"),
}

# Phase 2 placeholder: the frozen evidence hash-chain seal interface (PR #369,
# platform/evidence-plane/seal.py) is NOT wired into gate composition yet. Wiring
# it here now would change the exact gate set of already-accepted LAB_L1/PROD
# packages, so phase 2 must introduce it deliberately with its own change record.
# Keeping the hook name and mapping stable makes that a single-line activation.
PHASE2_SEAL_GATE_HOOK = "EVIDENCE_HASH_CHAIN_SEAL"
PHASE2_SEAL_GATE_REQUIREMENT_KEY = "requires_hash_chain"
PHASE2_SEAL_GATE_ENABLED = False

# Backwards-compatible PROD-equivalent projections (a profile-agnostic caller sees
# the strictest set). Profile-aware callers must use resolve_required_gates().
PRE_PROMOTION_GATES = BASE_PRE_PROMOTION_GATES | frozenset(
    gate
    for gate, (phase, _key) in PROFILE_CONDITIONAL_GATES.items()
    if phase == "PRE_PROMOTION"
)
POST_EFFECT_GATES = BASE_POST_EFFECT_GATES | frozenset(
    gate
    for gate, (phase, _key) in PROFILE_CONDITIONAL_GATES.items()
    if phase == "POST_EFFECT"
)
REQUIRED_GATES = {
    "PRE_PROMOTION": PRE_PROMOTION_GATES,
    "POST_EFFECT": POST_EFFECT_GATES,
}
BASE_REQUIRED_GATES = {
    "PRE_PROMOTION": BASE_PRE_PROMOTION_GATES,
    "POST_EFFECT": BASE_POST_EFFECT_GATES,
}


def load_assurance_profile(
    path: Path = DEFAULT_ASSURANCE_PROFILE,
) -> AssuranceProfileEvaluation:
    """Load the accepted assurance profile, failing closed to PROD on any defect."""

    try:
        document = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError, UnicodeDecodeError):
        document = {}
    if not isinstance(document, Mapping):
        document = {}
    return validate_profile_document(document)


def resolve_required_gates(
    phase: str, profile: AssuranceProfileEvaluation
) -> frozenset[str]:
    """Compose the required gate set for one phase from the resolved profile."""

    if phase not in BASE_REQUIRED_GATES:
        raise LiveEvidencePackageError(
            "PACKAGE_INVALID", f"unknown evidence package phase {phase}"
        )
    required = set(BASE_REQUIRED_GATES[phase])
    conditional = {
        "requires_external_worm_backend": profile.requires_external_worm_backend,
        "requires_tenant_isolation": profile.requires_tenant_isolation,
    }
    for gate, (gate_phase, key) in PROFILE_CONDITIONAL_GATES.items():
        if gate_phase != phase:
            continue
        if conditional.get(key, True):
            required.add(gate)
    if PHASE2_SEAL_GATE_ENABLED:  # pragma: no cover - phase 2 activation
        raise LiveEvidencePackageError(
            "PACKAGE_INVALID", "phase 2 seal gate wiring is not implemented"
        )
    return frozenset(required)


def optional_gates(phase: str, profile: AssuranceProfileEvaluation) -> frozenset[str]:
    """Gates not required under this profile but still verified when present."""

    return frozenset(REQUIRED_GATES[phase]) - resolve_required_gates(phase, profile)


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
    assurance_profile: str = PROD
    required_gates: tuple[str, ...] = ()
    optional_gates_present: tuple[str, ...] = ()

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
            "assurance_profile": self.assurance_profile,
            "required_gates": list(self.required_gates),
            "optional_gates_present": list(self.optional_gates_present),
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
    assurance_profile: AssuranceProfileEvaluation | None = None,
) -> LiveEvidencePackageResult:
    """Verify a phased evidence package without converting evidence to approval."""

    if not isinstance(package, Mapping):
        raise LiveEvidencePackageError("PACKAGE_INVALID", "package must be an object")
    _validate_schema(package)

    profile = assurance_profile or load_assurance_profile()
    phase = str(package["phase"])
    expected_gates = resolve_required_gates(phase, profile)
    permitted_optional = optional_gates(phase, profile)
    gates = _gate_map(package)
    actual_gate_ids = frozenset(gates)
    missing = sorted(expected_gates - actual_gate_ids)
    extra = sorted(actual_gate_ids - expected_gates - permitted_optional)
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
    optional_present = sorted(actual_gate_ids & permitted_optional)

    # Required gates gate completeness. Optional (profile-omitted) gates that are
    # nevertheless present are still integrity-verified and a FAIL still blocks;
    # they can never *relax* the outcome, only tighten it.
    for gate_id in sorted(expected_gates) + optional_present:
        gate = gates[gate_id]
        gate_result = str(gate["result"])
        if gate_result == "NOT_RUN":
            if gate_id in expected_gates:
                blockers.append(f"{gate_id}:NOT_RUN")
            continue

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

    return LiveEvidencePackageResult(
        phase=phase,
        package_valid=True,
        package_complete=complete,
        promotion_allowed=False,
        recommendation="HOLD",
        next_review=next_review,
        blockers=tuple(blockers),
        verified_evidence_count=verified_count,
        required_gate_count=len(expected_gates),
        assurance_profile=profile.resolved_profile,
        required_gates=tuple(sorted(expected_gates)),
        optional_gates_present=tuple(optional_present),
    )


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--package", type=Path, default=DEFAULT_PACKAGE)
    parser.add_argument("--campaign", type=Path, default=DEFAULT_CAMPAIGN)
    parser.add_argument(
        "--assurance-profile", type=Path, default=DEFAULT_ASSURANCE_PROFILE
    )
    parser.add_argument("--json", action="store_true")
    parser.add_argument("command", choices=("check",))
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        result = verify_live_evidence_package(
            load_package(args.package),
            load_campaign(args.campaign),
            assurance_profile=load_assurance_profile(args.assurance_profile),
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
            f"phase={result.phase} assurance_profile={result.assurance_profile} "
            f"package_complete={str(result.package_complete).lower()} "
            f"promotion_allowed=false recommendation={result.recommendation} "
            f"next_review={result.next_review}"
        )
        for blocker in result.blockers:
            print(f"- {blocker}")
    return 0 if result.package_complete else 2


if __name__ == "__main__":
    raise SystemExit(main())
