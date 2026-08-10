"""Read-only TB1 authorization deployment preflight.

This module validates a *declaration* of the external signer binding and the
public-key trust store required by the Hermes TB1 authorization boundary. It
never provisions a provider, reads a private key, installs a trust store,
changes a policy or contacts a runtime service.

Passing this preflight means only that the deployment declaration is internally
consistent and cryptographically well-formed. ``runtime_status`` is required to
remain ``NOT_RUN``.
"""

from __future__ import annotations

import argparse
import base64
import binascii
import importlib.util
import json
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Mapping, Sequence

import jsonschema
import yaml

ROOT = Path(__file__).resolve().parents[2]
RUNTIME_PROMOTION = ROOT / "deployment" / "runtime-promotion"
DESCRIPTOR_SCHEMA = RUNTIME_PROMOTION / "tb1-authorization-deployment-descriptor.schema.json"
DEFAULT_DESCRIPTOR = (
    RUNTIME_PROMOTION
    / "templates"
    / "tb1-authorization-deployment-descriptor.example.yaml"
)
AUTH_DIR = ROOT / "platform" / "authorization-contract"
TRUST_STORE_SCHEMA = AUTH_DIR / "authorization-trust-store.schema.json"
AUTH_MODULE_PATH = AUTH_DIR / "authorization_receipt.py"

EXIT_OK = 0
EXIT_FAIL_CLOSED = 2

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


class PreflightError(ValueError):
    """Descriptor load/schema failure with a stable fail-closed code."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


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


authorization_contract = _load_module(
    "tb1_deployment_preflight_authorization_contract", AUTH_MODULE_PATH
)


@dataclass(frozen=True)
class PreflightResult:
    ok: bool
    findings: tuple[str, ...]
    runtime_status: str
    authority: str
    provider_kind: str
    provider_ref: str
    key_id: str
    algorithm: str
    trust_store_path: str
    trust_key_count: int

    def as_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "findings": list(self.findings),
            "runtime_status": self.runtime_status,
            "authority": self.authority,
            "provider_kind": self.provider_kind,
            "provider_ref": self.provider_ref,
            "key_id": self.key_id,
            "algorithm": self.algorithm,
            "trust_store_path": self.trust_store_path,
            "trust_key_count": self.trust_key_count,
        }


def _load_json(path: Path, code: str) -> dict[str, Any]:
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, UnicodeDecodeError) as exc:
        raise PreflightError(code, f"cannot load {path.name}") from exc
    if not isinstance(document, dict):
        raise PreflightError(code, f"{path.name} must contain an object")
    return document


def load_descriptor(path: Path) -> dict[str, Any]:
    try:
        document = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError, UnicodeDecodeError) as exc:
        raise PreflightError("DESCRIPTOR_UNREADABLE", "descriptor cannot be read") from exc
    if not isinstance(document, dict):
        raise PreflightError("DESCRIPTOR_INVALID", "descriptor must contain an object")
    return document


def _validate_schema(document: Mapping[str, Any], schema_path: Path, code: str) -> None:
    schema = _load_json(schema_path, code)
    validator = jsonschema.Draft202012Validator(
        schema, format_checker=jsonschema.FormatChecker()
    )
    errors = sorted(validator.iter_errors(document), key=lambda error: list(error.path))
    if errors:
        first = errors[0]
        location = ".".join(str(part) for part in first.path) or "<root>"
        raise PreflightError(code, f"{location}: {first.message}")


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


def _parse_time(value: Any) -> datetime | None:
    if value is None:
        return None
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        return None
    return parsed


def _public_key_matches_algorithm(encoded: Any, algorithm: str) -> bool:
    if not isinstance(encoded, str) or not encoded:
        return False
    try:
        der = base64.b64decode(encoded, validate=True)
    except (binascii.Error, ValueError):
        return False
    try:
        from cryptography.hazmat.primitives.asymmetric import ec, ed25519
        from cryptography.hazmat.primitives.serialization import load_der_public_key

        key = load_der_public_key(der)
    except Exception:  # noqa: BLE001 - untrusted public material fails closed
        return False

    if algorithm == "Ed25519":
        return isinstance(key, ed25519.Ed25519PublicKey)
    if algorithm == "ECDSA-P256-SHA256":
        curve_name = getattr(getattr(key, "curve", None), "name", None)
        return isinstance(key, ec.EllipticCurvePublicKey) and curve_name == "secp256r1"
    return False


def run_preflight(descriptor: Mapping[str, Any]) -> PreflightResult:
    if not isinstance(descriptor, Mapping):
        raise PreflightError("DESCRIPTOR_INVALID", "descriptor must be a mapping")

    _validate_schema(descriptor, DESCRIPTOR_SCHEMA, "DESCRIPTOR_INVALID")

    findings = _find_secret_fields(descriptor)
    signer = descriptor["signer"]
    trust = descriptor["trust_store"]
    trust_document = trust["document"]

    if descriptor["domain"] != authorization_contract.DOMAIN:
        findings.append("descriptor domain does not match canonical TB1 domain")
    if descriptor["purpose"] != authorization_contract.KEY_PURPOSE:
        findings.append("descriptor purpose does not match canonical TB1 key purpose")
    if descriptor["authority"] != authorization_contract.ISSUER:
        findings.append("descriptor authority does not match Hermes control-plane issuer")
    if descriptor["runtime_status"] != "NOT_RUN":
        findings.append("runtime_status must remain NOT_RUN")
    if signer["private_key_local"] is not False:
        findings.append("private_key_local must remain false")

    try:
        _validate_schema(trust_document, TRUST_STORE_SCHEMA, "TRUST_STORE_INVALID")
    except PreflightError as exc:
        findings.append(f"trust store schema invalid: {exc}")

    if isinstance(trust_document, Mapping):
        if trust_document.get("domain") != descriptor["domain"]:
            findings.append("trust-store domain must equal descriptor domain")
        if trust_document.get("purpose") != descriptor["purpose"]:
            findings.append("trust-store purpose must equal descriptor purpose")

    keys = trust_document.get("keys", []) if isinstance(trust_document, Mapping) else []
    key_ids: set[str] = set()
    matching: list[Mapping[str, Any]] = []
    for entry in keys if isinstance(keys, list) else []:
        if not isinstance(entry, Mapping):
            continue
        key_id = str(entry.get("key_id", ""))
        if key_id in key_ids:
            findings.append(f"duplicate trust-store key_id: {key_id}")
        key_ids.add(key_id)
        if key_id == signer["key_id"]:
            matching.append(entry)

        if entry.get("purpose") != authorization_contract.KEY_PURPOSE:
            findings.append(f"trust key {key_id or '<unknown>'} has wrong purpose")
        algorithm = str(entry.get("algorithm", ""))
        if not _public_key_matches_algorithm(entry.get("public_key"), algorithm):
            findings.append(
                f"trust key {key_id or '<unknown>'} public key does not match algorithm"
            )
        not_before = _parse_time(entry.get("not_before"))
        not_after = _parse_time(entry.get("not_after"))
        if entry.get("not_before") is not None and not_before is None:
            findings.append(f"trust key {key_id or '<unknown>'} has invalid not_before")
        if entry.get("not_after") is not None and not_after is None:
            findings.append(f"trust key {key_id or '<unknown>'} has invalid not_after")
        if not_before is not None and not_after is not None and not not_before < not_after:
            findings.append(
                f"trust key {key_id or '<unknown>'} validity window is invalid"
            )

    if len(matching) != 1:
        findings.append("signer key_id must match exactly one trust-store key")
    else:
        key = matching[0]
        if key.get("state") != "active":
            findings.append("signer trust-store key must be active")
        if key.get("algorithm") != signer["algorithm"]:
            findings.append("signer algorithm must match trust-store key algorithm")
        if key.get("purpose") != descriptor["purpose"]:
            findings.append("signer trust-store key purpose must match descriptor purpose")

    return PreflightResult(
        ok=not findings,
        findings=tuple(findings),
        runtime_status=str(descriptor["runtime_status"]),
        authority=str(descriptor["authority"]),
        provider_kind=str(signer["provider_kind"]),
        provider_ref=str(signer["provider_ref"]),
        key_id=str(signer["key_id"]),
        algorithm=str(signer["algorithm"]),
        trust_store_path=str(trust["install_path"]),
        trust_key_count=len(keys) if isinstance(keys, list) else 0,
    )


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Validate TB1 signer/trust-store deployment prerequisites without promotion."
    )
    parser.add_argument(
        "--descriptor", type=Path, default=DEFAULT_DESCRIPTOR, help="deployment descriptor YAML"
    )
    parser.add_argument("--json", action="store_true", help="emit machine-readable output")
    parser.add_argument("command", choices=("check",))
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        result = run_preflight(load_descriptor(args.descriptor))
    except PreflightError as exc:
        if args.json:
            print(json.dumps({"ok": False, "code": exc.code, "findings": [str(exc)]}, sort_keys=True))
        else:
            print(f"FAIL-CLOSED [{exc.code}] {exc}")
        return EXIT_FAIL_CLOSED

    if args.json:
        print(json.dumps(result.as_dict(), sort_keys=True))
    elif result.ok:
        print(
            f"PASS runtime_status={result.runtime_status} provider={result.provider_kind} "
            f"key_id={result.key_id} trust_keys={result.trust_key_count}"
        )
    else:
        print("FAIL-CLOSED")
        for finding in result.findings:
            print(f"- {finding}")
    return EXIT_OK if result.ok else EXIT_FAIL_CLOSED


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
