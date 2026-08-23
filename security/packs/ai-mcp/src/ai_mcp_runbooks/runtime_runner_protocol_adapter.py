"""Controlled Runner Protocol composition for the calibrated AI/MCP runtime.

This module composes the existing pure protocol projection with an explicitly
injected runtime executor and durable idempotency. It provides no default
executor, opens no network connection and creates no subprocess. Production
activation, timeout/cancellation supervision and target authority remain out of
scope and fail closed.
"""

from __future__ import annotations

import copy
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable, Mapping

from ai_mcp_runbooks.contracts import ExecutionResult
from ai_mcp_runbooks.runner_protocol_projection import (
    CAPABILITY_ID,
    ProjectionRefusal,
    evidence_reference,
    is_calibrated,
    project_execution_result,
    project_step_request,
    refusal_outcome,
)
from runner_protocol_v2 import LedgerError, SQLiteIdempotencyLedger, request_fingerprint, validate_semantics

RuntimeExecutor = Callable[[dict[str, Any]], Mapping[str, Any]]
DEFAULT_EXECUTOR: RuntimeExecutor | None = None


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _refusal(
    code: str, category: str, message: str, *, retryable: bool = False
) -> ProjectionRefusal:
    return ProjectionRefusal(
        {
            "code": code,
            "category": category,
            "retryable": retryable,
            "message": message[:256].replace("\n", " ").replace("\r", " "),
        }
    )


def _messages(outcome: dict[str, Any]) -> dict[str, Any]:
    validate_semantics(outcome)
    return {"messages": [outcome]}


def _replay(request: Mapping[str, Any], stored: Mapping[str, Any]) -> dict[str, Any]:
    outcome = copy.deepcopy(dict(stored))
    outcome["correlation"] = dict(request["correlation"])
    outcome["emitted_at"] = _now()
    validate_semantics(outcome)
    return {"messages": [outcome]}


def _inconclusive_after_effect(
    request: Mapping[str, Any], *, started_at: str, message: str
) -> dict[str, Any]:
    record = {
        "decision": "effect_completed_but_durable_state_unavailable",
        "code": "INTERNAL_ERROR",
        "capability_id": CAPABILITY_ID,
    }
    outcome = {
        "message_type": "runner.outcome",
        "protocol_version": "2.0.0",
        "correlation": dict(request["correlation"]),
        "emitted_at": _now(),
        "status": "INCONCLUSIVE",
        "started_at": started_at,
        "finished_at": _now(),
        "evidence_refs": [evidence_reference(record, kind="protocol")],
        "error": {
            "code": "INTERNAL_ERROR",
            "category": "internal",
            "retryable": False,
            "message": message,
        },
    }
    return _messages(outcome)


@dataclass
class ControlledAiMcpRunnerProtocolAdapter:
    durable_ledger: SQLiteIdempotencyLedger
    executor: RuntimeExecutor | None = DEFAULT_EXECUTOR
    policy: dict[str, Any] | None = None
    effect_count: int = 0

    def __post_init__(self) -> None:
        if self.durable_ledger is None:
            raise ValueError("durable_ledger is required")

    def _claim(self, request: dict[str, Any], fingerprint: str) -> dict[str, Any] | None:
        try:
            decision = self.durable_ledger.claim(request["idempotency_key"], fingerprint)
        except LedgerError:
            return _messages(
                refusal_outcome(
                    request,
                    _refusal(
                        "INTERNAL_ERROR",
                        "internal",
                        "Durable idempotency state is unavailable; execution is refused",
                    ),
                )
            )

        if decision.classification == "NEW":
            return None
        if decision.classification == "REPLAY_SAME" and decision.record is not None:
            if decision.record.outcome is not None:
                return _replay(request, decision.record.outcome)
        return _messages(
            refusal_outcome(
                request,
                _refusal(
                    "IDEMPOTENCY_CONFLICT",
                    "conflict",
                    "Idempotency state is active, conflicting or incomplete",
                ),
            )
        )

    def dispatch(self, request: dict[str, Any]) -> dict[str, Any]:
        try:
            execution_request = project_step_request(request, self.policy)
        except ProjectionRefusal as refusal:
            return _messages(refusal_outcome(request, refusal))

        if not is_calibrated(execution_request):
            return _messages(
                refusal_outcome(
                    request,
                    _refusal(
                        "UNSUPPORTED_CAPABILITY",
                        "compatibility",
                        "AI/MCP handler is declared but not calibrated",
                    ),
                )
            )
        if self.executor is None:
            return _messages(
                refusal_outcome(
                    request,
                    _refusal(
                        "RUNNER_UNAVAILABLE",
                        "compatibility",
                        "Controlled AI/MCP runtime executor is not configured",
                        retryable=True,
                    ),
                )
            )

        fingerprint = request_fingerprint(request)
        preflight = self._claim(request, fingerprint)
        if preflight is not None:
            return preflight

        started_at = _now()
        self.effect_count += 1
        try:
            runtime_result = self.executor(execution_request.to_dict())
        except Exception as exc:  # noqa: BLE001 - normalize type only, never raw text
            runtime_result = ExecutionResult.error(
                f"runtime executor failure: {type(exc).__name__}",
                execution_request,
            )

        try:
            outcome = project_execution_result(
                request,
                runtime_result,
                started_at=started_at,
            )
        except Exception as exc:  # noqa: BLE001 - invalid runtime result fails closed
            outcome = project_execution_result(
                request,
                ExecutionResult.error(
                    f"runtime result projection failure: {type(exc).__name__}",
                    execution_request,
                ),
                started_at=started_at,
            )

        try:
            self.durable_ledger.complete(
                request["idempotency_key"],
                fingerprint,
                outcome,
            )
        except LedgerError:
            return _inconclusive_after_effect(
                request,
                started_at=started_at,
                message="Runtime outcome could not be committed to durable idempotency state",
            )
        return _messages(outcome)
