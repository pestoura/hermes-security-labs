"""Canonical, side-effect-free projection between Runner Protocol v2 and the
calibrated AI/MCP runtime contracts.

Why this module exists
----------------------

Runner Protocol v2 owns dispatch, correlation, idempotency, timeout,
cancellation, normalized errors and terminal evidence. The AI/MCP pack owns a
calibrated runtime with its own typed contracts
(:class:`ai_mcp_runbooks.contracts.ExecutionRequest` /
:class:`~ai_mcp_runbooks.contracts.ExecutionResult`), its own policy allowlist
and its own sanitiser.

Before this module the two contracts had no canonical translation, so the
calibrated runtime could neither be *addressed* by a protocol message nor be
*validated* against the protocol's terminal-outcome rules. The supervised
synthetic candidate does not close that gap: it deliberately runs a fixed
worker and never touches the runtime contracts.

What this module is
-------------------

A pure translation boundary in two directions:

``project_step_request``
    validated ``runner.step.request`` → validated, policy-authorised
    :class:`ExecutionRequest`. Refusals are raised as normalized protocol
    errors, never as pack exceptions.

``project_execution_result``
    sanitised :class:`ExecutionResult` → validated ``runner.outcome`` carrying
    a deterministic evidence reference over the sanitised document.

What this module is **not**
---------------------------

It never executes anything. It does not import ``ai_mcp_runbooks.dispatch``,
``ai_mcp_runbooks.execution`` or any adapter, creates no subprocess, opens no
socket, performs no HTTP request and reaches no provider, agent, memory/RAG
component, campaign or laboratory target. The caller remains responsible for
whether execution happens at all; ``execution_integration`` stays ``NOT_RUN``.

Authorization is not created here either: ``authorization_ref`` is copied from
the incoming protocol message and the pack policy can only refuse, never widen.
"""

from __future__ import annotations

import hashlib
import json
import uuid
from datetime import datetime, timezone
from typing import Any, Mapping

from ai_mcp_runbooks.contracts import Decision, ExecutionRequest, ExecutionResult, Status
from ai_mcp_runbooks.policy import PolicyViolation, authorise_request, is_implemented_handler
from ai_mcp_runbooks.sanitizer import sanitize_mapping
from runner_protocol_v2 import validate_semantics

PROTOCOL_VERSION = "2.0.0"

#: The single capability identifier this projection accepts. A protocol message
#: cannot name a provider/action pair directly; it names this capability and the
#: pack contract validates the payload.
CAPABILITY_ID = "ai-mcp.runtime.handler-invoke"

#: Deterministic namespace for evidence identifiers derived from a digest.
EVIDENCE_NAMESPACE = uuid.UUID("6f9d5f2e-3f0a-4c37-9a1a-2d0d1d6c5f00")

#: Runtime status → protocol terminal status. A security *decision* is never a
#: protocol failure: a handler that correctly proves a target vulnerable is a
#: successful step. Only the execution status maps to the terminal status.
STATUS_MAP: dict[Status, str] = {
    Status.OK: "PASS",
    Status.DRY_RUN: "PASS",
    Status.SKIPPED: "INCONCLUSIVE",
    Status.NOT_IMPLEMENTED: "REFUSED",
    Status.ERROR: "ERROR",
}


class ProjectionRefusal(Exception):
    """A protocol-level refusal carrying an already-normalized error.

    The message is bounded and sanitised by construction; raw pack exception
    text never reaches the protocol surface.
    """

    def __init__(self, error: dict[str, Any]) -> None:
        super().__init__(error["code"])
        self.error = error


def _error(code: str, category: str, message: str, *, retryable: bool = False) -> dict[str, Any]:
    return {
        "code": code,
        "category": category,
        "retryable": retryable,
        "message": message[:256].replace("\n", " ").replace("\r", " "),
    }


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def canonical_digest(document: Mapping[str, Any]) -> str:
    """SHA-256 over the canonical JSON encoding of a sanitised document."""

    encoded = json.dumps(
        document, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def evidence_reference(document: Mapping[str, Any], *, kind: str) -> dict[str, Any]:
    """Build a deterministic evidence reference over a sanitised document.

    The document itself is not embedded: only its digest travels, so no
    runtime text can escape through the protocol message.
    """

    if kind not in {"decision", "protocol", "execution"}:
        raise ValueError(f"unsupported evidence kind {kind!r}")
    digest = canonical_digest(document)
    return {
        "evidence_id": str(uuid.uuid5(EVIDENCE_NAMESPACE, digest)),
        "kind": kind,
        "classification": "INTERNAL",
        "sha256": digest,
        "uri": f"evidence://ai-mcp/runtime-projection/{digest}",
    }


def project_step_request(
    request: Mapping[str, Any], policy: dict[str, Any] | None = None
) -> ExecutionRequest:
    """Translate a ``runner.step.request`` into an authorised pack request.

    The protocol message is validated first, then the pack contract validates
    the untrusted input, then the pack policy authorises it. Every failure is
    a protocol refusal; nothing is executed on any path.
    """

    try:
        validate_semantics(request)
    except Exception as exc:  # noqa: BLE001 - normalized, never propagated raw
        raise ProjectionRefusal(
            _error("INVALID_REQUEST", "validation", f"protocol validation failed: {type(exc).__name__}")
        ) from None

    if request.get("message_type") != "runner.step.request":
        raise ProjectionRefusal(
            _error("INVALID_REQUEST", "validation", "projection accepts only runner.step.request")
        )

    operation = request["operation"]
    if operation["capability_id"] != CAPABILITY_ID:
        raise ProjectionRefusal(
            _error(
                "UNSUPPORTED_CAPABILITY",
                "compatibility",
                f"capability is not projected by the AI/MCP runtime: {operation['capability_id']}",
            )
        )

    try:
        execution_request = ExecutionRequest.from_payload(operation["input"])
    except ValueError as exc:
        raise ProjectionRefusal(
            _error("INVALID_REQUEST", "validation", f"invalid AI/MCP runtime input: {exc}")
        ) from None

    try:
        authorise_request(execution_request, policy)
    except PolicyViolation as exc:
        raise ProjectionRefusal(
            _error("AUTHORIZATION_DENIED", "authorization", f"pack policy refusal: {exc}")
        ) from None

    return execution_request


def project_execution_result(
    request: Mapping[str, Any],
    result: ExecutionResult | Mapping[str, Any],
    *,
    started_at: str,
    finished_at: str | None = None,
) -> dict[str, Any]:
    """Translate a sanitised runtime result into a validated ``runner.outcome``.

    ``result`` may be an :class:`ExecutionResult` or an already-sanitised
    document; sanitisation is applied unconditionally either way, so an adapter
    bug cannot leak prompt text, model output or markers into protocol
    evidence.
    """

    if isinstance(result, ExecutionResult):
        document = result.to_dict()
        status_value = result.status.value
        decision_value = result.decision.value
        reason = result.reason
    else:
        document = dict(result)
        status_value = str(document.get("status", ""))
        decision_value = str(document.get("decision", Decision.INCONCLUSIVE.value))
        reason = str(document.get("reason", ""))

    try:
        status_enum = Status(status_value)
    except ValueError:
        raise ProjectionRefusal(
            _error("INTERNAL_ERROR", "internal", f"unknown runtime status {status_value!r}")
        ) from None

    document["evidence"] = [
        sanitize_mapping(dict(item)) for item in document.get("evidence", []) or []
    ]
    document["meta"] = sanitize_mapping(dict(document.get("meta", {}) or {}))
    document["reason"] = sanitize_mapping({"reason": reason})["reason"]

    terminal_status = STATUS_MAP[status_enum]
    evidence_kind = "execution" if status_enum in {Status.OK, Status.ERROR} else "decision"

    outcome: dict[str, Any] = {
        "message_type": "runner.outcome",
        "protocol_version": PROTOCOL_VERSION,
        "correlation": dict(request["correlation"]),
        "emitted_at": _now(),
        "status": terminal_status,
        "started_at": started_at,
        "finished_at": finished_at or _now(),
        "evidence_refs": [evidence_reference(document, kind=evidence_kind)],
        "output": {
            "runtime_status": status_enum.value,
            "runtime_decision": decision_value,
            "vulnerable_signals": list(document.get("vulnerable_signals", []) or []),
            "secure_signals": list(document.get("secure_signals", []) or []),
            "inconclusive_signals": list(document.get("inconclusive_signals", []) or []),
            "evidence_items": len(document["evidence"]),
        },
    }

    if terminal_status == "ERROR":
        outcome["error"] = _error("EXECUTION_FAILED", "execution", document["reason"] or "handler error")
    elif terminal_status == "REFUSED":
        outcome["error"] = _error(
            "UNSUPPORTED_CAPABILITY",
            "compatibility",
            document["reason"] or "handler is declared but not calibrated",
        )

    validate_semantics(outcome)
    return outcome


def refusal_outcome(
    request: Mapping[str, Any],
    refusal: ProjectionRefusal,
    *,
    started_at: str | None = None,
) -> dict[str, Any]:
    """Build the validated ``REFUSED`` outcome for a pre-execution refusal.

    The evidence is a decision record: it states that a decision was taken, not
    that technical execution occurred.
    """

    moment = started_at or _now()
    decision_record = {
        "decision": "refused_before_execution",
        "code": refusal.error["code"],
        "category": refusal.error["category"],
        "capability_id": CAPABILITY_ID,
    }
    outcome = {
        "message_type": "runner.outcome",
        "protocol_version": PROTOCOL_VERSION,
        "correlation": dict(request["correlation"]),
        "emitted_at": _now(),
        "status": "REFUSED",
        "started_at": moment,
        "finished_at": _now(),
        "evidence_refs": [evidence_reference(decision_record, kind="decision")],
        "error": refusal.error,
    }
    validate_semantics(outcome)
    return outcome


def is_calibrated(execution_request: ExecutionRequest) -> bool:
    """Report whether the projected handler has a calibrated implementation.

    Exposed so a caller can decide *before* execution; the projection itself
    never executes and never promotes an uncalibrated handler.
    """

    return is_implemented_handler(*execution_request.handler)
