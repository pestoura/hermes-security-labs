#!/usr/bin/env python3
"""Fail-closed trust binding validation for the Runner runtime boundary (phase B).

Trust binding is intentionally NOT created or installed by the base
``#354`` deployment. The committed example descriptor is never treated as live,
and this module never creates or synthesizes a private signing key.

A trust binding is accepted only when it is built from an explicit *external*
source: a public, approved trust store with a known expected SHA-256, validated
fail-closed. Any other form (none, embedded, synthesized, example-as-live) is
rejected.

Phase B binding (``bind_trust_store``) is an *explicit* call only. It is never
invoked by the base deployment or the HOLD listener. It validates a regular,
non-symlink, public JSON trust store whose SHA-256 matches exactly, rejects any
private/secret material, and installs it to the canonical destination
``/etc/hexor/runner/authorization-trust-store.json`` owned root:hexor-runner
(4101) mode 0640 atomically. An existing destination that differs from the
validated source fails closed (RED). It never searches for or uses the committed
example descriptor and never generates a key.
"""

from __future__ import annotations

import hashlib
import json
import os
import stat
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping


class TrustBindingError(ValueError):
    """Stable fail-closed trust binding error."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class TrustBindingSource:
    """Explicit external trust store source for phase B binding validation.

    ``trust_store_path`` points at a *public* trust store that has already been
    delivered out-of-band. ``expected_sha256`` is the pinned digest that must
    match the on-disk file exactly. ``public_source`` asserts the store is an
    approved public trust store, not a synthesized or committed example.
    """

    trust_store_path: str
    expected_sha256: str
    public_source: bool

    def as_safe_dict(self) -> dict[str, Any]:
        return {
            "trust_store_path": self.trust_store_path,
            "expected_sha256": self.expected_sha256,
            "public_source": self.public_source,
        }


# Canonical destination for an explicitly-bound public trust store (phase B).
TRUST_STORE_CANONICAL_PATH = "/etc/hexor/runner/authorization-trust-store.json"

# Canonical destination ownership/mode: root-owned, group hexor-runner (4101),
# mode 0640 (root read/write, runner group read-only). Set atomically after a
# full validation pass; never created by the base deployment or the listener.
TRUST_STORE_OWNER_UID = 0
TRUST_STORE_OWNER_GID = 4101
TRUST_STORE_MODE = 0o0640

# Field names that, if present in a public trust store JSON, indicate private or
# secret material. Phase B binding rejects such stores fail-closed.
_PRIVATE_MATERIAL_KEYS = (
    "private_key", "private_key_pem", "private-key", "privatekey",
    "client_secret", "client-secret", "clientsecret",
    "secret", "signing_key", "signing-key", "signingkey",
    "api_key", "api-key", "apikey", "token", "password", "bearer",
)


def _is_hex_sha256(value: str) -> bool:
    return isinstance(value, str) and len(value) == 64 and all(c in "0123456789abcdef" for c in value)


def _contains_private_material(document: Any) -> bool:
    """Recursively reject JSON that carries private/secret material."""

    if isinstance(document, Mapping):
        for key, value in document.items():
            if isinstance(key, str) and key.lower() in _PRIVATE_MATERIAL_KEYS:
                return True
            if _contains_private_material(value):
                return True
    elif isinstance(document, (list, tuple, set)):
        for item in document:
            if _contains_private_material(item):
                return True
    return False


def validate_trust_binding(source: TrustBindingSource) -> Mapping[str, Any]:
    """Validate an explicit external trust binding fail-closed.

    Returns a safe summary dict. Raises ``TrustBindingError`` when the binding is
    not an explicit, public, SHA-256-pinned external source, when the on-disk
    store does not match exactly, or when it carries private/secret material.
    """

    if not isinstance(source, TrustBindingSource):
        raise TrustBindingError("BINDING_INVALID", "trust binding must be an explicit external source")

    if not source.public_source:
        raise TrustBindingError(
            "BINDING_NOT_PUBLIC",
            "trust binding requires an explicit public, approved trust store source",
        )

    if not _is_hex_sha256(source.expected_sha256):
        raise TrustBindingError(
            "BINDING_DIGEST_INVALID",
            "expected_sha256 must be a 64-char lowercase hex SHA-256 digest",
        )

    path = Path(source.trust_store_path)
    try:
        data = path.read_bytes()
    except OSError as exc:
        raise TrustBindingError("BINDING_UNREADABLE", f"trust store unreadable: {exc}") from exc

    actual = hashlib.sha256(data).hexdigest()
    if actual != source.expected_sha256:
        raise TrustBindingError(
            "BINDING_DIGEST_MISMATCH",
            f"trust store SHA-256 mismatch: expected {source.expected_sha256}, got {actual}",
        )

    try:
        document = json.loads(data)
    except json.JSONDecodeError as exc:
        raise TrustBindingError("BINDING_INVALID_JSON", f"trust store is not valid JSON: {exc}") from exc

    if not isinstance(document, Mapping):
        raise TrustBindingError("BINDING_INVALID_SHAPE", "trust store must be a JSON object")

    if _contains_private_material(document):
        raise TrustBindingError(
            "BINDING_PRIVATE_MATERIAL",
            "trust store must not contain private/secret material",
        )

    return {
        "bound": True,
        "trust_store_path": str(path),
        "sha256": actual,
        "public_source": True,
    }


def bind_trust_store(
    source: TrustBindingSource,
    destination: str = TRUST_STORE_CANONICAL_PATH,
) -> Mapping[str, Any]:
    """Validate-then-install an explicit external public trust store (phase B only).

    This is an *explicit* call: never invoked by the base ``#354`` deployment or
    the HOLD listener. The source must be a regular, non-symlink, public JSON
    file whose SHA-256 matches exactly; private/secret material is rejected. The
    destination is the canonical
    ``/etc/hexor/runner/authorization-trust-store.json`` owned root:hexor-runner
    (4101) mode 0640. An existing destination that differs from the validated
    source fails closed (RED). The committed example descriptor is never used as
    the source and no key is ever generated.
    """

    if str(destination) != TRUST_STORE_CANONICAL_PATH:
        raise TrustBindingError("BINDING_DEST_INVALID", "trust store destination must be the canonical path")

    return _install_trust_store_atomic(source, Path(destination))


def _install_trust_store_atomic(source: TrustBindingSource, dest: Path) -> Mapping[str, Any]:
    """Validate and atomically install a public trust store at ``dest``.

    Source must be a regular, non-symlink, public JSON file whose SHA-256 matches
    exactly; private/secret material is rejected. An existing ``dest`` with a
    different digest fails closed (BINDING_DEST_EXISTING_DIFFERS). On success the
    file is owned root:hexor-runner (best-effort when not privileged) and mode
    0640.
    """

    if not isinstance(source, TrustBindingSource):
        raise TrustBindingError("BINDING_INVALID", "trust binding must be an explicit external source")

    if not source.public_source:
        raise TrustBindingError(
            "BINDING_NOT_PUBLIC",
            "trust binding requires an explicit public, approved trust store source",
        )

    if not _is_hex_sha256(source.expected_sha256):
        raise TrustBindingError(
            "BINDING_DIGEST_INVALID",
            "expected_sha256 must be a 64-char lowercase hex SHA-256 digest",
        )

    path = Path(source.trust_store_path)
    if path.is_symlink():
        raise TrustBindingError("BINDING_SOURCE_SYMLINK", "trust store source must be a regular file, not a symlink")
    if not path.is_file() or not stat.S_ISREG(os.lstat(path).st_mode):
        raise TrustBindingError("BINDING_NOT_REGULAR", f"trust store source is not a regular file: {path}")

    try:
        data = path.read_bytes()
    except OSError as exc:
        raise TrustBindingError("BINDING_UNREADABLE", f"trust store unreadable: {exc}") from exc

    actual = hashlib.sha256(data).hexdigest()
    if actual != source.expected_sha256:
        raise TrustBindingError(
            "BINDING_DIGEST_MISMATCH",
            f"trust store SHA-256 mismatch: expected {source.expected_sha256}, got {actual}",
        )

    try:
        document = json.loads(data)
    except json.JSONDecodeError as exc:
        raise TrustBindingError("BINDING_INVALID_JSON", f"trust store is not valid JSON: {exc}") from exc
    if not isinstance(document, Mapping):
        raise TrustBindingError("BINDING_INVALID_SHAPE", "trust store must be a JSON object")
    if _contains_private_material(document):
        raise TrustBindingError(
            "BINDING_PRIVATE_MATERIAL",
            "trust store must not contain private/secret material",
        )

    # Fail closed on an existing destination that differs from the validated store.
    if dest.exists():
        try:
            existing_bytes = dest.read_bytes()
        except OSError as exc:
            raise TrustBindingError("BINDING_DEST_UNREADABLE", f"existing destination unreadable: {exc}") from exc
        if hashlib.sha256(existing_bytes).hexdigest() != actual:
            raise TrustBindingError(
                "BINDING_DEST_EXISTING_DIFFERS",
                f"existing trust store at {dest} differs from the validated source; refusing to overwrite",
            )

    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(dest.suffix + ".tmp")
    try:
        tmp.write_bytes(data)
        try:
            os.chmod(tmp, TRUST_STORE_MODE)
        except OSError:
            pass
        try:
            os.chown(tmp, TRUST_STORE_OWNER_UID, TRUST_STORE_OWNER_GID)
        except OSError:
            pass
        os.replace(tmp, dest)
    except OSError as exc:
        try:
            tmp.unlink()
        except OSError:
            pass
        raise TrustBindingError("BINDING_INSTALL_FAILED", f"trust store install failed: {exc}") from exc
    try:
        os.chmod(dest, TRUST_STORE_MODE)
    except OSError:
        pass

    return {
        "bound": True,
        "trust_store_path": str(dest),
        "sha256": actual,
        "public_source": True,
        "destination": str(dest),
        "owner_uid": TRUST_STORE_OWNER_UID,
        "owner_gid": TRUST_STORE_OWNER_GID,
        "mode": oct(TRUST_STORE_MODE),
    }


def from_cli_args(args: Mapping[str, Any]) -> TrustBindingSource | None:
    """Construct a binding source only from explicit external CLI arguments.

    Returns ``None`` when no explicit source is supplied (phase A safe default).
    Never fabricates a store path or digest.
    """

    path = args.get("trust_store_path")
    digest = args.get("expected_sha256")
    public = bool(args.get("public_source"))
    if not path and not digest and not public:
        return None  # no binding requested
    if not path or not digest or not public:
        raise TrustBindingError(
            "BINDING_ARGS_INCOMPLETE",
            "explicit trust binding requires trust_store_path, expected_sha256 and public_source",
        )
    return TrustBindingSource(trust_store_path=str(path), expected_sha256=str(digest), public_source=public)
