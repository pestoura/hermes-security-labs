from __future__ import annotations

import ast
import copy
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

API_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = API_ROOT.parents[2]
PROTOCOL_ROOT = REPO_ROOT / "platform" / "runner-protocol"
SDK_SRC = PROTOCOL_ROOT / "src"
API_SRC = API_ROOT / "src"
for source in (SDK_SRC, API_SRC):
    if str(source) not in sys.path:
        sys.path.insert(0, str(source))

from api_pentest_runbooks.supervised_runner_protocol_adapter import (  # noqa: E402
    WORKER,
    SupervisedSyntheticApiRunnerCandidate,
)
from runner_protocol_v2 import SQLiteIdempotencyLedger, validate_semantics  # noqa: E402

ADAPTER = (
    API_SRC / "api_pentest_runbooks" / "supervised_runner_protocol_adapter.py"
)
CORRELATION = {
    "campaign_id": "11111111-1111-4111-8111-111111111111",
    "run_id": "22222222-2222-4222-8222-222222222222",
    "step_id": "33333333-3333-4333-8333-333333333333",
    "attempt_id": "44444444-4444-4444-8444-444444444444",
}


def _request(
    capability: str,
    *,
    key: str,
    attempt_id: str = CORRELATION["attempt_id"],
    authorization_ref: str = "authz/conformance/active",
    input_data: dict[str, Any] | None = None,
    soft_timeout_ms: int = 100,
    hard_timeout_ms: int = 2_000,
    grace_period_ms: int = 75,
) -> dict[str, Any]:
    correlation = dict(CORRELATION)
    correlation["attempt_id"] = attempt_id
    request = {
        "message_type": "runner.step.request",
        "protocol_version": "2.0.0",
        "correlation": correlation,
        "emitted_at": "2026-08-06T10:45:00Z",
        "authorization_ref": authorization_ref,
        "idempotency_key": key,
        "operation": {
            "capability_id": capability,
            "input": input_data or {"target_ref": "lab://conformance"},
        },
        "timeout_budget": {
            "soft_timeout_ms": soft_timeout_ms,
            "hard_timeout_ms": hard_timeout_ms,
        },
        "retry_policy": {
            "max_attempts": 2,
            "retryable_error_codes": [
                "TRANSIENT_DEPENDENCY",
                "RUNNER_UNAVAILABLE",
            ],
        },
        "cancellation_policy": {
            "mode": "cooperative_then_force",
            "grace_period_ms": grace_period_ms,
        },
        "progress_mode": "optional",
    }
    validate_semantics(request)
    return request


def _cancellation(correlation: dict[str, str]) -> dict[str, Any]:
    request = {
        "message_type": "runner.cancellation.request",
        "protocol_version": "2.0.0",
        "correlation": correlation,
        "emitted_at": "2026-08-06T10:45:01Z",
        "reason": "operator",
        "requested_by": "control_plane",
    }
    validate_semantics(request)
    return request


def _candidate(database: Path) -> SupervisedSyntheticApiRunnerCandidate:
    return SupervisedSyntheticApiRunnerCandidate(
        durable_ledger=SQLiteIdempotencyLedger(database),
        working_directory=database.parent,
    )


def _outcome(response: dict[str, Any]) -> dict[str, Any]:
    messages = response.get("messages")
    assert isinstance(messages, list), response
    terminal = next(
        message
        for message in messages
        if isinstance(message, dict)
        and message.get("message_type") == "runner.outcome"
    )
    validate_semantics(terminal)
    return terminal


def _supervision(outcome: dict[str, Any]) -> dict[str, Any]:
    output = outcome.get("output")
    assert isinstance(output, dict)
    supervision = output.get("supervision")
    assert isinstance(supervision, dict)
    return supervision


def test_fixed_worker_success_is_durable_and_replays_without_second_process(
    tmp_path: Path,
) -> None:
    database = tmp_path / "success.sqlite3"
    request = _request(
        "conformance.process.success",
        key="api-supervised:success:0001",
        input_data={
            "target_ref": "lab://conformance",
            "argv": ["/bin/sh", "-c", "echo caller-controlled"],
            "cwd": "/",
            "environment": {"PATH": "/tmp"},
        },
    )

    first = _candidate(database)
    first_outcome = _outcome(first.dispatch(request))
    first_supervision = _supervision(first_outcome)
    assert first_outcome["status"] == "PASS"
    assert first_supervision["status"] == "EXITED"
    assert first_supervision["returncode"] == 0
    assert first_supervision["stdout_sha256"] == hashlib.sha256(
        b"synthetic-supervised-success\n"
    ).hexdigest()
    assert first.effect_count == 1
    serialized = json.dumps(first_outcome, sort_keys=True)
    assert "synthetic-supervised-success" not in serialized
    assert "caller-controlled" not in serialized

    retry = copy.deepcopy(request)
    retry["correlation"]["attempt_id"] = "55555555-5555-4555-8555-555555555555"
    retry["emitted_at"] = "2026-08-06T10:45:02Z"
    restarted = _candidate(database)
    replay = _outcome(restarted.dispatch(retry))
    assert replay["status"] == "PASS"
    assert replay["correlation"] == retry["correlation"]
    assert replay["output"] == first_outcome["output"]
    assert restarted.effect_count == 0


def test_fixed_worker_nonzero_exit_is_normalized_without_raw_stderr(
    tmp_path: Path,
) -> None:
    candidate = _candidate(tmp_path / "failure.sqlite3")
    outcome = _outcome(
        candidate.dispatch(
            _request(
                "conformance.process.execution-fail",
                key="api-supervised:failure:0001",
            )
        )
    )

    assert outcome["status"] == "ERROR"
    assert outcome["error"]["code"] == "EXECUTION_FAILED"
    assert outcome["error"]["retryable"] is False
    supervision = _supervision(outcome)
    assert supervision["status"] == "EXITED"
    assert supervision["returncode"] == 7
    assert supervision["stderr_bytes"] > 0
    assert "synthetic-supervised-failure" not in json.dumps(outcome, sort_keys=True)


@pytest.mark.skipif(os.name != "posix", reason="POSIX process groups required")
def test_hard_timeout_is_enforced_and_internal_readiness_file_is_removed(
    tmp_path: Path,
) -> None:
    candidate = _candidate(tmp_path / "timeout.sqlite3")
    request = _request(
        "conformance.process.timeout",
        key="api-supervised:timeout:0001",
        hard_timeout_ms=300,
        grace_period_ms=50,
    )
    outcome = _outcome(candidate.dispatch(request))

    assert outcome["status"] == "TIMED_OUT"
    assert outcome["error"]["code"] == "TIMEOUT_HARD"
    supervision = _supervision(outcome)
    assert supervision["status"] == "TIMED_OUT"
    assert supervision["force_killed"] is True
    assert supervision["cleanup_failed"] is False
    assert candidate.stats()["stats"]["active_processes"] == 0
    assert not list(tmp_path.glob(".supervised-ready-*.pid"))


@pytest.mark.skipif(os.name != "posix", reason="POSIX process groups required")
def test_async_cancellation_kills_process_persists_outcome_and_replays(
    tmp_path: Path,
) -> None:
    database = tmp_path / "cancel.sqlite3"
    request = _request(
        "conformance.process.cancel",
        key="api-supervised:cancel:0001",
        hard_timeout_ms=3_000,
        grace_period_ms=75,
    )
    candidate = _candidate(database)

    progress_response = candidate.dispatch(request)
    assert progress_response["messages"][0]["message_type"] == "runner.progress"
    assert candidate.stats()["stats"]["active_processes"] == 1

    response = candidate.cancel(_cancellation(request["correlation"]))
    assert [message["message_type"] for message in response["messages"]] == [
        "runner.cancellation.ack",
        "runner.outcome",
    ]
    assert response["messages"][0]["status"] == "accepted"
    outcome = _outcome(response)
    assert outcome["status"] == "CANCELLED"
    supervision = _supervision(outcome)
    assert supervision["status"] == "CANCELLED"
    assert supervision["force_killed"] is True
    assert supervision["cleanup_failed"] is False
    assert candidate.stats()["stats"]["active_processes"] == 0
    assert not list(tmp_path.glob(".supervised-ready-*.pid"))

    retry = copy.deepcopy(request)
    retry["correlation"]["attempt_id"] = "66666666-6666-4666-8666-666666666666"
    retry["emitted_at"] = "2026-08-06T10:45:03Z"
    restarted = _candidate(database)
    replay = _outcome(restarted.dispatch(retry))
    assert replay["status"] == "CANCELLED"
    assert replay["correlation"] == retry["correlation"]
    assert restarted.effect_count == 0


@pytest.mark.skipif(os.name != "posix", reason="POSIX process groups required")
def test_descendant_residue_is_cleaned_and_never_classified_as_pass(
    tmp_path: Path,
) -> None:
    candidate = _candidate(tmp_path / "residue.sqlite3")
    outcome = _outcome(
        candidate.dispatch(
            _request(
                "conformance.process.residue",
                key="api-supervised:residue:0001",
            )
        )
    )

    assert outcome["status"] == "INCONCLUSIVE"
    assert outcome["error"]["code"] == "INTERNAL_ERROR"
    supervision = _supervision(outcome)
    assert supervision["status"] == "RESIDUE_CLEANED"
    assert supervision["residue_cleaned"] is True
    assert supervision["cleanup_failed"] is False
    assert not list(tmp_path.glob(".supervised-residue-*.pid"))


def test_real_capability_and_customer_authorization_are_refused_before_claim(
    tmp_path: Path,
) -> None:
    database = tmp_path / "refused.sqlite3"
    candidate = _candidate(database)

    real_capability = _request(
        "api.http.get",
        key="api-supervised:real-cap:0001",
    )
    capability_outcome = _outcome(candidate.dispatch(real_capability))
    assert capability_outcome["status"] == "REFUSED"
    assert capability_outcome["error"]["code"] == "UNSUPPORTED_CAPABILITY"

    customer_authorization = _request(
        "conformance.process.success",
        key="api-supervised:real-authz:0001",
        authorization_ref="authz/customer/real",
    )
    authorization_outcome = _outcome(candidate.dispatch(customer_authorization))
    assert authorization_outcome["status"] == "REFUSED"
    assert authorization_outcome["error"]["code"] == "AUTHORIZATION_DENIED"

    assert candidate.effect_count == 0
    assert candidate.durable_ledger is not None
    assert candidate.durable_ledger.get(real_capability["idempotency_key"]) is None
    assert candidate.durable_ledger.get(customer_authorization["idempotency_key"]) is None


def test_invalid_supervision_budget_is_refused_before_durable_claim(
    tmp_path: Path,
) -> None:
    database = tmp_path / "invalid.sqlite3"
    candidate = _candidate(database)
    request = _request(
        "conformance.process.success",
        key="api-supervised:invalid-budget:0001",
        soft_timeout_ms=300_000,
        hard_timeout_ms=300_001,
        grace_period_ms=100,
    )
    outcome = _outcome(candidate.dispatch(request))

    assert outcome["status"] == "REFUSED"
    assert outcome["error"]["code"] == "INVALID_REQUEST"
    assert candidate.effect_count == 0
    assert candidate.durable_ledger is not None
    assert candidate.durable_ledger.get(request["idempotency_key"]) is None


def test_shutdown_cancels_active_synthetic_process_before_acknowledging(
    tmp_path: Path,
) -> None:
    candidate = _candidate(tmp_path / "shutdown.sqlite3")
    request = _request(
        "conformance.process.cancel",
        key="api-supervised:shutdown:0001",
        hard_timeout_ms=3_000,
        grace_period_ms=75,
    )
    candidate.dispatch(request)

    assert candidate.shutdown() == {"status": "shutdown"}
    assert candidate.stats()["stats"]["active_processes"] == 0
    assert not list(tmp_path.glob(".supervised-ready-*.pid"))


def test_cli_requires_all_synthetic_only_activation_flags(tmp_path: Path) -> None:
    database = tmp_path / "cli.sqlite3"
    missing_mode = subprocess.run(
        [
            sys.executable,
            str(ADAPTER),
            "--conformance-only",
            "--durable-ledger",
            str(database),
        ],
        text=True,
        capture_output=True,
        check=False,
    )
    assert missing_mode.returncode == 2
    assert "--synthetic-process-only" in missing_mode.stderr

    relative = subprocess.run(
        [
            sys.executable,
            str(ADAPTER),
            "--conformance-only",
            "--synthetic-process-only",
            "--durable-ledger",
            "relative.sqlite3",
        ],
        text=True,
        capture_output=True,
        check=False,
    )
    assert relative.returncode == 2
    assert "absolute path" in relative.stderr


def test_adapter_source_is_fixed_worker_only_and_disconnected_from_legacy() -> None:
    source = ADAPTER.read_text(encoding="utf-8")
    tree = ast.parse(source)
    imported_roots: set[str] = set()
    referenced_names: set[str] = set()

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported_roots.update(alias.name.split(".", 1)[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported_roots.add(node.module.split(".", 1)[0])
        elif isinstance(node, ast.Name):
            referenced_names.add(node.id)
        elif isinstance(node, ast.Attribute):
            referenced_names.add(node.attr)

    assert imported_roots.isdisjoint({"subprocess", "socket", "urllib", "requests"})
    assert referenced_names.isdisjoint(
        {"ProcessBridgeAdapter", "execute_runbook", "execute_command"}
    )
    assert "operation\"][\"input\"]" not in source
    assert WORKER == (
        API_SRC / "api_pentest_runbooks" / "synthetic_supervised_worker.py"
    ).resolve()
