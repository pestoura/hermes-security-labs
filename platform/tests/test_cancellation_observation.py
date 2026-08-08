from __future__ import annotations

import importlib.util
import json
import sys
from copy import deepcopy
from pathlib import Path

import jsonschema
import pytest


ROOT = Path(__file__).resolve().parents[2]
GATEWAY = ROOT / "platform/gateway-protocol"
MODULE = GATEWAY / "cancellation_observation.py"

spec = importlib.util.spec_from_file_location("cancellation_observation_test", MODULE)
assert spec and spec.loader
observation = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = observation
spec.loader.exec_module(observation)

CORRELATION = {
    "campaign_id": "11111111-1111-4111-8111-111111111111",
    "run_id": "22222222-2222-4222-8222-222222222222",
    "step_id": "33333333-3333-4333-8333-333333333333",
    "attempt_id": "44444444-4444-4444-8444-444444444444",
}
REQUEST_TIME = "2026-08-08T12:00:00Z"


def request() -> dict:
    return {
        "message_type": "runner.cancellation.request",
        "protocol_version": "2.0.0",
        "correlation": CORRELATION,
        "emitted_at": REQUEST_TIME,
        "reason": "policy",
        "requested_by": "gateway",
    }


def ack(status: str = "accepted", *, emitted_at: str = "2026-08-08T12:00:05Z") -> dict:
    message = {
        "message_type": "runner.cancellation.ack",
        "protocol_version": "2.0.0",
        "correlation": CORRELATION,
        "emitted_at": emitted_at,
        "status": status,
    }
    if status == "refused":
        message["error"] = {
            "code": "AUTHORIZATION_DENIED",
            "category": "authorization",
            "retryable": False,
            "message": "cancellation refused",
        }
    return message


def outcome(
    status: str = "CANCELLED",
    *,
    emitted_at: str = "2026-08-08T12:00:20Z",
    started_at: str = "2026-08-08T11:59:00Z",
    finished_at: str = "2026-08-08T12:00:15Z",
) -> dict:
    message = {
        "message_type": "runner.outcome",
        "protocol_version": "2.0.0",
        "correlation": CORRELATION,
        "emitted_at": emitted_at,
        "status": status,
        "started_at": started_at,
        "finished_at": finished_at,
        "evidence_refs": [
            {
                "evidence_id": "55555555-5555-4555-8555-555555555555",
                "kind": "protocol",
                "classification": "INTERNAL",
                "sha256": "a" * 64,
            }
        ],
    }
    if status == "ERROR":
        message["error"] = {
            "code": "EXECUTION_FAILED",
            "category": "execution",
            "retryable": False,
            "message": "terminal execution error",
        }
    return message


def observe(
    *,
    acks=None,
    outcomes=None,
    observed_at: str = "2026-08-08T12:00:10Z",
    ack_deadline: int = 30,
    terminal_deadline: int = 300,
) -> dict:
    return observation.observe_cancellation(
        cancellation_request=request(),
        acknowledgements=acks,
        outcomes=outcomes,
        observed_at=observed_at,
        acknowledgement_deadline_seconds=ack_deadline,
        terminal_deadline_seconds=terminal_deadline,
    )


def test_waiting_ack_and_ack_timeout_are_not_delivery_proof() -> None:
    waiting = observe(observed_at="2026-08-08T12:00:10Z")
    timed_out = observe(observed_at="2026-08-08T12:00:31Z")

    assert waiting["state"] == "WAITING_ACK"
    assert timed_out["state"] == "ACK_TIMEOUT"
    for result in (waiting, timed_out):
        assert result["ack_observed"] is False
        assert result["cancellation_result"] == "UNPROVEN"
        assert result["transport_authenticity"] == "NOT_VERIFIED"
        assert result["dispatch_performed_by_observer"] is False
        assert result["authorization_effect"] == "NONE"
        assert result["execution_authority"] == "NONE"


def test_accepted_ack_waits_for_terminal_then_times_out_without_overclaim() -> None:
    waiting = observe(acks=[ack()], observed_at="2026-08-08T12:00:20Z")
    timed_out = observe(
        acks=[ack()],
        observed_at="2026-08-08T12:05:01Z",
        terminal_deadline=300,
    )
    assert waiting["state"] == "WAITING_TERMINAL"
    assert timed_out["state"] == "TERMINAL_TIMEOUT"
    assert waiting["ack_observed"] is True
    assert timed_out["cancellation_result"] == "UNPROVEN"


def test_accepted_ack_plus_cancelled_outcome_is_declared_not_authenticated_proof() -> None:
    result = observe(
        acks=[ack()],
        outcomes=[outcome()],
        observed_at="2026-08-08T12:00:30Z",
    )
    assert result["state"] == "CANCELLED_DECLARED"
    assert result["cancellation_result"] == "CANCELLED_DECLARED"
    assert result["ack_status"] == "accepted"
    assert result["outcome_status"] == "CANCELLED"
    assert result["transport_authenticity"] == "NOT_VERIFIED"
    assert result["terminal_outcome_authenticity"] == "NOT_VERIFIED"
    assert "OBSERVER_DOES_NOT_PROVE_PROCESS_TERMINATION" in result["limitations"]


def test_non_cancelled_terminal_outcome_never_becomes_cancelled() -> None:
    result = observe(
        acks=[ack()],
        outcomes=[outcome("PASS")],
        observed_at="2026-08-08T12:00:30Z",
    )
    assert result["state"] == "TERMINAL_NON_CANCELLED_DECLARED"
    assert result["cancellation_result"] == "NON_CANCELLED_TERMINAL_DECLARED"


def test_already_terminal_ack_requires_outcome_to_classify_terminal_state() -> None:
    waiting = observe(
        acks=[ack("already_terminal")],
        observed_at="2026-08-08T12:00:20Z",
    )
    cancelled = observe(
        acks=[ack("already_terminal")],
        outcomes=[
            outcome(
                "CANCELLED",
                emitted_at="2026-08-08T11:59:55Z",
                finished_at="2026-08-08T11:59:50Z",
            )
        ],
        observed_at="2026-08-08T12:00:20Z",
    )
    noncancelled = observe(
        acks=[ack("already_terminal")],
        outcomes=[
            outcome(
                "PASS",
                emitted_at="2026-08-08T11:59:55Z",
                finished_at="2026-08-08T11:59:50Z",
            )
        ],
        observed_at="2026-08-08T12:00:20Z",
    )
    assert waiting["state"] == "WAITING_TERMINAL"
    assert cancelled["state"] == "ALREADY_TERMINAL_CANCELLED_DECLARED"
    assert noncancelled["state"] == "ALREADY_TERMINAL_NON_CANCELLED_DECLARED"


def test_terminal_outcome_without_ack_is_explicitly_missing_delivery_ack() -> None:
    cancelled = observe(
        outcomes=[outcome()], observed_at="2026-08-08T12:00:30Z"
    )
    noncancelled = observe(
        outcomes=[outcome("ERROR")], observed_at="2026-08-08T12:00:30Z"
    )
    assert cancelled["state"] == "CANCELLED_DECLARED_WITHOUT_ACK"
    assert cancelled["ack_observed"] is False
    assert noncancelled["state"] == "TERMINAL_NON_CANCELLED_DECLARED_WITHOUT_ACK"


@pytest.mark.parametrize(
    ("status", "expected"),
    [("not_found", "NOT_FOUND_DECLARED"), ("refused", "REFUSED_DECLARED")],
)
def test_negative_ack_is_not_cancellation_success(status: str, expected: str) -> None:
    result = observe(acks=[ack(status)], observed_at="2026-08-08T12:00:20Z")
    assert result["state"] == expected
    assert result["cancellation_result"] == "UNPROVEN"


def test_negative_ack_with_outcome_is_conflicting_evidence() -> None:
    with pytest.raises(
        observation.CancellationObservationError,
        match="CANCELLATION_NEGATIVE_ACK_WITH_OUTCOME_CONFLICT",
    ):
        observe(
            acks=[ack("not_found")],
            outcomes=[outcome()],
            observed_at="2026-08-08T12:00:30Z",
        )


def test_exact_duplicate_messages_are_idempotent() -> None:
    a = ack()
    o = outcome()
    once = observe(acks=[a], outcomes=[o], observed_at="2026-08-08T12:00:30Z")
    duplicate = observe(
        acks=[a, deepcopy(a)],
        outcomes=[o, deepcopy(o)],
        observed_at="2026-08-08T12:00:30Z",
    )
    assert duplicate == once


def test_conflicting_duplicate_ack_or_outcome_fails_closed() -> None:
    with pytest.raises(
        observation.CancellationObservationError, match="CANCELLATION_ACK_CONFLICT"
    ):
        observe(
            acks=[ack(), ack("already_terminal")],
            observed_at="2026-08-08T12:00:20Z",
        )

    altered = outcome()
    altered["emitted_at"] = "2026-08-08T12:00:21Z"
    with pytest.raises(
        observation.CancellationObservationError,
        match="CANCELLATION_OUTCOME_CONFLICT",
    ):
        observe(
            outcomes=[outcome(), altered],
            observed_at="2026-08-08T12:00:30Z",
        )


def test_correlation_mismatch_fails_closed() -> None:
    bad_ack = ack()
    bad_ack["correlation"] = {**CORRELATION, "attempt_id": "66666666-6666-4666-8666-666666666666"}
    with pytest.raises(
        observation.CancellationObservationError,
        match="CANCELLATION_ACK_CORRELATION_MISMATCH",
    ):
        observe(acks=[bad_ack], observed_at="2026-08-08T12:00:20Z")


def test_ack_or_outcome_from_future_fails_closed() -> None:
    with pytest.raises(
        observation.CancellationObservationError, match="CANCELLATION_ACK_FROM_FUTURE"
    ):
        observe(
            acks=[ack(emitted_at="2026-08-08T12:00:40Z")],
            observed_at="2026-08-08T12:00:20Z",
        )

    with pytest.raises(
        observation.CancellationObservationError,
        match="CANCELLATION_OUTCOME_FROM_FUTURE",
    ):
        observe(
            outcomes=[outcome(emitted_at="2026-08-08T12:00:40Z")],
            observed_at="2026-08-08T12:00:20Z",
        )


def test_accepted_ack_cannot_pair_with_pre_request_terminal_outcome() -> None:
    pre_request = outcome(
        "PASS",
        emitted_at="2026-08-08T12:00:06Z",
        finished_at="2026-08-08T11:59:50Z",
    )
    with pytest.raises(
        observation.CancellationObservationError,
        match="CANCELLATION_ACCEPTED_BUT_OUTCOME_PRECEDES_REQUEST",
    ):
        observe(
            acks=[ack()],
            outcomes=[pre_request],
            observed_at="2026-08-08T12:00:20Z",
        )


def test_output_is_content_addressed_and_schema_valid() -> None:
    result = observe(
        acks=[ack()], outcomes=[outcome()], observed_at="2026-08-08T12:00:30Z"
    )
    schema = json.loads(
        (GATEWAY / "cancellation-observation.schema.json").read_text(encoding="utf-8")
    )
    jsonschema.validate(result, schema, format_checker=jsonschema.FormatChecker())
    repeated = observe(
        acks=[ack()], outcomes=[outcome()], observed_at="2026-08-08T12:00:30Z"
    )
    assert result["observation_id"] == repeated["observation_id"]
    assert result["observation_id"].startswith("cobs_")
