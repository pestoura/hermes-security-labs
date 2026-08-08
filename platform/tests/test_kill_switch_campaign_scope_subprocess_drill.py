from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

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
    "svp2_a02_campaign_conformance",
    RUNNER_PROTOCOL / "conformance.py",
)
cancellation = load_module(
    "svp2_a02_campaign_kill_switch_cancellation",
    GATEWAY / "kill_switch_cancellation.py",
)

CAMPAIGN_A = "11111111-1111-4111-8111-111111111111"
CAMPAIGN_B = "22222222-2222-4222-8222-222222222222"
CORRELATION_A = {
    "campaign_id": CAMPAIGN_A,
    "run_id": "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
    "step_id": "33333333-3333-4333-8333-333333333333",
    "attempt_id": "55555555-5555-4555-8555-555555555555",
}
CORRELATION_B = {
    "campaign_id": CAMPAIGN_B,
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
            "input": {"synthetic_case": "svp2-a02-campaign-scope-drill"},
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


def cancellation_request(correlation: dict[str, str]) -> dict:
    message = {
        "message_type": "runner.cancellation.request",
        "protocol_version": "2.0.0",
        "correlation": correlation,
        "emitted_at": "2026-08-06T10:45:00Z",
        "reason": "operator",
        "requested_by": "control_plane",
    }
    validate_semantics(message)
    return message


def write_campaign_switch(path: Path) -> Path:
    path.write_text(
        json.dumps(
            {
                "schema_version": "1.0.0",
                "state": "engaged",
                "scope": "campaign",
                "campaign_id": CAMPAIGN_A,
                "updated_at": "2026-08-06T10:45:00Z",
            }
        ),
        encoding="utf-8",
    )
    return path


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


def test_campaign_kill_switch_cancels_only_matching_active_subprocess_attempt(
    tmp_path: Path,
) -> None:
    ledger_path = (tmp_path / "idempotency.sqlite3").resolve()
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
        "svp2-a02-campaign-scope-drill-campaign-a-001",
    )
    request_b = step_request(
        CORRELATION_B,
        "svp2-a02-campaign-scope-drill-campaign-b-001",
    )

    candidate = conformance.CandidateProcess(
        command=command,
        adapter_id="api-supervised-synthetic-a02-campaign-scope",
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
            kill_switch_path=write_campaign_switch(tmp_path / "kill-switch.json"),
            inventory=inventory,
            emitted_at="2026-08-06T10:45:00Z",
        )

        assert plan["decision"] == "CANCEL_REQUIRED"
        assert plan["kill_switch_scope"] == "campaign"
        assert plan["kill_switch_campaign_id"] == CAMPAIGN_A
        assert plan["fail_closed"] is False
        assert plan["dispatch_performed"] is False
        assert len(plan["cancellation_requests"]) == 1
        assert len(plan["unaffected_attempt_refs"]) == 1
        planned = plan["cancellation_requests"][0]
        assert planned["correlation"] == CORRELATION_A
        validate_semantics(planned)

        assert_cancelled(
            candidate.exchange({"action": "cancel", "message": planned}),
            CORRELATION_A,
        )

        after_campaign_cancel = candidate.exchange({"action": "stats"})["stats"]
        assert after_campaign_cancel["active_processes"] == 1
        assert after_campaign_cancel["effect_count"] == 1
        assert after_campaign_cancel["ledger_entries"] == 2

        # Campaign B is deliberately still active after the campaign-A kill switch.
        # Terminate it explicitly only to leave no synthetic process behind after the test.
        cleanup_b = cancellation_request(CORRELATION_B)
        assert_cancelled(
            candidate.exchange({"action": "cancel", "message": cleanup_b}),
            CORRELATION_B,
        )

        final_stats = candidate.exchange({"action": "stats"})["stats"]
        assert final_stats["active_processes"] == 0
        assert final_stats["effect_count"] == 2
        assert final_stats["ledger_entries"] == 2

    assert candidate.process is not None
    assert candidate.process.returncode == 0
    assert candidate.stderr_text == ""
