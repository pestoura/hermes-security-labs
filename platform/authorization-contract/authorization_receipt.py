"""TB1 signed authorization receipt contract.

Hermes is the only component allowed to issue execution authorization.  The
execution plane may validate a receipt and refuse it, but it may never create,
expand or approve authorization.  This module therefore contains canonical
serialization/reference helpers and a verifier only; it deliberately contains
no private-key loader and no operational issuer.

The receipt carries identifiers and digests only.  It never carries a raw
target, operation parameters, credentials or secret material.  The dedicated
trust store is purpose-bound to ``tb1-authorization`` so a Rules of Engagement
signing key cannot be reused accidentally across trust domains.
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

import jsonschema

SCHEMA_VERSION = "1.0.0"
DOMAIN = "hex0r.tb1.authorization.v1"
ISSUER = "hermes-control-plane"
KEY_PURPOSE = "tb1-authorization"
AUTHORIZATION_REF_PREFIX = "tb1-authz:v1:"
MAX_RECEIPT_LIFETIME_SECONDS = 900
SUPPORTED_ALGORITHMS = ("Ed25519", "ECDSA-P256-SHA256")
KEY_STATES = ("active", "revoked", "retired")

ROOT = Path(__file__).resolve().parent
RECEIPT_SCHEMA = ROOT / "authorization-receipt.schema.json"
TRUST_STORE_SCHEMA = ROOT / "authorization-trust-store.schema.json"

_FORBIDDEN_KEY_FIELDS = {
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
    "api_key",
}


class AuthorizationReceiptError(ValueError):
    """Fail-closed receipt/trust-store error carrying a stable refusal code."""

    @property
    def decision_code(self) -> str:
        return str(self)


@dataclass(frozen=True)
class AuthorizationKey:
    key_id: str
    algorithm: str
    state: str
    purpose: str
    public_key_der: bytes
    not_before: datetime | None
    not_after: datetime | None


@dataclass(frozen=True)
class VerifiedAuthorization:
    """Sanitized authorization metadata obtained from a verified receipt."""

    authorization_id: str
    authorization_ref: str
    issued_at: str
    expires_at: str
    campaign_id: str
    run_id: str
    step_id: str
    roe_contract_id: str
    roe_contract_payload_sha256: str
    roe_step_request_id: str
    operation_id: str
    operation_version: str
    capability_id: str
    target_sha256: str
    intrusiveness_level: str


def _load_schema(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _validate_schema(document: Mapping[str, Any], path: Path, code: str) -> None:
    validator = jsonschema.Draft202012Validator(
        _load_schema(path), format_checker=jsonschema.FormatChecker()
    )
    if list(validator.iter_errors(document)):
        raise AuthorizationReceiptError(code)


def _parse_datetime(value: Any, code: str) -> datetime:
    if not isinstance(value, str):
        raise AuthorizationReceiptError(code)
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise AuthorizationReceiptError(code) from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise AuthorizationReceiptError(code)
    return parsed


def _decode_base64(value: Any, code: str) -> bytes:
    if not isinstance(value, str) or not value:
        raise AuthorizationReceiptError(code)
    try:
        return base64.b64decode(value, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise AuthorizationReceiptError(code) from exc


def _normalized_key(name: Any) -> str:
    return str(name).lower().replace("-", "_")


def _reject_secret_material(value: Any, *, allow_public_key: bool = False) -> None:
    if isinstance(value, Mapping):
        for key, nested in value.items():
            normalized = _normalized_key(key)
            if normalized in _FORBIDDEN_KEY_FIELDS:
                raise AuthorizationReceiptError("AUTH_SECRET_MATERIAL")
            if normalized == "public_key" and not allow_public_key:
                raise AuthorizationReceiptError("AUTH_RECEIPT_KEY_MATERIAL_FORBIDDEN")
            _reject_secret_material(nested, allow_public_key=allow_public_key)
    elif isinstance(value, list):
        for nested in value:
            _reject_secret_material(nested, allow_public_key=allow_public_key)


def authorization_body(receipt: Mapping[str, Any]) -> dict[str, Any]:
    """Return the body over which Hermes deterministically derives the ref.

    ``authorization_ref`` and ``signature`` are excluded to avoid circularity.
    The explicit domain remains part of the body and is also prepended as a
    domain-separation prefix before hashing.
    """

    return {
        key: value
        for key, value in receipt.items()
        if key not in {"authorization_ref", "signature"}
    }


def _canonical_json(document: Mapping[str, Any]) -> bytes:
    return json.dumps(
        dict(document), sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")


def build_authorization_ref(receipt: Mapping[str, Any]) -> str:
    """Compute the reference that the control plane places in a signed receipt.

    Execution-plane callers may recompute this value only to validate integrity;
    recomputation does not create authority and a naked reference is never
    sufficient for authorization.
    """

    digest = hashlib.sha256(
        DOMAIN.encode("utf-8") + b"\x00" + _canonical_json(authorization_body(receipt))
    ).hexdigest()
    return AUTHORIZATION_REF_PREFIX + digest


def canonical_signed_payload(receipt: Mapping[str, Any]) -> bytes:
    """Canonical bytes signed by the Hermes authorization authority."""

    return _canonical_json(
        {key: value for key, value in receipt.items() if key != "signature"}
    )


def _load_trust_store(path: Path) -> dict[str, AuthorizationKey]:
    try:
        raw = Path(path).read_text(encoding="utf-8")
    except OSError as exc:
        raise AuthorizationReceiptError("AUTH_TRUST_STORE_UNAVAILABLE") from exc
    try:
        document = json.loads(raw)
    except (ValueError, UnicodeDecodeError) as exc:
        raise AuthorizationReceiptError("AUTH_TRUST_STORE_INVALID") from exc
    if not isinstance(document, Mapping):
        raise AuthorizationReceiptError("AUTH_TRUST_STORE_INVALID")

    _reject_secret_material(document, allow_public_key=True)
    _validate_schema(document, TRUST_STORE_SCHEMA, "AUTH_TRUST_STORE_INVALID")

    if document.get("schema_version") != SCHEMA_VERSION:
        raise AuthorizationReceiptError("AUTH_TRUST_STORE_SCHEMA_UNSUPPORTED")
    if document.get("domain") != DOMAIN:
        raise AuthorizationReceiptError("AUTH_TRUST_STORE_DOMAIN_MISMATCH")
    if document.get("purpose") != KEY_PURPOSE:
        raise AuthorizationReceiptError("AUTH_TRUST_STORE_PURPOSE_MISMATCH")

    loaded: dict[str, AuthorizationKey] = {}
    for entry in document["keys"]:
        key_id = str(entry["key_id"])
        if key_id in loaded:
            raise AuthorizationReceiptError("AUTH_TRUST_STORE_DUPLICATE_KEY_ID")
        if entry.get("purpose") != KEY_PURPOSE:
            raise AuthorizationReceiptError("AUTH_KEY_PURPOSE_MISMATCH")
        not_before = (
            _parse_datetime(entry["not_before"], "AUTH_TRUST_STORE_INVALID")
            if entry.get("not_before") is not None
            else None
        )
        not_after = (
            _parse_datetime(entry["not_after"], "AUTH_TRUST_STORE_INVALID")
            if entry.get("not_after") is not None
            else None
        )
        if not_before and not_after and not not_before < not_after:
            raise AuthorizationReceiptError("AUTH_TRUST_STORE_INVALID")
        loaded[key_id] = AuthorizationKey(
            key_id=key_id,
            algorithm=str(entry["algorithm"]),
            state=str(entry["state"]),
            purpose=str(entry["purpose"]),
            public_key_der=_decode_base64(
                entry["public_key"], "AUTH_TRUST_STORE_INVALID"
            ),
            not_before=not_before,
            not_after=not_after,
        )
    return loaded


def _public_key(key: AuthorizationKey) -> Any:
    try:
        from cryptography.hazmat.primitives.asymmetric import ec, ed25519
        from cryptography.hazmat.primitives.serialization import load_der_public_key
    except ImportError as exc:  # pragma: no cover - environment dependent
        raise AuthorizationReceiptError("AUTH_CRYPTO_BACKEND_UNAVAILABLE") from exc

    try:
        public_key = load_der_public_key(key.public_key_der)
    except Exception as exc:  # noqa: BLE001 - malformed material is untrusted
        raise AuthorizationReceiptError("AUTH_TRUST_STORE_INVALID") from exc

    if key.algorithm == "Ed25519":
        if not isinstance(public_key, ed25519.Ed25519PublicKey):
            raise AuthorizationReceiptError("AUTH_KEY_ALGORITHM_MISMATCH")
    elif key.algorithm == "ECDSA-P256-SHA256":
        if not isinstance(public_key, ec.EllipticCurvePublicKey) or not isinstance(
            public_key.curve, ec.SECP256R1
        ):
            raise AuthorizationReceiptError("AUTH_KEY_ALGORITHM_MISMATCH")
    else:  # pragma: no cover - schema rejects this first
        raise AuthorizationReceiptError("AUTH_ALGORITHM_UNSUPPORTED")
    return public_key


def _verify_signature(
    key: AuthorizationKey, public_key: Any, payload: bytes, signature: bytes
) -> bool:
    from cryptography.exceptions import InvalidSignature
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.asymmetric import ec

    try:
        if key.algorithm == "Ed25519":
            public_key.verify(signature, payload)
        else:
            public_key.verify(signature, payload, ec.ECDSA(hashes.SHA256()))
    except InvalidSignature:
        return False
    except Exception as exc:  # noqa: BLE001 - malformed signature is untrusted
        raise AuthorizationReceiptError("AUTH_SIGNATURE_MALFORMED") from exc
    return True


def verify_authorization_receipt(
    receipt: Mapping[str, Any], trust_store_path: Path | None
) -> VerifiedAuthorization:
    """Verify one Hermes-issued TB1 authorization receipt using the real clock.

    There is intentionally no caller-supplied clock or signature verifier on
    this API.  Missing configuration, malformed data, key-purpose confusion,
    invalid signatures, expired receipts and reference mismatches all fail
    closed with stable codes.
    """

    if not isinstance(receipt, Mapping):
        raise AuthorizationReceiptError("AUTH_RECEIPT_REQUIRED")
    if trust_store_path is None:
        raise AuthorizationReceiptError("AUTH_TRUST_STORE_REQUIRED")

    _reject_secret_material(receipt)
    _validate_schema(receipt, RECEIPT_SCHEMA, "AUTH_RECEIPT_SCHEMA_INVALID")

    if receipt.get("schema_version") != SCHEMA_VERSION:
        raise AuthorizationReceiptError("AUTH_RECEIPT_SCHEMA_UNSUPPORTED")
    if receipt.get("domain") != DOMAIN:
        raise AuthorizationReceiptError("AUTH_RECEIPT_DOMAIN_MISMATCH")
    if receipt.get("issuer") != ISSUER:
        raise AuthorizationReceiptError("AUTH_RECEIPT_ISSUER_MISMATCH")

    expected_ref = build_authorization_ref(receipt)
    if receipt.get("authorization_ref") != expected_ref:
        raise AuthorizationReceiptError("AUTHORIZATION_REF_MISMATCH")

    signature = receipt.get("signature")
    if not isinstance(signature, Mapping):
        raise AuthorizationReceiptError("AUTH_SIGNATURE_MALFORMED")
    key_id = signature.get("key_id")
    algorithm = signature.get("algorithm")
    if not isinstance(key_id, str) or not isinstance(algorithm, str):
        raise AuthorizationReceiptError("AUTH_SIGNATURE_MALFORMED")

    keys = _load_trust_store(Path(trust_store_path))
    key = keys.get(key_id)
    if key is None:
        raise AuthorizationReceiptError("AUTH_SIGNATURE_KEY_UNKNOWN")
    if key.purpose != KEY_PURPOSE:
        raise AuthorizationReceiptError("AUTH_KEY_PURPOSE_MISMATCH")
    if key.state == "revoked":
        raise AuthorizationReceiptError("AUTH_SIGNATURE_KEY_REVOKED")
    if key.state != "active":
        raise AuthorizationReceiptError("AUTH_SIGNATURE_KEY_NOT_ACTIVE")
    if key.algorithm != algorithm:
        raise AuthorizationReceiptError("AUTH_SIGNATURE_ALGORITHM_MISMATCH")

    now = datetime.now(timezone.utc)
    if key.not_before and now < key.not_before:
        raise AuthorizationReceiptError("AUTH_SIGNATURE_KEY_NOT_YET_VALID")
    if key.not_after and now >= key.not_after:
        raise AuthorizationReceiptError("AUTH_SIGNATURE_KEY_EXPIRED")

    raw_signature = _decode_base64(signature.get("value"), "AUTH_SIGNATURE_MALFORMED")
    if not _verify_signature(
        key, _public_key(key), canonical_signed_payload(receipt), raw_signature
    ):
        raise AuthorizationReceiptError("AUTH_SIGNATURE_INVALID")

    issued_at = _parse_datetime(receipt["issued_at"], "AUTH_RECEIPT_SCHEMA_INVALID")
    expires_at = _parse_datetime(receipt["expires_at"], "AUTH_RECEIPT_SCHEMA_INVALID")
    if not issued_at < expires_at:
        raise AuthorizationReceiptError("AUTH_RECEIPT_WINDOW_INVALID")
    if (expires_at - issued_at).total_seconds() > MAX_RECEIPT_LIFETIME_SECONDS:
        raise AuthorizationReceiptError("AUTH_RECEIPT_LIFETIME_EXCEEDED")
    if now < issued_at:
        raise AuthorizationReceiptError("AUTH_RECEIPT_NOT_YET_VALID")
    if now >= expires_at:
        raise AuthorizationReceiptError("AUTH_RECEIPT_EXPIRED")

    return VerifiedAuthorization(
        authorization_id=str(receipt["authorization_id"]),
        authorization_ref=str(receipt["authorization_ref"]),
        issued_at=str(receipt["issued_at"]),
        expires_at=str(receipt["expires_at"]),
        campaign_id=str(receipt["campaign_id"]),
        run_id=str(receipt["run_id"]),
        step_id=str(receipt["step_id"]),
        roe_contract_id=str(receipt["roe_contract_id"]),
        roe_contract_payload_sha256=str(receipt["roe_contract_payload_sha256"]),
        roe_step_request_id=str(receipt["roe_step_request_id"]),
        operation_id=str(receipt["operation_id"]),
        operation_version=str(receipt["operation_version"]),
        capability_id=str(receipt["capability_id"]),
        target_sha256=str(receipt["target_sha256"]),
        intrusiveness_level=str(receipt["intrusiveness_level"]),
    )
