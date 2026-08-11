#!/usr/bin/env python3
"""Fail-closed verifier for a production Evidence Plane backend observation.

This module is provider-neutral. It does not provision storage, call a cloud API,
modify retention, delete evidence or persist Runner output. It validates a fresh,
normalized read-only observation of backend controls and requires independent
verification of the captured source-evidence reference and digest.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Protocol

import jsonschema
import yaml

ROOT = Path(__file__).resolve().parents[2]
HERE = ROOT / "deployment" / "runtime-promotion"
SCHEMA_PATH = HERE / "evidence-backend-attestation.schema.json"
DEFAULT_ATTESTATION = HERE / "templates" / "evidence-backend-attestation.example.yaml"

MAX_ATTESTATION_AGE = timedelta(minutes=15)
MAX_FUTURE_SKEW = timedelta(seconds=30)

_FORBIDDEN_SECRET_FIELDS = {
    "secret",
    "secret_key",
    "password",
    "passphrase",
    "token",
    "cookie",
    "credential",
    "credentials",
    "api_key",
    "access_key",
    "client_secret",
    "private_key",
}

REMAINING_EVIDENCE = (
    "LIVE_RUNNER_TO_EVIDENCE_HANDOFF_NOT_RUN",
    "LIVE_AUDIT_PERSISTENCE_NOT_RUN",
    "RETENTION_OPERATION_NOT_RUN",
    "BACKEND_TENANT_ISOLATION_NOT_PROVEN",
    "HUMAN_PROMOTION_REQUIRED",
)


class EvidenceBackendAttestationError(ValueError):
    """Stable fail-closed backend-attestation error."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


class EvidenceVerifier(Protocol):
    """Verify custody and integrity of the provider observation source artifact."""

    def verify(self, evidence_ref: str, sha256: str) -> bool:
        ...


class DenyAllEvidenceVerifier:
    """Default boundary: an attestation file is never trusted by presence alone."""

    def verify(self, evidence_ref: str, sha256: str) -> bool:
        del evidence_ref, sha256
        return False


@dataclass(frozen=True)
class EvidenceBackendAttestationResult:
    backend_attestation_checks_passed: bool
    promotion_allowed: bool
    runtime_status: str
    findings: tuple[str, ...]
    remaining_evidence: tuple[str, ...]
    backend_id: str
    deployment_scope: str
    immutability_mode: str
    source_evidence_verified: bool

    def as_dict(self) -> dict[str, Any]:
        return {
            "backend_attestation_checks_passed": self.backend_attestation_checks_passed,
            "promotion_allowed": self.promotion_allowed,
            "runtime_status": self.runtime_status,
            "findings": list(self.findings),
            "remaining_evidence": list(self.remaining_evidence),
            "backend_id": self.backend_id,
            "deployment_scope": self.deployment_scope,
            "immutability_mode": self.immutability_mode,
            "source_evidence_verified": self.source_evidence_verified,
        }


def _load_json(path: Path, code: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, UnicodeDecodeError) as exc:
        raise EvidenceBackendAttestationError(code, f"cannot load {path.name}") from exc
    if not isinstance(value, dict):
        raise EvidenceBackendAttestationError(code, f"{path.name} must contain an object")
    return value


def _load_yaml(path: Path, code: str) -> dict[str, Any]:
    try:
        value = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError, UnicodeDecodeError) as exc:
        raise EvidenceBackendAttestationError(code, f"cannot load {path.name}") from exc
    if not isinstance(value, dict):
        raise EvidenceBackendAttestationError(code, f"{path.name} must contain an object")
    return value


def _normalized_key(value: Any) -> str:
    return str(value).lower().replace("-", "_")


def _find_secret_fields(value: Any, path: str = "") -> list[str]:
    findings: list[str] = []
    if isinstance(value, Mapping):
        for key, nested in value.items():
            child = f"{path}.{key}" if path else str(key)
            if _normalized_key(key) in _FORBIDDEN_SECRET_FIELDS:
                findings.append(f"secret/private material field is forbidden: {child}")
            findings.extend(_find_secret_fields(nested, child))
    elif isinstance(value, list):
        for index, nested in enumerate(value):
            findings.extend(_find_secret_fields(nested, f"{path}[{index}]"))
    return findings


def _validate_schema(attestation: Mapping[str, Any]) -> None:
    schema = _load_json(SCHEMA_PATH, "ATTESTATION_SCHEMA_UNAVAILABLE")
    validator = jsonschema.Draft202012Validator(
        schema, format_checker=jsonschema.FormatChecker()
    )
    errors = sorted(validator.iter_errors(attestation), key=lambda error: list(error.path))
    if errors:
        first = errors[0]
        location = ".".join(str(part) for part in first.path) or "<root>"
        raise EvidenceBackendAttestationError(
            "ATTESTATION_INVALID", f"{location}: {first.message}"
        )
    secret_fields = _find_secret_fields(attestation)
    if secret_fields:
        raise EvidenceBackendAttestationError(
            "ATTESTATION_SECRET_MATERIAL_REFUSED", "; ".join(secret_fields)
        )


def load_attestation(path: Path = DEFAULT_ATTESTATION) -> dict[str, Any]:
    attestation = _load_yaml(path, "ATTESTATION_UNREADABLE")
    _validate_schema(attestation)
    return attestation


def _parse_observed_at(value: Any) -> datetime:
    if not isinstance(value, str):
        raise EvidenceBackendAttestationError(
            "ATTESTATION_TIMESTAMP_INVALID", "observed_at must be an RFC3339 timestamp"
        )
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise EvidenceBackendAttestationError(
            "ATTESTATION_TIMESTAMP_INVALID", "observed_at is invalid"
        ) from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise EvidenceBackendAttestationError(
            "ATTESTATION_TIMESTAMP_INVALID", "observed_at must be timezone-aware"
        )
    return parsed.astimezone(timezone.utc)


def verify_backend_attestation(
    attestation: Mapping[str, Any],
    *,
    evidence_verifier: EvidenceVerifier | None = None,
) -> EvidenceBackendAttestationResult:
    """Verify one fresh durable-backend observation without contacting the backend."""

    if not isinstance(attestation, Mapping):
        raise EvidenceBackendAttestationError(
            "ATTESTATION_INVALID", "backend attestation must be an object"
        )
    _validate_schema(attestation)

    findings: list[str] = []
    if attestation["observation_status"] != "OBSERVED":
        findings.append("production evidence backend observation has not run")
    else:
        observed_at = _parse_observed_at(attestation["observed_at"])
        now = datetime.now(timezone.utc)
        if observed_at > now + MAX_FUTURE_SKEW:
            findings.append("backend attestation timestamp is in the future")
        elif now - observed_at > MAX_ATTESTATION_AGE:
            findings.append("backend attestation is stale")

    required_values: tuple[tuple[str, Any, str], ...] = (
        ("deployment_scope", "PRODUCTION", "backend is not scoped to production"),
        ("backend_state", "active", "backend is not active"),
        ("encryption_at_rest", True, "encryption at rest is not enforced"),
        ("immutability_mode", "WORM_COMPLIANCE", "WORM compliance mode is not enforced"),
        ("retention_enforced", True, "retention enforcement is not active"),
        ("legal_hold_supported", True, "legal hold is not supported"),
        ("privileged_delete_bypass", False, "privileged delete bypass remains available"),
        ("public_access_blocked", True, "public access is not blocked"),
        ("overwrite_protected", True, "retained evidence overwrite protection is not enforced"),
        ("integrity_digest", "sha256", "integrity digest is not sha256"),
    )
    for field, expected, finding in required_values:
        if attestation[field] != expected:
            findings.append(finding)

    source_verified = False
    if attestation["observation_status"] == "OBSERVED":
        verifier = evidence_verifier or DenyAllEvidenceVerifier()
        evidence_ref = str(attestation["source_evidence_ref"])
        evidence_sha = str(attestation["source_evidence_sha256"])
        try:
            source_verified = bool(verifier.verify(evidence_ref, evidence_sha))
        except Exception:  # noqa: BLE001 - verifier internals do not cross boundary
            source_verified = False
        if not source_verified:
            findings.append("source backend observation evidence is not verified")

    return EvidenceBackendAttestationResult(
        backend_attestation_checks_passed=not findings,
        promotion_allowed=False,
        runtime_status="NOT_RUN",
        findings=tuple(findings),
        remaining_evidence=REMAINING_EVIDENCE,
        backend_id=str(attestation["backend_id"]),
        deployment_scope=str(attestation["deployment_scope"]),
        immutability_mode=str(attestation["immutability_mode"]),
        source_evidence_verified=source_verified,
    )


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--attestation", type=Path, default=DEFAULT_ATTESTATION)
    parser.add_argument("--json", action="store_true")
    parser.add_argument("command", choices=("check",))
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        result = verify_backend_attestation(load_attestation(args.attestation))
    except EvidenceBackendAttestationError as exc:
        payload = {
            "backend_attestation_checks_passed": False,
            "promotion_allowed": False,
            "runtime_status": "NOT_RUN",
            "code": exc.code,
            "error": str(exc),
        }
        if args.json:
            print(json.dumps(payload, sort_keys=True))
        else:
            print(f"FAIL {exc.code}: {exc}", file=sys.stderr)
        return 2

    if args.json:
        print(json.dumps(result.as_dict(), sort_keys=True))
    elif result.backend_attestation_checks_passed:
        print("OK durable Evidence Plane backend observation satisfies the contract")
    else:
        for finding in result.findings:
            print(f"FAIL {finding}", file=sys.stderr)
    return 0 if result.backend_attestation_checks_passed else 2


if __name__ == "__main__":
    raise SystemExit(main())
