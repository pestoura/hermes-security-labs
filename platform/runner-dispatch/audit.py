"""Pure Runner dispatch audit-event projection.

This module binds the authenticated transport principal to the canonical Runner
correlation tuple and authorization reference without logging raw targets,
operation parameters, credentials or other application payload. It performs no
I/O and is not itself a durable audit sink.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

import jsonschema
from runner_protocol_v2 import ProtocolValidationError, validate_semantics

ROOT = Path(__file__).resolve().parents[2]
SCHEMA_PATH = Path(__file__).resolve().parent / "dispatch-audit-event.schema.json"
GATEWAY_CONTRACT_PATH = ROOT / "platform" / "gateway-protocol" / "gateway_protocol.py"

SCHEMA_VERSION = "1.0.0"
DOMAIN = "hex0r.runner.dispatch.audit.v1"
_PRINCIPAL = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
_TRANSPORT = re.compile(r"^[a-z0-9][a-z0-9._-]{0,63}$")
_REASON = re.compile(r"^[A-Z][A-Z0-9_]{1,95}$")
_TYPED_ID = re.compile(r"^[a-z0-9]+(?:[._-][a-z0-9]+)*$")


class DispatchAuditError(ValueError):
    """Fail-closed audit projection error carrying a stable code."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


def _load_gateway_module() -> Any:
    name = "runner_dispatch_audit_gateway_contract"
    existing = sys.modules.get(name)
    if existing is not None:
        return existing
    spec = importlib.util.spec_from_file_location(name, GATEWAY_CONTRACT_PATH)
    if spec is None or spec.loader is None:  # pragma: no cover - packaging defect
        raise RuntimeError("cannot load canonical gateway contract")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


gateway_contract = _load_gateway_module()


def _iso_now() -> str:
    return (
        datetime.now(timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


def _schema() -> dict[str, Any]:
    try:
        schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError, UnicodeDecodeError) as exc:
        raise DispatchAuditError("AUDIT_SCHEMA_UNAVAILABLE", "audit schema cannot be loaded") from exc
    if not isinstance(schema, dict):
        raise DispatchAuditError("AUDIT_SCHEMA_INVALID", "audit schema must be an object")
    return schema


def _validate_output(event: Mapping[str, Any]) -> None:
    validator = jsonschema.Draft202012Validator(
        _schema(), format_checker=jsonschema.FormatChecker()
    )
    errors = sorted(validator.iter_errors(event), key=lambda error: list(error.path))
    if errors:
        raise DispatchAuditError("AUDIT_EVENT_INVALID", errors[0].message)


def _validate_identity(principal_id: str, transport: str) -> None:
    if not isinstance(principal_id, str) or _PRINCIPAL.fullmatch(principal_id) is None:
        raise DispatchAuditError("AUDIT_PRINCIPAL_INVALID", "authenticated principal_id is invalid")
    if not isinstance(transport, str) or _TRANSPORT.fullmatch(transport) is None:
        raise DispatchAuditError("AUDIT_TRANSPORT_INVALID", "authenticated transport is invalid")


def _request_projection(request: Mapping[str, Any]) -> dict[str, Any]:
    try:
        validate_semantics(request)
    except ProtocolValidationError as exc:
        raise DispatchAuditError("AUDIT_REQUEST_INVALID", str(exc)) from exc
    if request.get("message_type") != "runner.step.request":
        raise DispatchAuditError("AUDIT_REQUEST_INVALID", "audit projection accepts runner.step.request only")

    try:
        correlation = request["correlation"]
        authorization_ref = request["authorization_ref"]
        capability_id = request["operation"]["capability_id"]
        target = request["operation"]["input"]["target"]
    except (KeyError, TypeError) as exc:  # schema validation should already cover this
        raise DispatchAuditError("AUDIT_REQUEST_INVALID", "request lacks canonical audit fields") from exc

    try:
        target_sha256 = gateway_contract.canonical_target_digest(target)
    except Exception as exc:  # noqa: BLE001 - malformed target fails closed
        raise DispatchAuditError("AUDIT_TARGET_INVALID", "target cannot be canonically digested") from exc

    return {
        "correlation": {
            "campaign_id": str(correlation["campaign_id"]),
            "run_id": str(correlation["run_id"]),
            "step_id": str(correlation["step_id"]),
            "attempt_id": str(correlation["attempt_id"]),
        },
        "authorization_ref": str(authorization_ref),
        "capability_id": str(capability_id),
        "target_sha256": target_sha256,
    }


def _fingerprint(event: Mapping[str, Any]) -> str:
    canonical = {
        key: value
        for key, value in event.items()
        if key not in {"recorded_at", "event_fingerprint"}
    }
    encoded = json.dumps(
        canonical, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def build_dispatch_audit_event(
    *,
    principal_id: str,
    transport: str,
    request: Mapping[str, Any],
    phase: str,
    decision: str,
    reason_code: str,
    adapter_id: str | None = None,
    terminal_status: str | None = None,
) -> dict[str, Any]:
    """Build one sanitized audit event from authenticated and protocol-valid inputs.

    `principal_id` and `transport` are expected to originate from the trusted
    transport-authentication boundary, never from the Runner request payload.
    Raw target values and operation parameters are intentionally not emitted.
    """

    _validate_identity(principal_id, transport)
    if phase not in {"pre-dispatch", "terminal"}:
        raise DispatchAuditError("AUDIT_PHASE_INVALID", "unsupported audit phase")
    if decision not in {"ALLOW", "DENY", "OUTCOME"}:
        raise DispatchAuditError("AUDIT_DECISION_INVALID", "unsupported audit decision")
    if not isinstance(reason_code, str) or _REASON.fullmatch(reason_code) is None:
        raise DispatchAuditError("AUDIT_REASON_INVALID", "reason_code is invalid")
    if adapter_id is not None and (
        not isinstance(adapter_id, str) or _TYPED_ID.fullmatch(adapter_id) is None
    ):
        raise DispatchAuditError("AUDIT_ADAPTER_INVALID", "adapter_id is invalid")

    if phase == "pre-dispatch":
        if decision not in {"ALLOW", "DENY"}:
            raise DispatchAuditError("AUDIT_DECISION_INVALID", "pre-dispatch requires ALLOW or DENY")
        if terminal_status is not None:
            raise DispatchAuditError("AUDIT_TERMINAL_INVALID", "pre-dispatch cannot carry terminal_status")
    else:
        if decision != "OUTCOME":
            raise DispatchAuditError("AUDIT_DECISION_INVALID", "terminal phase requires OUTCOME")
        if adapter_id is None:
            raise DispatchAuditError("AUDIT_ADAPTER_REQUIRED", "terminal phase requires adapter_id")
        if terminal_status not in {"SUCCEEDED", "FAILED", "REFUSED", "CANCELLED", "TIMED_OUT"}:
            raise DispatchAuditError("AUDIT_TERMINAL_INVALID", "terminal_status is invalid")

    projection = _request_projection(request)
    event: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "domain": DOMAIN,
        "recorded_at": _iso_now(),
        "phase": phase,
        "decision": decision,
        "reason_code": reason_code,
        "principal_id": principal_id,
        "transport": transport,
        **projection,
    }
    if adapter_id is not None:
        event["adapter_id"] = adapter_id
    if terminal_status is not None:
        event["terminal_status"] = terminal_status
    event["event_fingerprint"] = _fingerprint(event)
    _validate_output(event)
    return event
