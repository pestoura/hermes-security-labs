#!/usr/bin/env python3
"""Deterministic in-memory adapter used only to self-test the conformance kit."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import uuid
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from validate_protocol import request_fingerprint, validate_semantics  # noqa: E402

PROTOCOL_VERSION = "2.0.0"
STARTED_AT = "2026-08-06T06:00:00Z"
FINISHED_AT = "2026-08-06T06:00:01Z"


def _evidence(key: str, status: str, kind: str = "protocol") -> dict[str, Any]:
    digest = hashlib.sha256(f"{key}:{status}:{kind}".encode()).hexdigest()
    evidence_id = str(uuid.uuid5(uuid.NAMESPACE_URL, f"runner-conformance:{digest}"))
    return {
        "evidence_id": evidence_id,
        "kind": kind,
        "classification": "INTERNAL",
        "sha256": digest,
        "uri": f"evidence://runner-conformance/{evidence_id}",
    }


def _outcome(
    correlation: dict[str, str],
    status: str,
    key: str,
    *,
    error: dict[str, Any] | None = None,
    output: dict[str, Any] | None = None,
) -> dict[str, Any]:
    message: dict[str, Any] = {
        "message_type": "runner.outcome",
        "protocol_version": PROTOCOL_VERSION,
        "correlation": correlation,
        "emitted_at": FINISHED_AT,
        "status": status,
        "started_at": STARTED_AT,
        "finished_at": FINISHED_AT,
        "evidence_refs": [_evidence(key, status)],
    }
    if output is not None:
        message["output"] = output
    if error is not None:
        message["error"] = error
    validate_semantics(message)
    return message


def _progress(correlation: dict[str, str]) -> dict[str, Any]:
    message = {
        "message_type": "runner.progress",
        "protocol_version": PROTOCOL_VERSION,
        "correlation": correlation,
        "emitted_at": STARTED_AT,
        "sequence": 1,
        "state": "accepted",
        "percent": 0,
        "message": "Accepted by the isolated conformance adapter",
    }
    validate_semantics(message)
    return message


def _ack(correlation: dict[str, str], status: str = "accepted") -> dict[str, Any]:
    message = {
        "message_type": "runner.cancellation.ack",
        "protocol_version": PROTOCOL_VERSION,
        "correlation": correlation,
        "emitted_at": FINISHED_AT,
        "status": status,
    }
    validate_semantics(message)
    return message


class ReferenceAdapter:
    def __init__(self, mode: str) -> None:
        self.mode = mode
        self.effect_count = 0
        self.ledger: dict[str, dict[str, Any]] = {}
        self.pending: dict[str, dict[str, Any]] = {}

    def reset(self) -> dict[str, str]:
        self.effect_count = 0
        self.ledger.clear()
        self.pending.clear()
        return {"status": "reset"}

    def stats(self) -> dict[str, Any]:
        return {
            "stats": {
                "effect_count": self.effect_count,
                "ledger_entries": len(self.ledger),
            }
        }

    def _decorate_output(self, output: dict[str, Any]) -> dict[str, Any]:
        if self.mode == "secret-leak":
            output = dict(output)
            output["debug"] = os.environ.get(
                "RUNNER_CONFORMANCE_SECRET_CANARY", "missing-canary"
            )
        return output

    def dispatch(self, request: dict[str, Any]) -> dict[str, Any]:
        validate_semantics(request)
        key = request["idempotency_key"]
        fingerprint = request_fingerprint(request)
        correlation = request["correlation"]
        capability = request["operation"]["capability_id"]

        existing = self.ledger.get(key)
        if existing is not None:
            if existing["fingerprint"] != fingerprint:
                outcome = _outcome(
                    correlation,
                    "REFUSED",
                    key,
                    error={
                        "code": "IDEMPOTENCY_CONFLICT",
                        "category": "conflict",
                        "retryable": False,
                        "message": "Idempotency key already identifies another effect",
                    },
                )
                return {"messages": [outcome]}
            if self.mode == "duplicate-effects":
                self.effect_count += 1
            outcome = _outcome(
                correlation,
                existing["status"],
                key,
                error=existing.get("error"),
                output=self._decorate_output(existing.get("output") or {}),
            )
            return {"messages": [outcome]}

        if capability == "conformance.cancel.wait":
            self.pending[key] = {
                "correlation": correlation,
                "fingerprint": fingerprint,
            }
            return {"messages": [_progress(correlation)]}

        if capability == "conformance.timeout.hard":
            outcome = _outcome(
                correlation,
                "TIMED_OUT",
                key,
                error={
                    "code": "TIMEOUT_HARD",
                    "category": "timeout",
                    "retryable": False,
                    "message": "Hard timeout budget expired",
                },
            )
            self.ledger[key] = {
                "fingerprint": fingerprint,
                "status": "TIMED_OUT",
                "error": outcome["error"],
            }
            return {"messages": [outcome]}

        if capability == "conformance.error.transient":
            outcome = _outcome(
                correlation,
                "ERROR",
                key,
                error={
                    "code": "TRANSIENT_DEPENDENCY",
                    "category": "dependency",
                    "retryable": True,
                    "message": "Dependency temporarily unavailable",
                },
            )
            self.ledger[key] = {
                "fingerprint": fingerprint,
                "status": "ERROR",
                "error": outcome["error"],
            }
            return {"messages": [outcome]}

        self.effect_count += 1
        output = self._decorate_output({"result": "sanitized-success"})
        outcome = _outcome(correlation, "PASS", key, output=output)
        self.ledger[key] = {
            "fingerprint": fingerprint,
            "status": "PASS",
            "output": {"result": "sanitized-success"},
        }
        return {"messages": [outcome]}

    def cancel(self, request: dict[str, Any]) -> dict[str, Any]:
        validate_semantics(request)
        correlation = request["correlation"]
        pending_key = next(
            (
                key
                for key, value in self.pending.items()
                if value["correlation"] == correlation
            ),
            None,
        )
        if pending_key is None:
            return {"messages": [_ack(correlation, "not_found")]}

        self.pending.pop(pending_key)
        acknowledgement = _ack(correlation)
        outcome = _outcome(
            correlation,
            "CANCELLED",
            pending_key,
            error={
                "code": "CANCELLED",
                "category": "cancellation",
                "retryable": False,
                "message": "Execution cancelled cooperatively",
            },
        )
        self.ledger[pending_key] = {
            "fingerprint": "cancelled-pending",
            "status": "CANCELLED",
            "error": outcome["error"],
        }
        return {"messages": [acknowledgement, outcome]}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--mode",
        choices=("conformant", "duplicate-effects", "secret-leak"),
        default="conformant",
    )
    args = parser.parse_args()
    adapter = ReferenceAdapter(args.mode)

    for line in sys.stdin:
        try:
            payload = json.loads(line)
            action = payload.get("action")
            if action == "reset":
                response = adapter.reset()
            elif action == "stats":
                response = adapter.stats()
            elif action == "dispatch":
                response = adapter.dispatch(payload["message"])
            elif action == "cancel":
                response = adapter.cancel(payload["message"])
            elif action == "shutdown":
                print(json.dumps({"status": "shutdown"}), flush=True)
                return 0
            else:
                response = {"transport_error": "unsupported conformance action"}
        except Exception as exc:
            response = {"transport_error": str(exc)[:256]}
        print(json.dumps(response, sort_keys=True), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
