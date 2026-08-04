#!/usr/bin/env python3
"""AI/MCP pack runner.

Stable JSON boundary between the security layer and a laboratory. The runner
is standard-library only so it can be copied verbatim into the Kali MCP
container and invoked as::

    python3 ai_mcp_runner.py execute --payload-b64 <urlsafe-base64-json>

The payload is a JSON object::

    {
      "schema_version": 1,
      "provider": "agent",
      "action": "conversation-test",
      "profile": "promptme-direct-injection",
      "target_ref": "promptme",
      "scope": "laboratory",
      "control_id": "AIMCP-DIRECTPROMPTINJECTION-001",
      "arguments": {"base_url": "http://target:8080"}
    }

Execution mode is ``dry-run`` by default; set
``SECURITY_RUNBOOK_EXECUTION_MODE=enabled`` (or pass ``--force``) to execute.

Exit codes: ``0`` result produced (any decision), ``2`` malformed invocation.
Prompt text, runtime responses and synthetic markers are never emitted: every
result is sanitised before printing.
"""

from __future__ import annotations

import argparse
import base64
import binascii
import json
import os
import sys
from pathlib import Path
from typing import Any

_SRC = Path(__file__).resolve().parents[1] / "src"
if _SRC.is_dir() and str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from ai_mcp_runbooks.contracts import Decision, ExecutionRequest, ExecutionResult, Status  # noqa: E402
from ai_mcp_runbooks.dispatch import dispatch, sanitize_result  # noqa: E402

EXECUTION_MODE_ENV = "SECURITY_RUNBOOK_EXECUTION_MODE"


def _emit(document: dict[str, Any]) -> None:
    print(json.dumps(document, sort_keys=True, separators=(",", ": ")))


def fail(message: str) -> None:
    _emit({"schema_version": 1, "status": "error", "decision": "inconclusive", "reason": message})
    raise SystemExit(2)


def decode_payload(encoded: str) -> Any:
    try:
        raw = base64.urlsafe_b64decode(encoded.encode())
        return json.loads(raw)
    except (binascii.Error, ValueError, UnicodeDecodeError) as exc:
        fail(f"invalid payload: {exc}")
        raise  # unreachable, keeps type checkers happy


def dry_run_result(payload: Any) -> dict[str, Any]:
    try:
        request = ExecutionRequest.from_payload(payload)
    except ValueError as exc:
        return sanitize_result(ExecutionResult.error(f"invalid request: {exc}"))
    return sanitize_result(
        ExecutionResult(
            status=Status.DRY_RUN,
            decision=Decision.NOT_APPLICABLE,
            provider=request.provider,
            action=request.action,
            profile=request.profile,
            target_ref=request.target_ref,
            scope=request.scope,
            control_id=request.control_id,
            reason=f"dry-run: set {EXECUTION_MODE_ENV}=enabled to execute",
            meta={"execution_mode": "dry-run"},
        )
    )


def execute(payload: Any, force: bool = False) -> dict[str, Any]:
    mode = os.environ.get(EXECUTION_MODE_ENV, "dry-run")
    if not force and mode != "enabled":
        return dry_run_result(payload)
    return dispatch(payload)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="AI/MCP pack runner")
    sub = parser.add_subparsers(dest="command", required=True)
    run = sub.add_parser("execute", help="execute an encoded handler request")
    run.add_argument("--payload-b64", required=True)
    run.add_argument(
        "--force",
        action="store_true",
        help=f"execute even when {EXECUTION_MODE_ENV} is not 'enabled'",
    )
    handlers = sub.add_parser("handlers", help="list the allowed handler catalogue")
    handlers.set_defaults(command="handlers")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "handlers":
        from ai_mcp_runbooks.policy import ALLOWED_HANDLERS

        _emit(
            {
                "schema_version": 1,
                "handlers": [
                    {"provider": provider, "action": action, "implemented": implemented}
                    for (provider, action), implemented in sorted(ALLOWED_HANDLERS.items())
                ],
            }
        )
        return 0
    payload = decode_payload(args.payload_b64)
    _emit(execute(payload, force=bool(getattr(args, "force", False))))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
