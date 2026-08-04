"""Frozen copy of the pre-calibration AI/MCP runner stub (issue #66 baseline).

This file is a *fixture*, not production code. It reproduces the behaviour of
``security/packs/ai-mcp/runner/ai_mcp_runner.py`` at commit
``76b955c25fbe24421d39ae1cd49a271dfb00865c`` so the differential test can prove
that the old dispatch path returned ``not-implemented`` for the exact payload
that the calibrated path now answers functionally.
"""

from __future__ import annotations

from typing import Any

ALLOWED = {
    ("agent", "conversation-test"),
    ("agent", "agency-test"),
    ("agent", "content-test"),
    ("memory", "isolation-test"),
    ("agent", "output-test"),
    ("mcp", "security-test"),
    ("rag", "poison-test"),
    ("agent", "boundary-test"),
    ("agent", "discover"),
    ("mcp", "tool-poison-test"),
}


def legacy_execute(request: dict[str, Any], mode: str = "enabled") -> dict[str, Any]:
    """Legacy stub behaviour for an allowed handler."""

    pair = (request.get("provider"), request.get("action"))
    if pair not in ALLOWED:
        return {"status": "error", "error": f"provider/action {pair!r} is not allowed"}
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
        "provider": pair[0],
        "action": pair[1],
        "profile": request.get("profile"),
        "target_ref": request.get("arguments", {}).get("target_ref") or request.get("profile"),
        "decision": "inconclusive",
        "vulnerable_signals": [],
        "secure_signals": [],
        "reason": "real adapter execution pending calibration",
    }
