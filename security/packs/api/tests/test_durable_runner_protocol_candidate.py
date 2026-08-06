from __future__ import annotations

import ast
import copy
import subprocess
import sys
from pathlib import Path
from typing import Any

API_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = API_ROOT.parents[2]
PROTOCOL_ROOT = REPO_ROOT / "platform" / "runner-protocol"
SDK_SRC = PROTOCOL_ROOT / "src"
API_SRC = API_ROOT / "src"
for source in (SDK_SRC, API_SRC):
    if str(source) not in sys.path:
        sys.path.insert(0, str(source))

from api_pentest_runbooks.durable_runner_protocol_adapter import (  # noqa: E402
    DurableApiRunnerProtocolCandidate,
)
from runner_protocol_v2 import (  # noqa: E402
    LedgerError,
    SQLiteIdempotencyLedger,
    request_fingerprint,
    validate_semantics,
)

sys.path.insert(0, str(PROTOCOL_ROOT))
from conformance import run_conformance  # noqa: E402

DURABLE_CANDIDATE_PATH = (
    API_SRC / "api_pentest_runbooks" / "durable_runner_protocol_adapter.py"
)
CORRELATION = {
    "campaign_id": "11111111-1111-4111-8111-111111111111",
    "run_id": "22222222-2222-4222-8222-222222222222",
    "step_id": "33333333-3333-4333-8333-333333333333",
    "attempt_id": "44444444-4444-4444-8444-444444444444",
}


def _request(
    capability_id: str,
    *,
    key: str = "api-durable:test:0001",
    attempt_id: str = CORRELATION["attempt_id"],
    target_ref: str = "lab://conformance",
    authorization_ref: str = "authz/conformance/active",
) -> dict[str, Any]:
    correlation = dict(CORRELATION)
    correlation["attempt_id"] = attempt_id
    return {
        "message_type": "runner.step.request",
        "protocol_version": "2.0.0",
        "correlation": correlation,
        "emitted_at": "2026-08-06T09:40:00Z",
        "authorization_ref": authorization_ref,
        "idempotency_key": key,
        "operation": {
            "capability_id": capability_id,
            "input": {"target_ref": target_ref},
        },
        "timeout_budget": {
            "soft_timeout_ms": 1000,
            "hard_timeout_ms": 5000,
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
            "grace_period_ms": 500,
        },
        "progress_mode": "optional",
    }


def _cancellation(correlation: dict[str, str]) -> dict[str, Any]:
    return {
        "message_type": "runner.cancellation.request",
        "protocol_version": "2.0.0",
        "correlation": correlation,
        "emitted_at": "2026-08-06T09:40:01Z",
        "reason": "operator",
        "requested_by": "control_plane",
    }


def _candidate(database: Path) -> DurableApiRunnerProtocolCandidate:
    return DurableApiRunnerProtocolCandidate(
        durable_ledger=SQLiteIdempotencyLedger(database)
    )


def _candidate_command(database: Path) -> list[str]:
    return [
        sys.executable,
        str(DURABLE_CANDIDATE_PATH),
        "--conformance-only",
        "--durable-ledger",
        str(database),
    ]


def _outcome(response: dict[str, Any]) -> dict[str, Any]:
    messages = response["messages"]
    terminal = next(
        message for message in messages if message["message_type"] == "runner.outcome"
    )
    validate_semantics(terminal)
    return terminal


def test_durable_candidate_passes_vendor_neutral_conformance_kit(
    tmp_path: Path,
) -> None:
    report = run_conformance(
        _candidate_command(tmp_path / "conformance.sqlite3"),
        "api-runner-durable-candidate",
    )
    assert report["verdict"] == "PASS", report
    assert {case["status"] for case in report["cases"]} == {"PASS"}


def test_completed_synthetic_effect_replays_after_process_restart(
    tmp_path: Path,
) -> None:
    database = tmp_path / "restart.sqlite3"
    first_request = _request("conformance.effect.replay")
    first = _candidate(database)
    first_outcome = _outcome(first.dispatch(first_request))
    assert first_outcome["status"] == "PASS"
    assert first.effect_count == 1

    retry = copy.deepcopy(first_request)
    retry["correlation"]["attempt_id"] = "55555555-5555-4555-8555-555555555555"
    retry["emitted_at"] = "2026-08-06T09:40:02Z"
    assert request_fingerprint(retry) == request_fingerprint(first_request)

    restarted = _candidate(database)
    replay = _outcome(restarted.dispatch(retry))
    assert replay["status"] == "PASS"
    assert replay["correlation"] == retry["correlation"]
    assert restarted.effect_count == 0
    assert restarted.stats()["stats"]["ledger_entries"] == 1


def test_changed_effect_is_refused_after_restart_without_effect(
    tmp_path: Path,
) -> None:
    database = tmp_path / "conflict.sqlite3"
    original = _request("conformance.effect.conflict")
    _candidate(database).dispatch(original)

    changed = _request(
        "conformance.effect.conflict",
        attempt_id="66666666-6666-4666-8666-666666666666",
        target_ref="lab://changed",
    )
    restarted = _candidate(database)
    outcome = _outcome(restarted.dispatch(changed))
    assert outcome["status"] == "REFUSED"
    assert outcome["error"]["code"] == "IDEMPOTENCY_CONFLICT"
    assert outcome["error"]["retryable"] is False
    assert restarted.effect_count == 0


def test_in_progress_claim_is_not_reclaimed_after_restart(tmp_path: Path) -> None:
    database = tmp_path / "in-progress.sqlite3"
    request = _request("conformance.effect.success")
    ledger = SQLiteIdempotencyLedger(database)
    assert ledger.claim(
        request["idempotency_key"], request_fingerprint(request)
    ).classification == "NEW"

    restarted = _candidate(database)
    outcome = _outcome(restarted.dispatch(request))
    assert outcome["status"] == "REFUSED"
    assert outcome["error"]["code"] == "IDEMPOTENCY_CONFLICT"
    assert "reconciliation" in outcome["error"]["message"]
    assert restarted.effect_count == 0
    assert ledger.get(request["idempotency_key"]).state == "IN_PROGRESS"


def test_same_process_cancellation_is_persisted_and_replayed(
    tmp_path: Path,
) -> None:
    database = tmp_path / "cancel.sqlite3"
    request = _request("conformance.cancel.wait", key="api-durable:cancel:0001")
    candidate = _candidate(database)
    progress = candidate.dispatch(request)["messages"][0]
    assert progress["message_type"] == "runner.progress"

    cancellation = _cancellation(request["correlation"])
    cancelled = _outcome(candidate.cancel(cancellation))
    assert cancelled["status"] == "CANCELLED"

    retry = copy.deepcopy(request)
    retry["correlation"]["attempt_id"] = "77777777-7777-4777-8777-777777777777"
    retry["emitted_at"] = "2026-08-06T09:40:03Z"
    restarted = _candidate(database)
    replay = _outcome(restarted.dispatch(retry))
    assert replay["status"] == "CANCELLED"
    assert replay["correlation"] == retry["correlation"]
    assert restarted.effect_count == 0


def test_real_capability_and_authorization_remain_refused_without_claim(
    tmp_path: Path,
) -> None:
    database = tmp_path / "refusal.sqlite3"
    candidate = _candidate(database)
    real_capability = _request("api.http.get")
    capability_outcome = _outcome(candidate.dispatch(real_capability))
    assert capability_outcome["error"]["code"] == "UNSUPPORTED_CAPABILITY"

    real_authorization = _request(
        "conformance.effect.success",
        key="api-durable:authz:0001",
        authorization_ref="authz/customer/real",
    )
    authorization_outcome = _outcome(candidate.dispatch(real_authorization))
    assert authorization_outcome["error"]["code"] == "AUTHORIZATION_DENIED"
    assert candidate.effect_count == 0
    assert candidate.durable_ledger is not None
    assert candidate.durable_ledger.get(real_capability["idempotency_key"]) is None
    assert candidate.durable_ledger.get(real_authorization["idempotency_key"]) is None


def test_cli_requires_explicit_mode_and_safe_absolute_ledger_path(
    tmp_path: Path,
) -> None:
    no_mode = subprocess.run(
        [
            sys.executable,
            str(DURABLE_CANDIDATE_PATH),
            "--durable-ledger",
            str(tmp_path / "no-mode.sqlite3"),
        ],
        text=True,
        capture_output=True,
        check=False,
    )
    assert no_mode.returncode == 2
    assert "--conformance-only is required" in no_mode.stderr

    no_ledger = subprocess.run(
        [sys.executable, str(DURABLE_CANDIDATE_PATH), "--conformance-only"],
        text=True,
        capture_output=True,
        check=False,
    )
    assert no_ledger.returncode == 2
    assert "--durable-ledger is required" in no_ledger.stderr

    relative = subprocess.run(
        [
            sys.executable,
            str(DURABLE_CANDIDATE_PATH),
            "--conformance-only",
            "--durable-ledger",
            "relative.sqlite3",
        ],
        text=True,
        capture_output=True,
        check=False,
    )
    assert relative.returncode == 2
    assert "must be an absolute path" in relative.stderr

    inside_tree = subprocess.run(
        [
            sys.executable,
            str(DURABLE_CANDIDATE_PATH),
            "--conformance-only",
            "--durable-ledger",
            str(REPO_ROOT / "forbidden.sqlite3"),
        ],
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    assert inside_tree.returncode == 2
    assert "outside the current working tree" in inside_tree.stderr
    assert not (REPO_ROOT / "forbidden.sqlite3").exists()


def test_completion_failure_is_inconclusive_and_non_retryable(tmp_path: Path) -> None:
    class FailingCompletionLedger:
        def claim(self, idempotency_key: str, fingerprint: str) -> Any:
            return type("Decision", (), {"classification": "NEW", "record": None})()

        def complete(
            self, idempotency_key: str, fingerprint: str, outcome: dict[str, Any]
        ) -> None:
            raise LedgerError("controlled completion failure")

    candidate = DurableApiRunnerProtocolCandidate(
        durable_ledger=FailingCompletionLedger()  # type: ignore[arg-type]
    )
    outcome = _outcome(candidate.dispatch(_request("conformance.effect.success")))
    assert outcome["status"] == "INCONCLUSIVE"
    assert outcome["error"] == {
        "code": "INTERNAL_ERROR",
        "category": "internal",
        "retryable": False,
        "message": (
            "Synthetic effect outcome could not be committed to durable "
            "idempotency state"
        ),
    }
    assert candidate.effect_count == 1


def test_durable_candidate_has_no_legacy_execution_imports_or_calls() -> None:
    tree = ast.parse(DURABLE_CANDIDATE_PATH.read_text(encoding="utf-8"))
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
