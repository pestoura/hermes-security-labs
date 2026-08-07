"""Sanitized Runner Protocol v2 outcome -> Hermes gateway outcome boundary.

This module never executes a runner and never treats an outcome as authorization.
It validates a terminal ``runner.outcome`` against the exact Runner request that
was previously built by the gateway, then emits only a sanitized derivative for
the control plane.

Raw runner ``output``, evidence ``uri``, error ``message`` and ``safe_context``
are deliberately excluded from the derivative. Evidence references remain
attestations of what happened; they do not create or expand execution authority.

Boundary: repository-level contract transformation only. Runner identity,
transport authenticity, deployed gateway reception and Evidence Plane
persistence remain NOT_IMPLEMENTED / NOT_RUN.
"""

from __future__ import annotations

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


runner_handoff = _load_module("gateway_runner_handoff_outcome_core", ROOT / "runner_handoff.py")

OUTCOME_SCHEMA_VERSION = "1.0.0"
OUTCOME_MESSAGE_TYPE = "gateway.execution.outcome"
RUNNER_PROTOCOL_VERSION = "2.0.0"


class GatewayOutcomeError(ValueError):
    """Stable contract error for a gateway outcome that cannot be trusted."""


@dataclass(frozen=True)
class GatewayOutcomeResult:
    """Result of building a sanitized control-plane outcome derivative.

    ``typed_outcome`` is safe for the gateway/control-plane contract but is
    still operational metadata. It is excluded from ``repr`` so callers do not
    accidentally log the complete cross-plane record.
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
    evidence_count: int
    output_present: bool
    error_code: str | None
    typed_outcome: dict[str, Any] | None = field(repr=False, default=None)

    @classmethod
    def refuse(
        cls,
        codes: Iterable[str],
        *,
        handoff_result: Any | None = None,
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
            authorization_ref=_safe_attr(handoff_result, "authorization_ref"),
            request_fingerprint=_safe_attr(handoff_result, "request_fingerprint"),
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
            "evidence_count": int(self.evidence_count),
            "output_present": bool(self.output_present),
            "error_code": self.error_code,
            "typed_outcome_present": self.typed_outcome is not None,
        }


def build_execution_outcome(
    handoff_result: Any,
    runner_outcome: Mapping[str, Any],
) -> GatewayOutcomeResult:
    """Validate and sanitize a terminal Runner Protocol v2 outcome.

    The previously built Runner request is the local binding context. This
    function verifies that context has not changed, validates the runner
    outcome, requires exact four-ID correlation, and only then derives the
    control-plane outcome.

    This does not prove runner identity or transport authenticity. Those are
    deployment concerns and remain outside this repository-only boundary.
    """

    if not _handoff_built(handoff_result):
        return GatewayOutcomeResult.refuse(
            ("OUTCOME_HANDOFF_NOT_BUILT",),
            handoff_result=handoff_result,
            runner_outcome=runner_outcome,
        )

    runner_request = getattr(handoff_result, "runner_request", None)
    if not isinstance(runner_request, Mapping):
        return GatewayOutcomeResult.refuse(
            ("OUTCOME_HANDOFF_REQUEST_MISSING",),
            handoff_result=handoff_result,
            runner_outcome=runner_outcome,
        )

    try:
        validate_semantics(runner_request)
    except ProtocolValidationError:
        return GatewayOutcomeResult.refuse(
            ("OUTCOME_HANDOFF_REQUEST_INVALID",),
            handoff_result=handoff_result,
            runner_outcome=runner_outcome,
        )
    except Exception:  # noqa: BLE001 - any contract integration defect fails closed
        return GatewayOutcomeResult.refuse(
            ("OUTCOME_HANDOFF_INTEGRATION_ERROR",),
            handoff_result=handoff_result,
            runner_outcome=runner_outcome,
        )

    if runner_request.get("message_type") != "runner.step.request":
        return GatewayOutcomeResult.refuse(
            ("OUTCOME_HANDOFF_REQUEST_TYPE_INVALID",),
            handoff_result=handoff_result,
            runner_outcome=runner_outcome,
        )

    try:
        computed_fingerprint = request_fingerprint(runner_request)
    except ProtocolValidationError:
        return GatewayOutcomeResult.refuse(
            ("OUTCOME_HANDOFF_REQUEST_INVALID",),
            handoff_result=handoff_result,
            runner_outcome=runner_outcome,
        )

    if getattr(handoff_result, "request_fingerprint", None) != computed_fingerprint:
        return GatewayOutcomeResult.refuse(
            ("OUTCOME_HANDOFF_FINGERPRINT_MISMATCH",),
            handoff_result=handoff_result,
            runner_outcome=runner_outcome,
        )
    if getattr(handoff_result, "authorization_ref", None) != runner_request.get(
        "authorization_ref"
    ):
        return GatewayOutcomeResult.refuse(
            ("OUTCOME_HANDOFF_AUTHORIZATION_MISMATCH",),
            handoff_result=handoff_result,
            runner_outcome=runner_outcome,
        )
    if getattr(handoff_result, "idempotency_key", None) != runner_request.get(
        "idempotency_key"
    ):
        return GatewayOutcomeResult.refuse(
            ("OUTCOME_HANDOFF_IDEMPOTENCY_MISMATCH",),
            handoff_result=handoff_result,
            runner_outcome=runner_outcome,
        )

    if not isinstance(runner_outcome, Mapping):
        return GatewayOutcomeResult.refuse(
            ("RUNNER_OUTCOME_INVALID",),
            handoff_result=handoff_result,
            runner_outcome=None,
        )
    try:
        validate_semantics(runner_outcome)
    except ProtocolValidationError:
        return GatewayOutcomeResult.refuse(
            ("RUNNER_OUTCOME_INVALID",),
            handoff_result=handoff_result,
            runner_outcome=runner_outcome,
        )
    except Exception:  # noqa: BLE001 - any contract integration defect fails closed
        return GatewayOutcomeResult.refuse(
            ("RUNNER_OUTCOME_INTEGRATION_ERROR",),
            handoff_result=handoff_result,
            runner_outcome=runner_outcome,
        )

    if runner_outcome.get("message_type") != "runner.outcome":
        return GatewayOutcomeResult.refuse(
            ("RUNNER_OUTCOME_TYPE_INVALID",),
            handoff_result=handoff_result,
            runner_outcome=runner_outcome,
        )

    request_correlation = runner_request.get("correlation")
    outcome_correlation = runner_outcome.get("correlation")
    if outcome_correlation != request_correlation:
        return GatewayOutcomeResult.refuse(
            ("RUNNER_OUTCOME_CORRELATION_MISMATCH",),
            handoff_result=handoff_result,
            runner_outcome=runner_outcome,
        )

    try:
        typed_outcome = _sanitize_outcome(
            runner_request=runner_request,
            request_fingerprint_value=computed_fingerprint,
            runner_outcome=runner_outcome,
        )
        _validate_gateway_outcome(typed_outcome)
    except GatewayOutcomeError as exc:
        return GatewayOutcomeResult.refuse(
            (str(exc),),
            handoff_result=handoff_result,
            runner_outcome=runner_outcome,
        )
    except Exception:  # noqa: BLE001 - never emit a partial derivative
        return GatewayOutcomeResult.refuse(
            ("GATEWAY_OUTCOME_INTEGRATION_ERROR",),
            handoff_result=handoff_result,
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
        authorization_ref=str(typed_outcome["authorization_ref"]),
        request_fingerprint=str(typed_outcome["request_fingerprint"]),
        evidence_count=len(typed_outcome["evidence_refs"]),
        output_present=bool(typed_outcome["output_present"]),
        error_code=str(error["code"]) if isinstance(error, Mapping) else None,
        typed_outcome=typed_outcome,
    )


def _sanitize_outcome(
    *,
    runner_request: Mapping[str, Any],
    request_fingerprint_value: str,
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
        "authorization_ref": str(runner_request["authorization_ref"]),
        "idempotency_key": str(runner_request["idempotency_key"]),
        "request_fingerprint": request_fingerprint_value,
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


def _handoff_built(value: Any) -> bool:
    return bool(getattr(value, "request_built", False))


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


def _safe_attr(value: Any, key: str) -> str | None:
    candidate = getattr(value, key, None)
    return candidate if isinstance(candidate, str) else None
