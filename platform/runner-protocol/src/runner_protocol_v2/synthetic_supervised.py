"""Shared fixed-worker synthetic candidate for Runner Protocol conformance.

This module is a repository test and integration primitive. It combines the canonical
protocol validator, durable idempotency ledger and POSIX process supervisor while
requiring the consuming family wrapper to provide one fixed worker path and a stable
family identifier. It never authorizes production work or accepts a command from a
Runner Protocol request.
"""

from __future__ import annotations

import hashlib
import json
import re
import sys
import threading
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, TextIO

from .contracts import request_fingerprint, validate_semantics
from .idempotency import LedgerError, LedgerRecord, SQLiteIdempotencyLedger
from .supervision import (
    PosixProcessSupervisor,
    SupervisedProcessResult,
    SupervisedProcessSpec,
    SupervisionError,
)

PROTOCOL_VERSION = "2.0.0"
CONFORMANCE_AUTHORIZATION = "authz/conformance/active"
STARTED_AT = "2026-08-06T10:45:00Z"
FINISHED_AT = "2026-08-06T10:45:01Z"
SYNTHETIC_PROCESS_CAPABILITIES = frozenset(
    {
        "conformance.process.success",
        "conformance.process.execution-fail",
        "conformance.process.timeout",
        "conformance.process.cancel",
        "conformance.process.residue",
    }
)
_FAMILY_PATTERN = re.compile(r"^[a-z0-9][a-z0-9-]{0,31}$")


def _evidence(family: str, idempotency_key: str, status: str) -> dict[str, Any]:
    digest = hashlib.sha256(
        f"{family}-supervised-candidate:{idempotency_key}:{status}".encode("utf-8")
    ).hexdigest()
    evidence_id = str(
        uuid.uuid5(
            uuid.NAMESPACE_URL,
            f"{family}-supervised-runner-candidate:{digest}",
        )
    )
    return {
        "evidence_id": evidence_id,
        "kind": "protocol",
        "classification": "INTERNAL",
        "sha256": digest,
        "uri": f"evidence://{family}-supervised-runner-candidate/{evidence_id}",
    }


def _outcome(
    family: str,
    correlation: dict[str, str],
    status: str,
    idempotency_key: str,
    *,
    error: dict[str, Any] | None = None,
    output: dict[str, Any] | None = None,
) -> dict[str, Any]:
    message: dict[str, Any] = {
        "message_type": "runner.outcome",
        "protocol_version": PROTOCOL_VERSION,
        "correlation": correlation,
        "emitted_at": FINISHED_AT,
        "status": status,
        "started_at": STARTED_AT,
        "finished_at": FINISHED_AT,
        "evidence_refs": [_evidence(family, idempotency_key, status)],
    }
    if output is not None:
        message["output"] = output
    if error is not None:
        message["error"] = error
    validate_semantics(message)
    return message


def _progress(family: str, correlation: dict[str, str]) -> dict[str, Any]:
    message = {
        "message_type": "runner.progress",
        "protocol_version": PROTOCOL_VERSION,
        "correlation": correlation,
        "emitted_at": STARTED_AT,
        "sequence": 1,
        "state": "accepted",
        "percent": 0,
        "message": f"Accepted by the {family} supervised synthetic candidate",
    }
    validate_semantics(message)
    return message


def _acknowledgement(
    correlation: dict[str, str], status: str = "accepted"
) -> dict[str, Any]:
    message = {
        "message_type": "runner.cancellation.ack",
        "protocol_version": PROTOCOL_VERSION,
        "correlation": correlation,
        "emitted_at": FINISHED_AT,
        "status": status,
    }
    validate_semantics(message)
    return message


@dataclass
class PendingSyntheticExecution:
    request: dict[str, Any]
    fingerprint: str
    spec: SupervisedProcessSpec
    cleanup_paths: tuple[Path, ...] = ()
    ready_file: Path | None = None
    cancellation: threading.Event = field(default_factory=threading.Event)
    done: threading.Event = field(default_factory=threading.Event)
    response: dict[str, Any] | None = None
    thread: threading.Thread | None = None


@dataclass
class SyntheticSupervisedRunnerCandidate:
    """Durable fixed-worker candidate shared by isolated runner families."""

    family: str
    worker_path: Path
    durable_ledger: SQLiteIdempotencyLedger
    working_directory: Path | None = None
    supervisor: PosixProcessSupervisor = field(default_factory=PosixProcessSupervisor)
    effect_count: int = 0
    process_pending: dict[str, PendingSyntheticExecution] = field(default_factory=dict)
    _process_lock: threading.RLock = field(default_factory=threading.RLock)

    def __post_init__(self) -> None:
        if not _FAMILY_PATTERN.fullmatch(self.family):
            raise ValueError("family must be a stable lowercase identifier")
        worker = self.worker_path
        if not worker.is_absolute():
            raise ValueError("worker_path must be absolute")
        resolved_worker = worker.resolve(strict=True)
        if not resolved_worker.is_file():
            raise ValueError("worker_path must identify a regular file")
        self.worker_path = resolved_worker

        if self.working_directory is None:
            directory = self.durable_ledger.database_path.parent.resolve(strict=True)
        else:
            directory = self.working_directory.resolve(strict=True)
        if not directory.is_dir():
            raise ValueError("working_directory must be an existing directory")
        self.working_directory = directory

    def reset(self) -> dict[str, str]:
        with self._process_lock:
            if any(not pending.done.is_set() for pending in self.process_pending.values()):
                return {"status": "active_processes"}
            self.effect_count = 0
            self.process_pending.clear()
        return {"status": "reset"}

    def stats(self) -> dict[str, Any]:
        with self._process_lock:
            active = sum(
                1 for pending in self.process_pending.values() if not pending.done.is_set()
            )
        return {
            "stats": {
                "effect_count": self.effect_count,
                "ledger_entries": self.durable_ledger.count(),
                "active_processes": active,
            }
        }

    @staticmethod
    def _worker_mode(capability: str) -> str:
        return {
            "conformance.process.success": "success",
            "conformance.process.execution-fail": "execution-fail",
            "conformance.process.timeout": "ignore-term",
            "conformance.process.cancel": "ignore-term",
            "conformance.process.residue": "spawn-and-exit",
        }[capability]

    def _internal_path(self, purpose: str, key: str) -> Path:
        assert self.working_directory is not None
        digest = hashlib.sha256(
            f"{self.family}:{purpose}:{key}".encode("utf-8")
        ).hexdigest()[:20]
        return self.working_directory / f".{self.family}-{purpose}-{digest}.pid"

    def _spec(
        self,
        request: dict[str, Any],
        capability: str,
    ) -> tuple[SupervisedProcessSpec, tuple[Path, ...], Path | None]:
        assert self.working_directory is not None
        mode = self._worker_mode(capability)
        argv = [
            str(Path(sys.executable).resolve()),
            str(self.worker_path),
            "--mode",
            mode,
        ]
        cleanup_paths: list[Path] = []
        ready_file: Path | None = None

        if capability == "conformance.process.residue":
            residue_file = self._internal_path("residue", request["idempotency_key"])
            residue_file.unlink(missing_ok=True)
            cleanup_paths.append(residue_file)
            argv.extend(["--pid-file", str(residue_file)])

        if capability in {
            "conformance.process.timeout",
            "conformance.process.cancel",
        }:
            ready_file = self._internal_path("ready", request["idempotency_key"])
            ready_file.unlink(missing_ok=True)
            cleanup_paths.append(ready_file)
            argv.extend(["--ready-file", str(ready_file)])

        spec = SupervisedProcessSpec(
            argv=tuple(argv),
            cwd=self.working_directory,
            environment={"PYTHONUNBUFFERED": "1"},
            hard_timeout_ms=request["timeout_budget"]["hard_timeout_ms"],
            termination_grace_ms=request["cancellation_policy"]["grace_period_ms"],
            cleanup_timeout_ms=2_000,
            poll_interval_ms=10,
            output_limit_bytes=16 * 1024,
        )
        spec.validated_argv()
        spec.validated_cwd()
        spec.validated_environment()
        spec.validate_limits()
        return spec, tuple(cleanup_paths), ready_file

    def _refusal(
        self,
        request: dict[str, Any],
        *,
        code: str,
        category: str,
        message: str,
    ) -> dict[str, Any]:
        return {
            "messages": [
                _outcome(
                    self.family,
                    request["correlation"],
                    "REFUSED",
                    request["idempotency_key"],
                    error={
                        "code": code,
                        "category": category,
                        "retryable": False,
                        "message": message,
                    },
                )
            ]
        }

    def _replay(self, request: dict[str, Any], record: LedgerRecord) -> dict[str, Any]:
        if record.outcome is None:
            return self._refusal(
                request,
                code="IDEMPOTENCY_CONFLICT",
                category="conflict",
                message="The synthetic process is active or requires reconciliation",
            )
        stored = record.outcome
        return {
            "messages": [
                _outcome(
                    self.family,
                    request["correlation"],
                    stored["status"],
                    request["idempotency_key"],
                    error=stored.get("error"),
                    output=stored.get("output"),
                )
            ]
        }

    def _claim(self, request: dict[str, Any], fingerprint: str) -> dict[str, Any] | None:
        try:
            decision = self.durable_ledger.claim(
                request["idempotency_key"],
                fingerprint,
            )
        except LedgerError:
            return self._refusal(
                request,
                code="INTERNAL_ERROR",
                category="internal",
                message="Durable idempotency state is unavailable; execution is refused",
            )

        if decision.classification == "NEW":
            return None
        if decision.classification == "IDEMPOTENCY_CONFLICT":
            return self._refusal(
                request,
                code="IDEMPOTENCY_CONFLICT",
                category="conflict",
                message="Idempotency key already identifies another synthetic process",
            )
        if decision.classification == "IN_PROGRESS":
            return self._refusal(
                request,
                code="IDEMPOTENCY_CONFLICT",
                category="conflict",
                message="The synthetic process is active or requires reconciliation",
            )
        if decision.classification == "REPLAY_SAME" and decision.record is not None:
            return self._replay(request, decision.record)
        return self._refusal(
            request,
            code="INTERNAL_ERROR",
            category="internal",
            message="Durable idempotency state returned an unsupported decision",
        )

    def _complete_response(
        self,
        *,
        key: str,
        fingerprint: str,
        correlation: dict[str, str],
        response: dict[str, Any],
    ) -> dict[str, Any]:
        messages = response.get("messages")
        if not isinstance(messages, list):
            return response
        terminal = next(
            (
                message
                for message in messages
                if isinstance(message, dict)
                and message.get("message_type") == "runner.outcome"
            ),
            None,
        )
        if terminal is None:
            return response

        try:
            self.durable_ledger.complete(key, fingerprint, terminal)
        except LedgerError:
            inconclusive = _outcome(
                self.family,
                correlation,
                "INCONCLUSIVE",
                key,
                error={
                    "code": "INTERNAL_ERROR",
                    "category": "internal",
                    "retryable": False,
                    "message": (
                        "Synthetic process outcome could not be committed to durable "
                        "idempotency state"
                    ),
                },
            )
            return {
                "messages": [
                    inconclusive if message is terminal else message for message in messages
                ]
            }
        return response

    @staticmethod
    def _safe_process_output(result: SupervisedProcessResult) -> dict[str, Any]:
        return {
            "result": "synthetic-supervised-process",
            "supervision": {
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
            },
        }

    def _result_response(
        self,
        request: dict[str, Any],
        capability: str,
        result: SupervisedProcessResult,
    ) -> dict[str, Any]:
        correlation = request["correlation"]
        key = request["idempotency_key"]
        output = self._safe_process_output(result)

        if result.status == "EXITED" and result.returncode == 0:
            if capability == "conformance.process.success":
                return {
                    "messages": [
                        _outcome(
                            self.family,
                            correlation,
                            "PASS",
                            key,
                            output=output,
                        )
                    ]
                }
            return {
                "messages": [
                    _outcome(
                        self.family,
                        correlation,
                        "INCONCLUSIVE",
                        key,
                        output=output,
                        error={
                            "code": "INTERNAL_ERROR",
                            "category": "internal",
                            "retryable": False,
                            "message": (
                                "Synthetic process exited without the expected lifecycle state"
                            ),
                        },
                    )
                ]
            }

        if result.status == "TIMED_OUT":
            return {
                "messages": [
                    _outcome(
                        self.family,
                        correlation,
                        "TIMED_OUT",
                        key,
                        output=output,
                        error={
                            "code": "TIMEOUT_HARD",
                            "category": "timeout",
                            "retryable": False,
                            "message": "Supervised synthetic process exceeded the hard timeout",
                        },
                    )
                ]
            }

        if result.status == "CANCELLED":
            return {
                "messages": [
                    _outcome(
                        self.family,
                        correlation,
                        "CANCELLED",
                        key,
                        output=output,
                        error={
                            "code": "CANCELLED",
                            "category": "cancellation",
                            "retryable": False,
                            "message": "Supervised synthetic process was cancelled and cleaned",
                        },
                    )
                ]
            }

        if result.status == "EXITED" and result.returncode not in {None, 0}:
            return {
                "messages": [
                    _outcome(
                        self.family,
                        correlation,
                        "ERROR",
                        key,
                        output=output,
                        error={
                            "code": "EXECUTION_FAILED",
                            "category": "execution",
                            "retryable": False,
                            "message": "Fixed synthetic worker returned a non-zero status",
                        },
                    )
                ]
            }

        if result.status == "START_FAILED":
            return {
                "messages": [
                    _outcome(
                        self.family,
                        correlation,
                        "ERROR",
                        key,
                        output=output,
                        error={
                            "code": "RUNNER_UNAVAILABLE",
                            "category": "execution",
                            "retryable": True,
                            "message": "Fixed synthetic worker could not be started",
                        },
                    )
                ]
            }

        message = (
            "Unexpected descendant residue was removed; the synthetic result is not trusted"
            if result.status == "RESIDUE_CLEANED"
            else "Supervised process cleanup could not be verified"
        )
        return {
            "messages": [
                _outcome(
                    self.family,
                    correlation,
                    "INCONCLUSIVE",
                    key,
                    output=output,
                    error={
                        "code": "INTERNAL_ERROR",
                        "category": "internal",
                        "retryable": False,
                        "message": message,
                    },
                )
            ]
        }

    def _run_and_complete(
        self,
        request: dict[str, Any],
        capability: str,
        fingerprint: str,
        spec: SupervisedProcessSpec,
        *,
        cancellation: threading.Event | None = None,
        cleanup_paths: tuple[Path, ...] = (),
    ) -> dict[str, Any]:
        try:
            result = self.supervisor.run(spec, cancellation=cancellation)
        except SupervisionError:
            response = {
                "messages": [
                    _outcome(
                        self.family,
                        request["correlation"],
                        "INCONCLUSIVE",
                        request["idempotency_key"],
                        error={
                            "code": "INTERNAL_ERROR",
                            "category": "internal",
                            "retryable": False,
                            "message": "Synthetic process supervision failed closed",
                        },
                    )
                ]
            }
        else:
            if result.root_pid is not None:
                with self._process_lock:
                    self.effect_count += 1
            response = self._result_response(request, capability, result)
        finally:
            for cleanup_path in cleanup_paths:
                cleanup_path.unlink(missing_ok=True)

        return self._complete_response(
            key=request["idempotency_key"],
            fingerprint=fingerprint,
            correlation=request["correlation"],
            response=response,
        )

    def _background_run(
        self,
        key: str,
        pending: PendingSyntheticExecution,
    ) -> None:
        capability = pending.request["operation"]["capability_id"]
        pending.response = self._run_and_complete(
            pending.request,
            capability,
            pending.fingerprint,
            pending.spec,
            cancellation=pending.cancellation,
            cleanup_paths=pending.cleanup_paths,
        )
        pending.done.set()

    def dispatch(self, request: dict[str, Any]) -> dict[str, Any]:
        validate_semantics(request)
        if request["message_type"] != "runner.step.request":
            raise ValueError("dispatch requires runner.step.request")
        if request["authorization_ref"] != CONFORMANCE_AUTHORIZATION:
            return self._refusal(
                request,
                code="AUTHORIZATION_DENIED",
                category="authorization",
                message="Synthetic process candidate requires conformance authorization",
            )

        capability = request["operation"]["capability_id"]
        if capability not in SYNTHETIC_PROCESS_CAPABILITIES:
            return self._refusal(
                request,
                code="UNSUPPORTED_CAPABILITY",
                category="compatibility",
                message="Candidate exposes only fixed synthetic process capabilities",
            )

        try:
            spec, cleanup_paths, ready_file = self._spec(request, capability)
        except (OSError, SupervisionError, ValueError):
            return self._refusal(
                request,
                code="INVALID_REQUEST",
                category="validation",
                message="Synthetic process supervision limits are invalid or unavailable",
            )

        fingerprint = request_fingerprint(request)
        preflight = self._claim(request, fingerprint)
        if preflight is not None:
            for cleanup_path in cleanup_paths:
                cleanup_path.unlink(missing_ok=True)
            return preflight

        if capability != "conformance.process.cancel":
            return self._run_and_complete(
                request,
                capability,
                fingerprint,
                spec,
                cleanup_paths=cleanup_paths,
            )

        key = request["idempotency_key"]
        pending = PendingSyntheticExecution(
            request=json.loads(json.dumps(request)),
            fingerprint=fingerprint,
            spec=spec,
            cleanup_paths=cleanup_paths,
            ready_file=ready_file,
        )
        thread = threading.Thread(
            target=self._background_run,
            args=(key, pending),
            name=(
                f"{self.family}-synthetic-supervisor-"
                f"{hashlib.sha256(key.encode()).hexdigest()[:12]}"
            ),
            daemon=False,
        )
        pending.thread = thread
        with self._process_lock:
            self.process_pending[key] = pending
        try:
            thread.start()
        except RuntimeError:
            with self._process_lock:
                self.process_pending.pop(key, None)
            response = {
                "messages": [
                    _outcome(
                        self.family,
                        request["correlation"],
                        "INCONCLUSIVE",
                        key,
                        error={
                            "code": "INTERNAL_ERROR",
                            "category": "internal",
                            "retryable": False,
                            "message": "Synthetic supervisor thread could not be started",
                        },
                    )
                ]
            }
            return self._complete_response(
                key=key,
                fingerprint=fingerprint,
                correlation=request["correlation"],
                response=response,
            )

        if ready_file is not None:
            deadline = time.monotonic() + 2
            while (
                not ready_file.is_file()
                and not pending.done.is_set()
                and time.monotonic() < deadline
            ):
                time.sleep(0.01)
            if pending.done.is_set():
                with self._process_lock:
                    self.process_pending.pop(key, None)
                return pending.response or {
                    "transport_error": "synthetic process ended without a response"
                }
            if not ready_file.is_file():
                pending.cancellation.set()
                pending.done.wait(
                    (spec.termination_grace_ms + spec.cleanup_timeout_ms + 1_000)
                    / 1_000
                )
                with self._process_lock:
                    self.process_pending.pop(key, None)
                return pending.response or {
                    "transport_error": "synthetic process readiness failed closed"
                }
        return {"messages": [_progress(self.family, request["correlation"])]}

    def cancel(self, request: dict[str, Any]) -> dict[str, Any]:
        validate_semantics(request)
        if request["message_type"] != "runner.cancellation.request":
            raise ValueError("cancel requires runner.cancellation.request")

        correlation = request["correlation"]
        with self._process_lock:
            match = next(
                (
                    (key, pending)
                    for key, pending in self.process_pending.items()
                    if pending.request["correlation"] == correlation
                ),
                None,
            )
        if match is None:
            return {"messages": [_acknowledgement(correlation, "not_found")]}

        key, pending = match
        pending.cancellation.set()
        wait_seconds = (
            pending.spec.termination_grace_ms
            + pending.spec.cleanup_timeout_ms
            + 1_000
        ) / 1_000
        if not pending.done.wait(wait_seconds):
            return {"messages": [_acknowledgement(correlation)]}

        with self._process_lock:
            self.process_pending.pop(key, None)
        messages = (pending.response or {}).get("messages")
        terminal = next(
            (
                message
                for message in messages or []
                if isinstance(message, dict)
                and message.get("message_type") == "runner.outcome"
            ),
            None,
        )
        if terminal is None:
            return {"messages": [_acknowledgement(correlation)]}
        return {"messages": [_acknowledgement(correlation), terminal]}

    def shutdown(self) -> dict[str, str]:
        with self._process_lock:
            active = list(self.process_pending.values())
        for pending in active:
            pending.cancellation.set()
        for pending in active:
            pending.done.wait(
                (
                    pending.spec.termination_grace_ms
                    + pending.spec.cleanup_timeout_ms
                    + 1_000
                )
                / 1_000
            )
        if any(not pending.done.is_set() for pending in active):
            return {"status": "shutdown_refused_active_processes"}
        return {"status": "shutdown"}

    def handle_control(self, payload: dict[str, Any]) -> dict[str, Any]:
        action = payload.get("action")
        if action == "reset":
            return self.reset()
        if action == "stats":
            return self.stats()
        if action == "dispatch":
            return self.dispatch(payload["message"])
        if action == "cancel":
            return self.cancel(payload["message"])
        if action == "shutdown":
            return self.shutdown()
        return {"transport_error": "unsupported conformance action"}


def ledger_path(value: str) -> Path:
    """Argparse-compatible external durable ledger path validator."""

    path = Path(value)
    if not path.is_absolute():
        raise ValueError("durable ledger must be an absolute path")
    resolved = path.resolve(strict=False)
    working_tree = Path.cwd().resolve()
    if resolved == working_tree or working_tree in resolved.parents:
        raise ValueError("durable ledger must be outside the current working tree")
    return resolved


def serve_json_lines(
    candidate: SyntheticSupervisedRunnerCandidate,
    *,
    input_stream: TextIO = sys.stdin,
    output_stream: TextIO = sys.stdout,
) -> int:
    """Serve the isolated JSON-lines conformance control surface."""

    for line in input_stream:
        try:
            payload = json.loads(line)
            if not isinstance(payload, dict):
                raise ValueError("control payload must be a JSON object")
            response = candidate.handle_control(payload)
        except Exception as exc:
            response = {"transport_error": str(exc)[:256]}
        print(json.dumps(response, sort_keys=True), file=output_stream, flush=True)
        if response == {"status": "shutdown"}:
            return 0
    return 0
