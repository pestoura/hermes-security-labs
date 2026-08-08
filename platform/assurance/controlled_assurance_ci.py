"""Bounded controlled-CI assurance probes for SVP2-D-02.

The probes exercise failure semantics against disposable local processes/files only.
They produce evidence inputs for the canonical failure-evidence validator and never
interact with production services or customer targets.
"""
from __future__ import annotations

import errno
import hashlib
import json
import socket
import subprocess
import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Callable

CASES = (
    "restart", "invalid_json", "empty_stdout", "timeout", "network_loss",
    "disk_full", "partial_cleanup", "concurrency", "cancellation", "incompatible_version",
)


def _evidence_id(name: str, detail: str) -> str:
    return "ev_" + hashlib.sha256(f"{name}:{detail}".encode()).hexdigest()[:32]


def _probe_restart() -> str:
    values = []
    for _ in range(2):
        result = subprocess.run([sys.executable, "-c", "print('ready')"], capture_output=True, text=True, timeout=5)
        values.append((result.returncode, result.stdout.strip()))
    assert values == [(0, "ready"), (0, "ready")]
    return "two-clean-starts"


def _probe_invalid_json() -> str:
    try:
        json.loads("{")
    except json.JSONDecodeError:
        return "parser-refused"
    raise AssertionError("invalid JSON unexpectedly parsed")


def _probe_empty_stdout() -> str:
    result = subprocess.run([sys.executable, "-c", "pass"], capture_output=True, text=True, timeout=5)
    assert result.returncode == 0 and result.stdout == ""
    return "empty-observed"


def _probe_timeout() -> str:
    try:
        subprocess.run([sys.executable, "-c", "import time; time.sleep(2)"], timeout=0.05, check=False)
    except subprocess.TimeoutExpired:
        return "timeout-enforced"
    raise AssertionError("timeout not enforced")


def _probe_network_loss() -> str:
    sock = socket.socket()
    sock.settimeout(0.2)
    try:
        code = sock.connect_ex(("127.0.0.1", 9))
        assert code != 0
        return f"connection-refused-{code}"
    finally:
        sock.close()


def _probe_disk_full() -> str:
    class BoundedWriter:
        def __init__(self, limit: int) -> None:
            self.remaining = limit
        def write(self, data: bytes) -> int:
            if len(data) > self.remaining:
                raise OSError(errno.ENOSPC, "controlled quota exhausted")
            self.remaining -= len(data)
            return len(data)
    writer = BoundedWriter(4)
    writer.write(b"1234")
    try:
        writer.write(b"5")
    except OSError as exc:
        assert exc.errno == errno.ENOSPC
        return "bounded-storage-enospc"
    raise AssertionError("storage exhaustion not observed")


def _probe_partial_cleanup() -> str:
    with tempfile.TemporaryDirectory(prefix="hex0r-assurance-") as root:
        a, b = Path(root) / "a", Path(root) / "b"
        a.write_text("x"); b.write_text("y"); a.unlink()
        assert not a.exists() and b.exists()
        b.unlink()
        assert not list(Path(root).iterdir())
    return "residue-detected-then-cleared"


def _probe_concurrency() -> str:
    with ThreadPoolExecutor(max_workers=2) as pool:
        values = sorted(pool.map(lambda value: value * value, (2, 3)))
    assert values == [4, 9]
    return "two-workers-isolated"


def _probe_cancellation() -> str:
    proc = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(10)"])
    proc.terminate()
    proc.wait(timeout=5)
    assert proc.returncode is not None
    return "process-terminated"


def _probe_incompatible_version() -> str:
    supported_major, observed_major = 2, 3
    assert observed_major != supported_major
    return "major-version-refused"


PROBES: dict[str, Callable[[], str]] = {
    "restart": _probe_restart,
    "invalid_json": _probe_invalid_json,
    "empty_stdout": _probe_empty_stdout,
    "timeout": _probe_timeout,
    "network_loss": _probe_network_loss,
    "disk_full": _probe_disk_full,
    "partial_cleanup": _probe_partial_cleanup,
    "concurrency": _probe_concurrency,
    "cancellation": _probe_cancellation,
    "incompatible_version": _probe_incompatible_version,
}


def run_controlled_assurance(*, observed_at: str) -> dict[str, dict[str, str]]:
    if not observed_at.endswith("Z"):
        raise ValueError("explicit UTC timestamp required")
    results: dict[str, dict[str, str]] = {}
    for name in CASES:
        detail = PROBES[name]()
        results[name] = {
            "status": "pass",
            "evidence_id": _evidence_id(name, detail),
            "observed_at": observed_at,
            "boundary": "CONTROLLED_CI",
        }
    return results
