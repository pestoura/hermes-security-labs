"""Allowlisted local command execution.

No command is ever assembled from payload text. Callers select a named probe
from :data:`PROBES`; the module renders a fixed ``argv`` list and executes it
with ``shell=False``, a hard timeout and a bounded output buffer.
"""

from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass
from typing import Any, Protocol

#: Executables the pack may invoke. Everything else is refused.
ALLOWED_BINARIES = frozenset({"curl"})

DEFAULT_TIMEOUT_SECONDS = 20
MAX_CAPTURE_BYTES = 262144


class CommandError(RuntimeError):
    """Raised when a command cannot be executed under the policy."""


@dataclass(frozen=True)
class CommandResult:
    """Raw (unsanitised) result of a local command."""

    argv: tuple[str, ...]
    exit_code: int
    stdout: str
    stderr: str
    timed_out: bool = False

    @property
    def ok(self) -> bool:
        return self.exit_code == 0 and not self.timed_out


class CommandRunner(Protocol):
    def run(self, argv: list[str], timeout: int = DEFAULT_TIMEOUT_SECONDS) -> CommandResult: ...


@dataclass
class LocalCommandRunner:
    """Execute an allowlisted binary locally without a shell."""

    timeout: int = DEFAULT_TIMEOUT_SECONDS

    def run(self, argv: list[str], timeout: int | None = None) -> CommandResult:
        if not argv:
            raise CommandError("empty argv")
        binary = argv[0]
        if binary not in ALLOWED_BINARIES:
            raise CommandError(f"binary {binary!r} is not allowlisted")
        if shutil.which(binary) is None:
            raise CommandError(f"binary {binary!r} is not available on this host")
        effective_timeout = int(timeout or self.timeout)
        try:
            completed = subprocess.run(  # noqa: S603 - argv is allowlisted, shell=False
                argv,
                capture_output=True,
                text=True,
                timeout=effective_timeout,
                check=False,
                shell=False,
            )
        except subprocess.TimeoutExpired:
            return CommandResult(tuple(argv), exit_code=124, stdout="", stderr="timeout", timed_out=True)
        return CommandResult(
            argv=tuple(argv),
            exit_code=completed.returncode,
            stdout=(completed.stdout or "")[:MAX_CAPTURE_BYTES],
            stderr=(completed.stderr or "")[:MAX_CAPTURE_BYTES],
        )


def build_http_probe(
    base_url: str,
    path: str,
    timeout: int = DEFAULT_TIMEOUT_SECONDS,
    max_bytes: int = 65536,
) -> list[str]:
    """Build a fixed, read-only HTTP GET probe.

    ``base_url`` and ``path`` are validated by the caller against the target
    allowlist; only ``http`` against the isolated laboratory network is used.
    """

    if not base_url.startswith("http://") and not base_url.startswith("https://"):
        raise CommandError("probe base_url must be http(s)")
    if not path.startswith("/"):
        raise CommandError("probe path must start with '/'")
    url = base_url.rstrip("/") + path
    return [
        "curl",
        "--silent",
        "--show-error",
        "--get",
        "--location",
        "--max-time",
        str(int(timeout)),
        "--max-filesize",
        str(int(max_bytes)),
        "--write-out",
        "\\n__HTTP_STATUS__:%{http_code}",
        url,
    ]


def parse_http_status(stdout: str) -> tuple[int | None, str]:
    """Split the curl write-out marker from the body.

    Returns ``(status_code, body)``; ``status_code`` is ``None`` when the
    marker is absent (connection failure).
    """

    marker = "__HTTP_STATUS__:"
    index = stdout.rfind(marker)
    if index == -1:
        return None, stdout
    body = stdout[:index].rstrip("\n")
    raw = stdout[index + len(marker):].strip()
    try:
        status = int(raw)
    except ValueError:
        return None, body
    # curl writes 000 when the transfer never produced an HTTP response.
    return (status if status > 0 else None), body


def describe(result: CommandResult) -> dict[str, Any]:
    """Non-sensitive description of a command execution."""

    return {
        "binary": result.argv[0] if result.argv else "",
        "exit_code": result.exit_code,
        "timed_out": result.timed_out,
        "stdout_bytes": len(result.stdout),
        "stderr_bytes": len(result.stderr),
    }
