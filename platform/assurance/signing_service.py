#!/usr/bin/env python3
"""Provider-neutral external signing-service boundary for Hermes assurance flows.

This module is deliberately provider-agnostic. It defines only the bounded data
contract that a future external custody backend must implement. It performs no
networking, process execution, provider access, trust installation or key handling.

The boundary accepts an already-computed SHA-256 digest plus explicit purpose/domain
metadata. Raw commands, evidence payloads and arbitrary content do not cross this
contract. Runtime/provider attestation, custody evidence and trust verification remain
separate canonical gates.
"""

from __future__ import annotations

import base64
from dataclasses import dataclass
from typing import Protocol

_HEX = frozenset("0123456789abcdef")
_MAX_PURPOSE = 128
_MAX_DOMAIN = 256
_MAX_CORRELATION_ID = 128
_MAX_RESULT_TEXT = 500
_MAX_SIGNATURE_B64 = 8192
_LAB_L1_CUSTODY_CLASSES = frozenset({"VAULT", "KMS", "HSM"})
_LAB_L1_ALGORITHMS = frozenset({"Ed25519", "ECDSA-P256-SHA256"})
_NON_AUTHORITATIVE_MARKERS = ("CI_ONLY", "NON_AUTHORITATIVE", "TEST")


class SigningServiceError(ValueError):
    """Stable fail-closed signing-boundary error."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class SigningRequest:
    digest_sha256: str
    purpose: str
    domain: str
    correlation_id: str


@dataclass(frozen=True)
class SigningResult:
    signature_b64: str
    key_id: str
    algorithm: str
    public_key_spki_sha256: str
    signer_class: str
    authority: str
    admissible_for_lab_l1: bool
    audit_ref: str


class SigningService(Protocol):
    """Provider-neutral signing interface.

    Implementations may only consume a validated :class:`SigningRequest` and return
    public signature/identity metadata. The interface itself grants no execution or
    promotion authority.
    """

    def sign(self, request: SigningRequest) -> SigningResult:
        ...


def _bounded_text(value: object, *, field: str, maximum: int) -> str:
    if not isinstance(value, str) or not value or len(value) > maximum:
        raise SigningServiceError(
            "SIGNING_REQUEST_INVALID", f"{field} must be non-empty and at most {maximum} characters"
        )
    if any(ord(char) < 32 or ord(char) == 127 for char in value):
        raise SigningServiceError(
            "SIGNING_REQUEST_INVALID", f"{field} contains control characters"
        )
    return value


def _bounded_result_text(value: object, *, field: str, maximum: int = _MAX_RESULT_TEXT) -> str:
    if not isinstance(value, str) or not value or len(value) > maximum:
        raise SigningServiceError(
            "SIGNER_RESPONSE_INVALID",
            f"{field} must be non-empty and at most {maximum} characters",
        )
    if any(ord(char) < 32 or ord(char) == 127 for char in value):
        raise SigningServiceError(
            "SIGNER_RESPONSE_INVALID", f"{field} contains control characters"
        )
    return value


def validate_signing_request(request: SigningRequest) -> SigningRequest:
    """Validate a bounded digest-only signing request and return it unchanged."""

    if not isinstance(request, SigningRequest):
        raise SigningServiceError(
            "SIGNING_REQUEST_INVALID", "request must be a SigningRequest"
        )

    digest = request.digest_sha256
    if (
        not isinstance(digest, str)
        or len(digest) != 64
        or any(char not in _HEX for char in digest)
    ):
        raise SigningServiceError(
            "SIGNING_REQUEST_INVALID",
            "digest_sha256 must be exactly 64 lowercase hexadecimal characters",
        )

    _bounded_text(request.purpose, field="purpose", maximum=_MAX_PURPOSE)
    _bounded_text(request.domain, field="domain", maximum=_MAX_DOMAIN)
    _bounded_text(
        request.correlation_id,
        field="correlation_id",
        maximum=_MAX_CORRELATION_ID,
    )
    return request


def require_lab_l1_admissible(result: SigningResult) -> SigningResult:
    """Require a structurally admissible external-custody result envelope.

    This is deliberately only a *preliminary envelope guard*. Passing it does not prove
    signer custody, provider authenticity, R1-R8 compliance, source-evidence integrity or
    trust binding, and it never grants execution or promotion authority. Those properties
    remain the responsibility of the canonical runtime signer-attestation,
    EvidenceVerifier and trust-store gates.

    CI/test signers, PKCS11 as a standalone class and explicitly non-authoritative
    envelopes fail closed before any structural acceptance can be inferred.
    """

    if not isinstance(result, SigningResult):
        raise SigningServiceError(
            "SIGNER_RESPONSE_INVALID", "result must be a SigningResult"
        )

    if result.admissible_for_lab_l1 is not True:
        raise SigningServiceError(
            "SIGNER_NOT_ADMISSIBLE", "signer result is not marked LAB_L1-admissible"
        )

    if result.signer_class not in _LAB_L1_CUSTODY_CLASSES:
        raise SigningServiceError(
            "SIGNER_NOT_ADMISSIBLE",
            "signer class is not an admissible external custody backend",
        )

    authority = _bounded_result_text(result.authority, field="authority", maximum=160)
    authority_upper = authority.upper()
    if any(marker in authority_upper for marker in _NON_AUTHORITATIVE_MARKERS):
        raise SigningServiceError(
            "SIGNER_NOT_ADMISSIBLE", "signer authority is explicitly non-authoritative"
        )

    if result.algorithm not in _LAB_L1_ALGORITHMS:
        raise SigningServiceError(
            "SIGNER_RESPONSE_INVALID", "signer algorithm is not supported for LAB_L1"
        )

    _bounded_result_text(result.key_id, field="key_id", maximum=160)

    spki_digest = result.public_key_spki_sha256
    if (
        not isinstance(spki_digest, str)
        or len(spki_digest) != 64
        or any(char not in _HEX for char in spki_digest)
    ):
        raise SigningServiceError(
            "SIGNER_RESPONSE_INVALID",
            "public_key_spki_sha256 must be exactly 64 lowercase hexadecimal characters",
        )

    signature_b64 = _bounded_result_text(
        result.signature_b64, field="signature_b64", maximum=_MAX_SIGNATURE_B64
    )
    try:
        signature = base64.b64decode(signature_b64, validate=True)
    except (ValueError, TypeError) as exc:
        raise SigningServiceError(
            "SIGNER_RESPONSE_INVALID", "signature_b64 is not canonical base64"
        ) from exc
    if not signature:
        raise SigningServiceError(
            "SIGNER_RESPONSE_INVALID", "signature_b64 decodes to an empty signature"
        )

    audit_ref = _bounded_result_text(result.audit_ref, field="audit_ref")
    if not audit_ref.startswith("evidence://") or len(audit_ref) <= len("evidence://"):
        raise SigningServiceError(
            "SIGNER_RESPONSE_INVALID", "audit_ref must be a canonical evidence:// reference"
        )

    return result
