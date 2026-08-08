from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest
from runner_protocol_v2 import validate_semantics


ROOT = Path(__file__).resolve().parents[2]
GATEWAY = ROOT / "platform/gateway-protocol"
RUNNER_PROTOCOL = ROOT / "platform/runner-protocol"
API_ADAPTER = (
    ROOT
    / "security/packs/api/src/api_pentest_runbooks/"
    "supervised_runner_protocol_adapter.py"
)


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


conformance = load_module(
    "svp2_a02_fail_closed_conformance",
    RUNNER_PROTOCOL / "conformance.py",
)
cancellation = load_module(
    "svp2_a02_fail_closed_kill_switch_cancellation",
    GATEWAY / "kill_switch_cancellation.py",
)

CORRELATION_A = {
    "campaign_id": "11111111-1111-4111-8111-111111111111",
    "run_id": "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
    "step_id": "33333333-3333-4333-8333-333333333333",
    "attempt_id": "55555555-5555-4555-8555-555555555555",
}
CORRELATION_B = {
    "campaign_id": "22222222-2222-4222-8222-222222222222",
    "run_id": "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb",
    "step_id": "44444444-4444-4444-8444-444444444444",
    "attempt_id": "66666666-6666-4666-8666-666666666666",
}


def step_request(correlation: dict[str, str], key: str) -> dict:
    message = {
        "message_type": "runner.step.request",
        "protocol_version": "2.0.0",
        "correlation": correlation,
        "emitted_at": "2026-08-06T10:44:59Z",
        "authorization_ref": "authz/conformance/active",
        "idempotency_key": key,
        "operation": {
            "capability_id": "conformance.process.cancel",
            "input": {"synthetic_case": "svp2-a02-fail-closed-source-drill"},
        },
        "timeout_budget": {
            "soft_timeout_ms": 100,
            "hard_timeout_ms": 3_000,
        },
        "retry_policy": {
            "max_attempts": 1,
            "retryable_error_codes": ["RUNNER_UNAVAILABLE"],
        },
        "cancellation_policy": {
            "mode": "cooperative_then_force",
            "grace_period_ms": 100,
        },
        "progress_mode": "optional",
    }
    validate_semantics(message)
    return message


def protocol_messages(response: dict) -> list[dict]:
    messages = response.get("messages")
    assert isinstance(messages, list) and messages
    for message in messages:
        assert isinstance(message, dict)
        validate_semantics(message)
    return messages


def assert_cancelled(response: dict, correlation: dict[str, str]) -> None:
    messages = protocol_messages(response)
    acknowledgements = [
        message
        for message in messages
        if message["message_type"] == "runner.cancellation.ack"
    ]
    outcomes = [
        message for message in messages if message["message_type"] == "runner.outcome"
    ]
    assert len(acknowledgements) == 1
    assert acknowledgements[0]["status"] == "accepted"
    assert acknowledgements[0]["correlation"] == correlation
    assert len(outcomes) == 1
    assert outcomes[0]["status"] == "CANCELLED"
    assert outcomes[0]["correlation"] == correlation
    supervision = outcomes[0]["output"]["supervision"]
    assert supervision["status"] == "CANCELLED"
    assert supervision["force_killed"] is True
    assert supervision["cleanup_failed"] is False
    assert supervision["residue_cleaned"] is False


def source_for_case(tmp_path: Path, source_case: str) -> Path | None:
    if source_case == "missing":
        return None
    if source_case == "invalid":
        path = tmp_path / "invalid-kill-switch.json"
        path.write_text("not-json", encoding="utf-8")
        return path
    raise AssertionError(f"unsupported source_case {source_case!r}")


@pytest.mark.parametrize(
    ("source_case", "expected_code"),
    [
        ("missing", "KILL_SWITCH_SOURCE_REQUIRED"),
        ("invalid", "KILL_SWITCH_INVALID"),
    ],
)
def test_untrusted_kill_switch_source_fails_closed_over_active_subprocesses(
    tmp_path: Path,
    source_case: str,
    expected_code: str,
) -> None:
    ledger_path = (tmp_path / f"{source_case}-idempotency.sqlite3").resolve()
    command = [
        sys.executable,
        str(API_ADAPTER),
        "--conformance-only",
        "--synthetic-process-only",
        "--durable-ledger",
        str(ledger_path),
    ]
    request_a = step_request(
        CORRELATION_A,
        f"svp2-a02-fail-closed-{source_case}-campaign-a-001",
    )
    request_b = step_request(
        CORRELATION_B,
        f"svp2-a02-fail-closed-{source_case}-campaign-b-001",
    )

    candidate = conformance.CandidateProcess(
        command=command,
        adapter_id=f"api-supervised-synthetic-a02-fail-closed-{source_case}",
    )
    with candidate:
        progress_a = protocol_messages(
            candidate.exchange({"action": "dispatch", "message": request_a})
        )
        progress_b = protocol_messages(
            candidate.exchange({"action": "dispatch", "message": request_b})
        )
        assert progress_a[0]["state"] == "accepted"
        assert progress_b[0]["state"] == "accepted"

        active = candidate.exchange({"action": "stats"})["stats"]
        assert active["active_processes"] == 2
        assert active["effect_count"] == 0
        assert active["ledger_entries"] == 2

        inventory = cancellation.build_active_attempt_inventory(
            attempts=[
                {
                    "correlation": CORRELATION_A,
                    "state": "running",
                    "cancellation_mode": "cooperative_then_force",
                    "grace_period_ms": 100,
                },
                {
                    "correlation": CORRELATION_B,
                    "state": "running",
                    "cancellation_mode": "cooperative_then_force",
                    "grace_period_ms": 100,
                },
            ],
            generated_at="2026-08-06T10:45:00Z",
        )
        plan = cancellation.plan_kill_switch_cancellations(
            kill_switch_path=source_for_case(tmp_path, source_case),
            inventory=inventory,
            emitted_at="2026-08-06T10:45:00Z",
        )

        assert plan["decision"] == "CANCEL_REQUIRED"
        assert plan["fail_closed"] is True
        assert plan["codes"] == [expected_code]
        assert plan["kill_switch_scope"] is None
        assert plan["unaffected_attempt_refs"] == []
        assert plan["already_cancelling_attempt_refs"] == []
        assert plan["dispatch_performed"] is False
        assert plan["safety_effect"] == "RESTRICT_ONLY"
        assert plan["authorization_effect"] == "NONE"
        assert plan["execution_authority"] == "NONE"
        assert len(plan["cancellation_requests"]) == 2

        requests_by_attempt = {
            item["correlation"]["attempt_id"]: item
            for item in plan["cancellation_requests"]
        }
        assert set(requests_by_attempt) == {
            CORRELATION_A["attempt_id"],
            CORRELATION_B["attempt_id"],
        }

        assert_cancelled(
            candidate.exchange(
                {
                    "action": "cancel",
                    "message": requests_by_attempt[CORRELATION_A["attempt_id"]],
                }
            ),
            CORRELATION_A,
        )
        after_first = candidate.exchange({"action": "stats"})["stats"]
        assert after_first["active_processes"] == 1
        assert after_first["effect_count"] == 1

        assert_cancelled(
            candidate.exchange(
                {
                    "action": "cancel",
                    "message": requests_by_attempt[CORRELATION_B["attempt_id"]],
                }
            ),
            CORRELATION_B,
        )
        final_stats = candidate.exchange({"action": "stats"})["stats"]
        assert final_stats["active_processes"] == 0
        assert final_stats["effect_count"] == 2
        assert final_stats["ledger_entries"] == 2
        assert candidate.process is not None
        assert candidate.process.poll() is None

    assert candidate.process is not None
    assert candidate.process.returncode == 0
    assert candidate.stderr_text == ""
