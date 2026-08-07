"""File-backed Rules of Engagement signing trust store.

The trust store holds **public verification material only**. Private keys,
seeds, passphrases and any other secret material are never read, accepted,
stored or emitted by this module, and the repository never commits key
material of any kind: deployments point the store at a path outside Git.

Every failure mode is fail-closed: an unreadable, malformed, empty,
ambiguous or otherwise untrustworthy store refuses the signature instead of
degrading to a permissive decision.
"""

from __future__ import annotations

import base64
import binascii
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

SCHEMA_VERSION = "1.0.0"
SUPPORTED_ALGORITHMS = ("Ed25519", "ECDSA-P256-SHA256")
ACTIVE_STATE = "active"
KEY_STATES = ("active", "revoked", "retired")

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


class TrustStoreError(ValueError):
    """Raised with a stable decision code when a signature cannot be trusted."""

    @property
    def decision_code(self) -> str:
        """Stable refusal code consumed by the authorization decision."""

        return str(self)


@dataclass(frozen=True)
class TrustedKey:
    key_id: str
    algorithm: str
    state: str
    public_key_der: bytes
    not_before: datetime | None
    not_after: datetime | None


def _parse_datetime(value: str, code: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (TypeError, ValueError) as exc:
        raise TrustStoreError(code) from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise TrustStoreError(code)
    return parsed


def _decode_base64(value: Any, code: str) -> bytes:
    if not isinstance(value, str) or not value:
        raise TrustStoreError(code)
    try:
        return base64.b64decode(value, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise TrustStoreError(code) from exc


def _reject_secret_material(entry: Mapping[str, Any]) -> None:
    for key in entry:
        if str(key).lower().replace("-", "_") in _FORBIDDEN_KEY_FIELDS:
            raise TrustStoreError("TRUST_STORE_SECRET_MATERIAL")


def _load_key_entry(entry: Any) -> TrustedKey:
    if not isinstance(entry, Mapping):
        raise TrustStoreError("TRUST_STORE_INVALID")
    _reject_secret_material(entry)

    required = ("key_id", "algorithm", "state", "public_key")
    if any(field not in entry for field in required):
        raise TrustStoreError("TRUST_STORE_INVALID")

    key_id = entry["key_id"]
    algorithm = entry["algorithm"]
    state = entry["state"]
    if not isinstance(key_id, str) or not key_id.strip():
        raise TrustStoreError("TRUST_STORE_INVALID")
    if algorithm not in SUPPORTED_ALGORITHMS:
        raise TrustStoreError("TRUST_STORE_ALGORITHM_UNSUPPORTED")
    if state not in KEY_STATES:
        raise TrustStoreError("TRUST_STORE_INVALID")

    not_before = (
        _parse_datetime(entry["not_before"], "TRUST_STORE_INVALID")
        if entry.get("not_before") is not None
        else None
    )
    not_after = (
        _parse_datetime(entry["not_after"], "TRUST_STORE_INVALID")
        if entry.get("not_after") is not None
        else None
    )
    if not_before and not_after and not not_before < not_after:
        raise TrustStoreError("TRUST_STORE_INVALID")

    return TrustedKey(
        key_id=key_id,
        algorithm=algorithm,
        state=state,
        public_key_der=_decode_base64(entry["public_key"], "TRUST_STORE_INVALID"),
        not_before=not_before,
        not_after=not_after,
    )


def load_trust_store(path: Path) -> dict[str, TrustedKey]:
    """Load and validate a trust store file, fail-closed on any defect."""

    try:
        raw = Path(path).read_text(encoding="utf-8")
    except OSError as exc:
        raise TrustStoreError("TRUST_STORE_UNAVAILABLE") from exc

    try:
        document = json.loads(raw)
    except (ValueError, UnicodeDecodeError) as exc:
        raise TrustStoreError("TRUST_STORE_INVALID") from exc

    if not isinstance(document, Mapping):
        raise TrustStoreError("TRUST_STORE_INVALID")
    if document.get("schema_version") != SCHEMA_VERSION:
        raise TrustStoreError("TRUST_STORE_SCHEMA_UNSUPPORTED")

    keys = document.get("keys")
    if not isinstance(keys, list) or not keys:
        raise TrustStoreError("TRUST_STORE_INVALID")

    loaded: dict[str, TrustedKey] = {}
    for entry in keys:
        key = _load_key_entry(entry)
        if key.key_id in loaded:
            raise TrustStoreError("TRUST_STORE_DUPLICATE_KEY_ID")
        loaded[key.key_id] = key
    return loaded


def _public_key(key: TrustedKey) -> Any:
    try:
        from cryptography.hazmat.primitives.asymmetric import ec, ed25519
        from cryptography.hazmat.primitives.serialization import load_der_public_key
    except ImportError as exc:  # pragma: no cover - depends on environment
        raise TrustStoreError("CRYPTO_BACKEND_UNAVAILABLE") from exc

    try:
        public_key = load_der_public_key(key.public_key_der)
    except Exception as exc:  # noqa: BLE001 - any parse failure is untrusted
        raise TrustStoreError("TRUST_STORE_INVALID") from exc

    if key.algorithm == "Ed25519":
        if not isinstance(public_key, ed25519.Ed25519PublicKey):
            raise TrustStoreError("TRUST_STORE_KEY_ALGORITHM_MISMATCH")
    elif key.algorithm == "ECDSA-P256-SHA256":
        if not isinstance(public_key, ec.EllipticCurvePublicKey) or not isinstance(
            public_key.curve, ec.SECP256R1
        ):
            raise TrustStoreError("TRUST_STORE_KEY_ALGORITHM_MISMATCH")
    else:  # pragma: no cover - guarded at load time
        raise TrustStoreError("TRUST_STORE_ALGORITHM_UNSUPPORTED")
    return public_key


def _verify_bytes(key: TrustedKey, public_key: Any, payload: bytes, signature: bytes) -> bool:
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
        raise TrustStoreError("SIGNATURE_MALFORMED") from exc
    return True


class TrustStoreVerifier:
    """Signature verifier backed by a file trust store.

    Instances are callables compatible with the existing
    ``SignatureVerifier`` protocol: ``(payload, signature) -> bool``. Every
    refusal raises :class:`TrustStoreError` carrying a stable code so the
    authorization decision stays deterministic.
    """

    def __init__(self, path: Path, *, now: datetime | None = None) -> None:
        self.path = Path(path)
        self._now = now

    def _current_time(self) -> datetime:
        return self._now or datetime.now(timezone.utc)

    def __call__(self, payload: bytes, signature: Mapping[str, Any]) -> bool:
        keys = load_trust_store(self.path)

        key_id = signature.get("key_id")
        algorithm = signature.get("algorithm")
        value = signature.get("value")
        if not isinstance(key_id, str) or not isinstance(algorithm, str):
            raise TrustStoreError("SIGNATURE_MALFORMED")

        key = keys.get(key_id)
        if key is None:
            raise TrustStoreError("SIGNATURE_KEY_UNKNOWN")
        if key.state == "revoked":
            raise TrustStoreError("SIGNATURE_KEY_REVOKED")
        if key.state != ACTIVE_STATE:
            raise TrustStoreError("SIGNATURE_KEY_NOT_ACTIVE")
        if key.algorithm != algorithm:
            raise TrustStoreError("SIGNATURE_ALGORITHM_MISMATCH")

        now = self._current_time()
        if key.not_before and now < key.not_before:
            raise TrustStoreError("SIGNATURE_KEY_NOT_YET_VALID")
        if key.not_after and now >= key.not_after:
            raise TrustStoreError("SIGNATURE_KEY_EXPIRED")

        raw_signature = _decode_base64(value, "SIGNATURE_MALFORMED")
        return _verify_bytes(key, _public_key(key), payload, raw_signature)


def build_verifier(path: Path | None, *, now: datetime | None = None) -> TrustStoreVerifier | None:
    """Return a verifier for ``path``; ``None`` keeps the fail-closed default."""

    if path is None:
        return None
    return TrustStoreVerifier(path, now=now)
