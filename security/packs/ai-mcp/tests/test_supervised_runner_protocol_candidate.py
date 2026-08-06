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

PACK_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = PACK_ROOT.parents[2]
PROTOCOL_ROOT = REPO_ROOT / "platform" / "runner-protocol"
SDK_SRC = PROTOCOL_ROOT / "src"
PACK_SRC = PACK_ROOT / "src"
for source in (SDK_SRC, PACK_SRC):
    if str(source) not in sys.path:
        sys.path.insert(0, str(source))

from ai_mcp_runbooks.supervised_runner_protocol_adapter import (  # noqa: E402
    WORKER,
    SupervisedSyntheticAiMcpRunnerCandidate,
)
from runner_protocol_v2 import SQLiteIdempotencyLedger, validate_semantics  # noqa: E402

ADAPTER = PACK_SRC / "ai_mcp_runbooks" / "supervised_runner_protocol_adapter.py"
SHARED_ENGINE = SDK_SRC / "runner_protocol_v2" / "synthetic_supervised.py"
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
    message = {
        "message_type": "runner.step.request",
        "protocol_version": "2.0.0",
        "correlation": correlation,
        "emitted_at": "2026-08-06T11:15:00Z",
        "authorization_ref": authorization_ref,
        "idempotency_key": key,
        "operation": {
            "capability_id": capability,
            "input": input_data or {"target_ref": "repository://conformance"},
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
    validate_semantics(message)
    return message


def _cancellation(correlation: dict[str, str]) -> dict[str, Any]:
    message = {
        "message_type": "runner.cancellation.request",
        "protocol_version": "2.0.0",
        "correlation": correlation,
        "emitted_at": "2026-08-06T11:15:01Z",
        "reason": "operator",
        "requested_by": "control_plane",
    }
    validate_semantics(message)
    return message


def _candidate(database: Path) -> SupervisedSyntheticAiMcpRunnerCandidate:
    return SupervisedSyntheticAiMcpRunnerCandidate(
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


def test_success_uses_ai_mcp_worker_and_replays_without_second_process(
    tmp_path: Path,
) -> None:
    database = tmp_path / "success.sqlite3"
    request = _request(
        "conformance.process.success",
        key="ai-mcp-supervised:success:0001",
        input_data={
            "target_ref": "repository://conformance",
            "argv": ["/bin/sh", "-c", "echo caller-controlled"],
            "cwd": "/",
            "environment": {"PATH": "/tmp"},
            "scanner": "real-scanner",
        },
    )

    first = _candidate(database)
    first_outcome = _outcome(first.dispatch(request))
    supervision = _supervision(first_outcome)
    assert first_outcome["status"] == "PASS"
    assert supervision["status"] == "EXITED"
    assert supervision["returncode"] == 0
    assert supervision["stdout_sha256"] == hashlib.sha256(
        b"synthetic-ai-mcp-supervised-success\n"
    ).hexdigest()
    assert first.effect_count == 1
    serialized = json.dumps(first_outcome, sort_keys=True)
    assert "synthetic-ai-mcp-supervised-success" not in serialized
    assert "caller-controlled" not in serialized
    assert "real-scanner" not in serialized
    assert first_outcome["evidence_refs"][0]["uri"].startswith(
        "evidence://ai-mcp-supervised-runner-candidate/"
    )

    retry = copy.deepcopy(request)
    retry["correlation"]["attempt_id"] = "55555555-5555-4555-8555-555555555555"
    retry["emitted_at"] = "2026-08-06T11:15:02Z"
    restarted = _candidate(database)
    replay = _outcome(restarted.dispatch(retry))
    assert replay["status"] == "PASS"
    assert replay["correlation"] == retry["correlation"]
    assert replay["output"] == first_outcome["output"]
    assert restarted.effect_count == 0
    assert restarted.stats()["stats"]["ledger_entries"] == 1


def test_nonzero_worker_exit_is_normalized_without_raw_stderr(tmp_path: Path) -> None:
    candidate = _candidate(tmp_path / "failure.sqlite3")
    outcome = _outcome(
        candidate.dispatch(
            _request(
                "conformance.process.execution-fail",
                key="ai-mcp-supervised:failure:0001",
            )
        )
    )

    assert outcome["status"] == "ERROR"
    assert outcome["error"]["code"] == "EXECUTION_FAILED"
    assert outcome["error"]["retryable"] is False
    supervision = _supervision(outcome)
    assert supervision["returncode"] == 9
    assert supervision["stderr_bytes"] > 0
    assert "synthetic-ai-mcp-supervised-failure" not in json.dumps(
        outcome, sort_keys=True
    )


@pytest.mark.skipif(os.name != "posix", reason="POSIX process groups required")
def test_timeout_and_cancellation_are_bounded_and_cleanup_internal_state(
    tmp_path: Path,
) -> None:
    timeout_candidate = _candidate(tmp_path / "timeout.sqlite3")
    timeout_outcome = _outcome(
        timeout_candidate.dispatch(
            _request(
                "conformance.process.timeout",
                key="ai-mcp-supervised:timeout:0001",
                hard_timeout_ms=300,
                grace_period_ms=50,
            )
        )
    )
    assert timeout_outcome["status"] == "TIMED_OUT"
    assert timeout_outcome["error"]["code"] == "TIMEOUT_HARD"
    timeout_supervision = _supervision(timeout_outcome)
    assert timeout_supervision["force_killed"] is True
    assert timeout_supervision["cleanup_failed"] is False

    cancel_database = tmp_path / "cancel.sqlite3"
    request = _request(
        "conformance.process.cancel",
        key="ai-mcp-supervised:cancel:0001",
        hard_timeout_ms=3_000,
        grace_period_ms=75,
    )
    candidate = _candidate(cancel_database)
    progress = candidate.dispatch(request)
    assert progress["messages"][0]["message_type"] == "runner.progress"
    response = candidate.cancel(_cancellation(request["correlation"]))
    assert [message["message_type"] for message in response["messages"]] == [
        "runner.cancellation.ack",
        "runner.outcome",
    ]
    outcome = _outcome(response)
    assert outcome["status"] == "CANCELLED"
    assert _supervision(outcome)["force_killed"] is True
    assert candidate.stats()["stats"]["active_processes"] == 0
    assert not list(tmp_path.glob(".ai-mcp-ready-*.pid"))

    retry = copy.deepcopy(request)
    retry["correlation"]["attempt_id"] = "66666666-6666-4666-8666-666666666666"
    retry["emitted_at"] = "2026-08-06T11:15:03Z"
    restarted = _candidate(cancel_database)
    replay = _outcome(restarted.dispatch(retry))
    assert replay["status"] == "CANCELLED"
    assert restarted.effect_count == 0


@pytest.mark.skipif(os.name != "posix", reason="POSIX process groups required")
def test_descendant_residue_is_inconclusive_and_removed(tmp_path: Path) -> None:
    candidate = _candidate(tmp_path / "residue.sqlite3")
    outcome = _outcome(
        candidate.dispatch(
            _request(
                "conformance.process.residue",
                key="ai-mcp-supervised:residue:0001",
            )
        )
    )

    assert outcome["status"] == "INCONCLUSIVE"
    assert outcome["error"]["code"] == "INTERNAL_ERROR"
    supervision = _supervision(outcome)
    assert supervision["status"] == "RESIDUE_CLEANED"
    assert supervision["residue_cleaned"] is True
    assert supervision["cleanup_failed"] is False
    assert not list(tmp_path.glob(".ai-mcp-residue-*.pid"))


def test_real_capability_and_authorization_are_refused_before_claim(
    tmp_path: Path,
) -> None:
    database = tmp_path / "refused.sqlite3"
    candidate = _candidate(database)
    real_capability = _request(
        "ai-mcp.agent.execute",
        key="ai-mcp-supervised:real-capability:0001",
    )
    capability_outcome = _outcome(candidate.dispatch(real_capability))
    assert capability_outcome["error"]["code"] == "UNSUPPORTED_CAPABILITY"

    real_authorization = _request(
        "conformance.process.success",
        key="ai-mcp-supervised:real-authorization:0001",
        authorization_ref="authz/customer/real",
    )
    authorization_outcome = _outcome(candidate.dispatch(real_authorization))
    assert authorization_outcome["error"]["code"] == "AUTHORIZATION_DENIED"

    assert candidate.durable_ledger.get(real_capability["idempotency_key"]) is None
    assert candidate.durable_ledger.get(real_authorization["idempotency_key"]) is None
    assert candidate.effect_count == 0


def test_cli_requires_every_synthetic_only_activation_flag(tmp_path: Path) -> None:
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


def test_wrapper_is_pack_isolated_and_shared_engine_owns_lifecycle() -> None:
    wrapper_source = ADAPTER.read_text(encoding="utf-8")
    wrapper_tree = ast.parse(wrapper_source)
    imported_modules: set[str] = set()
    referenced_names: set[str] = set()
    for node in ast.walk(wrapper_tree):
        if isinstance(node, ast.Import):
            imported_modules.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported_modules.add(node.module)
        elif isinstance(node, ast.Name):
            referenced_names.add(node.id)
        elif isinstance(node, ast.Attribute):
            referenced_names.add(node.attr)

    assert all(
        not module.startswith(("api_pentest_runbooks", "devsecops_runbooks"))
        for module in imported_modules
    )
    assert imported_modules.isdisjoint(
        {
            "ai_mcp_runbooks.dispatch",
            "ai_mcp_runbooks.execution",
            "ai_mcp_runbooks.adapters",
        }
    )
    assert referenced_names.isdisjoint(
        {
            "subprocess",
            "ProcessBridgeAdapter",
            "execute_runbook",
            "execute_command",
            "execute_operation",
            "execute_handler",
            "dispatch_operation",
        }
    )
    assert "operation\"][\"input\"]" not in wrapper_source

    shared_source = SHARED_ENGINE.read_text(encoding="utf-8")
    assert "api_pentest_runbooks" not in shared_source
    assert "devsecops_runbooks" not in shared_source
    assert "ai_mcp_runbooks" not in shared_source
    assert WORKER == (
        PACK_SRC / "ai_mcp_runbooks" / "synthetic_supervised_worker.py"
    ).resolve()
