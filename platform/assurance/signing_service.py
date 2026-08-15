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

from dataclasses import dataclass
from typing import Protocol

_HEX = frozenset("0123456789abcdef")
_MAX_PURPOSE = 128
_MAX_DOMAIN = 256
_MAX_CORRELATION_ID = 128


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
