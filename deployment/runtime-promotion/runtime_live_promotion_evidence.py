#!/usr/bin/env python3
"""Fail-closed verifier for phased live-promotion evidence packages.

The package aggregates content-addressed evidence references for one exact
WebGoat L1 candidate. It does not collect evidence, run a target operation,
change policy, update the validation campaign or grant promotion authority.

PRE_PROMOTION packages prove that machine/runtime prerequisites are assembled
for explicit Human-in-the-Loop review. POST_EFFECT packages bind the approved
promotion decision, the effective minimum policy set and the one bounded live
effect/persistence/reset acceptance. Both phases remain evidence only.
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

EXPECTED_CANDIDATE = {
    "environment_id": "webgoat",
    "adapter_id": "webgoat-l1",
    "capability_id": "web.discovery.headers",
    "intrusiveness_level": "L1",
}

PRE_PROMOTION_GATES = frozenset(
    {
        "GATEWAY_ADMISSION_REOBSERVATION",
        "BRIDGE_REVISION_REOBSERVATION",
        "HOST_IDENTITY_SOCKET_TRUST",
        "USER_NAMESPACE_MAPPING",
        "SIGNER_PROVIDER_ATTESTATION",
        "RECEIPT_DELIVERY",
        "UNAUTHORIZED_PEER_NEGATIVE",
        "EVIDENCE_BACKEND_CONTROLS",
        "EVIDENCE_TENANT_ISOLATION",
    }
)
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
    expected_gates = REQUIRED_GATES[phase]
    gates = _gate_map(package)
    actual_gate_ids = frozenset(gates)
    if actual_gate_ids != expected_gates:
        missing = sorted(expected_gates - actual_gate_ids)
        extra = sorted(actual_gate_ids - expected_gates)
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

    for gate_id in sorted(expected_gates):
        gate = gates[gate_id]
        gate_result = str(gate["result"])
        if gate_result == "NOT_RUN":
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
