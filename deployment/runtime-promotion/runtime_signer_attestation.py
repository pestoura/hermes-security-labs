#!/usr/bin/env python3
"""Fail-closed TB1 external signer observation attestation verifier.

The verifier does not contact KMS/HSM/Vault/PKCS#11 and never reads private key
material. It validates a normalized read-only provider observation against the
accepted TB1 deployment descriptor and the public key already approved in the
Runner trust store.

An OBSERVED envelope is accepted only when an injected EvidenceVerifier confirms
that the source provider-metadata artifact exists with the declared SHA-256. The
committed example remains NOT_RUN and the CLI has no implicit evidence verifier,
so repository presence can never become a live attestation by itself.
"""

from __future__ import annotations

import argparse
import base64
import binascii
import hashlib
import importlib.util
import json
import sys
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Mapping, Protocol, Sequence

import jsonschema
import yaml

ROOT = Path(__file__).resolve().parents[2]
HERE = ROOT / "deployment" / "runtime-promotion"
ATTESTATION_SCHEMA = HERE / "tb1-signer-attestation.schema.json"
DEFAULT_ATTESTATION = HERE / "templates" / "tb1-signer-attestation.example.yaml"
DEFAULT_DEPLOYMENT_DESCRIPTOR = (
    HERE / "templates" / "tb1-authorization-deployment-descriptor.example.yaml"
)
TB1_PREFLIGHT_PATH = HERE / "tb1_authorization_preflight.py"

MAX_ATTESTATION_AGE = timedelta(minutes=5)
MAX_FUTURE_SKEW = timedelta(seconds=30)

_FORBIDDEN_SECRET_FIELDS = {
    "private_key",
    "privatekey",
    "secret",
    "secret_key",
    "seed",
    "passphrase",
    "password",
    "token",
    "cookie",
    "credential",
    "credentials",
    "api_key",
    "access_key",
    "client_secret",
}

REMAINING_EVIDENCE = (
    "HOST_IDENTITY_SOCKET_TRUST_EVIDENCE_NOT_OBSERVED",
    "USER_NAMESPACE_MAPPING_NOT_OBSERVED",
    "UNAUTHORIZED_PEER_NEGATIVE_TEST_NOT_RUN",
    "LIVE_AUDIT_SINK_NOT_OBSERVED",
    "LIVE_RUNNER_EFFECT_NOT_RUN",
)


class SignerAttestationError(ValueError):
    """Stable fail-closed signer-attestation error."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


class EvidenceVerifier(Protocol):
    """Verify custody/integrity of the provider observation source artifact."""

    def verify(self, evidence_ref: str, sha256: str) -> bool:
        ...


class DenyAllEvidenceVerifier:
    """Default boundary: no external evidence is trusted implicitly."""

    def verify(self, evidence_ref: str, sha256: str) -> bool:
        del evidence_ref, sha256
        return False


@dataclass(frozen=True)
class SignerAttestationResult:
    signer_attestation_checks_passed: bool
    promotion_allowed: bool
    runtime_status: str
    findings: tuple[str, ...]
    remaining_evidence: tuple[str, ...]
    provider_kind: str
    provider_ref: str
    key_id: str
    algorithm: str
    public_key_spki_sha256: str
    source_evidence_verified: bool

    def as_dict(self) -> dict[str, Any]:
        return {
            "signer_attestation_checks_passed": self.signer_attestation_checks_passed,
            "promotion_allowed": self.promotion_allowed,
            "runtime_status": self.runtime_status,
            "findings": list(self.findings),
            "remaining_evidence": list(self.remaining_evidence),
            "provider_kind": self.provider_kind,
            "provider_ref": self.provider_ref,
            "key_id": self.key_id,
            "algorithm": self.algorithm,
            "public_key_spki_sha256": self.public_key_spki_sha256,
            "source_evidence_verified": self.source_evidence_verified,
        }


def _load_module(name: str, path: Path) -> Any:
    existing = sys.modules.get(name)
    if existing is not None:
        return existing
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:  # pragma: no cover - packaging defect
        raise RuntimeError(f"cannot load canonical module {path.name}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


tb1_preflight = _load_module("runtime_signer_attestation_tb1_preflight", TB1_PREFLIGHT_PATH)


def _load_json(path: Path, code: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, UnicodeDecodeError) as exc:
        raise SignerAttestationError(code, f"cannot load {path.name}") from exc
    if not isinstance(value, dict):
        raise SignerAttestationError(code, f"{path.name} must contain an object")
    return value


def _load_yaml(path: Path, code: str) -> dict[str, Any]:
    try:
        value = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError, UnicodeDecodeError) as exc:
        raise SignerAttestationError(code, f"cannot load {path.name}") from exc
    if not isinstance(value, dict):
        raise SignerAttestationError(code, f"{path.name} must contain an object")
    return value


def load_attestation(path: Path = DEFAULT_ATTESTATION) -> dict[str, Any]:
    attestation = _load_yaml(path, "ATTESTATION_UNREADABLE")
    schema = _load_json(ATTESTATION_SCHEMA, "ATTESTATION_SCHEMA_UNAVAILABLE")
    validator = jsonschema.Draft202012Validator(
        schema, format_checker=jsonschema.FormatChecker()
    )
    errors = sorted(validator.iter_errors(attestation), key=lambda error: list(error.path))
    if errors:
        first = errors[0]
        location = ".".join(str(part) for part in first.path) or "<root>"
        raise SignerAttestationError(
            "ATTESTATION_INVALID", f"{location}: {first.message}"
        )
    secret_fields = _find_secret_fields(attestation)
    if secret_fields:
        raise SignerAttestationError(
            "ATTESTATION_SECRET_MATERIAL_REFUSED", "; ".join(secret_fields)
        )
    return attestation


def load_deployment_descriptor(path: Path = DEFAULT_DEPLOYMENT_DESCRIPTOR) -> dict[str, Any]:
    try:
        return tb1_preflight.load_descriptor(path)
    except Exception as exc:  # noqa: BLE001 - normalize canonical preflight errors
        raise SignerAttestationError(
            "DEPLOYMENT_DESCRIPTOR_INVALID", "TB1 deployment descriptor cannot be loaded"
        ) from exc


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


def _parse_observed_at(value: Any) -> datetime:
    if not isinstance(value, str):
        raise SignerAttestationError(
            "ATTESTATION_TIMESTAMP_INVALID", "observed_at must be an RFC3339 timestamp"
        )
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise SignerAttestationError(
            "ATTESTATION_TIMESTAMP_INVALID", "observed_at is invalid"
        ) from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise SignerAttestationError(
            "ATTESTATION_TIMESTAMP_INVALID", "observed_at must be timezone-aware"
        )
    return parsed.astimezone(timezone.utc)


def _approved_public_key_digest(descriptor: Mapping[str, Any]) -> str:
    signer = descriptor["signer"]
    keys = descriptor["trust_store"]["document"]["keys"]
    matching = [
        item
        for item in keys
        if isinstance(item, Mapping) and item.get("key_id") == signer["key_id"]
    ]
    if len(matching) != 1:
        raise SignerAttestationError(
            "APPROVED_KEY_UNAVAILABLE", "deployment descriptor lacks one approved signer key"
        )
    encoded = matching[0].get("public_key")
    if not isinstance(encoded, str):
        raise SignerAttestationError(
            "APPROVED_KEY_UNAVAILABLE", "approved public key is unavailable"
        )
    try:
        der = base64.b64decode(encoded, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise SignerAttestationError(
            "APPROVED_KEY_UNAVAILABLE", "approved public key is malformed"
        ) from exc
    return hashlib.sha256(der).hexdigest()


def verify_signer_attestation(
    deployment_descriptor: Mapping[str, Any],
    attestation: Mapping[str, Any],
    *,
    evidence_verifier: EvidenceVerifier | None = None,
) -> SignerAttestationResult:
    """Verify one fresh provider observation without contacting the provider."""

    if not isinstance(deployment_descriptor, Mapping):
        raise SignerAttestationError(
            "DEPLOYMENT_DESCRIPTOR_INVALID", "deployment descriptor must be an object"
        )
    if not isinstance(attestation, Mapping):
        raise SignerAttestationError(
            "ATTESTATION_INVALID", "signer attestation must be an object"
        )

    try:
        preflight = tb1_preflight.run_preflight(deployment_descriptor)
    except Exception as exc:  # noqa: BLE001
        raise SignerAttestationError(
            "DEPLOYMENT_DESCRIPTOR_INVALID", "TB1 deployment descriptor failed preflight"
        ) from exc
    if not preflight.ok:
        raise SignerAttestationError(
            "DEPLOYMENT_DESCRIPTOR_INVALID", "; ".join(preflight.findings)
        )

    schema = _load_json(ATTESTATION_SCHEMA, "ATTESTATION_SCHEMA_UNAVAILABLE")
    validator = jsonschema.Draft202012Validator(
        schema, format_checker=jsonschema.FormatChecker()
    )
    errors = sorted(validator.iter_errors(attestation), key=lambda error: list(error.path))
    if errors:
        first = errors[0]
        location = ".".join(str(part) for part in first.path) or "<root>"
        raise SignerAttestationError(
            "ATTESTATION_INVALID", f"{location}: {first.message}"
        )
    secret_fields = _find_secret_fields(attestation)
    if secret_fields:
        raise SignerAttestationError(
            "ATTESTATION_SECRET_MATERIAL_REFUSED", "; ".join(secret_fields)
        )

    signer = deployment_descriptor["signer"]
    expected_digest = _approved_public_key_digest(deployment_descriptor)
    findings: list[str] = []

    if attestation["observation_status"] != "OBSERVED":
        findings.append("external signer provider observation has not run")
    else:
        observed_at = _parse_observed_at(attestation["observed_at"])
        now = datetime.now(timezone.utc)
        if observed_at > now + MAX_FUTURE_SKEW:
            findings.append("signer attestation timestamp is in the future")
        elif now - observed_at > MAX_ATTESTATION_AGE:
            findings.append("signer attestation is stale")

    for field in ("provider_kind", "provider_ref", "key_id", "algorithm"):
        if attestation[field] != signer[field]:
            findings.append(f"observed {field} does not match approved signer binding")

    if attestation["key_state"] != "active":
        findings.append("observed signer key is not active")
    if attestation["signing_enabled"] is not True:
        findings.append("observed signer key is not enabled for signing")
    if attestation["private_key_exportable"] is not False:
        findings.append("observed signer private key is exportable")
    if attestation["public_key_spki_sha256"] != expected_digest:
        findings.append("observed signer public-key fingerprint does not match trust store")

    source_verified = False
    if attestation["observation_status"] == "OBSERVED":
        evidence_ref = attestation["source_evidence_ref"]
        evidence_sha = attestation["source_evidence_sha256"]
        verifier = evidence_verifier or DenyAllEvidenceVerifier()
        try:
            source_verified = bool(verifier.verify(str(evidence_ref), str(evidence_sha)))
        except Exception:  # noqa: BLE001 - verifier internals do not cross boundary
            source_verified = False
        if not source_verified:
            findings.append("source provider observation evidence is not verified")

    return SignerAttestationResult(
        signer_attestation_checks_passed=not findings,
        promotion_allowed=False,
        runtime_status="NOT_RUN",
        findings=tuple(findings),
        remaining_evidence=REMAINING_EVIDENCE,
        provider_kind=str(attestation["provider_kind"]),
        provider_ref=str(attestation["provider_ref"]),
        key_id=str(attestation["key_id"]),
        algorithm=str(attestation["algorithm"]),
        public_key_spki_sha256=str(attestation["public_key_spki_sha256"]),
        source_evidence_verified=source_verified,
    )


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--deployment-descriptor", type=Path, default=DEFAULT_DEPLOYMENT_DESCRIPTOR
    )
    parser.add_argument("--attestation", type=Path, default=DEFAULT_ATTESTATION)
    parser.add_argument("--json", action="store_true")
    parser.add_argument("command", choices=("check",))
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        result = verify_signer_attestation(
            load_deployment_descriptor(args.deployment_descriptor),
            load_attestation(args.attestation),
        )
    except SignerAttestationError as exc:
        payload = {
            "signer_attestation_checks_passed": False,
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
    elif result.signer_attestation_checks_passed:
        print("OK external signer observation matches approved TB1 binding")
    else:
        for finding in result.findings:
            print(f"FAIL {finding}", file=sys.stderr)
    return 0 if result.signer_attestation_checks_passed else 2


if __name__ == "__main__":
    raise SystemExit(main())
