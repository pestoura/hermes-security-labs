#!/usr/bin/env python3
"""Synthetic-process-only AI/MCP Runner Protocol v2 candidate.

The wrapper supplies a fixed AI/MCP worker to the shared repository-owned
supervised synthetic engine. It cannot invoke runtime handlers, MCP providers,
agents, memory/RAG adapters, networks or commands supplied by a request.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from runner_protocol_v2 import PosixProcessSupervisor, SQLiteIdempotencyLedger
from runner_protocol_v2.synthetic_supervised import (
    SyntheticSupervisedRunnerCandidate,
    ledger_path,
    serve_json_lines,
)

WORKER = Path(__file__).with_name("synthetic_supervised_worker.py").resolve()


class SupervisedSyntheticAiMcpRunnerCandidate(
    SyntheticSupervisedRunnerCandidate
):
    """Fixed-worker AI/MCP wrapper for synthetic conformance only."""

    def __init__(
        self,
        *,
        durable_ledger: SQLiteIdempotencyLedger,
        working_directory: Path | None = None,
        supervisor: PosixProcessSupervisor | None = None,
    ) -> None:
        if supervisor is None:
            super().__init__(
                family="ai-mcp",
                worker_path=WORKER,
                durable_ledger=durable_ledger,
                working_directory=working_directory,
            )
        else:
            super().__init__(
                family="ai-mcp",
                worker_path=WORKER,
                durable_ledger=durable_ledger,
                working_directory=working_directory,
                supervisor=supervisor,
            )


def _ledger_argument(value: str) -> Path:
    try:
        return ledger_path(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(str(exc)) from exc


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--conformance-only", action="store_true")
    parser.add_argument("--synthetic-process-only", action="store_true")
    parser.add_argument("--durable-ledger", type=_ledger_argument)
    args = parser.parse_args()

    if not args.conformance_only or not args.synthetic_process_only:
        parser.error(
            "--conformance-only and --synthetic-process-only are required; "
            "real execution is unavailable"
        )
    if args.durable_ledger is None:
        parser.error("--durable-ledger is required")

    try:
        ledger = SQLiteIdempotencyLedger(args.durable_ledger)
        candidate = SupervisedSyntheticAiMcpRunnerCandidate(
            durable_ledger=ledger,
        )
    except (OSError, RuntimeError, ValueError) as exc:
        parser.error(f"synthetic supervised candidate unavailable: {exc}")
    return serve_json_lines(candidate)


if __name__ == "__main__":
    raise SystemExit(main())
