"""File-backed trust store and kill-switch state for the RoE contract.

Design boundaries:

- the repository never stores private keys or secrets; only SPKI-encoded
  public keys are loaded, and they arrive from an operator-controlled file
  outside version control;
- every failure mode is fail-closed: a missing, unreadable, malformed or
  schema-invalid file refuses verification deterministically;
- `key_id` resolves to exactly one active key; duplicates are rejected at
  load time so resolution can never be ambiguous;
- the declared signature algorithm must match the key algorithm exactly.
"""

from __future__ import annotations

import base64
import binascii
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

import jsonschema

try:  # pragma: no cover - import guard exercised only without cryptography
    from cryptography.exceptions import InvalidSignature
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import ec, ed25519

    CRYPTOGRAPHY_AVAILABLE = True
except ModuleNotFoundError:  # pragma: no cover
    CRYPTOGRAPHY_AVAILABLE = False

ROOT = Path(__file__).resolve().parent
TRUST_STORE_SCHEMA = ROOT / "roe-trust-store.schema.json"
KILL_SWITCH_SCHEMA = ROOT / "roe-kill-switch.schema.json"

SUPPORTED_ALGORITHMS = ("Ed25519", "ECDSA-P256-SHA256")
MAX_STORE_BYTES = 1_048_576


class TrustStoreError(ValueError):
    """Raised with a stable code when trust material cannot be trusted."""


@dataclass(frozen=True)
class TrustedKey:
    key_id: str
    algorithm: str
    state: str
    not_before: datetime
    not_after: datetime
    public_key_spki: bytes

    def is_usable_at(self, moment: datetime) -> bool:
        return (
            self.state == "active"
            and self.not_before <= moment < self.not_after
        )


@dataclass(frozen=True)
class KillSwitchState:
    state: str
    updated_at: datetime
    campaign_id: str | None
    reason_code: str | None

    @property
    def engaged(self) -> bool:
        return self.state == "engaged"

    def applies_to(self, campaign_id: str | None) -> bool:
        if not self.engaged:
            return False
        if self.campaign_id is None:
            return True
        return self.campaign_id == campaign_id


def _load_json_document(path: Path, schema_path: Path, error_prefix: str) -> dict[str, Any]:
    try:
        raw = path.read_bytes()
    except OSError as exc:
        raise TrustStoreError(f"{error_prefix}_UNAVAILABLE") from exc
    if len(raw) > MAX_STORE_BYTES:
        raise TrustStoreError(f"{error_prefix}_TOO_LARGE")
    try:
        document = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise TrustStoreError(f"{error_prefix}_MALFORMED") from exc
    if not isinstance(document, dict):
        raise TrustStoreError(f"{error_prefix}_MALFORMED")
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    validator = jsonschema.Draft202012Validator(
        schema,
        format_checker=jsonschema.FormatChecker(),
    )
    if list(validator.iter_errors(document)):
        raise TrustStoreError(f"{error_prefix}_SCHEMA_INVALID")
    return document


def _parse_datetime(value: str, error_code: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError as exc:
        raise TrustStoreError(error_code) from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise TrustStoreError(error_code)
    return parsed.astimezone(timezone.utc)


def _decode_base64(value: str, error_code: str) -> bytes:
    try:
        return base64.b64decode(value, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise TrustStoreError(error_code) from exc


class TrustStore:
    """Immutable, fail-closed view over an operator-provided key file."""

    def __init__(self, keys: Mapping[str, TrustedKey], store_id: str | None = None) -> None:
        self._keys = dict(keys)
        self.store_id = store_id

    @classmethod
    def load(cls, path: Path | str) -> "TrustStore":
        document = _load_json_document(
            Path(path), TRUST_STORE_SCHEMA, "TRUST_STORE"
        )
        keys: dict[str, TrustedKey] = {}
        for entry in document["keys"]:
            key_id = str(entry["key_id"])
            if key_id in keys:
                raise TrustStoreError("TRUST_STORE_DUPLICATE_KEY_ID")
            not_before = _parse_datetime(
                entry["not_before"], "TRUST_STORE_INVALID_VALIDITY"
            )
            not_after = _parse_datetime(
                entry["not_after"], "TRUST_STORE_INVALID_VALIDITY"
            )
            if not_before >= not_after:
                raise TrustStoreError("TRUST_STORE_INVALID_VALIDITY")
            spki = _decode_base64(
                entry["public_key_spki_base64"], "TRUST_STORE_INVALID_PUBLIC_KEY"
            )
            key = TrustedKey(
                key_id=key_id,
                algorithm=str(entry["algorithm"]),
                state=str(entry["state"]),
                not_before=not_before,
                not_after=not_after,
                public_key_spki=spki,
            )
            _load_public_key(key)
            keys[key_id] = key
        return cls(keys, store_id=document.get("store_id"))

    def resolve(self, key_id: str, algorithm: str, moment: datetime) -> TrustedKey:
        key = self._keys.get(str(key_id))
        if key is None:
            raise TrustStoreError("TRUST_STORE_KEY_UNKNOWN")
        if key.state == "revoked":
            raise TrustStoreError("TRUST_STORE_KEY_REVOKED")
        if not key.is_usable_at(moment.astimezone(timezone.utc)):
            raise TrustStoreError("TRUST_STORE_KEY_EXPIRED")
        if key.algorithm != str(algorithm):
            raise TrustStoreError("TRUST_STORE_ALGORITHM_MISMATCH")
        return key

    def key_ids(self) -> tuple[str, ...]:
        return tuple(sorted(self._keys))


def _load_public_key(key: TrustedKey) -> Any:
    if not CRYPTOGRAPHY_AVAILABLE:
        raise TrustStoreError("TRUST_STORE_CRYPTO_UNAVAILABLE")
    if key.algorithm not in SUPPORTED_ALGORITHMS:
        raise TrustStoreError("TRUST_STORE_ALGORITHM_UNSUPPORTED")
    try:
        public_key = serialization.load_der_public_key(key.public_key_spki)
    except Exception as exc:  # noqa: BLE001 - any parse failure is fail-closed
        raise TrustStoreError("TRUST_STORE_INVALID_PUBLIC_KEY") from exc
    if key.algorithm == "Ed25519":
        if not isinstance(public_key, ed25519.Ed25519PublicKey):
            raise TrustStoreError("TRUST_STORE_ALGORITHM_MISMATCH")
    else:
        if not isinstance(public_key, ec.EllipticCurvePublicKey) or not isinstance(
            public_key.curve, ec.SECP256R1
        ):
            raise TrustStoreError("TRUST_STORE_ALGORITHM_MISMATCH")
    return public_key


def verify_with_trust_store(
    store: TrustStore,
    payload: bytes,
    signature: Mapping[str, Any],
    moment: datetime,
) -> bool:
    """Verify a detached signature envelope against the trust store.

    Returns True only for a cryptographically valid signature produced by a
    resolvable, active, non-expired key whose algorithm matches the envelope.
    Any other outcome raises `TrustStoreError` or returns False.
    """

    algorithm = str(signature.get("algorithm", ""))
    key_id = str(signature.get("key_id", ""))
    key = store.resolve(key_id, algorithm, moment)
    public_key = _load_public_key(key)
    raw_signature = _decode_base64(
        str(signature.get("value", "")), "SIGNATURE_ENCODING_INVALID"
    )
    try:
        if algorithm == "Ed25519":
            public_key.verify(raw_signature, payload)
        else:
            public_key.verify(raw_signature, payload, ec.ECDSA(hashes.SHA256()))
    except InvalidSignature:
        return False
    except Exception as exc:  # noqa: BLE001
        raise TrustStoreError("SIGNATURE_VERIFICATION_FAILED") from exc
    return True


def make_trust_store_verifier(store: TrustStore, moment: datetime):
    """Adapt a trust store to the `SignatureVerifier` callable contract."""

    def _verifier(payload: bytes, signature: Mapping[str, Any]) -> bool:
        return verify_with_trust_store(store, payload, signature, moment)

    return _verifier


def load_kill_switch_state(path: Path | str) -> KillSwitchState:
    document = _load_json_document(Path(path), KILL_SWITCH_SCHEMA, "KILL_SWITCH")
    scope = document.get("scope") or {}
    campaign_id = scope.get("campaign_id")
    return KillSwitchState(
        state=str(document["state"]),
        updated_at=_parse_datetime(document["updated_at"], "KILL_SWITCH_MALFORMED"),
        campaign_id=str(campaign_id) if campaign_id is not None else None,
        reason_code=document.get("reason_code"),
    )
