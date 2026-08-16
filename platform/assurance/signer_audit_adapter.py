#!/usr/bin/env python3
"""Provider-neutral signer-operation audit adapter for the canonical LAB_L1 AuditSink.

The adapter translates one validated signing operation into a closed public
``signer-operation-audit/v1`` record and appends that record to the already-existing
Evidence Plane ``AuditSink``. It deliberately implements no second ledger, evidence
chain or seal primitive.

Security boundaries:
- no provider client, network, subprocess or external delivery;
- no trust installation, key provisioning or private-key handling;
- no raw payload and no raw signature/base64 in the audit record;
- no execution/promotion authority; every record locks promotion false, runtime
  NOT_RUN and execution authority NONE;
- TEST signer records are mechanically marked test-only and cannot be represented as
  external LAB_L1 custody evidence.
"""

from __future__ import annotations

import base64
import hashlib
import importlib.util
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

HERE = Path(__file__).resolve().parent
EVIDENCE_PLANE = HERE.parent / "evidence-plane"
SIGNING_SERVICE_PATH = HERE / "signing_service.py"
AUDIT_SINK_PATH = EVIDENCE_PLANE / "audit_sink.py"

SCHEMA_VERSION = "signer-operation-audit/v1"
OPERATION = "SIGN"
CANONICAL_PURPOSE = "tb1-authorization"
CANONICAL_DOMAIN = "hex0r.tb1.authorization.v1"
_ALLOWED_SIGNER_CLASSES = frozenset({"VAULT", "KMS", "HSM", "TEST"})
_ALLOWED_ALGORITHMS = frozenset({"Ed25519", "ECDSA-P256-SHA256"})
_SAFE_ID_CHARS = frozenset(
    "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789._:@/-"
)
_HEX = frozenset("0123456789abcdef")
_CORRELATION_KEYS = ("campaign_id", "run_id", "step_id", "attempt_id")
_OBJECT_KIND = "evidence_record"
_OBJECT_MEDIA_TYPE = "application/json"


class SignerAuditError(ValueError):
    """Stable fail-closed signer-audit contract error."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


def _load_module(path: Path, name: str):
    resolved = path.resolve()
    for module in tuple(sys.modules.values()):
        module_file = getattr(module, "__file__", None)
        if module_file and Path(module_file).resolve() == resolved:
            return module
    existing = sys.modules.get(name)
    if existing is not None:
        return existing
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load canonical module: {path.name}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


_signing = _load_module(SIGNING_SERVICE_PATH, "_hsl_signer_audit_signing_service")
_audit = _load_module(AUDIT_SINK_PATH, "_hsl_signer_audit_canonical_sink")

SigningRequest = _signing.SigningRequest
SigningResult = _signing.SigningResult
SigningServiceError = _signing.SigningServiceError
validate_signing_request = _signing.validate_signing_request
AuditSink = _audit.AuditSink
AuditContext = _audit.AuditContext
AuditSinkError = _audit.AuditSinkError


@dataclass(frozen=True)
class SignerAuditAttribution:
    """Public attribution labels supplied by the surrounding governed workflow."""

    principal: str
    provider_ref: str
    test_only: bool = False


def sha256_hex(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _is_lower_sha256(value: object) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 64
        and all(char in _HEX for char in value)
    )


def _bounded_public_text(value: object, *, field: str, maximum: int) -> str:
    if not isinstance(value, str) or not value or len(value) > maximum:
        raise SignerAuditError(
            "SIGNER_AUDIT_RESULT_INVALID",
            f"{field} must be non-empty and at most {maximum} characters",
        )
    if any(ord(char) < 32 or ord(char) == 127 for char in value):
        raise SignerAuditError(
            "SIGNER_AUDIT_RESULT_INVALID", f"{field} contains control characters"
        )
    return value


def _safe_attribution_text(value: object, *, field: str, maximum: int = 256) -> str:
    if not isinstance(value, str) or not value or len(value) > maximum:
        raise SignerAuditError(
            "SIGNER_AUDIT_ATTRIBUTION_INVALID",
            f"{field} must be non-empty and at most {maximum} characters",
        )
    if field == "principal":
        if any(char not in _SAFE_ID_CHARS for char in value):
            raise SignerAuditError(
                "SIGNER_AUDIT_ATTRIBUTION_INVALID", "principal contains unsafe characters"
            )
    elif any(ord(char) < 32 or ord(char) == 127 for char in value):
        raise SignerAuditError(
            "SIGNER_AUDIT_ATTRIBUTION_INVALID", f"{field} contains control characters"
        )
    return value


def _validate_result(result: SigningResult) -> bytes:
    if not isinstance(result, SigningResult):
        raise SignerAuditError(
            "SIGNER_AUDIT_RESULT_INVALID", "result must be a SigningResult"
        )
    if result.signer_class not in _ALLOWED_SIGNER_CLASSES:
        raise SignerAuditError(
            "SIGNER_AUDIT_RESULT_INVALID", "unsupported signer_class"
        )
    if result.algorithm not in _ALLOWED_ALGORITHMS:
        raise SignerAuditError("SIGNER_AUDIT_RESULT_INVALID", "unsupported algorithm")
    _bounded_public_text(result.key_id, field="key_id", maximum=160)
    _bounded_public_text(result.authority, field="authority", maximum=160)
    audit_ref = _bounded_public_text(result.audit_ref, field="audit_ref", maximum=500)
    if result.signer_class == "TEST":
        if not audit_ref.startswith("ci-test://"):
            raise SignerAuditError(
                "SIGNER_AUDIT_RESULT_INVALID", "TEST audit_ref must use ci-test://"
            )
    elif not audit_ref.startswith("evidence://"):
        raise SignerAuditError(
            "SIGNER_AUDIT_RESULT_INVALID",
            "external custody audit_ref must use evidence://",
        )
    if not _is_lower_sha256(result.public_key_spki_sha256):
        raise SignerAuditError(
            "SIGNER_AUDIT_RESULT_INVALID",
            "public_key_spki_sha256 must be lowercase SHA-256",
        )
    signature_b64 = _bounded_public_text(
        result.signature_b64, field="signature_b64", maximum=8192
    )
    try:
        signature = base64.b64decode(signature_b64, validate=True)
    except (ValueError, TypeError) as exc:
        raise SignerAuditError(
            "SIGNER_AUDIT_RESULT_INVALID", "signature_b64 is not canonical base64"
        ) from exc
    if not signature:
        raise SignerAuditError(
            "SIGNER_AUDIT_RESULT_INVALID", "signature_b64 decodes to empty bytes"
        )
    return signature


def build_signer_audit_record(
    request: SigningRequest,
    result: SigningResult,
    attribution: SignerAuditAttribution,
) -> dict[str, object]:
    """Build one deterministic public signing-operation audit record.

    The result intentionally includes only digests/public identity metadata. Passing this
    function never proves custody or grants authorization/promotion authority.
    """

    try:
        request = validate_signing_request(request)
    except SigningServiceError as exc:
        raise SignerAuditError("SIGNER_AUDIT_REQUEST_INVALID", str(exc)) from exc

    if not isinstance(attribution, SignerAuditAttribution):
        raise SignerAuditError(
            "SIGNER_AUDIT_ATTRIBUTION_INVALID",
            "attribution must be SignerAuditAttribution",
        )
    principal = _safe_attribution_text(attribution.principal, field="principal")
    provider_ref = _safe_attribution_text(attribution.provider_ref, field="provider_ref")
    if not isinstance(attribution.test_only, bool):
        raise SignerAuditError(
            "SIGNER_AUDIT_ATTRIBUTION_INVALID", "test_only must be boolean"
        )

    signature = _validate_result(result)
    if result.signer_class == "TEST" and attribution.test_only is not True:
        raise SignerAuditError(
            "SIGNER_AUDIT_TEST_CLASSIFICATION_REQUIRED",
            "TEST signer operations must be explicitly test_only",
        )

    return {
        "schema_version": SCHEMA_VERSION,
        "operation": OPERATION,
        "request_digest_sha256": request.digest_sha256,
        "purpose": request.purpose,
        "domain": request.domain,
        "request_correlation_id": request.correlation_id,
        "signature_sha256": sha256_hex(signature),
        "key_id": result.key_id,
        "algorithm": result.algorithm,
        "public_key_spki_sha256": result.public_key_spki_sha256,
        "signer_class": result.signer_class,
        "authority": result.authority,
        "audit_ref": result.audit_ref,
        "principal": principal,
        "provider_ref": provider_ref,
        "test_only": bool(attribution.test_only or result.signer_class == "TEST"),
        "promotion_allowed": False,
        "runtime_status": "NOT_RUN",
        "execution_authority": "NONE",
    }


def signer_record_digest(record: Mapping[str, object]) -> tuple[str, int]:
    """Return deterministic SHA-256 and byte size of canonical public record JSON."""

    payload = json.dumps(
        dict(record), sort_keys=True, separators=(",", ":"), ensure_ascii=True
    ).encode("utf-8")
    return sha256_hex(payload), len(payload)


class CanonicalSignerAuditAdapter:
    """Signer-operation -> existing canonical AuditSink adapter."""

    def __init__(self, *, chain_id: str, correlation: Mapping[str, str]) -> None:
        if not isinstance(correlation, Mapping):
            raise SignerAuditError(
                "SIGNER_AUDIT_CONTEXT_INVALID", "correlation mapping required"
            )
        normalized: dict[str, str] = {}
        for key in _CORRELATION_KEYS:
            value = correlation.get(key)
            if (
                not isinstance(value, str)
                or not value
                or len(value) > 256
                or any(char not in _SAFE_ID_CHARS for char in value)
            ):
                raise SignerAuditError(
                    "SIGNER_AUDIT_CONTEXT_INVALID", f"invalid correlation field {key}"
                )
            normalized[key] = value
        try:
            self._sink = AuditSink(chain_id)
        except AuditSinkError as exc:
            raise SignerAuditError("SIGNER_AUDIT_CONTEXT_INVALID", str(exc)) from exc
        self._correlation = normalized

    def record_signing(
        self,
        *,
        request: SigningRequest,
        result: SigningResult,
        attribution: SignerAuditAttribution,
    ) -> dict[str, object]:
        record = build_signer_audit_record(request, result, attribution)
        digest, size = signer_record_digest(record)
        context = AuditContext(
            campaign_id=self._correlation["campaign_id"],
            run_id=self._correlation["run_id"],
            step_id=self._correlation["step_id"],
            attempt_id=self._correlation["attempt_id"],
            principal=attribution.principal,
            decision=OPERATION,
            correlation_id=request.correlation_id,
            outcome="observed" if record["test_only"] else "recorded",
            notes=SCHEMA_VERSION,
        )
        try:
            self._sink.append(
                object_kind=_OBJECT_KIND,
                object_ref=f"evidence://signer-operation/{digest}",
                object_digest_sha256=digest,
                object_size_bytes=size,
                object_media_type=_OBJECT_MEDIA_TYPE,
                context=context,
            )
        except AuditSinkError as exc:
            raise SignerAuditError("SIGNER_AUDIT_APPEND_FAILED", str(exc)) from exc
        return record

    @property
    def length(self) -> int:
        return self._sink.length

    def seal(self, *, sealed_at: str | None = None) -> dict[str, Any]:
        return self._sink.seal(sealed_at=sealed_at)

    def verify(self, *, resolver: Any | None = None) -> dict[str, Any]:
        return self._sink.verify(resolver=resolver)
