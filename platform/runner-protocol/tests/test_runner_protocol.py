from __future__ import annotations

import copy
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SDK_SRC = ROOT / "src"
if str(SDK_SRC) not in sys.path:
    sys.path.insert(0, str(SDK_SRC))

from runner_protocol_v2 import (  # noqa: E402
    ProtocolValidationError,
    classify_idempotency,
    load_schema,
    request_fingerprint,
    validate_compatibility_matrix,
    validate_progress_sequence,
    validate_semantics,
)

CORRELATION = {
    "campaign_id": "11111111-1111-4111-8111-111111111111",
    "run_id": "22222222-2222-4222-8222-222222222222",
    "step_id": "33333333-3333-4333-8333-333333333333",
    "attempt_id": "44444444-4444-4444-8444-444444444444",
}
EVIDENCE = {
    "evidence_id": "55555555-5555-4555-8555-555555555555",
    "kind": "protocol",
    "classification": "INTERNAL",
    "sha256": "a" * 64,
    "uri": "evidence://campaign/run/step/attempt/outcome",
}


def valid_request() -> dict:
    return {
        "message_type": "runner.step.request",
        "protocol_version": "2.0.0",
        "correlation": copy.deepcopy(CORRELATION),
        "emitted_at": "2026-08-06T06:30:00Z",
        "authorization_ref": "authz/campaign/001",
        "idempotency_key": "idem:campaign:step:001",
        "operation": {
            "capability_id": "api.http.get",
            "input": {
                "target_ref": "lab://juice-shop",
                "secret_ref": "vault://runner/demo-credential",
            },
        },
        "timeout_budget": {
            "soft_timeout_ms": 1000,
            "hard_timeout_ms": 5000,
        },
        "retry_policy": {
            "max_attempts": 3,
            "retryable_error_codes": [
                "TRANSIENT_DEPENDENCY",
                "RUNNER_UNAVAILABLE",
            ],
        },
        "cancellation_policy": {
            "mode": "cooperative_then_force",
            "grace_period_ms": 500,
        },
        "progress_mode": "optional",
    }


def valid_outcome(status: str = "PASS") -> dict:
    outcome = {
        "message_type": "runner.outcome",
        "protocol_version": "2.0.0",
        "correlation": copy.deepcopy(CORRELATION),
        "emitted_at": "2026-08-06T06:30:03Z",
        "status": status,
        "started_at": "2026-08-06T06:30:01Z",
        "finished_at": "2026-08-06T06:30:03Z",
        "evidence_refs": [copy.deepcopy(EVIDENCE)],
        "output": {"summary": "sanitized"},
    }
    if status == "TIMED_OUT":
        outcome["error"] = {
            "code": "TIMEOUT_HARD",
            "category": "timeout",
            "retryable": False,
            "message": "Hard timeout budget expired",
        }
    elif status == "REFUSED":
        outcome["error"] = {
            "code": "AUTHORIZATION_DENIED",
            "category": "authorization",
            "retryable": False,
            "message": "Active authorization did not cover the request",
        }
    elif status == "ERROR":
        outcome["error"] = {
            "code": "TRANSIENT_DEPENDENCY",
            "category": "dependency",
            "retryable": True,
            "message": "Dependency temporarily unavailable",
        }
    return outcome


def valid_progress(sequence: int, percent: int) -> dict:
    return {
        "message_type": "runner.progress",
        "protocol_version": "2.0.0",
        "correlation": copy.deepcopy(CORRELATION),
        "emitted_at": f"2026-08-06T06:30:0{sequence}Z",
        "sequence": sequence,
        "state": "running",
        "percent": percent,
        "message": "Sanitized progress",
    }


def test_schema_bundle_is_valid() -> None:
    schema = load_schema()
    assert schema["title"] == "Security Validation Platform Runner Protocol v2"
    assert set(schema["$defs"]) >= {
        "step_request",
        "progress_event",
        "cancellation_request",
        "cancellation_ack",
        "outcome",
        "normalized_error",
    }


def test_valid_step_and_terminal_outcomes() -> None:
    validate_semantics(valid_request())
    for status in ("PASS", "TIMED_OUT", "REFUSED", "ERROR"):
        validate_semantics(valid_outcome(status))


def test_all_messages_require_four_correlation_ids() -> None:
    request = valid_request()
    del request["correlation"]["attempt_id"]
    with pytest.raises(ProtocolValidationError, match="attempt_id"):
        validate_semantics(request)


def test_unknown_protocol_version_fails_closed() -> None:
    request = valid_request()
    request["protocol_version"] = "3.0.0"
    with pytest.raises(ProtocolValidationError):
        validate_semantics(request)


def test_terminal_outcome_requires_evidence() -> None:
    outcome = valid_outcome()
    outcome["evidence_refs"] = []
    with pytest.raises(ProtocolValidationError):
        validate_semantics(outcome)


def test_pass_cannot_carry_error() -> None:
    outcome = valid_outcome()
    outcome["error"] = {
        "code": "EXECUTION_FAILED",
        "category": "execution",
        "retryable": False,
        "message": "Execution failed",
    }
    with pytest.raises(ProtocolValidationError):
        validate_semantics(outcome)


def test_timeout_budget_is_ordered() -> None:
    request = valid_request()
    request["timeout_budget"] = {
        "soft_timeout_ms": 5000,
        "hard_timeout_ms": 1000,
    }
    with pytest.raises(ProtocolValidationError, match="hard_timeout_ms"):
        validate_semantics(request)


def test_cancellation_grace_fits_hard_budget() -> None:
    request = valid_request()
    request["cancellation_policy"]["grace_period_ms"] = 6000
    with pytest.raises(ProtocolValidationError, match="grace_period_ms"):
        validate_semantics(request)


def test_raw_secret_fields_are_rejected_but_references_are_allowed() -> None:
    validate_semantics(valid_request())
    request = valid_request()
    request["operation"]["input"]["password"] = "not-allowed"
    with pytest.raises(ProtocolValidationError, match="raw secret field"):
        validate_semantics(request)


def test_error_retryability_matches_stable_taxonomy() -> None:
    outcome = valid_outcome("ERROR")
    outcome["error"]["retryable"] = False
    with pytest.raises(ProtocolValidationError, match="stable taxonomy"):
        validate_semantics(outcome)


def test_timed_out_outcome_uses_hard_timeout_code() -> None:
    outcome = valid_outcome("TIMED_OUT")
    outcome["error"]["code"] = "TIMEOUT_SOFT"
    outcome["error"]["retryable"] = True
    with pytest.raises(ProtocolValidationError, match="TIMEOUT_HARD"):
        validate_semantics(outcome)


def test_outcome_time_order_is_validated() -> None:
    outcome = valid_outcome()
    outcome["finished_at"] = "2026-08-06T06:29:59Z"
    with pytest.raises(ProtocolValidationError, match="finished_at"):
        validate_semantics(outcome)


def test_same_logical_retry_has_same_fingerprint() -> None:
    first = valid_request()
    retry = copy.deepcopy(first)
    retry["correlation"]["attempt_id"] = "66666666-6666-4666-8666-666666666666"
    retry["emitted_at"] = "2026-08-06T06:31:00Z"

    first_fingerprint = request_fingerprint(first)
    assert request_fingerprint(retry) == first_fingerprint
    assert classify_idempotency(first_fingerprint, retry) == "REPLAY_SAME"


def test_changed_effect_with_same_key_is_conflict() -> None:
    first = valid_request()
    changed = copy.deepcopy(first)
    changed["operation"]["input"]["target_ref"] = "lab://different-target"

    assert classify_idempotency(None, first) == "NEW"
    assert (
        classify_idempotency(request_fingerprint(first), changed)
        == "IDEMPOTENCY_CONFLICT"
    )


def test_progress_sequence_and_percent_are_monotonic() -> None:
    validate_progress_sequence(
        [valid_progress(1, 5), valid_progress(2, 50), valid_progress(3, 100)]
    )

    with pytest.raises(ProtocolValidationError, match="sequence"):
        validate_progress_sequence([valid_progress(2, 20), valid_progress(1, 30)])

    with pytest.raises(ProtocolValidationError, match="percent"):
        validate_progress_sequence([valid_progress(1, 80), valid_progress(2, 70)])


def test_cancellation_messages_are_typed() -> None:
    request = {
        "message_type": "runner.cancellation.request",
        "protocol_version": "2.0.0",
        "correlation": copy.deepcopy(CORRELATION),
        "emitted_at": "2026-08-06T06:30:02Z",
        "reason": "operator",
        "requested_by": "control_plane",
    }
    acknowledgement = {
        "message_type": "runner.cancellation.ack",
        "protocol_version": "2.0.0",
        "correlation": copy.deepcopy(CORRELATION),
        "emitted_at": "2026-08-06T06:30:03Z",
        "status": "accepted",
    }
    validate_semantics(request)
    validate_semantics(acknowledgement)


def test_compatibility_matrix_accepts_scoped_api_and_devsecops_candidates() -> None:
    validate_compatibility_matrix()
