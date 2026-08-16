#!/usr/bin/env python3
"""Repository-only TB1 authorization decision audit adapter.

Builds sanitized ``authorization-receipt-audit/v1`` records and appends them to
the existing canonical LAB_L1 AuditSink. Optional injected custody may persist the
same sanitized record through the existing Evidence Plane and bind its canonical
``ev_`` identifier into the AuditSink entry.

The adapter implements no receipt verification, authorization issuance, runtime
transport, datastore, EvidenceChain, seal, trust installation, Runner effect or
execution/promotion authority.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import re
import sys
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
AUDIT_SINK_PATH = HERE.parent / "evidence-plane" / "audit_sink.py"

SCHEMA_VERSION = "authorization-receipt-audit/v1"
AUTHORIZATION_REF_PREFIX = "tb1-authz:v1:"
AUTHORIZATION_REF = re.compile(r"^tb1-authz:v1:[a-f0-9]{64}$")
SAFE_ID = re.compile(r"^[A-Za-z0-9._:@/-]{1,256}$")
REASON_CODE = re.compile(r"^[A-Z][A-Z0-9_]{0,255}$")
EVIDENCE_ID = re.compile(r"^ev_[a-f0-9]{32}$")
EVIDENCE_URI = re.compile(r"^evidence://(ev_[a-f0-9]{32})$")
CONTEXT_FIELDS = {
    "campaign_id",
    "run_id",
    "step_id",
    "attempt_id",
    "principal",
    "correlation_id",
}
EVENT_MATRIX = {
    "REGISTERED": ("REGISTRATION", "ACCEPT"),
    "LOOKUP_HIT": ("LOOKUP", "ACCEPT"),
    "LOOKUP_MISS": ("LOOKUP", "DENY"),
    "LOOKUP_EXPIRED": ("LOOKUP", "DENY"),
}


class AuthorizationAuditError(ValueError):
    """Stable fail-closed authorization-audit contract error."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


def _load_audit_sink() -> Any:
    name = "_hsl_authorization_audit_sink"
    existing = sys.modules.get(name)
    if existing is not None:
        return existing
    spec = importlib.util.spec_from_file_location(name, AUDIT_SINK_PATH)
    if spec is None or spec.loader is None:  # pragma: no cover - packaging defect
        raise RuntimeError("cannot load canonical AuditSink")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


_audit = _load_audit_sink()
AuditSink = _audit.AuditSink
AuditContext = _audit.AuditContext
AuditSinkError = _audit.AuditSinkError


@dataclass(frozen=True)
class AuthorizationAuditContext:
    campaign_id: str
    run_id: str
    step_id: str
    attempt_id: str
    principal: str
    correlation_id: str

    def __post_init__(self) -> None:
        for field in (
            "campaign_id",
            "run_id",
            "step_id",
            "attempt_id",
            "principal",
            "correlation_id",
        ):
            value = getattr(self, field)
            if not isinstance(value, str) or not SAFE_ID.fullmatch(value):
                raise AuthorizationAuditError(
                    "AUTHORIZATION_AUDIT_CONTEXT_INVALID",
                    f"invalid trusted audit context field {field}",
                )


def _normalize_context(value: object) -> AuthorizationAuditContext:
    if isinstance(value, AuthorizationAuditContext):
        return value
    if not isinstance(value, Mapping) or set(value) != CONTEXT_FIELDS:
        raise AuthorizationAuditError(
            "AUTHORIZATION_AUDIT_CONTEXT_INVALID",
            "exact trusted authorization audit context fields are required",
        )
    try:
        return AuthorizationAuditContext(**dict(value))
    except (TypeError, ValueError) as exc:
        if isinstance(exc, AuthorizationAuditError):
            raise
        raise AuthorizationAuditError(
            "AUTHORIZATION_AUDIT_CONTEXT_INVALID",
            "trusted authorization audit context is invalid",
        ) from exc


def _bounded_public(value: object, *, field: str, maximum: int) -> str | None:
    if value is None:
        return None
    if (
        not isinstance(value, str)
        or not value
        or len(value) > maximum
        or not SAFE_ID.fullmatch(value)
    ):
        raise AuthorizationAuditError(
            "AUTHORIZATION_AUDIT_EVENT_INVALID",
            f"{field} is not bounded public metadata",
        )
    return value


def _authorization_ref_sha256(value: object) -> str | None:
    if not isinstance(value, str) or not AUTHORIZATION_REF.fullmatch(value):
        return None
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _validate_event_matrix(event_type: object, phase: object, decision: object) -> None:
    if not all(isinstance(item, str) for item in (event_type, phase, decision)):
        raise AuthorizationAuditError(
            "AUTHORIZATION_AUDIT_EVENT_INVALID", "event type, phase and decision are required"
        )
    if event_type == "REFUSED":
        if phase not in {"DELIVERY", "REGISTRATION"} or decision != "DENY":
            raise AuthorizationAuditError(
                "AUTHORIZATION_AUDIT_EVENT_INVALID",
                "REFUSED must be a DELIVERY or REGISTRATION denial",
            )
        return
    expected = EVENT_MATRIX.get(event_type)
    if expected is None or (phase, decision) != expected:
        raise AuthorizationAuditError(
            "AUTHORIZATION_AUDIT_EVENT_INVALID",
            "event type, phase and decision do not match the canonical matrix",
        )


def build_authorization_audit_record(
    *,
    event_type: str,
    phase: str,
    decision: str,
    reason_code: str,
    authorization_ref: object,
    duplicate: bool,
    capability_id: str | None,
    intrusiveness_level: str | None,
) -> dict[str, object]:
    """Build deterministic sanitized public authorization decision metadata."""

    _validate_event_matrix(event_type, phase, decision)
    if not isinstance(reason_code, str) or not REASON_CODE.fullmatch(reason_code):
        raise AuthorizationAuditError(
            "AUTHORIZATION_AUDIT_REASON_INVALID", "reason_code must be a bounded machine label"
        )
    if not isinstance(duplicate, bool):
        raise AuthorizationAuditError(
            "AUTHORIZATION_AUDIT_EVENT_INVALID", "duplicate must be boolean"
        )
    capability = _bounded_public(capability_id, field="capability_id", maximum=256)
    intrusiveness = _bounded_public(
        intrusiveness_level, field="intrusiveness_level", maximum=64
    )

    return {
        "schema_version": SCHEMA_VERSION,
        "event_type": event_type,
        "phase": phase,
        "decision": decision,
        "reason_code": reason_code,
        "authorization_ref_sha256": _authorization_ref_sha256(authorization_ref),
        "duplicate": duplicate,
        "capability_id": capability,
        "intrusiveness_level": intrusiveness,
        "promotion_allowed": False,
        "runtime_status": "NOT_RUN",
        "execution_authority": "NONE",
    }


def authorization_audit_record_digest(record: dict[str, object]) -> tuple[str, int]:
    payload = json.dumps(
        record, sort_keys=True, separators=(",", ":"), ensure_ascii=True
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest(), len(payload)


def _canonical_evidence_id(evidence_ref: object) -> str:
    """Normalize Evidence Plane custody URI/id to AuditSink's canonical ``ev_`` ID."""

    if isinstance(evidence_ref, str) and EVIDENCE_ID.fullmatch(evidence_ref):
        return evidence_ref
    if isinstance(evidence_ref, str):
        match = EVIDENCE_URI.fullmatch(evidence_ref)
        if match:
            return match.group(1)
    raise AuthorizationAuditError(
        "AUTHORIZATION_AUDIT_EVIDENCE_REF_INVALID",
        "evidence_ref must be ev_<32 lowercase hex> or evidence://ev_<32 lowercase hex>",
    )


def _utc_now_z() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


class CanonicalAuthorizationAuditAdapter:
    """Authorization-decision -> existing canonical AuditSink adapter."""

    def __init__(
        self,
        *,
        chain_id: str,
        custody: Any | None = None,
        evidence_store: Any | None = None,
        recorded_at_provider: Callable[[], str] | None = None,
    ) -> None:
        try:
            self._sink = AuditSink(chain_id)
        except AuditSinkError as exc:
            raise AuthorizationAuditError(
                "AUTHORIZATION_AUDIT_SINK_INVALID", str(exc)
            ) from exc
        if recorded_at_provider is not None and not callable(recorded_at_provider):
            raise AuthorizationAuditError(
                "AUTHORIZATION_AUDIT_CUSTODY_INVALID",
                "recorded_at_provider must be callable",
            )
        self._custody = custody
        self._evidence_store = evidence_store
        self._recorded_at_provider = recorded_at_provider or _utc_now_z
        self._emitted: dict[tuple[str, ...], dict[str, object]] = {}
        self._pending_recorded_at: dict[tuple[str, ...], str] = {}

    def record_event(
        self,
        *,
        context: AuthorizationAuditContext | Mapping[str, str],
        event_type: str,
        phase: str,
        decision: str,
        reason_code: str,
        authorization_ref: object,
        duplicate: bool,
        capability_id: str | None,
        intrusiveness_level: str | None,
    ) -> dict[str, object]:
        normalized_context = _normalize_context(context)
        record = build_authorization_audit_record(
            event_type=event_type,
            phase=phase,
            decision=decision,
            reason_code=reason_code,
            authorization_ref=authorization_ref,
            duplicate=duplicate,
            capability_id=capability_id,
            intrusiveness_level=intrusiveness_level,
        )
        digest, size = authorization_audit_record_digest(record)
        identity = (
            normalized_context.campaign_id,
            normalized_context.run_id,
            normalized_context.step_id,
            normalized_context.attempt_id,
            normalized_context.principal,
            normalized_context.correlation_id,
            digest,
        )
        prior = self._emitted.get(identity)
        if prior is not None:
            return dict(prior)

        bound_evidence_id: str | None = None
        if self._custody is not None:
            if self._evidence_store is None:
                raise AuthorizationAuditError(
                    "AUTHORIZATION_AUDIT_CUSTODY_UNAVAILABLE",
                    "authorization audit custody requires the canonical Evidence Plane store",
                )
            recorded_at = self._pending_recorded_at.get(identity)
            if recorded_at is None:
                try:
                    recorded_at = self._recorded_at_provider()
                except Exception as exc:  # noqa: BLE001 - provider details are private
                    raise AuthorizationAuditError(
                        "AUTHORIZATION_AUDIT_CUSTODY_FAILED",
                        "authorization audit custody timestamp failed safely: "
                        f"{type(exc).__name__}",
                    ) from exc
                if not isinstance(recorded_at, str):
                    raise AuthorizationAuditError(
                        "AUTHORIZATION_AUDIT_CUSTODY_FAILED",
                        "authorization audit custody timestamp provider returned invalid data",
                    )
                self._pending_recorded_at[identity] = recorded_at
            try:
                persisted = self._custody.persist(
                    record,
                    correlation={
                        "campaign_id": normalized_context.campaign_id,
                        "run_id": normalized_context.run_id,
                        "step_id": normalized_context.step_id,
                        "attempt_id": normalized_context.attempt_id,
                    },
                    recorded_at=recorded_at,
                    evidence_store=self._evidence_store,
                )
            except Exception as exc:  # noqa: BLE001 - custody details remain private
                raise AuthorizationAuditError(
                    "AUTHORIZATION_AUDIT_CUSTODY_FAILED",
                    f"authorization audit custody failed safely: {type(exc).__name__}",
                ) from exc

            persisted_digest = getattr(persisted, "payload_sha256", None)
            persisted_size = getattr(persisted, "payload_size_bytes", None)
            if persisted_digest != digest or persisted_size != size:
                raise AuthorizationAuditError(
                    "AUTHORIZATION_AUDIT_CUSTODY_MISMATCH",
                    "persisted authorization audit identity does not match the canonical record",
                )
            bound_evidence_id = _canonical_evidence_id(
                getattr(persisted, "evidence_ref", None)
            )
            returned_evidence_id = _canonical_evidence_id(
                getattr(persisted, "evidence_id", None)
            )
            if returned_evidence_id != bound_evidence_id:
                raise AuthorizationAuditError(
                    "AUTHORIZATION_AUDIT_CUSTODY_MISMATCH",
                    "persisted authorization audit custody ID does not match its evidence reference",
                )

        audit_context = AuditContext(
            campaign_id=normalized_context.campaign_id,
            run_id=normalized_context.run_id,
            step_id=normalized_context.step_id,
            attempt_id=normalized_context.attempt_id,
            principal=normalized_context.principal,
            decision=event_type,
            correlation_id=normalized_context.correlation_id,
            outcome="recorded" if decision == "ACCEPT" else "denied",
            notes=SCHEMA_VERSION,
        )
        try:
            self._sink.append(
                object_kind="evidence_record",
                object_ref=f"evidence://authorization-receipt-audit/{digest}",
                object_digest_sha256=digest,
                object_size_bytes=size,
                object_media_type="application/json",
                context=audit_context,
                evidence_ref=bound_evidence_id,
            )
        except AuditSinkError as exc:
            raise AuthorizationAuditError(
                "AUTHORIZATION_AUDIT_APPEND_FAILED", str(exc)
            ) from exc
        self._emitted[identity] = dict(record)
        self._pending_recorded_at.pop(identity, None)
        return record

    @property
    def length(self) -> int:
        return self._sink.length

    def seal(self, *, sealed_at: str | None = None) -> dict[str, Any]:
        return self._sink.seal(sealed_at=sealed_at)

    def verify(self, *, resolver: Any | None = None) -> dict[str, Any]:
        return self._sink.verify(resolver=resolver)
