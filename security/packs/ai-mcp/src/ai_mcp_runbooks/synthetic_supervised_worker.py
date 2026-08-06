#!/usr/bin/env python3
"""Fixed synthetic worker for AI/MCP Runner Protocol supervision tests."""

from __future__ import annotations

import argparse
import os
import signal
import subprocess
import sys
import time
from pathlib import Path


def _ignore_termination() -> None:
    signal.signal(signal.SIGTERM, signal.SIG_IGN)


def _spawn_stubborn_descendant(pid_file: Path) -> None:
    child = subprocess.Popen(  # noqa: S603 - fixed interpreter and worker path
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
            raise RuntimeError("synthetic descendant exited before readiness")
        if time.monotonic() >= deadline:
            child.kill()
            child.wait()
            raise RuntimeError("synthetic descendant readiness timed out")
        time.sleep(0.01)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--mode",
        required=True,
        choices={
            "success",
            "execution-fail",
            "ignore-term",
            "spawn-and-exit",
            "stubborn-child",
        },
    )
    parser.add_argument("--pid-file", type=Path)
    parser.add_argument("--ready-file", type=Path)
    args = parser.parse_args()

    if args.mode == "success":
        print("synthetic-ai-mcp-supervised-success", flush=True)
        return 0

    if args.mode == "execution-fail":
        print("synthetic-ai-mcp-supervised-failure", file=sys.stderr, flush=True)
        return 9

    if args.mode == "ignore-term":
        if args.ready_file is None:
            parser.error("--ready-file is required for ignore-term")
        _ignore_termination()
        args.ready_file.write_text(f"{os.getpid()}\n", encoding="utf-8")
        while True:
            time.sleep(1)

    if args.mode == "stubborn-child":
        if args.pid_file is None:
            parser.error("--pid-file is required for stubborn-child")
        _ignore_termination()
        args.pid_file.write_text(f"{os.getpid()}\n", encoding="utf-8")
        while True:
            time.sleep(1)

    if args.pid_file is None:
        parser.error("--pid-file is required for spawn-and-exit")
    _spawn_stubborn_descendant(args.pid_file)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
