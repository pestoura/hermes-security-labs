"""Fail-closed POSIX process supervision for Runner Protocol adapters.

The supervisor starts exactly one absolute executable without a shell, places the
process in a new session/process group, captures bounded output and owns cleanup of
the complete process group. It is an execution primitive only: it does not authorize
capabilities, select targets or translate process output into protocol evidence.
"""

from __future__ import annotations

import os
import selectors
import signal
import subprocess
import time
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from threading import Event
from typing import Literal

SupervisionStatus = Literal[
    "EXITED",
    "CANCELLED",
    "TIMED_OUT",
    "RESIDUE_CLEANED",
    "CLEANUP_FAILED",
    "START_FAILED",
]

_SAFE_ENVIRONMENT_KEYS = frozenset({"LANG", "LC_ALL", "TZ", "PYTHONUNBUFFERED"})
_BASE_ENVIRONMENT = {
    "LANG": "C.UTF-8",
    "LC_ALL": "C.UTF-8",
    "PATH": "/usr/bin:/bin",
}


class SupervisionError(RuntimeError):
    """Base error for the supervised-process boundary."""


class SupervisionSpecError(SupervisionError):
    """Raised before process creation when a specification is unsafe or invalid."""


class SupervisionUnavailableError(SupervisionError):
    """Raised when the required POSIX process-group primitives are unavailable."""


@dataclass(frozen=True)
class SupervisedProcessSpec:
    """Bounded process specification validated before any child is created."""

    argv: tuple[str, ...]
    cwd: Path
    environment: Mapping[str, str] = field(default_factory=dict)
    hard_timeout_ms: int = 5_000
    termination_grace_ms: int = 250
    cleanup_timeout_ms: int = 2_000
    poll_interval_ms: int = 20
    output_limit_bytes: int = 64 * 1024

    def validated_argv(self) -> tuple[str, ...]:
        if not self.argv or not all(isinstance(item, str) and item for item in self.argv):
            raise SupervisionSpecError("argv must contain non-empty strings")
        if any("\x00" in item for item in self.argv):
            raise SupervisionSpecError("argv must not contain NUL bytes")

        executable = Path(self.argv[0])
        if not executable.is_absolute():
            raise SupervisionSpecError("the executable path must be absolute")
        resolved = executable.resolve(strict=True)
        if not resolved.is_file() or not os.access(resolved, os.X_OK):
            raise SupervisionSpecError("the executable must be an executable file")
        return (str(resolved), *self.argv[1:])

    def validated_cwd(self) -> Path:
        if not self.cwd.is_absolute():
            raise SupervisionSpecError("cwd must be an absolute path")
        resolved = self.cwd.resolve(strict=True)
        if not resolved.is_dir():
            raise SupervisionSpecError("cwd must identify an existing directory")
        return resolved

    def validated_environment(self) -> dict[str, str]:
        environment = dict(_BASE_ENVIRONMENT)
        for key, value in self.environment.items():
            if key not in _SAFE_ENVIRONMENT_KEYS:
                raise SupervisionSpecError(
                    f"environment key is not permitted by the supervisor: {key}"
                )
            if not isinstance(value, str) or "\x00" in value:
                raise SupervisionSpecError("environment values must be NUL-free strings")
            environment[key] = value
        return environment

    def validate_limits(self) -> None:
        if not 1 <= self.hard_timeout_ms <= 300_000:
            raise SupervisionSpecError("hard_timeout_ms must be between 1 and 300000")
        if not 0 <= self.termination_grace_ms <= 10_000:
            raise SupervisionSpecError(
                "termination_grace_ms must be between 0 and 10000"
            )
        if not 100 <= self.cleanup_timeout_ms <= 10_000:
            raise SupervisionSpecError(
                "cleanup_timeout_ms must be between 100 and 10000"
            )
        if not 5 <= self.poll_interval_ms <= 1_000:
            raise SupervisionSpecError("poll_interval_ms must be between 5 and 1000")
        if not 1 <= self.output_limit_bytes <= 1024 * 1024:
            raise SupervisionSpecError(
                "output_limit_bytes must be between 1 and 1048576"
            )


@dataclass(frozen=True)
class SupervisedProcessResult:
    """Bounded, non-authoritative result returned by the process supervisor."""

    status: SupervisionStatus
    returncode: int | None
    stdout: bytes
    stderr: bytes
    stdout_truncated: bool
    stderr_truncated: bool
    force_killed: bool
    residue_cleaned: bool
    cleanup_failed: bool
    duration_ms: int
    root_pid: int | None
    start_error: str | None = None

    @property
    def successful(self) -> bool:
        return self.status == "EXITED" and self.returncode == 0


def _group_exists(process_group_id: int) -> bool:
    try:
        os.killpg(process_group_id, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def _signal_group(process_group_id: int, selected_signal: int) -> None:
    try:
        os.killpg(process_group_id, selected_signal)
    except ProcessLookupError:
        return


def _append_bounded(buffer: bytearray, data: bytes, limit: int) -> bool:
    remaining = max(0, limit - len(buffer))
    if remaining:
        buffer.extend(data[:remaining])
    return len(data) > remaining


def _drain_ready_streams(
    selector: selectors.BaseSelector,
    buffers: dict[str, bytearray],
    truncated: dict[str, bool],
    limit: int,
    timeout_seconds: float,
) -> None:
    for key, _ in selector.select(timeout_seconds):
        stream = key.fileobj
        label = key.data
        try:
            data = os.read(stream.fileno(), 64 * 1024)
        except BlockingIOError:
            continue
        if not data:
            selector.unregister(stream)
            stream.close()
            continue
        truncated[label] = (
            _append_bounded(buffers[label], data, limit) or truncated[label]
        )


class PosixProcessSupervisor:
    """Own one child process group until exit or verified cleanup."""

    def run(
        self,
        spec: SupervisedProcessSpec,
        *,
        cancellation: Event | None = None,
    ) -> SupervisedProcessResult:
        if os.name != "posix" or not hasattr(os, "killpg"):
            raise SupervisionUnavailableError(
                "POSIX process-group supervision is required"
            )

        argv = spec.validated_argv()
        cwd = spec.validated_cwd()
        environment = spec.validated_environment()
        spec.validate_limits()

        started = time.monotonic()
        if cancellation is not None and cancellation.is_set():
            return SupervisedProcessResult(
                status="CANCELLED",
                returncode=None,
                stdout=b"",
                stderr=b"",
                stdout_truncated=False,
                stderr_truncated=False,
                force_killed=False,
                residue_cleaned=False,
                cleanup_failed=False,
                duration_ms=0,
                root_pid=None,
            )

        try:
            process = subprocess.Popen(  # noqa: S603 - absolute executable, no shell
                argv,
                cwd=cwd,
                env=environment,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                shell=False,
                start_new_session=True,
                close_fds=True,
            )
        except OSError as exc:
            return SupervisedProcessResult(
                status="START_FAILED",
                returncode=None,
                stdout=b"",
                stderr=b"",
                stdout_truncated=False,
                stderr_truncated=False,
                force_killed=False,
                residue_cleaned=False,
                cleanup_failed=False,
                duration_ms=int((time.monotonic() - started) * 1_000),
                root_pid=None,
                start_error=type(exc).__name__,
            )

        process_group_id = process.pid
        selector = selectors.DefaultSelector()
        buffers = {"stdout": bytearray(), "stderr": bytearray()}
        truncated = {"stdout": False, "stderr": False}
        assert process.stdout is not None
        assert process.stderr is not None
        for label, stream in (("stdout", process.stdout), ("stderr", process.stderr)):
            os.set_blocking(stream.fileno(), False)
            selector.register(stream, selectors.EVENT_READ, label)

        hard_deadline = started + spec.hard_timeout_ms / 1_000
        stop_status: SupervisionStatus | None = None
        termination_deadline: float | None = None
        cleanup_deadline: float | None = None
        force_killed = False
        residue_cleaned = False
        cleanup_failed = False

        while True:
            now = time.monotonic()
            root_returncode = process.poll()
            group_alive = _group_exists(process_group_id)

            if stop_status is None:
                if cancellation is not None and cancellation.is_set():
                    stop_status = "CANCELLED"
                    _signal_group(process_group_id, signal.SIGTERM)
                    termination_deadline = now + spec.termination_grace_ms / 1_000
                elif now >= hard_deadline:
                    stop_status = "TIMED_OUT"
                    _signal_group(process_group_id, signal.SIGTERM)
                    termination_deadline = now + spec.termination_grace_ms / 1_000
                elif root_returncode is not None and group_alive:
                    stop_status = "RESIDUE_CLEANED"
                    residue_cleaned = True
                    _signal_group(process_group_id, signal.SIGTERM)
                    termination_deadline = now + spec.termination_grace_ms / 1_000

            if (
                stop_status is not None
                and group_alive
                and termination_deadline is not None
                and now >= termination_deadline
                and not force_killed
            ):
                _signal_group(process_group_id, signal.SIGKILL)
                force_killed = True
                cleanup_deadline = now + spec.cleanup_timeout_ms / 1_000

            if (
                stop_status is not None
                and force_killed
                and group_alive
                and cleanup_deadline is not None
                and now >= cleanup_deadline
            ):
                cleanup_failed = True
                stop_status = "CLEANUP_FAILED"

            wait_seconds = spec.poll_interval_ms / 1_000
            deadlines = [hard_deadline]
            if termination_deadline is not None and not force_killed:
                deadlines.append(termination_deadline)
            if cleanup_deadline is not None:
                deadlines.append(cleanup_deadline)
            future_deadlines = [deadline for deadline in deadlines if deadline > now]
            if future_deadlines:
                wait_seconds = min(wait_seconds, min(future_deadlines) - now)
            _drain_ready_streams(
                selector,
                buffers,
                truncated,
                spec.output_limit_bytes,
                max(0.0, wait_seconds),
            )

            root_returncode = process.poll()
            group_alive = _group_exists(process_group_id)
            streams_open = bool(selector.get_map())

            if cleanup_failed:
                break
            if root_returncode is not None and not group_alive and not streams_open:
                break

        if process.poll() is None:
            _signal_group(process_group_id, signal.SIGKILL)
            force_killed = True
            try:
                process.wait(timeout=spec.cleanup_timeout_ms / 1_000)
            except subprocess.TimeoutExpired:
                cleanup_failed = True
                stop_status = "CLEANUP_FAILED"
        else:
            process.wait()

        for key in list(selector.get_map().values()):
            stream = key.fileobj
            try:
                selector.unregister(stream)
            except KeyError:
                pass
            stream.close()
        selector.close()

        duration_ms = int((time.monotonic() - started) * 1_000)
        final_status: SupervisionStatus
        if cleanup_failed:
            final_status = "CLEANUP_FAILED"
        elif stop_status is not None:
            final_status = stop_status
        else:
            final_status = "EXITED"

        return SupervisedProcessResult(
            status=final_status,
            returncode=process.returncode,
            stdout=bytes(buffers["stdout"]),
            stderr=bytes(buffers["stderr"]),
            stdout_truncated=truncated["stdout"],
            stderr_truncated=truncated["stderr"],
            force_killed=force_killed,
            residue_cleaned=residue_cleaned,
            cleanup_failed=cleanup_failed,
            duration_ms=duration_ms,
            root_pid=process.pid,
        )
