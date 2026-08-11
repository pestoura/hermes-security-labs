#!/usr/bin/env python3
"""Fail-closed verifier for Evidence Plane backend tenant-isolation evidence.

The verifier is provider-neutral and read-only. It does not provision tenants,
create namespaces, mutate policy, perform backend I/O or know customer names.
Tenant identities are represented only by distinct SHA-256 digests. A positive
observation requires independently verified source evidence covering both the
backend isolation controls and bounded cross-tenant negative tests.
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
SCHEMA_PATH = HERE / "evidence-backend-tenant-isolation-attestation.schema.json"
DEFAULT_ATTESTATION = (
    HERE / "templates" / "evidence-backend-tenant-isolation-attestation.example.yaml"
)

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
    "customer_name",
    "tenant_name",
}

REMAINING_EVIDENCE = (
    "PRODUCTION_BACKEND_DEPLOYMENT_NOT_PROVEN_BY_REPOSITORY_TEST",
    "LIVE_TENANT_ISOLATION_OBSERVATION_NOT_RUN",
    "LIVE_RUNNER_TO_EVIDENCE_HANDOFF_NOT_RUN",
    "LIVE_AUDIT_PERSISTENCE_NOT_RUN",
    "HUMAN_PROMOTION_REQUIRED",
)


class TenantIsolationAttestationError(ValueError):
    """Stable fail-closed tenant-isolation attestation error."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


class EvidenceVerifier(Protocol):
    def verify(self, evidence_ref: str, sha256: str) -> bool:
        ...


class DenyAllEvidenceVerifier:
    def verify(self, evidence_ref: str, sha256: str) -> bool:
        del evidence_ref, sha256
        return False


@dataclass(frozen=True)
class TenantIsolationAttestationResult:
    tenant_isolation_checks_passed: bool
    promotion_allowed: bool
    runtime_status: str
    findings: tuple[str, ...]
    remaining_evidence: tuple[str, ...]
    backend_id: str
    subject_tenant_sha256: str
    peer_tenant_sha256: str
    source_evidence_verified: bool

    def as_dict(self) -> dict[str, Any]:
        return {
            "tenant_isolation_checks_passed": self.tenant_isolation_checks_passed,
            "promotion_allowed": self.promotion_allowed,
            "runtime_status": self.runtime_status,
            "findings": list(self.findings),
            "remaining_evidence": list(self.remaining_evidence),
            "backend_id": self.backend_id,
            "subject_tenant_sha256": self.subject_tenant_sha256,
            "peer_tenant_sha256": self.peer_tenant_sha256,
            "source_evidence_verified": self.source_evidence_verified,
        }


def _load_json(path: Path, code: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, UnicodeDecodeError) as exc:
        raise TenantIsolationAttestationError(code, f"cannot load {path.name}") from exc
    if not isinstance(value, dict):
        raise TenantIsolationAttestationError(code, f"{path.name} must contain an object")
    return value


def _load_yaml(path: Path, code: str) -> dict[str, Any]:
    try:
        value = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError, UnicodeDecodeError) as exc:
        raise TenantIsolationAttestationError(code, f"cannot load {path.name}") from exc
    if not isinstance(value, dict):
        raise TenantIsolationAttestationError(code, f"{path.name} must contain an object")
    return value


def _normalized_key(value: Any) -> str:
    return str(value).lower().replace("-", "_")


def _find_forbidden_fields(value: Any, path: str = "") -> list[str]:
    findings: list[str] = []
    if isinstance(value, Mapping):
        for key, nested in value.items():
            child = f"{path}.{key}" if path else str(key)
            if _normalized_key(key) in _FORBIDDEN_SECRET_FIELDS:
                findings.append(f"secret or identifying field is forbidden: {child}")
            findings.extend(_find_forbidden_fields(nested, child))
    elif isinstance(value, list):
        for index, nested in enumerate(value):
            findings.extend(_find_forbidden_fields(nested, f"{path}[{index}]"))
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
        raise TenantIsolationAttestationError(
            "ATTESTATION_INVALID", f"{location}: {first.message}"
        )
    forbidden = _find_forbidden_fields(attestation)
    if forbidden:
        raise TenantIsolationAttestationError(
            "ATTESTATION_IDENTIFYING_OR_SECRET_MATERIAL_REFUSED", "; ".join(forbidden)
        )


def load_attestation(path: Path = DEFAULT_ATTESTATION) -> dict[str, Any]:
    attestation = _load_yaml(path, "ATTESTATION_UNREADABLE")
    _validate_schema(attestation)
    return attestation


def _parse_observed_at(value: Any) -> datetime:
    if not isinstance(value, str):
        raise TenantIsolationAttestationError(
            "ATTESTATION_TIMESTAMP_INVALID", "observed_at must be an RFC3339 timestamp"
        )
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise TenantIsolationAttestationError(
            "ATTESTATION_TIMESTAMP_INVALID", "observed_at is invalid"
        ) from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise TenantIsolationAttestationError(
            "ATTESTATION_TIMESTAMP_INVALID", "observed_at must be timezone-aware"
        )
    return parsed.astimezone(timezone.utc)


def verify_tenant_isolation_attestation(
    attestation: Mapping[str, Any],
    *,
    evidence_verifier: EvidenceVerifier | None = None,
) -> TenantIsolationAttestationResult:
    """Verify one tenant-isolation observation without touching the backend."""

    if not isinstance(attestation, Mapping):
        raise TenantIsolationAttestationError(
            "ATTESTATION_INVALID", "tenant-isolation attestation must be an object"
        )
    _validate_schema(attestation)

    findings: list[str] = []
    if attestation["subject_tenant_sha256"] == attestation["peer_tenant_sha256"]:
        findings.append("subject and peer tenant digests must identify distinct tenants")

    if attestation["observation_status"] != "OBSERVED":
        findings.append("production tenant-isolation observation has not run")
    else:
        observed_at = _parse_observed_at(attestation["observed_at"])
        now = datetime.now(timezone.utc)
        if observed_at > now + MAX_FUTURE_SKEW:
            findings.append("tenant-isolation attestation timestamp is in the future")
        elif now - observed_at > MAX_ATTESTATION_AGE:
            findings.append("tenant-isolation attestation is stale")

    required_values: tuple[tuple[str, Any, str], ...] = (
        ("namespace_isolated", True, "tenant namespace isolation is not enforced"),
        ("access_policy_isolated", True, "tenant access-policy isolation is not enforced"),
        (
            "encryption_context_isolated",
            True,
            "tenant encryption context is not isolated",
        ),
        (
            "shared_writable_namespace",
            False,
            "tenants share a writable evidence namespace",
        ),
        ("cross_tenant_list_result", "DENIED", "cross-tenant list was not denied"),
        ("cross_tenant_read_result", "DENIED", "cross-tenant read was not denied"),
        ("cross_tenant_write_result", "DENIED", "cross-tenant write was not denied"),
    )
    for field, expected, finding in required_values:
        if attestation[field] != expected:
            findings.append(finding)

    source_verified = False
    if attestation["observation_status"] == "OBSERVED":
        verifier = evidence_verifier or DenyAllEvidenceVerifier()
        try:
            source_verified = bool(
                verifier.verify(
                    str(attestation["source_evidence_ref"]),
                    str(attestation["source_evidence_sha256"]),
                )
            )
        except Exception:  # noqa: BLE001 - verifier internals do not cross boundary
            source_verified = False
        if not source_verified:
            findings.append("source tenant-isolation evidence is not verified")

    return TenantIsolationAttestationResult(
        tenant_isolation_checks_passed=not findings,
        promotion_allowed=False,
        runtime_status="NOT_RUN",
        findings=tuple(findings),
        remaining_evidence=REMAINING_EVIDENCE,
        backend_id=str(attestation["backend_id"]),
        subject_tenant_sha256=str(attestation["subject_tenant_sha256"]),
        peer_tenant_sha256=str(attestation["peer_tenant_sha256"]),
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
        result = verify_tenant_isolation_attestation(load_attestation(args.attestation))
    except TenantIsolationAttestationError as exc:
        payload = {
            "tenant_isolation_checks_passed": False,
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
    elif result.tenant_isolation_checks_passed:
        print("OK Evidence Plane backend tenant-isolation observation satisfies the contract")
    else:
        for finding in result.findings:
            print(f"FAIL {finding}", file=sys.stderr)
    return 0 if result.tenant_isolation_checks_passed else 2


if __name__ == "__main__":
    raise SystemExit(main())
