#!/usr/bin/env python3
"""Fixed supervised worker for the calibrated local PromptMe laboratory."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

_SRC = Path(__file__).resolve().parents[1]
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from ai_mcp_runbooks.dispatch import dispatch  # noqa: E402
from ai_mcp_runbooks.execution import HttpTransport  # noqa: E402

LIVE_BASE_URL = "http://127.0.0.1:8210"


def _fixed_request() -> dict[str, Any]:
    return {
        "schema_version": 1,
        "provider": "agent",
        "action": "conversation-test",
        "profile": "promptme-direct-injection",
        "target_ref": "promptme",
        "scope": "laboratory",
        "arguments": {"base_url": LIVE_BASE_URL},
    }


def execute_fixed_promptme(*, transport: HttpTransport | None = None) -> dict[str, Any]:
    """Execute only the fixed localhost PromptMe calibration path."""
    return dispatch(_fixed_request(), transport=transport)


def main() -> int:
    result = execute_fixed_promptme()
    sys.stdout.write(json.dumps(result, sort_keys=True, separators=(",", ":")))
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
