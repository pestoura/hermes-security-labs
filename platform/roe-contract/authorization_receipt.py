"""TB1 control-plane authorization receipt contract and verifier.

Authority model (see `docs/architecture/adr/ADR-0001-plane-separation-and-authorization-authority.md`):

- **Hermes / the control plane is the only authorization authority.** It issues
  the signed authorization receipt defined here and computes the canonical
  ``authorization_ref`` that the receipt carries.
- **The execution plane (gateway) may only VALIDATE and CONSUME a receipt.** It
  may never create, expand or approve an authorization. Recomputing the
  canonical reference locally is a *verification* operation only: it proves the
  supplied ``authorization_ref`` matches the signed body. It creates no
  authority, and the reference propagated downstream is always the one carried
  by the verified receipt.

Ownership: Hermes control plane, delivered under `EPIC-28` (Rules of Engagement
as Code) with `EPIC-03` as the consuming typed-gateway boundary. The artefact
lives next to the RoE contract because it is the signed authorization layer of
the same TB0/TB1 authorization chain; it is deliberately **not** a second source
of truth and deliberately not a new plane.

Content rules: references and digests only. The receipt never carries a raw
target, operation parameters, secrets or credentials. No issuer runtime is
implemented here: this module offers canonicalization, reference derivation and
verification primitives only. Operational issuance with a private key is
``NOT_IMPLEMENTED`` / ``NOT_RUN`` in this repository, and no private key
material is ever read, accepted, stored or emitted.
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

ROOT = Path(__file__).resolve().parent

SCHEMA_VERSION = "1.0.0"
#: Explicit domain separation string. A signature produced for any other
#: protocol (notably the RoE contract) can never be replayed as a TB1
#: authorization receipt.
AUTHORIZATION_DOMAIN = "hex0r.tb1.authorization.v1"
AUTHORIZATION_REF_PREFIX = "hex0r-authz:v1:"
#: Fixed key purpose. An authorization trust store and every key inside it must
#: declare this purpose; an RoE signing key can therefore not be reused for
#: authorization, which closes the cross-protocol key-confusion path.
KEY_PURPOSE = "tb1-authorization"
CONTROL_PLANE_DOMAIN = "hermes.control-plane"
TRUST_STORE_SCHEMA_VERSION = "1.0.0"
SUPPORTED_ALGORITHMS = ("Ed25519", "ECDSA-P256-SHA256")
ACTIVE_STATE = "active"
KEY_STATES = ("active", "revoked", "retired")
MAX_VALIDITY_SECONDS = 3600

_FORBIDDEN_KEY_FIELDS = {
    "private_key",
    "privatekey",
    "secret",
    "secret_key",
    "seed",
    "passphrase",
    "password",
    "token",
}

#: Fields of the authorization body excluded from the canonical reference
#: pre-image: the reference itself and the signature over it.
_REF_EXCLUDED_TOP_LEVEL = ("authorization_ref", "signature")


class AuthorizationReceiptError(ValueError):
    """Raised with a stable code when a receipt cannot be trusted."""

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
    """Sanitized projection of a verified receipt.

    Carries stable identifiers, digests and the control-plane issued
    ``authorization_ref`` only — never a raw target, parameters, signature
    value, public key or trust-store path.
    """

    authorization_ref: str
    receipt_id: str
    authorization_id: str
    issuer_id: str
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


# ---------------------------------------------------------------------------
# canonicalization and reference derivation
# ---------------------------------------------------------------------------


def canonical_payload(receipt: Mapping[str, Any]) -> bytes:
    """Return the canonical signing pre-image of a receipt.

    The signature itself is excluded; everything else, including the
    control-plane issued ``authorization_ref``, is covered.
    """

    payload = {key: value for key, value in receipt.items() if key != "signature"}
    return json.dumps(
        payload, ensure_ascii=False, separators=(",", ":"), sort_keys=True
    ).encode("utf-8")


def payload_sha256(receipt: Mapping[str, Any]) -> str:
    return hashlib.sha256(canonical_payload(receipt)).hexdigest()


def canonical_reference_preimage(receipt: Mapping[str, Any]) -> bytes:
    """Return the domain-separated pre-image of the authorization reference.

    The pre-image is the sanitized authorization body with the reference and
    the signature removed, prefixed by the explicit domain separation string.
    ``attempt_id`` is not part of the authorization at all, so a retry of the
    same logical step reuses the same receipt and the same reference.
    """

    body = {
        key: value
        for key, value in receipt.items()
        if key not in _REF_EXCLUDED_TOP_LEVEL
    }
    encoded = json.dumps(
        body, ensure_ascii=False, separators=(",", ":"), sort_keys=True
    ).encode("utf-8")
    return AUTHORIZATION_DOMAIN.encode("utf-8") + b"\x1f" + encoded


def compute_authorization_ref(receipt: Mapping[str, Any]) -> str:
    """Compute the canonical authorization reference for a receipt body.

    This is the algorithm Hermes uses to **issue** a reference. The execution
    plane may call it only to verify that a supplied reference matches the
    signed body; doing so grants no authority and creates no authorization.
    """

    digest = hashlib.sha256(canonical_reference_preimage(receipt)).hexdigest()
    return AUTHORIZATION_REF_PREFIX + digest


# ---------------------------------------------------------------------------
# authorization trust store (public keys only, purpose-bound)
# ---------------------------------------------------------------------------


def _decode_base64(value: Any, code: str) -> bytes:
    if not isinstance(value, str) or not value:
        raise AuthorizationReceiptError(code)
    try:
        return base64.b64decode(value, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise AuthorizationReceiptError(code) from exc


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


def _load_key_entry(entry: Any) -> AuthorizationKey:
    if not isinstance(entry, Mapping):
        raise AuthorizationReceiptError("AUTHORIZATION_TRUST_STORE_INVALID")
    for key in entry:
        if str(key).lower().replace("-", "_") in _FORBIDDEN_KEY_FIELDS:
            raise AuthorizationReceiptError("AUTHORIZATION_TRUST_STORE_SECRET_MATERIAL")

    required = ("key_id", "algorithm", "state", "purpose", "public_key")
    if any(field not in entry for field in required):
        raise AuthorizationReceiptError("AUTHORIZATION_TRUST_STORE_INVALID")

    key_id = entry["key_id"]
    algorithm = entry["algorithm"]
    state = entry["state"]
    purpose = entry["purpose"]
    if not isinstance(key_id, str) or not key_id.strip():
        raise AuthorizationReceiptError("AUTHORIZATION_TRUST_STORE_INVALID")
    if purpose != KEY_PURPOSE:
        raise AuthorizationReceiptError("AUTHORIZATION_KEY_PURPOSE_MISMATCH")
    if algorithm not in SUPPORTED_ALGORITHMS:
        raise AuthorizationReceiptError("AUTHORIZATION_TRUST_STORE_ALGORITHM_UNSUPPORTED")
    if state not in KEY_STATES:
        raise AuthorizationReceiptError("AUTHORIZATION_TRUST_STORE_INVALID")

    not_before = (
        _parse_datetime(entry["not_before"], "AUTHORIZATION_TRUST_STORE_INVALID")
        if entry.get("not_before") is not None
        else None
    )
    not_after = (
        _parse_datetime(entry["not_after"], "AUTHORIZATION_TRUST_STORE_INVALID")
        if entry.get("not_after") is not None
        else None
    )
    if not_before and not_after and not not_before < not_after:
        raise AuthorizationReceiptError("AUTHORIZATION_TRUST_STORE_INVALID")

    return AuthorizationKey(
        key_id=key_id,
        algorithm=algorithm,
        state=state,
        purpose=purpose,
        public_key_der=_decode_base64(
            entry["public_key"], "AUTHORIZATION_TRUST_STORE_INVALID"
        ),
        not_before=not_before,
        not_after=not_after,
    )


def load_authorization_trust_store(path: Path) -> dict[str, AuthorizationKey]:
    """Load the dedicated authorization trust store, fail-closed on any defect.

    The store is separate from the RoE signing trust store and must declare the
    fixed ``purpose`` at document level and on every key. Pointing this loader
    at an RoE trust store refuses with a purpose code instead of silently
    accepting an RoE signing key for authorization.
    """

    try:
        raw = Path(path).read_text(encoding="utf-8")
    except OSError as exc:
        raise AuthorizationReceiptError("AUTHORIZATION_TRUST_STORE_UNAVAILABLE") from exc

    try:
        document = json.loads(raw)
    except (ValueError, UnicodeDecodeError) as exc:
        raise AuthorizationReceiptError("AUTHORIZATION_TRUST_STORE_INVALID") from exc

    if not isinstance(document, Mapping):
        raise AuthorizationReceiptError("AUTHORIZATION_TRUST_STORE_INVALID")
    if document.get("schema_version") != TRUST_STORE_SCHEMA_VERSION:
        raise AuthorizationReceiptError("AUTHORIZATION_TRUST_STORE_SCHEMA_UNSUPPORTED")
    if document.get("purpose") != KEY_PURPOSE:
        raise AuthorizationReceiptError("AUTHORIZATION_KEY_PURPOSE_MISMATCH")

    keys = document.get("keys")
    if not isinstance(keys, list) or not keys:
        raise AuthorizationReceiptError("AUTHORIZATION_TRUST_STORE_INVALID")

    loaded: dict[str, AuthorizationKey] = {}
    for entry in keys:
        key = _load_key_entry(entry)
        if key.key_id in loaded:
            raise AuthorizationReceiptError("AUTHORIZATION_TRUST_STORE_DUPLICATE_KEY_ID")
        loaded[key.key_id] = key
    return loaded


def _public_key(key: AuthorizationKey) -> Any:
    try:
        from cryptography.hazmat.primitives.asymmetric import ec, ed25519
        from cryptography.hazmat.primitives.serialization import load_der_public_key
    except ImportError as exc:  # pragma: no cover - depends on environment
        raise AuthorizationReceiptError("CRYPTO_BACKEND_UNAVAILABLE") from exc

    try:
        public_key = load_der_public_key(key.public_key_der)
    except Exception as exc:  # noqa: BLE001 - any parse failure is untrusted
        raise AuthorizationReceiptError("AUTHORIZATION_TRUST_STORE_INVALID") from exc

    if key.algorithm == "Ed25519":
        if not isinstance(public_key, ed25519.Ed25519PublicKey):
            raise AuthorizationReceiptError("AUTHORIZATION_KEY_ALGORITHM_MISMATCH")
    elif key.algorithm == "ECDSA-P256-SHA256":
        if not isinstance(public_key, ec.EllipticCurvePublicKey) or not isinstance(
            public_key.curve, ec.SECP256R1
        ):
            raise AuthorizationReceiptError("AUTHORIZATION_KEY_ALGORITHM_MISMATCH")
    else:  # pragma: no cover - guarded at load time
        raise AuthorizationReceiptError("AUTHORIZATION_TRUST_STORE_ALGORITHM_UNSUPPORTED")
    return public_key


def _verify_signature_bytes(
    key: AuthorizationKey, payload: bytes, signature: bytes
) -> bool:
    from cryptography.exceptions import InvalidSignature
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.asymmetric import ec

    public_key = _public_key(key)
    try:
        if key.algorithm == "Ed25519":
            public_key.verify(signature, payload)
        else:
            public_key.verify(signature, payload, ec.ECDSA(hashes.SHA256()))
    except InvalidSignature:
        return False
    except Exception as exc:  # noqa: BLE001 - malformed signature is untrusted
        raise AuthorizationReceiptError("AUTHORIZATION_SIGNATURE_MALFORMED") from exc
    return True


# ---------------------------------------------------------------------------
# receipt verification
# ---------------------------------------------------------------------------


def validate_receipt_structure(receipt: Mapping[str, Any]) -> None:
    if not isinstance(receipt, Mapping):
        raise AuthorizationReceiptError("AUTHORIZATION_RECEIPT_SCHEMA_INVALID")
    schema = json.loads(
        (ROOT / "authorization-receipt.schema.json").read_text(encoding="utf-8")
    )
    validator = jsonschema.Draft202012Validator(
        schema, format_checker=jsonschema.FormatChecker()
    )
    if list(validator.iter_errors(receipt)):
        raise AuthorizationReceiptError("AUTHORIZATION_RECEIPT_SCHEMA_INVALID")


def verify_receipt(
    receipt: Mapping[str, Any],
    trust_store_path: Path | None,
    *,
    now: datetime | None = None,
) -> VerifiedAuthorization:
    """Verify a control-plane issued receipt; fail closed on any defect.

    Verification order is deterministic: structure -> domain/issuer ->
    reference integrity -> validity window -> trust store and key purpose ->
    cryptographic signature. Nothing here issues, extends or approves an
    authorization.
    """

    validate_receipt_structure(receipt)

    if receipt["domain"] != AUTHORIZATION_DOMAIN:
        raise AuthorizationReceiptError("AUTHORIZATION_DOMAIN_MISMATCH")
    issuer = receipt["issuer"]
    if issuer["plane"] != "control-plane" or issuer["domain"] != CONTROL_PLANE_DOMAIN:
        raise AuthorizationReceiptError("AUTHORIZATION_ISSUER_INVALID")

    expected_ref = compute_authorization_ref(receipt)
    if receipt["authorization_ref"] != expected_ref:
        raise AuthorizationReceiptError("AUTHORIZATION_REF_MISMATCH")

    issued_at = _parse_datetime(receipt["issued_at"], "AUTHORIZATION_RECEIPT_TIME_INVALID")
    expires_at = _parse_datetime(
        receipt["expires_at"], "AUTHORIZATION_RECEIPT_TIME_INVALID"
    )
    if not issued_at < expires_at:
        raise AuthorizationReceiptError("AUTHORIZATION_RECEIPT_WINDOW_INVALID")
    if (expires_at - issued_at).total_seconds() > MAX_VALIDITY_SECONDS:
        raise AuthorizationReceiptError("AUTHORIZATION_RECEIPT_WINDOW_TOO_LONG")

    current = now or datetime.now(timezone.utc)
    if current < issued_at:
        raise AuthorizationReceiptError("AUTHORIZATION_RECEIPT_NOT_YET_VALID")
    if current >= expires_at:
        raise AuthorizationReceiptError("AUTHORIZATION_RECEIPT_EXPIRED")

    if trust_store_path is None:
        raise AuthorizationReceiptError("AUTHORIZATION_TRUST_STORE_REQUIRED")
    keys = load_authorization_trust_store(trust_store_path)

    signature = receipt["signature"]
    key = keys.get(signature["key_id"])
    if key is None:
        raise AuthorizationReceiptError("AUTHORIZATION_KEY_UNKNOWN")
    if key.purpose != KEY_PURPOSE:  # pragma: no cover - guarded at load time
        raise AuthorizationReceiptError("AUTHORIZATION_KEY_PURPOSE_MISMATCH")
    if key.state == "revoked":
        raise AuthorizationReceiptError("AUTHORIZATION_KEY_REVOKED")
    if key.state != ACTIVE_STATE:
        raise AuthorizationReceiptError("AUTHORIZATION_KEY_NOT_ACTIVE")
    if key.algorithm != signature["algorithm"]:
        raise AuthorizationReceiptError("AUTHORIZATION_KEY_ALGORITHM_MISMATCH")
    if key.not_before and current < key.not_before:
        raise AuthorizationReceiptError("AUTHORIZATION_KEY_NOT_YET_VALID")
    if key.not_after and current >= key.not_after:
        raise AuthorizationReceiptError("AUTHORIZATION_KEY_EXPIRED")

    if signature["payload_sha256"] != payload_sha256(receipt):
        raise AuthorizationReceiptError("AUTHORIZATION_SIGNATURE_PAYLOAD_MISMATCH")

    raw_signature = _decode_base64(
        signature["value"], "AUTHORIZATION_SIGNATURE_MALFORMED"
    )
    if not _verify_signature_bytes(key, canonical_payload(receipt), raw_signature):
        raise AuthorizationReceiptError("AUTHORIZATION_SIGNATURE_INVALID")

    body = receipt["authorization"]
    return VerifiedAuthorization(
        authorization_ref=str(receipt["authorization_ref"]),
        receipt_id=str(receipt["receipt_id"]),
        authorization_id=str(body["authorization_id"]),
        issuer_id=str(issuer["issuer_id"]),
        campaign_id=str(body["campaign_id"]),
        run_id=str(body["run_id"]),
        step_id=str(body["step_id"]),
        roe_contract_id=str(body["roe_contract_id"]),
        roe_contract_payload_sha256=str(body["roe_contract_payload_sha256"]),
        roe_step_request_id=str(body["roe_step_request_id"]),
        operation_id=str(body["operation_id"]),
        operation_version=str(body["operation_version"]),
        capability_id=str(body["capability_id"]),
        target_sha256=str(body["target_sha256"]),
        intrusiveness_level=str(body["intrusiveness_level"]),
    )
