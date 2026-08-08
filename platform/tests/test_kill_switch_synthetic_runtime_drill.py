from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

from runner_protocol_v2 import SQLiteIdempotencyLedger, validate_semantics


ROOT = Path(__file__).resolve().parents[2]
GATEWAY = ROOT / "platform/gateway-protocol"
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


api_adapter = load_module("svp2_a02_api_supervised_adapter", API_ADAPTER)
cancellation = load_module(
    "svp2_a02_kill_switch_cancellation",
    GATEWAY / "kill_switch_cancellation.py",
)
observation = load_module(
    "svp2_a02_cancellation_observation",
    GATEWAY / "cancellation_observation.py",
)

CORRELATION = {
    "campaign_id": "11111111-1111-4111-8111-111111111111",
    "run_id": "22222222-2222-4222-8222-222222222222",
    "step_id": "33333333-3333-4333-8333-333333333333",
    "attempt_id": "77777777-7777-4777-8777-777777777777",
}


def synthetic_step_request() -> dict:
    message = {
        "message_type": "runner.step.request",
        "protocol_version": "2.0.0",
        "correlation": CORRELATION,
        "emitted_at": "2026-08-06T10:44:59Z",
        "authorization_ref": "authz/conformance/active",
        "idempotency_key": "svp2-a02-kill-switch-runtime-drill-001",
        "operation": {
            "capability_id": "conformance.process.cancel",
            "input": {"synthetic_case": "svp2-a02-kill-switch-drill"},
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


def write_engaged_switch(path: Path) -> Path:
    path.write_text(
        json.dumps(
            {
                "schema_version": "1.0.0",
                "state": "engaged",
                "scope": "global",
                "reason_code": "svp2-a02-synthetic-drill",
                "updated_at": "2026-08-06T10:45:00Z",
            }
        ),
        encoding="utf-8",
    )
    return path


def test_kill_switch_reaches_running_synthetic_process_and_observes_cancelled(
    tmp_path: Path,
) -> None:
    ledger = SQLiteIdempotencyLedger(tmp_path / "idempotency.sqlite3")
    candidate = api_adapter.SupervisedSyntheticApiRunnerCandidate(
        durable_ledger=ledger,
        working_directory=tmp_path,
    )
    step_request = synthetic_step_request()

    try:
        dispatched = candidate.dispatch(step_request)
        progress = dispatched["messages"]
        assert len(progress) == 1
        assert progress[0]["message_type"] == "runner.progress"
        assert progress[0]["state"] == "accepted"
        assert candidate.stats()["stats"]["active_processes"] == 1

        inventory = cancellation.build_active_attempt_inventory(
            attempts=[
                {
                    "correlation": CORRELATION,
                    "state": "running",
                    "cancellation_mode": "cooperative_then_force",
                    "grace_period_ms": 100,
                }
            ],
            generated_at="2026-08-06T10:45:00Z",
        )
        plan = cancellation.plan_kill_switch_cancellations(
            kill_switch_path=write_engaged_switch(tmp_path / "kill-switch.json"),
            inventory=inventory,
            emitted_at="2026-08-06T10:45:00Z",
        )

        assert plan["decision"] == "CANCEL_REQUIRED"
        assert plan["cancellation_scope"] == "global"
        assert plan["dispatch_performed"] is False
        assert plan["execution_authority"] == "NONE"
        assert len(plan["cancellation_requests"]) == 1
        cancellation_request = plan["cancellation_requests"][0]
        validate_semantics(cancellation_request)

        cancelled = candidate.cancel(cancellation_request)
        messages = cancelled["messages"]
        acknowledgements = [
            message
            for message in messages
            if message["message_type"] == "runner.cancellation.ack"
        ]
        outcomes = [
            message
            for message in messages
            if message["message_type"] == "runner.outcome"
        ]
        assert len(acknowledgements) == 1
        assert acknowledgements[0]["status"] == "accepted"
        assert len(outcomes) == 1
        assert outcomes[0]["status"] == "CANCELLED"

        supervision = outcomes[0]["output"]["supervision"]
        assert supervision["status"] == "CANCELLED"
        assert supervision["force_killed"] is True
        assert supervision["cleanup_failed"] is False
        assert supervision["residue_cleaned"] is False

        observed = observation.observe_cancellation(
            cancellation_request=cancellation_request,
            acknowledgements=acknowledgements,
            outcomes=outcomes,
            observed_at="2026-08-06T10:45:02Z",
            acknowledgement_deadline_seconds=30,
            terminal_deadline_seconds=300,
        )
        assert observed["state"] == "CANCELLED_DECLARED"
        assert observed["cancellation_result"] == "CANCELLED_DECLARED"
        assert observed["transport_authenticity"] == "NOT_VERIFIED"
        assert observed["terminal_outcome_authenticity"] == "NOT_VERIFIED"
        assert observed["dispatch_performed_by_observer"] is False

        stats = candidate.stats()["stats"]
        assert stats["active_processes"] == 0
        assert stats["effect_count"] == 1
        assert stats["ledger_entries"] == 1
    finally:
        assert candidate.shutdown()["status"] == "shutdown"
