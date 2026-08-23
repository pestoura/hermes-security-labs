#!/usr/bin/env python3
from __future__ import annotations

import json

result = {
    "schema_version": 1,
    "status": "ok",
    "decision": "vulnerable",
    "provider": "agent",
    "action": "conversation-test",
    "profile": "promptme-direct-injection",
    "target_ref": "promptme",
    "scope": "laboratory",
    "control_id": None,
    "reason": "controlled PromptMe calibration detected the expected override",
    "vulnerable_signals": ["promptme.controlled_override"],
    "secure_signals": [],
    "inconclusive_signals": [],
    "evidence": [
        {"ref": "fixture/runtime", "kind": "chat-probe", "value": {"matched": True}, "redacted": True}
    ],
    "meta": {"laboratory": "promptme", "redaction": "enforced"},
}
print(json.dumps(result, sort_keys=True, separators=(",", ":")))
