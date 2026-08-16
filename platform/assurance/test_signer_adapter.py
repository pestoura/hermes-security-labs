#!/usr/bin/env python3
"""Deterministic CI-only signer for provider-neutral contract testing.

This adapter is intentionally non-authoritative and mechanically inadmissible for
LAB_L1 promotion. It exists only to exercise serialization/domain binding/signature
verification before a real external custody backend (target architecture: VAULT)
is implemented.

No key file, provider client, network access or trust-store binding exists here. The
32-byte seed is supplied directly by the caller and remains in memory for the lifetime
of the test adapter.
"""

from __future__ import annotations

import base64
import hashlib
import importlib.util
import sys

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

CI_ONLY = True
NON_AUTHORITATIVE = True
NOT_ADMISSIBLE_FOR_LAB_L1_PROMOTION = True

_SERVICE_PATH = __file__.rsplit("/", 1)[0] + "/signing_service.py"
_SERVICE_MODULE_NAME = "hsl_provider_neutral_signing_service"


def _load_signing_service():
    # Reuse an already-loaded copy when tests loaded signing_service dynamically. This
    # preserves SigningRequest class identity without turning platform/assurance into a
    # Python package solely for this repository-level contract.
    for module in tuple(sys.modules.values()):
        if getattr(module, "__file__", None) == _SERVICE_PATH:
            return module

    existing = sys.modules.get(_SERVICE_MODULE_NAME)
    if existing is not None:
        return existing

    spec = importlib.util.spec_from_file_location(_SERVICE_MODULE_NAME, _SERVICE_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError("SIGNING_SERVICE_LOAD_FAILED")
    module = importlib.util.module_from_spec(spec)
    sys.modules[_SERVICE_MODULE_NAME] = module
    spec.loader.exec_module(module)
    return module


_signing = _load_signing_service()


def verification_payload(request) -> bytes:
    """Return the canonical domain-separated bytes signed by a test adapter."""

    return _signing.canonical_signing_payload(request)


class TestSignerAdapter:
    """In-memory deterministic signer that can never satisfy LAB_L1 custody evidence."""

    __test__ = False

    def __init__(self, seed: bytes, *, key_id: str = "ci-test-ed25519") -> None:
        if not isinstance(seed, bytes) or len(seed) != 32:
            raise ValueError("CI_SIGNER_SEED_MUST_BE_32_BYTES")
        if (
            not isinstance(key_id, str)
            or not key_id
            or len(key_id) > 128
            or any(ord(char) < 32 or ord(char) == 127 for char in key_id)
        ):
            raise ValueError("CI_SIGNER_KEY_ID_INVALID")

        self._signer = Ed25519PrivateKey.from_private_bytes(seed)
        self._key_id = key_id
        self.public_key_der = self._signer.public_key().public_bytes(
            encoding=serialization.Encoding.DER,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        )
        self._spki_sha256 = hashlib.sha256(self.public_key_der).hexdigest()

    def sign(self, request):
        request = _signing.validate_signing_request(request)
        signature = self._signer.sign(verification_payload(request))
        return _signing.SigningResult(
            signature_b64=base64.b64encode(signature).decode("ascii"),
            key_id=self._key_id,
            algorithm="Ed25519",
            public_key_spki_sha256=self._spki_sha256,
            signer_class="TEST",
            authority="CI_ONLY/NON_AUTHORITATIVE",
            admissible_for_lab_l1=False,
            audit_ref=(
                f"ci-test://{request.correlation_id}/{request.digest_sha256[:12]}"
            ),
        )
