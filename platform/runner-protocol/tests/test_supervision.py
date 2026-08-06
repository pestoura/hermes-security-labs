from __future__ import annotations

import ast
import os
import sys
import threading
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SDK_SRC = ROOT / "src"
if str(SDK_SRC) not in sys.path:
    sys.path.insert(0, str(SDK_SRC))

from runner_protocol_v2.supervision import (  # noqa: E402
    PosixProcessSupervisor,
    SupervisedProcessSpec,
    SupervisionSpecError,
)

WORKER = Path(__file__).parent / "fixtures" / "supervised_worker.py"
PYTHON = Path(sys.executable).resolve()


def _spec(tmp_path: Path, *worker_args: str, **limits: int) -> SupervisedProcessSpec:
    return SupervisedProcessSpec(
        argv=(str(PYTHON), str(WORKER), *worker_args),
        cwd=tmp_path.resolve(),
        environment={"PYTHONUNBUFFERED": "1"},
        hard_timeout_ms=limits.get("hard_timeout_ms", 2_000),
        termination_grace_ms=limits.get("termination_grace_ms", 100),
        cleanup_timeout_ms=limits.get("cleanup_timeout_ms", 2_000),
        poll_interval_ms=limits.get("poll_interval_ms", 10),
        output_limit_bytes=limits.get("output_limit_bytes", 64 * 1024),
    )


def _pid_exists(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    return True


def _assert_pid_gone(pid: int) -> None:
    deadline = time.monotonic() + 2
    while time.monotonic() < deadline:
        if not _pid_exists(pid):
            return
        time.sleep(0.02)
    pytest.fail(f"supervised descendant still exists: {pid}")


@pytest.mark.skipif(os.name != "posix", reason="POSIX process groups required")
def test_clean_exit_is_reported_without_forced_cleanup(tmp_path: Path) -> None:
    result = PosixProcessSupervisor().run(_spec(tmp_path, "--mode", "exit"))

    assert result.status == "EXITED"
    assert result.returncode == 0
    assert result.stdout == b"supervised-worker-ok\n"
    assert result.stderr == b""
    assert result.successful is True
    assert result.force_killed is False
    assert result.residue_cleaned is False
    assert result.cleanup_failed is False


@pytest.mark.skipif(os.name != "posix", reason="POSIX process groups required")
def test_hard_timeout_kills_root_and_stubborn_descendant(tmp_path: Path) -> None:
    pid_file = tmp_path / "descendant.pid"
    result = PosixProcessSupervisor().run(
        _spec(
            tmp_path,
            "--mode",
            "spawn-and-wait",
            "--pid-file",
            str(pid_file),
            hard_timeout_ms=300,
            termination_grace_ms=75,
        )
    )

    assert result.status == "TIMED_OUT"
    assert result.force_killed is True
    assert result.cleanup_failed is False
    descendant_pid = int(pid_file.read_text(encoding="utf-8").strip())
    _assert_pid_gone(descendant_pid)


@pytest.mark.skipif(os.name != "posix", reason="POSIX process groups required")
def test_cancellation_escalates_to_kill_for_stubborn_process(tmp_path: Path) -> None:
    cancellation = threading.Event()
    timer = threading.Timer(0.15, cancellation.set)
    timer.start()
    try:
        result = PosixProcessSupervisor().run(
            _spec(
                tmp_path,
                "--mode",
                "ignore-term",
                hard_timeout_ms=2_000,
                termination_grace_ms=75,
            ),
            cancellation=cancellation,
        )
    finally:
        timer.cancel()

    assert result.status == "CANCELLED"
    assert result.force_killed is True
    assert result.cleanup_failed is False
    assert result.duration_ms < 1_500


@pytest.mark.skipif(os.name != "posix", reason="POSIX process groups required")
def test_parent_exit_with_live_descendant_is_cleaned_and_not_passed(
    tmp_path: Path,
) -> None:
    pid_file = tmp_path / "residue.pid"
    result = PosixProcessSupervisor().run(
        _spec(
            tmp_path,
            "--mode",
            "spawn-and-exit",
            "--pid-file",
            str(pid_file),
            termination_grace_ms=75,
        )
    )

    assert result.status == "RESIDUE_CLEANED"
    assert result.residue_cleaned is True
    assert result.force_killed is True
    assert result.successful is False
    descendant_pid = int(pid_file.read_text(encoding="utf-8").strip())
    _assert_pid_gone(descendant_pid)


@pytest.mark.skipif(os.name != "posix", reason="POSIX process groups required")
def test_output_is_captured_with_independent_hard_limits(tmp_path: Path) -> None:
    result = PosixProcessSupervisor().run(
        _spec(
            tmp_path,
            "--mode",
            "output",
            "--bytes",
            "131072",
            output_limit_bytes=1_024,
        )
    )

    assert result.status == "EXITED"
    assert result.returncode == 0
    assert len(result.stdout) == 1_024
    assert len(result.stderr) == 1_024
    assert result.stdout_truncated is True
    assert result.stderr_truncated is True


def test_unsafe_specifications_fail_before_process_creation(tmp_path: Path) -> None:
    supervisor = PosixProcessSupervisor()

    with pytest.raises(SupervisionSpecError, match="executable path"):
        supervisor.run(
            SupervisedProcessSpec(
                argv=("python", "-c", "print('unsafe')"),
                cwd=tmp_path.resolve(),
            )
        )

    with pytest.raises(SupervisionSpecError, match="environment key"):
        supervisor.run(
            SupervisedProcessSpec(
                argv=(str(PYTHON), str(WORKER), "--mode", "exit"),
                cwd=tmp_path.resolve(),
                environment={"PYTHONPATH": "/tmp/injected"},
            )
        )


def test_supervisor_source_never_enables_shell_or_preexec_hooks() -> None:
    source_path = SDK_SRC / "runner_protocol_v2" / "supervision.py"
    source = source_path.read_text(encoding="utf-8")
    tree = ast.parse(source)

    assert "shell=True" not in source
    assert "preexec_fn" not in source
    assert "start_new_session=True" in source

    popen_calls = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "Popen"
    ]
    assert len(popen_calls) == 1
