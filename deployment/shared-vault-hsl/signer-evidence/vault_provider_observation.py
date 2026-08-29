#!/usr/bin/env python3
"""Normalize public Vault Transit key metadata into sanitized signer evidence."""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any, Mapping

import jsonschema
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

HERE = Path(__file__).resolve().parent
DEFAULT_SCHEMA = HERE / "provider-observation.schema.json"
SCHEMA_VERSION = "hsl.shared-vault-signer-provider-observation/v1"
VAULT_ADDR = "https://hermes-vault:8200"
TRANSIT_MOUNT = "hsl-transit"
KEY_NAME = "hsl-signing"
_EVIDENCE_REF = re.compile(r"^evidence://[^\s]+$")
_SHA256 = re.compile(r"^[a-f0-9]{64}$")

_REQUIRED_CHECKS = (
    "key_read_passed",
    "sign_verify_passed",
    "negative_sys_passed",
    "negative_auth_passed",
    "audit_attribution_passed",
    "no_secret_material_persisted",
)
_FORBIDDEN_FIELDS = frozenset(
    {
        "token",
        "client" + "_token",
        "secret",
        "secret" + "_id",
        "role" + "_id",
        "wrapping" + "_token",
        "password",
        "passphrase",
        "credential",
        "credentials",
        "private_key",
        "api_key",
    }
)


class ProviderObservationError(ValueError):
    """Stable fail-closed provider observation error."""

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(message)


def _normalize_key(value: Any) -> str:
    return str(value).strip().lower().replace("-", "_")


def _secret_paths(value: Any, path: str = "") -> list[str]:
    findings: list[str] = []
    if isinstance(value, Mapping):
        for key, nested in value.items():
            child = f"{path}.{key}" if path else str(key)
            if _normalize_key(key) in _FORBIDDEN_FIELDS:
                findings.append(child)
            findings.extend(_secret_paths(nested, child))
    elif isinstance(value, list):
        for index, nested in enumerate(value):
            findings.extend(_secret_paths(nested, f"{path}[{index}]"))
    return findings


def _require_mapping(value: Any, *, code: str, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ProviderObservationError(code, f"{label} must be an object")
    return value


def _require_evidence(value: Any) -> dict[str, str]:
    value = _require_mapping(value, code="PROVIDER_EVIDENCE_INVALID", label="evidence")
    if set(value) != {"ref", "sha256"}:
        raise ProviderObservationError("PROVIDER_EVIDENCE_INVALID", "evidence shape is invalid")
    ref = value.get("ref")
    digest = value.get("sha256")
    if not isinstance(ref, str) or not _EVIDENCE_REF.fullmatch(ref):
        raise ProviderObservationError("PROVIDER_EVIDENCE_INVALID", "evidence ref is invalid")
    if not isinstance(digest, str) or not _SHA256.fullmatch(digest):
        raise ProviderObservationError("PROVIDER_EVIDENCE_INVALID", "evidence digest is invalid")
    return {"ref": ref, "sha256": digest}


def _require_checks(value: Any) -> dict[str, bool]:
    value = _require_mapping(
        value, code="PROVIDER_CAPABILITY_CHECKS_FAILED", label="capability_checks"
    )
    if set(value) != set(_REQUIRED_CHECKS):
        raise ProviderObservationError(
            "PROVIDER_CAPABILITY_CHECKS_FAILED", "capability check shape is invalid"
        )
    normalized: dict[str, bool] = {}
    for key in _REQUIRED_CHECKS:
        if value.get(key) is not True:
            raise ProviderObservationError(
                "PROVIDER_CAPABILITY_CHECKS_FAILED", f"required check failed: {key}"
            )
        normalized[key] = True
    return normalized


def _extract_key_data(raw_response: Any) -> Mapping[str, Any]:
    raw_response = _require_mapping(
        raw_response, code="PROVIDER_OBSERVATION_INVALID", label="raw provider response"
    )
    secret_paths = _secret_paths(raw_response)
    if secret_paths:
        raise ProviderObservationError(
            "PROVIDER_OBSERVATION_SECRET_MATERIAL_REFUSED",
            "secret/private material field refused: " + ", ".join(secret_paths),
        )
    return _require_mapping(
        raw_response.get("data"), code="PROVIDER_OBSERVATION_INVALID", label="provider data"
    )


def _observe_public_key(data: Mapping[str, Any]) -> tuple[int, bytes]:
    if (
        data.get("name") != KEY_NAME
        or data.get("type") != "ed25519"
        or data.get("supports_signing") is not True
        or data.get("derived") is not False
        or data.get("exportable") is not False
        or data.get("allow_plaintext_backup") is not False
    ):
        raise ProviderObservationError(
            "VAULT_KEY_NOT_ADMISSIBLE", "Vault Transit key metadata is not admissible"
        )
    keys = data.get("keys")
    if not isinstance(keys, Mapping) or not keys:
        raise ProviderObservationError("VAULT_KEY_IDENTITY_INVALID", "key versions unavailable")
    versions = sorted(
        int(value) for value in keys if isinstance(value, str) and value.isdigit() and int(value) > 0
    )
    if not versions:
        raise ProviderObservationError("VAULT_KEY_IDENTITY_INVALID", "key version unavailable")
    version = versions[-1]
    entry = keys.get(str(version))
    if not isinstance(entry, Mapping):
        raise ProviderObservationError("VAULT_KEY_IDENTITY_INVALID", "key entry unavailable")
    public_pem = entry.get("public_key")
    if not isinstance(public_pem, str) or not public_pem or len(public_pem) > 8192:
        raise ProviderObservationError("VAULT_KEY_IDENTITY_INVALID", "public key unavailable")
    try:
        public_key = serialization.load_pem_public_key(public_pem.encode("ascii"))
    except (ValueError, TypeError, UnicodeEncodeError) as exc:
        raise ProviderObservationError(
            "VAULT_KEY_IDENTITY_INVALID", "public key is malformed"
        ) from exc
    if not isinstance(public_key, Ed25519PublicKey):
        raise ProviderObservationError("VAULT_KEY_IDENTITY_INVALID", "public key is not Ed25519")
    der = public_key.public_bytes(
        encoding=serialization.Encoding.DER,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    return version, der


def validate_provider_observation(
    document: Mapping[str, Any], *, schema_path: Path = DEFAULT_SCHEMA
) -> None:
    try:
        schema = json.loads(Path(schema_path).read_text(encoding="utf-8"))
    except (OSError, ValueError, UnicodeError) as exc:
        raise ProviderObservationError(
            "PROVIDER_OBSERVATION_SCHEMA_UNAVAILABLE", "provider observation schema unavailable"
        ) from exc
    validator = jsonschema.Draft202012Validator(
        schema, format_checker=jsonschema.FormatChecker()
    )
    errors = sorted(validator.iter_errors(document), key=lambda error: list(error.path))
    if errors:
        first = errors[0]
        location = ".".join(str(part) for part in first.path) or "<root>"
        raise ProviderObservationError(
            "PROVIDER_OBSERVATION_SCHEMA_INVALID", f"{location}: {first.message}"
        )


def normalize_provider_observation(
    raw_key_response: Mapping[str, Any],
    *,
    observed_at: str,
    capability_checks: Mapping[str, Any],
    bootstrap_evidence: Mapping[str, Any],
    audit_evidence: Mapping[str, Any],
    vault_addr: str = VAULT_ADDR,
    transit_mount: str = TRANSIT_MOUNT,
    key_name: str = KEY_NAME,
) -> dict[str, Any]:
    """Return one closed public observation for an already-authorized provider read."""

    if vault_addr != VAULT_ADDR or transit_mount != TRANSIT_MOUNT or key_name != KEY_NAME:
        raise ProviderObservationError(
            "PROVIDER_BINDING_INVALID", "shared-Vault signer binding does not match canonical contract"
        )
    if not isinstance(observed_at, str) or not observed_at:
        raise ProviderObservationError("PROVIDER_OBSERVATION_INVALID", "observed_at is required")

    checks = _require_checks(capability_checks)
    bootstrap = _require_evidence(bootstrap_evidence)
    audit = _require_evidence(audit_evidence)
    data = _extract_key_data(raw_key_response)
    version, public_der = _observe_public_key(data)
    provider_ref = f"{vault_addr}/{transit_mount}/{key_name}"
    key_id = f"vault:{transit_mount}:{key_name}:v{version}"
    result: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "state": "OBSERVED",
        "observed_at": observed_at,
        "provider_kind": "VAULT",
        "provider_ref": provider_ref,
        "transit_mount": transit_mount,
        "key_name": key_name,
        "key_version": version,
        "key_id": key_id,
        "algorithm": "Ed25519",
        "key_state": "active",
        "signing_enabled": True,
        "private_key_exportable": False,
        "allow_plaintext_backup": False,
        "public_key_spki_b64": base64.b64encode(public_der).decode("ascii"),
        "public_key_spki_sha256": hashlib.sha256(public_der).hexdigest(),
        "capability_checks": checks,
        "bootstrap_evidence": bootstrap,
        "audit_evidence": audit,
        "trust_binding_allowed": False,
        "promotion_allowed": False,
        "execution_authority": "NONE",
        "runtime_status": "NOT_RUN",
    }
    validate_provider_observation(result)
    return result


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    subparsers = parser.add_subparsers(dest="command", required=True)
    normalize = subparsers.add_parser("normalize")
    normalize.add_argument("--observed-at", required=True)
    normalize.add_argument("--bootstrap-ref", required=True)
    normalize.add_argument("--bootstrap-sha256", required=True)
    normalize.add_argument("--audit-ref", required=True)
    normalize.add_argument("--audit-sha256", required=True)
    normalize.add_argument("--key-read-passed", action="store_true")
    normalize.add_argument("--sign-verify-passed", action="store_true")
    normalize.add_argument("--negative-sys-passed", action="store_true")
    normalize.add_argument("--negative-auth-passed", action="store_true")
    normalize.add_argument("--audit-attribution-passed", action="store_true")
    normalize.add_argument("--no-secret-material-persisted", action="store_true")
    return parser


def main(argv=None, *, stdin=None, stdout=None, stderr=None) -> int:
    stdin = stdin or sys.stdin
    stdout = stdout or sys.stdout
    stderr = stderr or sys.stderr
    args = _parser().parse_args(argv)
    try:
        raw = json.load(stdin)
        checks = {
            "key_read_passed": args.key_read_passed,
            "sign_verify_passed": args.sign_verify_passed,
            "negative_sys_passed": args.negative_sys_passed,
            "negative_auth_passed": args.negative_auth_passed,
            "audit_attribution_passed": args.audit_attribution_passed,
            "no_secret_material_persisted": args.no_secret_material_persisted,
        }
        document = normalize_provider_observation(
            raw,
            observed_at=args.observed_at,
            capability_checks=checks,
            bootstrap_evidence={"ref": args.bootstrap_ref, "sha256": args.bootstrap_sha256},
            audit_evidence={"ref": args.audit_ref, "sha256": args.audit_sha256},
        )
    except (ValueError, ProviderObservationError) as exc:
        code = getattr(exc, "code", "PROVIDER_OBSERVATION_INVALID")
        print(f"FAIL {code}", file=stderr)
        return 2
    print(json.dumps(document, sort_keys=True, separators=(",", ":")), file=stdout)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
