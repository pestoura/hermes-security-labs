#!/usr/bin/env python3
"""Synthetic worker used only by process-supervision tests."""

from __future__ import annotations

import argparse
import os
import signal
import subprocess
import sys
import time
from pathlib import Path


def _ignore_term() -> None:
    signal.signal(signal.SIGTERM, signal.SIG_IGN)


def _write_pid(path: Path, pid: int) -> None:
    path.write_text(f"{pid}\n", encoding="utf-8")


def _spawn_stubborn_child(pid_file: Path) -> subprocess.Popen[bytes]:
    child = subprocess.Popen(  # noqa: S603 - fixed test worker invocation
        [
            str(Path(sys.executable).resolve()),
            str(Path(__file__).resolve()),
            "--mode",
            "stubborn-child",
            "--pid-file",
            str(pid_file),
        ],
        stdin=subprocess.DEVNULL,
        stdout=None,
        stderr=None,
        close_fds=True,
    )
    deadline = time.monotonic() + 2
    while not pid_file.is_file():
        if child.poll() is not None:
            raise RuntimeError("stubborn child exited before readiness")
        if time.monotonic() >= deadline:
            child.kill()
            child.wait()
            raise RuntimeError("stubborn child readiness timed out")
        time.sleep(0.01)
    return child


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--mode",
        required=True,
        choices={
            "exit",
            "ignore-term",
            "output",
            "spawn-and-wait",
            "spawn-and-exit",
            "stubborn-child",
        },
    )
    parser.add_argument("--pid-file", type=Path)
    parser.add_argument("--bytes", type=int, default=0)
    args = parser.parse_args()

    if args.mode == "exit":
        print("supervised-worker-ok", flush=True)
        return 0

    if args.mode == "ignore-term":
        _ignore_term()
        while True:
            time.sleep(1)

    if args.mode == "stubborn-child":
        if args.pid_file is None:
            parser.error("--pid-file is required for stubborn-child")
        _ignore_term()
        _write_pid(args.pid_file, os.getpid())
        while True:
            time.sleep(1)

    if args.mode == "output":
        chunk = b"x" * max(0, args.bytes)
        sys.stdout.buffer.write(chunk)
        sys.stdout.buffer.flush()
        sys.stderr.buffer.write(chunk)
        sys.stderr.buffer.flush()
        return 0

    if args.pid_file is None:
        parser.error("--pid-file is required for child-spawning modes")
    _spawn_stubborn_child(args.pid_file)

    if args.mode == "spawn-and-exit":
        return 0

    _ignore_term()
    while True:
        time.sleep(1)


if __name__ == "__main__":
    raise SystemExit(main())
