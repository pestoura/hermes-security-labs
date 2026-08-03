from __future__ import annotations

import argparse
import base64
import binascii
import json
import os
from typing import Any

ALLOWED = {('agent', 'conversation-test'), ('agent', 'agency-test'), ('agent', 'content-test'), ('memory', 'isolation-test'), ('agent', 'output-test'), ('mcp', 'security-test'), ('rag', 'poison-test'), ('agent', 'boundary-test'), ('agent', 'discover'), ('mcp', 'tool-poison-test')}


def fail(message: str) -> None:
    print(json.dumps({"status": "error", "error": message}))
    raise SystemExit(2)


def execute(request: dict[str, Any]) -> dict[str, Any]:
    pair = (request.get("provider"), request.get("action"))
    if pair not in ALLOWED:
        fail(f"provider/action {pair!r} is not allowed")
    mode = os.environ.get("SECURITY_RUNBOOK_EXECUTION_MODE", "dry-run")
    if mode != "enabled":
        return {
            "status": "dry-run",
            "provider": pair[0],
            "action": pair[1],
            "profile": request.get("profile"),
            "target_ref": request.get("arguments", {}).get("target_ref"),
        }
    return {
        "status": "not-implemented",
        "decision": "inconclusive",
        "reason": "adapter execution requires laboratory-specific calibration",
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--payload-b64", required=True)
    args = parser.parse_args()
    try:
        payload = base64.urlsafe_b64decode(args.payload_b64.encode())
        request = json.loads(payload)
    except (binascii.Error, UnicodeDecodeError, json.JSONDecodeError) as exc:
        fail(f"invalid payload: {exc}")
    print(json.dumps(execute(request), sort_keys=True))


if __name__ == "__main__":
    main()
