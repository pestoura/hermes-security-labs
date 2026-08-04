"""Dispatch layer: request → policy → adapter → sanitised result."""

from __future__ import annotations

from typing import Any

from ai_mcp_runbooks.adapters import build_adapter
from ai_mcp_runbooks.contracts import Decision, ExecutionRequest, ExecutionResult, Status
from ai_mcp_runbooks.execution import CommandError, HttpTransport
from ai_mcp_runbooks.policy import (
    PolicyViolation,
    authorise_request,
    is_implemented_handler,
)
from ai_mcp_runbooks.sanitizer import sanitize_mapping


def sanitize_result(result: ExecutionResult) -> dict[str, Any]:
    """Serialise ``result`` with unconditional sanitisation applied."""

    document = result.to_dict()
    document["evidence"] = [sanitize_mapping(item) for item in document.get("evidence", [])]
    document["meta"] = sanitize_mapping(document.get("meta", {}))
    return document


def _not_implemented(request: ExecutionRequest, reason: str) -> ExecutionResult:
    return ExecutionResult(
        status=Status.NOT_IMPLEMENTED,
        decision=Decision.INCONCLUSIVE,
        provider=request.provider,
        action=request.action,
        profile=request.profile,
        target_ref=request.target_ref,
        scope=request.scope,
        control_id=request.control_id,
        reason=reason,
        inconclusive_signals=("handler.not_calibrated",),
    )


def dispatch(
    payload: Any,
    policy: dict[str, Any] | None = None,
    transport: HttpTransport | None = None,
) -> dict[str, Any]:
    """Validate, authorise and execute ``payload``; always returns a dict."""

    try:
        request = ExecutionRequest.from_payload(payload)
    except ValueError as exc:
        return sanitize_result(ExecutionResult.error(f"invalid request: {exc}"))

    try:
        authorise_request(request, policy)
    except PolicyViolation as exc:
        return sanitize_result(ExecutionResult.error(f"policy violation: {exc}", request))

    if not is_implemented_handler(*request.handler):
        return sanitize_result(
            _not_implemented(
                request,
                f"handler {request.provider}/{request.action} is declared but has no "
                "calibrated adapter",
            )
        )

    try:
        adapter = build_adapter(request, transport=transport)
    except NotImplementedError as exc:
        return sanitize_result(_not_implemented(request, str(exc)))

    try:
        result = adapter.run(request)
    except CommandError as exc:
        return sanitize_result(ExecutionResult.error(f"execution refused: {exc}", request))
    except Exception as exc:  # noqa: BLE001 - the runner must never crash the caller
        return sanitize_result(
            ExecutionResult.error(f"adapter failure: {type(exc).__name__}", request)
        )

    return sanitize_result(result)
