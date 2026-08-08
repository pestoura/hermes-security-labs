"""Repository-only observation contract for Runner Protocol v2 cancellation.

This module correlates an already-built ``runner.cancellation.request`` with
observed canonical ``runner.cancellation.ack`` and ``runner.outcome`` messages.
It performs no transport, dispatch, process signalling or execution and does
not authenticate the origin of observed protocol messages.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from datetime import datetime, timezone
from typing import Any

from runner_protocol_v2 import ProtocolValidationError, validate_semantics

SCHEMA_VERSION = "1.0.0"
MAX_ACK_DEADLINE_SECONDS = 300
MAX_TERMINAL_DEADLINE_SECONDS = 1800


class CancellationObservationError(ValueError):
    """Fail-closed cancellation-observation contract violation."""


def _canonical(value: Any) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=True
    ).encode("utf-8")


def _sha256(value: Any) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def _parse_time(value: Any, code: str) -> datetime:
    if not isinstance(value, str) or not value:
        raise CancellationObservationError(code)
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise CancellationObservationError(code) from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise CancellationObservationError(code)
    return parsed.astimezone(timezone.utc)


def _validate_deadline(value: Any, *, maximum: int, code: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= maximum:
        raise CancellationObservationError(code)
    return value


def _validate_protocol_message(
    message: Mapping[str, Any], expected_type: str, code: str
) -> dict[str, Any]:
    if not isinstance(message, Mapping):
        raise CancellationObservationError(code)
    candidate = dict(message)
    try:
        validate_semantics(candidate)
    except ProtocolValidationError as exc:
        raise CancellationObservationError(code) from exc
    if candidate.get("message_type") != expected_type:
        raise CancellationObservationError(code)
    return candidate


def _one_distinct(
    messages: Sequence[Mapping[str, Any]] | None,
    *,
    expected_type: str,
    invalid_code: str,
    conflict_code: str,
) -> dict[str, Any] | None:
    if messages is None:
        return None
    if not isinstance(messages, Sequence) or isinstance(messages, (str, bytes)):
        raise CancellationObservationError(invalid_code)
    validated = [
        _validate_protocol_message(message, expected_type, invalid_code)
        for message in messages
    ]
    if not validated:
        return None
    unique = {_canonical(message): message for message in validated}
    if len(unique) > 1:
        raise CancellationObservationError(conflict_code)
    return next(iter(unique.values()))


def _same_correlation(request: Mapping[str, Any], event: Mapping[str, Any]) -> bool:
    return request.get("correlation") == event.get("correlation")


def _limitations() -> list[str]:
    return [
        "ACK_OBSERVATION_DOES_NOT_PROVE_TRANSPORT_AUTHENTICITY",
        "OUTCOME_OBSERVATION_DOES_NOT_PROVE_RUNNER_AUTHENTICITY",
        "OBSERVER_DOES_NOT_DISPATCH_CANCELLATION",
        "OBSERVER_DOES_NOT_PROVE_PROCESS_TERMINATION",
        "RUNTIME_DELIVERY_AND_INTERRUPTION_EVIDENCE_NOT_RUN",
    ]


def observe_cancellation(
    *,
    cancellation_request: Mapping[str, Any],
    acknowledgements: Sequence[Mapping[str, Any]] | None,
    outcomes: Sequence[Mapping[str, Any]] | None,
    observed_at: str,
    acknowledgement_deadline_seconds: int = 30,
    terminal_deadline_seconds: int = 300,
) -> dict[str, Any]:
    """Correlate canonical cancellation messages without claiming runtime proof.

    Exact duplicate observations are idempotent. Multiple distinct ACKs or
    outcomes for one cancellation request are refused as conflicting evidence.
    """

    request = _validate_protocol_message(
        cancellation_request,
        "runner.cancellation.request",
        "CANCELLATION_REQUEST_INVALID",
    )
    ack = _one_distinct(
        acknowledgements,
        expected_type="runner.cancellation.ack",
        invalid_code="CANCELLATION_ACK_INVALID",
        conflict_code="CANCELLATION_ACK_CONFLICT",
    )
    outcome = _one_distinct(
        outcomes,
        expected_type="runner.outcome",
        invalid_code="CANCELLATION_OUTCOME_INVALID",
        conflict_code="CANCELLATION_OUTCOME_CONFLICT",
    )

    ack_deadline = _validate_deadline(
        acknowledgement_deadline_seconds,
        maximum=MAX_ACK_DEADLINE_SECONDS,
        code="CANCELLATION_ACK_DEADLINE_INVALID",
    )
    terminal_deadline = _validate_deadline(
        terminal_deadline_seconds,
        maximum=MAX_TERMINAL_DEADLINE_SECONDS,
        code="CANCELLATION_TERMINAL_DEADLINE_INVALID",
    )
    if terminal_deadline < ack_deadline:
        raise CancellationObservationError("CANCELLATION_DEADLINE_ORDER_INVALID")

    request_time = _parse_time(request["emitted_at"], "CANCELLATION_REQUEST_TIME_INVALID")
    now = _parse_time(observed_at, "CANCELLATION_OBSERVED_AT_INVALID")
    if now < request_time:
        raise CancellationObservationError("CANCELLATION_OBSERVATION_PRECEDES_REQUEST")

    for event, code in (
        (ack, "CANCELLATION_ACK_CORRELATION_MISMATCH"),
        (outcome, "CANCELLATION_OUTCOME_CORRELATION_MISMATCH"),
    ):
        if event is not None and not _same_correlation(request, event):
            raise CancellationObservationError(code)

    if ack is not None:
        ack_time = _parse_time(ack["emitted_at"], "CANCELLATION_ACK_TIME_INVALID")
        if ack_time < request_time:
            raise CancellationObservationError("CANCELLATION_ACK_PRECEDES_REQUEST")
        if ack_time > now:
            raise CancellationObservationError("CANCELLATION_ACK_FROM_FUTURE")

    if outcome is not None:
        outcome_time = _parse_time(
            outcome["emitted_at"], "CANCELLATION_OUTCOME_TIME_INVALID"
        )
        if outcome_time > now:
            raise CancellationObservationError("CANCELLATION_OUTCOME_FROM_FUTURE")

    ack_status = ack.get("status") if ack is not None else None
    outcome_status = outcome.get("status") if outcome is not None else None

    if ack_status in {"not_found", "refused"} and outcome is not None:
        raise CancellationObservationError(
            "CANCELLATION_NEGATIVE_ACK_WITH_OUTCOME_CONFLICT"
        )

    elapsed = (now - request_time).total_seconds()
    ack_observed = ack is not None
    terminal_observed = outcome is not None
    cancellation_result = "UNPROVEN"

    if ack_status == "not_found":
        state = "NOT_FOUND_DECLARED"
    elif ack_status == "refused":
        state = "REFUSED_DECLARED"
    elif ack_status == "already_terminal":
        if outcome is None:
            state = (
                "TERMINAL_TIMEOUT"
                if elapsed > terminal_deadline
                else "WAITING_TERMINAL"
            )
        elif outcome_status == "CANCELLED":
            state = "ALREADY_TERMINAL_CANCELLED_DECLARED"
            cancellation_result = "CANCELLED_DECLARED"
        else:
            state = "ALREADY_TERMINAL_NON_CANCELLED_DECLARED"
            cancellation_result = "NON_CANCELLED_TERMINAL_DECLARED"
    elif ack_status == "accepted":
        if outcome is None:
            state = (
                "TERMINAL_TIMEOUT"
                if elapsed > terminal_deadline
                else "WAITING_TERMINAL"
            )
        else:
            finished = _parse_time(
                outcome["finished_at"], "CANCELLATION_OUTCOME_FINISHED_AT_INVALID"
            )
            if finished < request_time:
                raise CancellationObservationError(
                    "CANCELLATION_ACCEPTED_BUT_OUTCOME_PRECEDES_REQUEST"
                )
            if outcome_status == "CANCELLED":
                state = "CANCELLED_DECLARED"
                cancellation_result = "CANCELLED_DECLARED"
            else:
                state = "TERMINAL_NON_CANCELLED_DECLARED"
                cancellation_result = "NON_CANCELLED_TERMINAL_DECLARED"
    elif outcome is not None:
        if outcome_status == "CANCELLED":
            state = "CANCELLED_DECLARED_WITHOUT_ACK"
            cancellation_result = "CANCELLED_DECLARED"
        else:
            state = "TERMINAL_NON_CANCELLED_DECLARED_WITHOUT_ACK"
            cancellation_result = "NON_CANCELLED_TERMINAL_DECLARED"
    else:
        state = "ACK_TIMEOUT" if elapsed > ack_deadline else "WAITING_ACK"

    seed = {
        "cancellation_request_sha256": _sha256(request),
        "correlation": request["correlation"],
        "observed_at": observed_at,
        "state": state,
        "ack_sha256": _sha256(ack) if ack is not None else None,
        "outcome_sha256": _sha256(outcome) if outcome is not None else None,
    }
    return {
        "schema_version": SCHEMA_VERSION,
        "observation_id": f"cobs_{_sha256(seed)[:32]}",
        "cancellation_request_sha256": seed["cancellation_request_sha256"],
        "correlation": dict(request["correlation"]),
        "observed_at": observed_at,
        "state": state,
        "ack_observed": ack_observed,
        "ack_status": ack_status,
        "terminal_outcome_observed": terminal_observed,
        "outcome_status": outcome_status,
        "cancellation_result": cancellation_result,
        "transport_authenticity": "NOT_VERIFIED",
        "terminal_outcome_authenticity": "NOT_VERIFIED",
        "dispatch_performed_by_observer": False,
        "authorization_effect": "NONE",
        "execution_authority": "NONE",
        "limitations": _limitations(),
    }
