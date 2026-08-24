"""Supervised LAB-only PromptMe runtime candidate for Runner Protocol v2."""

from __future__ import annotations

import copy
import hashlib
import json
import sys
import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from ai_mcp_runbooks.runner_protocol_projection import (
    ProjectionRefusal,
    evidence_reference,
    is_calibrated,
    project_execution_result,
    project_step_request,
    refusal_outcome,
)
from runner_protocol_v2 import (
    LedgerError,
    PosixProcessSupervisor,
    SQLiteIdempotencyLedger,
    SupervisedProcessResult,
    SupervisedProcessSpec,
    SupervisionError,
    request_fingerprint,
    validate_semantics,
)

LIVE_BASE_URL = "http://127.0.0.1:8210"
DEFAULT_WORKER = Path(__file__).with_name("supervised_promptme_runtime_worker.py").resolve()
DURABLE_TERMINAL_ALLOWANCE_MS = 6_000


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _refusal(code: str, category: str, message: str) -> ProjectionRefusal:
    return ProjectionRefusal(
        {
            "code": code,
            "category": category,
            "retryable": False,
            "message": message[:256].replace("\n", " ").replace("\r", " "),
        }
    )


def _messages(outcome: dict[str, Any]) -> dict[str, Any]:
    validate_semantics(outcome)
    return {"messages": [outcome]}


def _acknowledgement(
    correlation: Mapping[str, str], status: str = "accepted"
) -> dict[str, Any]:
    message = {
        "message_type": "runner.cancellation.ack",
        "protocol_version": "2.0.0",
        "correlation": dict(correlation),
        "emitted_at": _now(),
        "status": status,
    }
    validate_semantics(message)
    return message


def _replay(request: Mapping[str, Any], stored: Mapping[str, Any]) -> dict[str, Any]:
    outcome = copy.deepcopy(dict(stored))
    outcome["correlation"] = dict(request["correlation"])
    outcome["emitted_at"] = _now()
    validate_semantics(outcome)
    return {"messages": [outcome]}


def _supervision_output(result: SupervisedProcessResult) -> dict[str, Any]:
    return {
        "status": result.status,
        "returncode": result.returncode,
        "stdout_sha256": hashlib.sha256(result.stdout).hexdigest(),
        "stderr_sha256": hashlib.sha256(result.stderr).hexdigest(),
        "stdout_bytes": len(result.stdout),
        "stderr_bytes": len(result.stderr),
        "stdout_truncated": result.stdout_truncated,
        "stderr_truncated": result.stderr_truncated,
        "force_killed": result.force_killed,
        "residue_cleaned": result.residue_cleaned,
        "cleanup_failed": result.cleanup_failed,
        "duration_ms": result.duration_ms,
    }


def _terminal_from_supervision(
    request: Mapping[str, Any], result: SupervisedProcessResult, *, started_at: str
) -> dict[str, Any]:
    supervision = _supervision_output(result)
    status = "INCONCLUSIVE"
    error = {
        "code": "INTERNAL_ERROR",
        "category": "internal",
        "retryable": False,
        "message": "Supervised PromptMe runtime did not produce a trusted terminal result",
    }
    if result.status == "CANCELLED":
        status = "CANCELLED"
        error = {
            "code": "CANCELLED",
            "category": "cancellation",
            "retryable": False,
            "message": "Supervised PromptMe runtime was cancelled and cleaned",
        }
    elif result.status == "TIMED_OUT":
        status = "TIMED_OUT"
        error = {
            "code": "TIMEOUT_HARD",
            "category": "timeout",
            "retryable": False,
            "message": "Supervised PromptMe runtime exceeded the hard timeout",
        }
    elif result.status == "START_FAILED" or (
        result.status == "EXITED" and result.returncode not in {None, 0}
    ):
        status = "ERROR"
        error = {
            "code": "EXECUTION_FAILED",
            "category": "execution",
            "retryable": False,
            "message": "Fixed PromptMe runtime worker failed safely",
        }

    record = {"supervision": supervision, "runtime": "promptme-lab"}
    outcome = {
        "message_type": "runner.outcome",
        "protocol_version": "2.0.0",
        "correlation": dict(request["correlation"]),
        "emitted_at": _now(),
        "status": status,
        "started_at": started_at,
        "finished_at": _now(),
        "evidence_refs": [evidence_reference(record, kind="execution")],
        "output": {"supervision": supervision},
        "error": error,
    }
    validate_semantics(outcome)
    return outcome


@dataclass
class PendingPromptMeExecution:
    request: dict[str, Any]
    fingerprint: str
    spec: SupervisedProcessSpec
    cancellation: threading.Event = field(default_factory=threading.Event)
    done: threading.Event = field(default_factory=threading.Event)
    outcome: dict[str, Any] | None = None


@dataclass
class SupervisedPromptMeAiMcpRunnerCandidate:
    durable_ledger: SQLiteIdempotencyLedger
    working_directory: Path
    worker_path: Path = DEFAULT_WORKER
    supervisor: PosixProcessSupervisor = field(default_factory=PosixProcessSupervisor)
    effect_count: int = 0
    process_pending: dict[str, PendingPromptMeExecution] = field(default_factory=dict)
    _process_lock: threading.RLock = field(default_factory=threading.RLock)

    def __post_init__(self) -> None:
        self.working_directory = self.working_directory.resolve(strict=True)
        if not self.working_directory.is_dir():
            raise ValueError("working_directory must be a directory")
        self.worker_path = self.worker_path.resolve(strict=True)
        if not self.worker_path.is_file():
            raise ValueError("worker_path must identify a regular file")

    def stats(self) -> dict[str, int]:
        with self._process_lock:
            active = sum(
                1 for pending in self.process_pending.values() if not pending.done.is_set()
            )
            effect_count = self.effect_count
        return {
            "effect_count": effect_count,
            "ledger_entries": self.durable_ledger.count(),
            "active_processes": active,
        }

    @staticmethod
    def _fixed_boundary(execution_request: Any) -> None:
        if execution_request.handler != ("agent", "conversation-test"):
            raise _refusal("UNSUPPORTED_CAPABILITY", "compatibility", "Only the calibrated PromptMe handler is supervised")
        if execution_request.profile != "promptme-direct-injection":
            raise _refusal("UNSUPPORTED_CAPABILITY", "compatibility", "Only the fixed PromptMe calibration profile is supervised")
        if execution_request.target_ref != "promptme" or execution_request.scope != "laboratory":
            raise _refusal("AUTHORIZATION_DENIED", "authorization", "Supervised runtime is restricted to the PromptMe laboratory")
        if execution_request.arguments != {"base_url": LIVE_BASE_URL}:
            raise _refusal("AUTHORIZATION_DENIED", "authorization", "PromptMe supervised runtime uses a fixed localhost endpoint")

    def _claim(self, request: dict[str, Any], fingerprint: str) -> dict[str, Any] | None:
        try:
            decision = self.durable_ledger.claim(request["idempotency_key"], fingerprint)
        except LedgerError:
            return _messages(
                refusal_outcome(
                    request,
                    _refusal(
                        "INTERNAL_ERROR",
                        "internal",
                        "Durable idempotency state is unavailable; execution is refused",
                    ),
                )
            )
        if decision.classification == "NEW":
            return None
        if decision.classification == "REPLAY_SAME" and decision.record is not None:
            if decision.record.outcome is not None:
                return _replay(request, decision.record.outcome)
        return _messages(
            refusal_outcome(
                request,
                _refusal(
                    "IDEMPOTENCY_CONFLICT",
                    "conflict",
                    "Idempotency state is active, conflicting or incomplete",
                ),
            )
        )

    def _spec(self, request: dict[str, Any]) -> SupervisedProcessSpec:
        return SupervisedProcessSpec(
            argv=(str(Path(sys.executable).resolve()), str(self.worker_path)),
            cwd=self.working_directory,
            environment={"PYTHONUNBUFFERED": "1"},
            hard_timeout_ms=request["timeout_budget"]["hard_timeout_ms"],
            termination_grace_ms=request["cancellation_policy"]["grace_period_ms"],
            cleanup_timeout_ms=2_000,
            poll_interval_ms=10,
            output_limit_bytes=64 * 1024,
        )

    def dispatch(self, request: dict[str, Any]) -> dict[str, Any]:
        try:
            execution_request = project_step_request(request)
            if not is_calibrated(execution_request):
                raise _refusal(
                    "UNSUPPORTED_CAPABILITY",
                    "compatibility",
                    "AI/MCP handler is declared but not calibrated",
                )
            self._fixed_boundary(execution_request)
        except ProjectionRefusal as refusal:
            return _messages(refusal_outcome(request, refusal))

        fingerprint = request_fingerprint(request)
        key = request["idempotency_key"]
        with self._process_lock:
            claimed = self._claim(request, fingerprint)
            if claimed is not None:
                return claimed
            started_at = _now()
            pending = PendingPromptMeExecution(
                request=copy.deepcopy(request),
                fingerprint=fingerprint,
                spec=self._spec(request),
            )
            self.process_pending[key] = pending

        outcome: dict[str, Any] | None = None
        try:
            try:
                result = self.supervisor.run(
                    pending.spec, cancellation=pending.cancellation
                )
            except SupervisionError:
                outcome = _terminal_supervision_unavailable(
                    request, started_at=started_at
                )
            else:
                if result.root_pid is not None:
                    with self._process_lock:
                        self.effect_count += 1

                if result.status == "EXITED" and result.returncode == 0:
                    try:
                        runtime_document = json.loads(result.stdout.decode("utf-8"))
                        if not isinstance(runtime_document, dict):
                            raise TypeError("worker output is not a JSON object")
                        outcome = project_execution_result(
                            request,
                            runtime_document,
                            started_at=started_at,
                        )
                        outcome.setdefault("output", {})["supervision"] = (
                            _supervision_output(result)
                        )
                        validate_semantics(outcome)
                    except (
                        UnicodeDecodeError,
                        json.JSONDecodeError,
                        TypeError,
                        ProjectionRefusal,
                    ):
                        outcome = _terminal_from_supervision(
                            request, result, started_at=started_at
                        )
                else:
                    outcome = _terminal_from_supervision(
                        request, result, started_at=started_at
                    )

            try:
                self.durable_ledger.complete(key, fingerprint, outcome)
            except LedgerError:
                outcome = _terminal_after_commit_failure(
                    request, started_at=started_at
                )
            pending.outcome = outcome
            return _messages(outcome)
        finally:
            pending.done.set()
            with self._process_lock:
                self.process_pending.pop(key, None)

    def cancel(self, request: dict[str, Any]) -> dict[str, Any]:
        validate_semantics(request)
        if request["message_type"] != "runner.cancellation.request":
            raise ValueError("cancel requires runner.cancellation.request")

        correlation = request["correlation"]
        with self._process_lock:
            match = next(
                (
                    pending
                    for pending in self.process_pending.values()
                    if pending.request["correlation"] == correlation
                    and not pending.done.is_set()
                ),
                None,
            )
        if match is None:
            return {"messages": [_acknowledgement(correlation, "not_found")]}

        match.cancellation.set()
        wait_seconds = (
            match.spec.termination_grace_ms
            + (2 * match.spec.cleanup_timeout_ms)
            + DURABLE_TERMINAL_ALLOWANCE_MS
        ) / 1_000
        if not match.done.wait(wait_seconds):
            return {"messages": [_acknowledgement(correlation)]}

        terminal = match.outcome
        if terminal is None:
            return {"messages": [_acknowledgement(correlation)]}

        supervision_status = (
            terminal.get("output", {}).get("supervision", {}).get("status")
        )
        if terminal.get("status") != "CANCELLED" and supervision_status != "CLEANUP_FAILED":
            return {"messages": [_acknowledgement(correlation, "not_found")]}
        return {
            "messages": [
                _acknowledgement(correlation),
                copy.deepcopy(terminal),
            ]
        }


def _terminal_after_commit_failure(
    request: Mapping[str, Any], *, started_at: str
) -> dict[str, Any]:
    record = {"decision": "effect_completed_but_durable_state_unavailable"}
    outcome = {
        "message_type": "runner.outcome",
        "protocol_version": "2.0.0",
        "correlation": dict(request["correlation"]),
        "emitted_at": _now(),
        "status": "INCONCLUSIVE",
        "started_at": started_at,
        "finished_at": _now(),
        "evidence_refs": [evidence_reference(record, kind="protocol")],
        "error": {
            "code": "INTERNAL_ERROR",
            "category": "internal",
            "retryable": False,
            "message": "Runtime outcome could not be committed to durable idempotency state",
        },
    }
    validate_semantics(outcome)
    return outcome


def _terminal_supervision_unavailable(
    request: Mapping[str, Any], *, started_at: str
) -> dict[str, Any]:
    record = {"decision": "supervision_unavailable_before_process_result"}
    outcome = {
        "message_type": "runner.outcome",
        "protocol_version": "2.0.0",
        "correlation": dict(request["correlation"]),
        "emitted_at": _now(),
        "status": "INCONCLUSIVE",
        "started_at": started_at,
        "finished_at": _now(),
        "evidence_refs": [evidence_reference(record, kind="protocol")],
        "error": {
            "code": "INTERNAL_ERROR",
            "category": "internal",
            "retryable": False,
            "message": "Supervised PromptMe runtime is unavailable",
        },
    }
    validate_semantics(outcome)
    return outcome
