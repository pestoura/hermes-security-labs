#!/usr/bin/env python3
"""Target-bound LAB_ONLY Runner adapter for the first WebGoat L1 scenario.

This module contains real read-only HTTP effect code, but it is deliberately
not wired to production dispatch. Authority is resolved from ``authorization_ref``
through an injected resolver. The default resolver denies every request, so the
adapter cannot become executable merely by being imported or installed.

Safety boundaries:
- fixed target: ``webgoat-web`` -> ``http://webgoat:8080/WebGoat/``;
- fixed capabilities: ``web.discovery.headers`` and ``web.discovery.tls``;
- consumes only the canonical gateway -> Runner Protocol v2 operation envelope;
- target envelope is fixed to ``lab-asset:webgoat-web``;
- authorization must resolve to canonical TB1 ``VerifiedAuthorization`` metadata;
- correlation, operation, capability, intrusiveness, target digest and parameter
  digest are independently rebound at the adapter before any effect;
- audited resolvers receive only schema-validated request correlation plus a fixed
  Runner principal; raw target/parameters are never placed in audit context;
- no raw URL/host/port/path input;
- no shell, subprocess, scanner, redirect following, credentials or egress;
- durable idempotency is required before any effect;
- Runner Protocol v2 messages are validated before and after dispatch.
"""

from __future__ import annotations

import hashlib
import http.client
import importlib.util
import inspect
import json
import re
import sys
import uuid
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Protocol

from runner_protocol_v2 import (
    LedgerError,
    SQLiteIdempotencyLedger,
    request_fingerprint,
    validate_semantics,
)

ROOT = Path(__file__).resolve().parents[2]
GATEWAY_CONTRACT_PATH = ROOT / "platform" / "gateway-protocol" / "gateway_protocol.py"
AUTHORIZATION_CONTRACT_PATH = (
    ROOT / "platform" / "authorization-contract" / "authorization_receipt.py"
)


def _load_contract_module(name: str, path: Path):
    existing = sys.modules.get(name)
    if existing is not None:
        return existing
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load canonical contract {path.name}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


gateway_contract = _load_contract_module(
    "webgoat_adapter_gateway_contract",
    GATEWAY_CONTRACT_PATH,
)
authorization_contract = _load_contract_module(
    "webgoat_adapter_authorization_contract",
    AUTHORIZATION_CONTRACT_PATH,
)

PROTOCOL_VERSION = "2.0.0"
ADAPTER_ID = "webgoat-l1"
TARGET_ID = "webgoat-web"
TARGET_HOST = "webgoat"
TARGET_PORT = 8080
TARGET_PATH = "/WebGoat/"
TARGET_SCHEME = "http"
TARGET_ENVELOPE = {"type": "lab-asset", "value": TARGET_ID}
EXPECTED_OPERATION_VERSION = "1.0.0"
EXPECTED_INTRUSIVENESS = "L1"
RUNNER_AUDIT_PRINCIPAL = "hexor.runner.webgoat-l1"
CANONICAL_INPUT_KEYS = frozenset(
    {
        "operation_id",
        "operation_version",
        "intrusiveness_level",
        "target",
        "parameters",
    }
)
SUPPORTED_CAPABILITIES = frozenset(
    {"web.discovery.headers", "web.discovery.tls"}
)
_REQUIRED_VERIFIED_FIELDS = (
    "authorization_ref",
    "issued_at",
    "expires_at",
    "campaign_id",
    "run_id",
    "step_id",
    "operation_id",
    "operation_version",
    "operation_parameters_sha256",
    "capability_id",
    "target_sha256",
    "intrusiveness_level",
)
_SENSITIVE_HEADERS = frozenset(
    {"authorization", "cookie", "proxy-authorization", "set-cookie"}
)
_SAFE_TEXT = re.compile(r"[^\x20-\x7e]")


def _utc_now() -> str:
    return (
        datetime.now(timezone.utc)
        .isoformat(timespec="milliseconds")
        .replace("+00:00", "Z")
    )


def _parse_utc(value: Any) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        return None
    return parsed.astimezone(timezone.utc)


class AuthorizationResolver(Protocol):
    """Runtime boundary returning canonical verified TB1 metadata or no authority."""

    def resolve(
        self,
        authorization_ref: str,
        *,
        audit_context: Mapping[str, str] | None = None,
    ) -> Any | None:
        ...


class DenyAllAuthorizationResolver:
    """Fail-closed default until a verified TB1 resolver is deployed."""

    def resolve(
        self,
        authorization_ref: str,
        *,
        audit_context: Mapping[str, str] | None = None,
    ) -> None:
        del authorization_ref, audit_context
        return None


def _authorization_audit_context(request: Mapping[str, Any]) -> dict[str, str]:
    correlation = request["correlation"]
    return {
        "campaign_id": correlation["campaign_id"],
        "run_id": correlation["run_id"],
        "step_id": correlation["step_id"],
        "attempt_id": correlation["attempt_id"],
        "principal": RUNNER_AUDIT_PRINCIPAL,
        "correlation_id": request["idempotency_key"],
    }


def _resolver_accepts_audit_context(resolver: Any) -> bool:
    method = getattr(resolver, "resolve", None)
    if not callable(method):
        return False
    try:
        parameters = inspect.signature(method).parameters
    except (TypeError, ValueError):
        return False
    return "audit_context" in parameters or any(
        parameter.kind is inspect.Parameter.VAR_KEYWORD
        for parameter in parameters.values()
    )


def _resolve_authorization(
    resolver: Any,
    authorization_ref: str,
    *,
    audit_context: Mapping[str, str],
) -> Any | None:
    if _resolver_accepts_audit_context(resolver):
        return resolver.resolve(authorization_ref, audit_context=dict(audit_context))
    return resolver.resolve(authorization_ref)


@dataclass(frozen=True)
class ProbeResponse:
    status: int
    headers: tuple[tuple[str, str], ...]


class HttpProbe(Protocol):
    def get(self, *, timeout_seconds: float) -> ProbeResponse:
        ...


class FixedWebGoatHttpProbe:
    """Minimal stdlib HTTP probe confined to the committed WebGoat target."""

    def get(self, *, timeout_seconds: float) -> ProbeResponse:
        connection = http.client.HTTPConnection(
            TARGET_HOST,
            TARGET_PORT,
            timeout=timeout_seconds,
        )
        try:
            connection.request(
                "GET",
                TARGET_PATH,
                headers={
                    "User-Agent": "hex0r-webgoat-l1-runner/1.0",
                    "Connection": "close",
                },
            )
            response = connection.getresponse()
            response.read(1)
            return ProbeResponse(
                status=int(response.status),
                headers=tuple((str(k), str(v)) for k, v in response.getheaders()),
            )
        finally:
            connection.close()


def _sanitize_text(value: str, *, limit: int = 256) -> str:
    return _SAFE_TEXT.sub("?", value)[:limit]


def _safe_headers(headers: tuple[tuple[str, str], ...]) -> list[dict[str, str]]:
    safe: list[dict[str, str]] = []
    for name, value in headers:
        normalized = name.strip().lower()
        if not normalized or normalized in _SENSITIVE_HEADERS:
            continue
        safe.append(
            {
                "name": _sanitize_text(normalized, limit=128),
                "value": _sanitize_text(value.strip()),
            }
        )
    return sorted(safe, key=lambda item: (item["name"], item["value"]))


def _evidence_ref(output: dict[str, Any]) -> dict[str, Any]:
    payload = json.dumps(
        output,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    ).encode("utf-8")
    digest = hashlib.sha256(payload).hexdigest()
    evidence_id = str(
        uuid.uuid5(uuid.NAMESPACE_URL, f"{ADAPTER_ID}:execution:{digest}")
    )
    return {
        "evidence_id": evidence_id,
        "kind": "execution",
        "classification": "INTERNAL",
        "sha256": digest,
    }


def _outcome(
    request: dict[str, Any],
    status: str,
    *,
    output: dict[str, Any] | None = None,
    error: dict[str, Any] | None = None,
    started_at: str | None = None,
) -> dict[str, Any]:
    started = started_at or _utc_now()
    finished = _utc_now()
    evidence_payload = output or {
        "adapter_id": ADAPTER_ID,
        "target_id": TARGET_ID,
        "status": status,
        "error_code": None if error is None else error["code"],
    }
    message: dict[str, Any] = {
        "message_type": "runner.outcome",
        "protocol_version": PROTOCOL_VERSION,
        "correlation": request["correlation"],
        "emitted_at": finished,
        "status": status,
        "started_at": started,
        "finished_at": finished,
        "evidence_refs": [_evidence_ref(evidence_payload)],
    }
    if output is not None:
        message["output"] = output
    if error is not None:
        message["error"] = error
    validate_semantics(message)
    return message


def _error(
    code: str,
    category: str,
    message: str,
    *,
    retryable: bool = False,
    safe_context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    normalized: dict[str, Any] = {
        "code": code,
        "category": category,
        "retryable": retryable,
        "message": _sanitize_text(message, limit=256),
    }
    if safe_context:
        normalized["safe_context"] = safe_context
    return normalized


class WebGoatL1RunnerAdapter:
    """Durable, target-bound adapter for the first read-only WebGoat scenario."""

    def __init__(
        self,
        *,
        authorization_resolver: AuthorizationResolver | None = None,
        probe: HttpProbe | None = None,
        ledger: SQLiteIdempotencyLedger,
    ) -> None:
        self.authorization_resolver = (
            authorization_resolver or DenyAllAuthorizationResolver()
        )
        self.probe = probe or FixedWebGoatHttpProbe()
        self.ledger = ledger

    def _authorize(
        self, request: dict[str, Any], capability_id: str
    ) -> dict[str, Any] | None:
        verified = _resolve_authorization(
            self.authorization_resolver,
            request["authorization_ref"],
            audit_context=_authorization_audit_context(request),
        )
        if verified is None:
            return _error(
                "AUTHORIZATION_DENIED",
                "authorization",
                "TB1 authorization reference is not resolvable by a verified resolver",
            )
        if any(not hasattr(verified, field) for field in _REQUIRED_VERIFIED_FIELDS):
            return _error(
                "AUTHORIZATION_DENIED",
                "authorization",
                "Resolved authorization metadata is incomplete",
            )

        payload = request["operation"]["input"]
        correlation = request["correlation"]
        parameters = payload["parameters"]
        target = payload["target"]

        expected_parameter_digest = authorization_contract.canonical_parameters_sha256(
            parameters
        )
        expected_target_digest = gateway_contract.canonical_target_digest(target)

        bindings = (
            (verified.authorization_ref, request["authorization_ref"]),
            (verified.campaign_id, correlation["campaign_id"]),
            (verified.run_id, correlation["run_id"]),
            (verified.step_id, correlation["step_id"]),
            (verified.operation_id, payload["operation_id"]),
            (verified.operation_version, payload["operation_version"]),
            (verified.capability_id, capability_id),
            (verified.intrusiveness_level, payload["intrusiveness_level"]),
            (verified.operation_parameters_sha256, expected_parameter_digest),
            (verified.target_sha256, expected_target_digest),
        )
        if any(actual != expected for actual, expected in bindings):
            return _error(
                "AUTHORIZATION_DENIED",
                "authorization",
                "Verified TB1 authorization does not bind to this exact Runner effect",
            )

        issued_at = _parse_utc(verified.issued_at)
        expires_at = _parse_utc(verified.expires_at)
        now = datetime.now(timezone.utc)
        if (
            issued_at is None
            or expires_at is None
            or not issued_at < expires_at
            or now < issued_at
            or now >= expires_at
        ):
            return _error(
                "AUTHORIZATION_DENIED",
                "authorization",
                "Verified TB1 authorization is outside its validity window",
            )
        return None

    @staticmethod
    def _validate_input(
        capability_id: str, payload: dict[str, Any]
    ) -> dict[str, Any] | None:
        if not isinstance(payload, dict):
            return _error(
                "INVALID_REQUEST",
                "validation",
                "Operation input must be the canonical gateway handoff object",
            )
        if set(payload) != CANONICAL_INPUT_KEYS:
            return _error(
                "INVALID_REQUEST",
                "validation",
                "Operation input does not match the canonical gateway handoff envelope",
            )
        if payload.get("operation_id") != capability_id:
            return _error(
                "INVALID_REQUEST",
                "validation",
                "Operation identity does not match the requested capability",
            )
        if payload.get("operation_version") != EXPECTED_OPERATION_VERSION:
            return _error(
                "INVALID_REQUEST",
                "validation",
                "Operation version is not accepted by the WebGoat L1 adapter",
            )
        if payload.get("intrusiveness_level") != EXPECTED_INTRUSIVENESS:
            return _error(
                "INVALID_REQUEST",
                "validation",
                "Operation intrusiveness does not match the WebGoat L1 contract",
            )
        if payload.get("target") != TARGET_ENVELOPE:
            return _error(
                "INVALID_REQUEST",
                "validation",
                "Runner target envelope does not match lab-asset:webgoat-web",
            )

        parameters = payload.get("parameters")
        if not isinstance(parameters, dict):
            return _error(
                "INVALID_REQUEST",
                "validation",
                "Operation parameters must be an object",
            )
        if capability_id == "web.discovery.headers":
            unknown = set(parameters) - {"follow_redirects"}
            if unknown:
                return _error(
                    "INVALID_REQUEST",
                    "validation",
                    "Header discovery parameters contain unsupported fields",
                )
            if parameters.get("follow_redirects", False) is not False:
                return _error(
                    "INVALID_REQUEST",
                    "validation",
                    "Redirect following is disabled for the first LAB_ONLY adapter",
                )
            return None
        if capability_id == "web.discovery.tls":
            if parameters:
                return _error(
                    "INVALID_REQUEST",
                    "validation",
                    "TLS discovery accepts no operation parameters",
                )
            return None
        return _error(
            "UNSUPPORTED_CAPABILITY",
            "compatibility",
            "Capability is not exposed by the WebGoat L1 adapter",
        )

    def _perform(
        self,
        capability_id: str,
        *,
        hard_timeout_ms: int,
    ) -> dict[str, Any]:
        timeout_seconds = min(max(hard_timeout_ms / 1000.0, 0.1), 10.0)
        response = self.probe.get(timeout_seconds=timeout_seconds)

        common: dict[str, Any] = {
            "adapter_id": ADAPTER_ID,
            "target_id": TARGET_ID,
            "environment_id": "webgoat",
            "capability_id": capability_id,
            "http_status": response.status,
        }
        if capability_id == "web.discovery.headers":
            common["headers"] = _safe_headers(response.headers)
            common["redirects_followed"] = False
            return common
        common.update(
            {
                "scheme": TARGET_SCHEME,
                "tls_enabled": False,
                "plaintext_transport": True,
                "assessment": "PLAINTEXT_HTTP",
            }
        )
        return common

    def dispatch(self, request: dict[str, Any]) -> dict[str, Any]:
        """Validate, authorize, atomically claim, perform and persist one effect."""
        validate_semantics(request)
        if request["message_type"] != "runner.step.request":
            raise ValueError("dispatch requires runner.step.request")

        capability_id = request["operation"]["capability_id"]
        if capability_id not in SUPPORTED_CAPABILITIES:
            return {
                "messages": [
                    _outcome(
                        request,
                        "REFUSED",
                        error=_error(
                            "UNSUPPORTED_CAPABILITY",
                            "compatibility",
                            "Capability is not exposed by the WebGoat L1 adapter",
                        ),
                    )
                ]
            }

        input_error = self._validate_input(
            capability_id, request["operation"]["input"]
        )
        if input_error is not None:
            return {"messages": [_outcome(request, "REFUSED", error=input_error)]}

        authorization_error = self._authorize(request, capability_id)
        if authorization_error is not None:
            return {
                "messages": [
                    _outcome(request, "REFUSED", error=authorization_error)
                ]
            }

        key = request["idempotency_key"]
        fingerprint = request_fingerprint(request)
        try:
            decision = self.ledger.claim(key, fingerprint)
        except LedgerError:
            return {
                "messages": [
                    _outcome(
                        request,
                        "ERROR",
                        error=_error(
                            "RUNNER_UNAVAILABLE",
                            "dependency",
                            "Durable idempotency ledger is unavailable",
                            retryable=True,
                        ),
                    )
                ]
            }

        if decision.classification == "IDEMPOTENCY_CONFLICT":
            return {
                "messages": [
                    _outcome(
                        request,
                        "REFUSED",
                        error=_error(
                            "IDEMPOTENCY_CONFLICT",
                            "conflict",
                            "Idempotency key identifies a different effect",
                        ),
                    )
                ]
            }
        if decision.classification == "REPLAY_SAME":
            assert decision.record is not None and decision.record.outcome is not None
            return {"messages": [decision.record.outcome]}
        if decision.classification == "IN_PROGRESS":
            return {
                "messages": [
                    _outcome(
                        request,
                        "ERROR",
                        error=_error(
                            "RUNNER_UNAVAILABLE",
                            "dependency",
                            "Identical effect is already in progress",
                            retryable=True,
                        ),
                    )
                ]
            }

        started_at = _utc_now()
        try:
            output = self._perform(
                capability_id,
                hard_timeout_ms=request["timeout_budget"]["hard_timeout_ms"],
            )
            outcome = _outcome(
                request,
                "PASS",
                output=output,
                started_at=started_at,
            )
        except (OSError, http.client.HTTPException, TimeoutError) as exc:
            outcome = _outcome(
                request,
                "ERROR",
                error=_error(
                    "TRANSIENT_DEPENDENCY",
                    "dependency",
                    "Bounded WebGoat HTTP probe failed",
                    retryable=True,
                    safe_context={"exception_type": type(exc).__name__},
                ),
                started_at=started_at,
            )
        except Exception as exc:
            outcome = _outcome(
                request,
                "ERROR",
                error=_error(
                    "EXECUTION_FAILED",
                    "execution",
                    "WebGoat L1 effect failed safely",
                    safe_context={"exception_type": type(exc).__name__},
                ),
                started_at=started_at,
            )

        try:
            completion = self.ledger.complete(key, fingerprint, outcome)
        except LedgerError:
            return {
                "messages": [
                    _outcome(
                        request,
                        "ERROR",
                        error=_error(
                            "EVIDENCE_MISSING",
                            "evidence",
                            "Terminal outcome could not be durably recorded",
                        ),
                        started_at=started_at,
                    )
                ]
            }
        assert completion.record is not None and completion.record.outcome is not None
        return {"messages": [completion.record.outcome]}


def build_adapter(
    *,
    ledger_path: str | Path,
    authorization_resolver: AuthorizationResolver | None = None,
    probe: HttpProbe | None = None,
) -> WebGoatL1RunnerAdapter:
    """Build the adapter with the required durable idempotency boundary."""
    return WebGoatL1RunnerAdapter(
        authorization_resolver=authorization_resolver,
        probe=probe,
        ledger=SQLiteIdempotencyLedger(ledger_path),
    )
