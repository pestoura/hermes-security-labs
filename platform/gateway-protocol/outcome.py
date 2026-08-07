"""Sanitized Runner Protocol v2 outcome -> Hermes gateway outcome boundary.

This module never executes a runner and never treats an outcome as authorization.
It seals the exact ``runner.step.request`` built by the gateway into an immutable
canonical JSON snapshot before any future transport, then validates a terminal
``runner.outcome`` against that sealed request and emits only a sanitized
control-plane derivative.

Raw runner ``output``, evidence ``uri``, error ``message`` and ``safe_context``
are deliberately excluded. Evidence references attest to what happened; they do
not create or expand execution authority.

Boundary: repository-level contract transformation only. Runner identity,
transport authenticity, deployed gateway reception and Evidence Plane
persistence remain NOT_IMPLEMENTED / NOT_RUN.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Mapping

import jsonschema

ROOT = Path(__file__).resolve().parent
REPOSITORY_ROOT = ROOT.parents[1]
RUNNER_SDK_SRC = REPOSITORY_ROOT / "platform" / "runner-protocol" / "src"

if str(RUNNER_SDK_SRC) not in sys.path:  # pragma: no cover - import wiring
    sys.path.insert(0, str(RUNNER_SDK_SRC))

from runner_protocol_v2 import (  # noqa: E402
    ProtocolValidationError,
    request_fingerprint,
    validate_semantics,
)


def _load_module(module_name: str, path: Path) -> Any:
    existing = sys.modules.get(module_name)
    if existing is not None:
        return existing
    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:  # pragma: no cover - packaging defect
        raise RuntimeError(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


runner_handoff = _load_module(
    "gateway_runner_handoff_outcome_core", ROOT / "runner_handoff.py"
)

OUTCOME_SCHEMA_VERSION = "1.0.0"
OUTCOME_MESSAGE_TYPE = "gateway.execution.outcome"
RUNNER_PROTOCOL_VERSION = "2.0.0"


class GatewayOutcomeError(ValueError):
    """Stable contract error for an outcome boundary that cannot be trusted."""


@dataclass(frozen=True)
class GatewayOutcomeContext:
    """Immutable integrity context sealed immediately after request construction.

    ``sealed_request_json`` contains the RESTRICTED Runner Protocol request and
    is deliberately excluded from repr. Its SHA-256 covers the complete message,
    including ``attempt_id`` and ``emitted_at``. The ordinary Runner Protocol
    request fingerprint remains separately available for logical-step replay
    semantics and intentionally excludes retry-specific fields.
    """

    request_envelope_sha256: str
    request_fingerprint: str
    authorization_ref: str
    idempotency_key: str
    sealed_request_json: str = field(repr=False)

    def sanitized_summary(self) -> dict[str, str]:
        return {
            "request_envelope_sha256": self.request_envelope_sha256,
            "request_fingerprint": self.request_fingerprint,
            "authorization_ref": self.authorization_ref,
            "idempotency_key": self.idempotency_key,
        }


@dataclass(frozen=True)
class GatewayOutcomeResult:
    """Result of deriving a sanitized control-plane execution outcome.

    ``typed_outcome`` is excluded from repr so log-safe summaries do not
    accidentally expand evidence references. It never contains raw target,
    parameters, runner output, evidence URI, or free-form runner error text.
    """

    outcome_built: bool
    codes: tuple[str, ...]
    runner_status: str | None
    campaign_id: str | None
    run_id: str | None
    step_id: str | None
    attempt_id: str | None
    authorization_ref: str | None
    request_fingerprint: str | None
    request_envelope_sha256: str | None
    evidence_count: int
    output_present: bool
    error_code: str | None
    typed_outcome: dict[str, Any] | None = field(repr=False, default=None)

    @classmethod
    def refuse(
        cls,
        codes: Iterable[str],
        *,
        context: GatewayOutcomeContext | None = None,
        runner_outcome: Mapping[str, Any] | None = None,
    ) -> "GatewayOutcomeResult":
        unique = tuple(dict.fromkeys(codes)) or ("OUTCOME_REFUSED",)
        correlation = _mapping(runner_outcome, "correlation")
        return cls(
            outcome_built=False,
            codes=unique,
            runner_status=_string(runner_outcome, "status"),
            campaign_id=_string(correlation, "campaign_id"),
            run_id=_string(correlation, "run_id"),
            step_id=_string(correlation, "step_id"),
            attempt_id=_string(correlation, "attempt_id"),
            authorization_ref=context.authorization_ref if context else None,
            request_fingerprint=context.request_fingerprint if context else None,
            request_envelope_sha256=(
                context.request_envelope_sha256 if context else None
            ),
            evidence_count=0,
            output_present=False,
            error_code=None,
            typed_outcome=None,
        )

    def sanitized_summary(self) -> dict[str, Any]:
        """Return log-safe metadata without evidence identifiers or raw payloads."""

        return {
            "outcome_built": bool(self.outcome_built),
            "codes": list(self.codes),
            "runner_status": self.runner_status,
            "campaign_id": self.campaign_id,
            "run_id": self.run_id,
            "step_id": self.step_id,
            "attempt_id": self.attempt_id,
            "authorization_ref": self.authorization_ref,
            "request_fingerprint": self.request_fingerprint,
            "request_envelope_sha256": self.request_envelope_sha256,
            "evidence_count": int(self.evidence_count),
            "output_present": bool(self.output_present),
            "error_code": self.error_code,
            "typed_outcome_present": self.typed_outcome is not None,
        }


def seal_handoff_result(handoff_result: Any) -> GatewayOutcomeContext:
    """Seal one already-built Runner request for later outcome verification.

    The complete canonical request is copied into an immutable string, so a
    later mutation of the mutable ``runner_request`` object cannot change the
    expected correlation or effect. Failure raises ``GatewayOutcomeError`` with
    a stable code; callers must not dispatch when sealing fails.
    """

    if not bool(getattr(handoff_result, "request_built", False)):
        raise GatewayOutcomeError("OUTCOME_HANDOFF_NOT_BUILT")

    runner_request = getattr(handoff_result, "runner_request", None)
    if not isinstance(runner_request, Mapping):
        raise GatewayOutcomeError("OUTCOME_HANDOFF_REQUEST_MISSING")

    try:
        validate_semantics(runner_request)
    except ProtocolValidationError as exc:
        raise GatewayOutcomeError("OUTCOME_HANDOFF_REQUEST_INVALID") from exc
    except Exception as exc:  # noqa: BLE001 - integration defect fails closed
        raise GatewayOutcomeError("OUTCOME_HANDOFF_INTEGRATION_ERROR") from exc

    if runner_request.get("message_type") != "runner.step.request":
        raise GatewayOutcomeError("OUTCOME_HANDOFF_REQUEST_TYPE_INVALID")

    try:
        logical_fingerprint = request_fingerprint(runner_request)
    except ProtocolValidationError as exc:
        raise GatewayOutcomeError("OUTCOME_HANDOFF_REQUEST_INVALID") from exc

    if getattr(handoff_result, "request_fingerprint", None) != logical_fingerprint:
        raise GatewayOutcomeError("OUTCOME_HANDOFF_FINGERPRINT_MISMATCH")

    authorization_ref = runner_request.get("authorization_ref")
    if (
        not isinstance(authorization_ref, str)
        or getattr(handoff_result, "authorization_ref", None) != authorization_ref
    ):
        raise GatewayOutcomeError("OUTCOME_HANDOFF_AUTHORIZATION_MISMATCH")

    idempotency_key = runner_request.get("idempotency_key")
    if (
        not isinstance(idempotency_key, str)
        or getattr(handoff_result, "idempotency_key", None) != idempotency_key
    ):
        raise GatewayOutcomeError("OUTCOME_HANDOFF_IDEMPOTENCY_MISMATCH")

    correlation = runner_request["correlation"]
    if getattr(handoff_result, "campaign_id", None) != correlation["campaign_id"]:
        raise GatewayOutcomeError("OUTCOME_HANDOFF_CAMPAIGN_MISMATCH")

    operation_input = runner_request["operation"]["input"]
    if getattr(handoff_result, "operation_id", None) != operation_input.get(
        "operation_id"
    ):
        raise GatewayOutcomeError("OUTCOME_HANDOFF_OPERATION_MISMATCH")
    if getattr(handoff_result, "operation_version", None) != operation_input.get(
        "operation_version"
    ):
        raise GatewayOutcomeError("OUTCOME_HANDOFF_OPERATION_VERSION_MISMATCH")

    sealed = _canonical_json(runner_request)
    return GatewayOutcomeContext(
        request_envelope_sha256=_sha256_text(sealed),
        request_fingerprint=logical_fingerprint,
        authorization_ref=authorization_ref,
        idempotency_key=idempotency_key,
        sealed_request_json=sealed,
    )


def build_execution_outcome(
    context: GatewayOutcomeContext,
    runner_outcome: Mapping[str, Any],
) -> GatewayOutcomeResult:
    """Validate and sanitize a terminal Runner Protocol v2 outcome.

    This function proves structural consistency with the request snapshot that
    the gateway sealed before transport. It does **not** prove the identity of a
    real runner or the authenticity of transport; deployed authentication is a
    separate runtime concern and remains NOT_IMPLEMENTED / NOT_RUN.
    """

    try:
        runner_request = _load_sealed_request(context)
    except GatewayOutcomeError as exc:
        return GatewayOutcomeResult.refuse((str(exc),), context=_context_or_none(context))
    except Exception:  # noqa: BLE001 - context integration defect fails closed
        return GatewayOutcomeResult.refuse(
            ("OUTCOME_CONTEXT_INTEGRATION_ERROR",),
            context=_context_or_none(context),
        )

    if not isinstance(runner_outcome, Mapping):
        return GatewayOutcomeResult.refuse(
            ("RUNNER_OUTCOME_INVALID",), context=context
        )

    try:
        validate_semantics(runner_outcome)
    except ProtocolValidationError:
        return GatewayOutcomeResult.refuse(
            ("RUNNER_OUTCOME_INVALID",),
            context=context,
            runner_outcome=runner_outcome,
        )
    except Exception:  # noqa: BLE001 - contract integration defect fails closed
        return GatewayOutcomeResult.refuse(
            ("RUNNER_OUTCOME_INTEGRATION_ERROR",),
            context=context,
            runner_outcome=runner_outcome,
        )

    if runner_outcome.get("message_type") != "runner.outcome":
        return GatewayOutcomeResult.refuse(
            ("RUNNER_OUTCOME_TYPE_INVALID",),
            context=context,
            runner_outcome=runner_outcome,
        )

    if runner_outcome.get("correlation") != runner_request.get("correlation"):
        return GatewayOutcomeResult.refuse(
            ("RUNNER_OUTCOME_CORRELATION_MISMATCH",),
            context=context,
            runner_outcome=runner_outcome,
        )

    try:
        typed_outcome = _sanitize_outcome(
            context=context,
            runner_request=runner_request,
            runner_outcome=runner_outcome,
        )
        _validate_gateway_outcome(typed_outcome)
    except GatewayOutcomeError as exc:
        return GatewayOutcomeResult.refuse(
            (str(exc),), context=context, runner_outcome=runner_outcome
        )
    except Exception:  # noqa: BLE001 - never emit a partial derivative
        return GatewayOutcomeResult.refuse(
            ("GATEWAY_OUTCOME_INTEGRATION_ERROR",),
            context=context,
            runner_outcome=runner_outcome,
        )

    correlation = typed_outcome["correlation"]
    error = typed_outcome.get("error")
    return GatewayOutcomeResult(
        outcome_built=True,
        codes=("GATEWAY_OUTCOME_BUILT",),
        runner_status=str(typed_outcome["runner_status"]),
        campaign_id=str(correlation["campaign_id"]),
        run_id=str(correlation["run_id"]),
        step_id=str(correlation["step_id"]),
        attempt_id=str(correlation["attempt_id"]),
        authorization_ref=context.authorization_ref,
        request_fingerprint=context.request_fingerprint,
        request_envelope_sha256=context.request_envelope_sha256,
        evidence_count=len(typed_outcome["evidence_refs"]),
        output_present=bool(typed_outcome["output_present"]),
        error_code=str(error["code"]) if isinstance(error, Mapping) else None,
        typed_outcome=typed_outcome,
    )


def _load_sealed_request(context: GatewayOutcomeContext) -> dict[str, Any]:
    if not isinstance(context, GatewayOutcomeContext):
        raise GatewayOutcomeError("OUTCOME_CONTEXT_INVALID")
    if _sha256_text(context.sealed_request_json) != context.request_envelope_sha256:
        raise GatewayOutcomeError("OUTCOME_CONTEXT_ENVELOPE_MISMATCH")

    try:
        request = json.loads(context.sealed_request_json)
    except (TypeError, json.JSONDecodeError) as exc:
        raise GatewayOutcomeError("OUTCOME_CONTEXT_INVALID") from exc
    if not isinstance(request, dict):
        raise GatewayOutcomeError("OUTCOME_CONTEXT_INVALID")

    try:
        validate_semantics(request)
    except ProtocolValidationError as exc:
        raise GatewayOutcomeError("OUTCOME_CONTEXT_REQUEST_INVALID") from exc
    if request.get("message_type") != "runner.step.request":
        raise GatewayOutcomeError("OUTCOME_CONTEXT_REQUEST_TYPE_INVALID")

    try:
        logical_fingerprint = request_fingerprint(request)
    except ProtocolValidationError as exc:
        raise GatewayOutcomeError("OUTCOME_CONTEXT_REQUEST_INVALID") from exc
    if logical_fingerprint != context.request_fingerprint:
        raise GatewayOutcomeError("OUTCOME_CONTEXT_FINGERPRINT_MISMATCH")
    if request.get("authorization_ref") != context.authorization_ref:
        raise GatewayOutcomeError("OUTCOME_CONTEXT_AUTHORIZATION_MISMATCH")
    if request.get("idempotency_key") != context.idempotency_key:
        raise GatewayOutcomeError("OUTCOME_CONTEXT_IDEMPOTENCY_MISMATCH")
    return request


def _sanitize_outcome(
    *,
    context: GatewayOutcomeContext,
    runner_request: Mapping[str, Any],
    runner_outcome: Mapping[str, Any],
) -> dict[str, Any]:
    operation = runner_request["operation"]
    operation_input = operation["input"]
    sanitized_evidence = [
        {
            "evidence_id": str(item["evidence_id"]),
            "kind": str(item["kind"]),
            "classification": str(item["classification"]),
            "sha256": str(item["sha256"]),
        }
        for item in runner_outcome["evidence_refs"]
    ]

    typed: dict[str, Any] = {
        "schema_version": OUTCOME_SCHEMA_VERSION,
        "message_type": OUTCOME_MESSAGE_TYPE,
        "runner_protocol_version": RUNNER_PROTOCOL_VERSION,
        "correlation": json.loads(json.dumps(runner_outcome["correlation"])),
        "authorization_ref": context.authorization_ref,
        "idempotency_key": context.idempotency_key,
        "request_fingerprint": context.request_fingerprint,
        "request_envelope_sha256": context.request_envelope_sha256,
        "operation_id": str(operation_input["operation_id"]),
        "operation_version": str(operation_input["operation_version"]),
        "capability_id": str(operation["capability_id"]),
        "runner_status": str(runner_outcome["status"]),
        "runner_emitted_at": str(runner_outcome["emitted_at"]),
        "started_at": str(runner_outcome["started_at"]),
        "finished_at": str(runner_outcome["finished_at"]),
        "evidence_refs": sanitized_evidence,
        "output_present": "output" in runner_outcome,
    }

    runner_error = runner_outcome.get("error")
    if isinstance(runner_error, Mapping):
        typed["error"] = {
            "code": str(runner_error["code"]),
            "category": str(runner_error["category"]),
            "retryable": bool(runner_error["retryable"]),
        }
    return typed


def _validate_gateway_outcome(outcome: Mapping[str, Any]) -> None:
    schema = json.loads(
        (ROOT / "gateway-execution-outcome.schema.json").read_text(encoding="utf-8")
    )
    validator = jsonschema.Draft202012Validator(
        schema,
        format_checker=jsonschema.FormatChecker(),
    )
    if list(validator.iter_errors(outcome)):
        raise GatewayOutcomeError("GATEWAY_OUTCOME_SCHEMA_INVALID")


def _canonical_json(value: Mapping[str, Any]) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _mapping(value: Any, key: str) -> Mapping[str, Any] | None:
    if not isinstance(value, Mapping):
        return None
    candidate = value.get(key)
    return candidate if isinstance(candidate, Mapping) else None


def _string(value: Any, key: str) -> str | None:
    if not isinstance(value, Mapping):
        return None
    candidate = value.get(key)
    return candidate if isinstance(candidate, str) else None


def _context_or_none(value: Any) -> GatewayOutcomeContext | None:
    return value if isinstance(value, GatewayOutcomeContext) else None
