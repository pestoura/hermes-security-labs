#!/usr/bin/env python3
"""Vendor-neutral JSON-lines conformance harness for Runner Protocol v2 adapters.

The harness starts a candidate command in a disposable process and exchanges
language-neutral JSON control messages over stdin/stdout. It never invokes real
security tooling and must be executed in an isolated sandbox for third-party adapters.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import selectors
import shlex
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import jsonschema

from validate_protocol import request_fingerprint, validate_semantics

ROOT = Path(__file__).resolve().parent
REPORT_SCHEMA = ROOT / "schemas" / "conformance-report.schema.json"
REFERENCE_ADAPTER = ROOT / "fixtures" / "reference_adapter.py"
PROTOCOL_VERSION = "2.0.0"
EXCHANGE_TIMEOUT_SECONDS = 5.0
SECRET_CANARY = "RUNNER_PROTOCOL_CONFORMANCE_SECRET_CANARY_7F3A"

CAMPAIGN_ID = "11111111-1111-4111-8111-111111111111"
RUN_ID = "22222222-2222-4222-8222-222222222222"
STEP_ID = "33333333-3333-4333-8333-333333333333"


class ConformanceError(RuntimeError):
    """Raised when a candidate violates the conformance transport or protocol."""


@dataclass
class CandidateProcess:
    command: list[str]
    adapter_id: str
    process: subprocess.Popen[str] | None = None
    stderr_text: str = ""

    def __enter__(self) -> CandidateProcess:
        env = dict(os.environ)
        env["RUNNER_CONFORMANCE_SECRET_CANARY"] = SECRET_CANARY
        self.process = subprocess.Popen(
            self.command,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
            env=env,
        )
        return self

    def exchange(self, payload: dict[str, Any]) -> dict[str, Any]:
        if self.process is None or self.process.stdin is None or self.process.stdout is None:
            raise ConformanceError("candidate process is not running")
        if self.process.poll() is not None:
            raise ConformanceError(
                f"candidate exited before exchange with code {self.process.returncode}"
            )

        self.process.stdin.write(json.dumps(payload, sort_keys=True) + "\n")
        self.process.stdin.flush()

        selector = selectors.DefaultSelector()
        selector.register(self.process.stdout, selectors.EVENT_READ)
        events = selector.select(EXCHANGE_TIMEOUT_SECONDS)
        selector.close()
        if not events:
            raise ConformanceError("candidate response timed out")

        line = self.process.stdout.readline()
        if not line:
            raise ConformanceError("candidate closed stdout without a response")
        try:
            response = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ConformanceError("candidate returned invalid JSON") from exc
        if not isinstance(response, dict):
            raise ConformanceError("candidate response must be a JSON object")
        if SECRET_CANARY in json.dumps(response, sort_keys=True):
            raise ConformanceError("candidate leaked the conformance secret canary")
        return response

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> None:
        if self.process is None:
            return
        try:
            if self.process.poll() is None:
                try:
                    self.exchange({"action": "shutdown"})
                except ConformanceError:
                    self.process.terminate()
            _, stderr = self.process.communicate(timeout=2)
        except subprocess.TimeoutExpired:
            self.process.kill()
            _, stderr = self.process.communicate()
        self.stderr_text = stderr or ""
        if SECRET_CANARY in self.stderr_text:
            raise ConformanceError("candidate leaked the conformance secret canary to stderr")


def _correlation(attempt: str) -> dict[str, str]:
    return {
        "campaign_id": CAMPAIGN_ID,
        "run_id": RUN_ID,
        "step_id": STEP_ID,
        "attempt_id": attempt,
    }


def _request(
    capability_id: str,
    *,
    attempt: str,
    idempotency_key: str,
    input_data: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "message_type": "runner.step.request",
        "protocol_version": PROTOCOL_VERSION,
        "correlation": _correlation(attempt),
        "emitted_at": "2026-08-06T06:00:00Z",
        "authorization_ref": "authz/conformance/active",
        "idempotency_key": idempotency_key,
        "operation": {
            "capability_id": capability_id,
            "input": input_data or {"target_ref": "lab://conformance"},
        },
        "timeout_budget": {"soft_timeout_ms": 1000, "hard_timeout_ms": 5000},
        "retry_policy": {
            "max_attempts": 2,
            "retryable_error_codes": ["TRANSIENT_DEPENDENCY", "RUNNER_UNAVAILABLE"],
        },
        "cancellation_policy": {
            "mode": "cooperative_then_force",
            "grace_period_ms": 500,
        },
        "progress_mode": "optional",
    }


def _cancel(correlation: dict[str, str]) -> dict[str, Any]:
    return {
        "message_type": "runner.cancellation.request",
        "protocol_version": PROTOCOL_VERSION,
        "correlation": correlation,
        "emitted_at": "2026-08-06T06:00:01Z",
        "reason": "operator",
        "requested_by": "control_plane",
    }


def _messages(response: dict[str, Any]) -> list[dict[str, Any]]:
    messages = response.get("messages")
    if not isinstance(messages, list) or not messages:
        raise ConformanceError("candidate response must contain a non-empty messages list")
    for message in messages:
        if not isinstance(message, dict):
            raise ConformanceError("candidate messages must be JSON objects")
        validate_semantics(message)
    return messages


def _single_message(response: dict[str, Any], message_type: str) -> dict[str, Any]:
    messages = _messages(response)
    if len(messages) != 1 or messages[0].get("message_type") != message_type:
        raise ConformanceError(f"expected one {message_type} message")
    return messages[0]


def _stats(candidate: CandidateProcess) -> dict[str, int]:
    response = candidate.exchange({"action": "stats"})
    stats = response.get("stats")
    if not isinstance(stats, dict):
        raise ConformanceError("candidate stats response is missing")
    effect_count = stats.get("effect_count")
    ledger_entries = stats.get("ledger_entries")
    if not isinstance(effect_count, int) or effect_count < 0:
        raise ConformanceError("effect_count must be a non-negative integer")
    if not isinstance(ledger_entries, int) or ledger_entries < 0:
        raise ConformanceError("ledger_entries must be a non-negative integer")
    return {"effect_count": effect_count, "ledger_entries": ledger_entries}


def _dispatch(candidate: CandidateProcess, request: dict[str, Any]) -> dict[str, Any]:
    validate_semantics(request)
    return candidate.exchange({"action": "dispatch", "message": request})


def _evidence_digest(value: Any) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _case_success_and_correlation(candidate: CandidateProcess) -> dict[str, Any]:
    request = _request(
        "conformance.effect.success",
        attempt="44444444-4444-4444-8444-444444444444",
        idempotency_key="conformance:success:0001",
    )
    outcome = _single_message(_dispatch(candidate, request), "runner.outcome")
    if outcome["status"] != "PASS":
        raise ConformanceError("success capability did not return PASS")
    if outcome["correlation"] != request["correlation"]:
        raise ConformanceError("terminal outcome did not preserve all correlation identifiers")
    stats = _stats(candidate)
    if stats["effect_count"] != 1:
        raise ConformanceError("success capability did not produce exactly one effect")
    return {"outcome": outcome, "stats": stats}


def _case_idempotent_replay(candidate: CandidateProcess) -> dict[str, Any]:
    first = _request(
        "conformance.effect.replay",
        attempt="55555555-5555-4555-8555-555555555555",
        idempotency_key="conformance:replay:0001",
    )
    retry = json.loads(json.dumps(first))
    retry["correlation"]["attempt_id"] = "66666666-6666-4666-8666-666666666666"
    retry["emitted_at"] = "2026-08-06T06:00:02Z"
    if request_fingerprint(first) != request_fingerprint(retry):
        raise ConformanceError("logical retry fingerprint changed across attempts")

    first_outcome = _single_message(_dispatch(candidate, first), "runner.outcome")
    after_first = _stats(candidate)
    retry_outcome = _single_message(_dispatch(candidate, retry), "runner.outcome")
    after_retry = _stats(candidate)
    if first_outcome["status"] != "PASS" or retry_outcome["status"] != "PASS":
        raise ConformanceError("idempotency replay did not return the successful outcome")
    if retry_outcome["correlation"] != retry["correlation"]:
        raise ConformanceError("replay outcome did not use the retry attempt correlation")
    if after_retry["effect_count"] != after_first["effect_count"]:
        raise ConformanceError("idempotent replay duplicated an effect")
    return {"first": first_outcome, "retry": retry_outcome, "stats": after_retry}


def _case_idempotency_conflict(candidate: CandidateProcess) -> dict[str, Any]:
    original = _request(
        "conformance.effect.conflict",
        attempt="77777777-7777-4777-8777-777777777777",
        idempotency_key="conformance:conflict:0001",
        input_data={"target_ref": "lab://first"},
    )
    changed = json.loads(json.dumps(original))
    changed["correlation"]["attempt_id"] = "88888888-8888-4888-8888-888888888888"
    changed["operation"]["input"]["target_ref"] = "lab://changed"

    _single_message(_dispatch(candidate, original), "runner.outcome")
    before = _stats(candidate)
    outcome = _single_message(_dispatch(candidate, changed), "runner.outcome")
    after = _stats(candidate)
    if outcome["status"] != "REFUSED":
        raise ConformanceError("changed effect under the same key was not refused")
    error = outcome.get("error") or {}
    if error.get("code") != "IDEMPOTENCY_CONFLICT":
        raise ConformanceError("conflicting request used the wrong normalized error")
    if after["effect_count"] != before["effect_count"]:
        raise ConformanceError("idempotency conflict produced an effect")
    return {"outcome": outcome, "stats": after}


def _case_hard_timeout(candidate: CandidateProcess) -> dict[str, Any]:
    request = _request(
        "conformance.timeout.hard",
        attempt="99999999-9999-4999-8999-999999999999",
        idempotency_key="conformance:timeout:0001",
    )
    outcome = _single_message(_dispatch(candidate, request), "runner.outcome")
    if outcome["status"] != "TIMED_OUT":
        raise ConformanceError("hard-timeout capability did not return TIMED_OUT")
    if (outcome.get("error") or {}).get("code") != "TIMEOUT_HARD":
        raise ConformanceError("hard timeout used the wrong normalized error")
    return {"outcome": outcome}


def _case_cooperative_cancellation(candidate: CandidateProcess) -> dict[str, Any]:
    request = _request(
        "conformance.cancel.wait",
        attempt="aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
        idempotency_key="conformance:cancel:0001",
    )
    progress = _single_message(_dispatch(candidate, request), "runner.progress")
    cancellation = _cancel(request["correlation"])
    validate_semantics(cancellation)
    response = candidate.exchange({"action": "cancel", "message": cancellation})
    messages = _messages(response)
    if [message["message_type"] for message in messages] != [
        "runner.cancellation.ack",
        "runner.outcome",
    ]:
        raise ConformanceError("cancellation must return acknowledgement then terminal outcome")
    acknowledgement, outcome = messages
    if acknowledgement["status"] != "accepted" or outcome["status"] != "CANCELLED":
        raise ConformanceError("cooperative cancellation did not terminate as CANCELLED")
    if outcome["correlation"] != progress["correlation"]:
        raise ConformanceError("cancellation outcome lost correlation")
    return {"progress": progress, "ack": acknowledgement, "outcome": outcome}


def _case_normalized_transient_error(candidate: CandidateProcess) -> dict[str, Any]:
    request = _request(
        "conformance.error.transient",
        attempt="bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb",
        idempotency_key="conformance:error:0001",
    )
    outcome = _single_message(_dispatch(candidate, request), "runner.outcome")
    error = outcome.get("error") or {}
    if outcome["status"] != "ERROR":
        raise ConformanceError("transient error capability did not return ERROR")
    if error.get("code") != "TRANSIENT_DEPENDENCY" or error.get("retryable") is not True:
        raise ConformanceError("transient error taxonomy is inconsistent")
    return {"outcome": outcome}


CASES = (
    ("correlation-and-evidence", _case_success_and_correlation),
    ("idempotent-replay", _case_idempotent_replay),
    ("idempotency-conflict", _case_idempotency_conflict),
    ("hard-timeout", _case_hard_timeout),
    ("cooperative-cancellation", _case_cooperative_cancellation),
    ("normalized-transient-error", _case_normalized_transient_error),
)


def run_conformance(command: list[str], adapter_id: str) -> dict[str, Any]:
    """Run all conformance cases and return a sanitized machine-readable report."""
    report: dict[str, Any] = {
        "schema_version": "1.0",
        "protocol_version": PROTOCOL_VERSION,
        "adapter_id": adapter_id,
        "command_sha256": hashlib.sha256("\0".join(command).encode()).hexdigest(),
        "verdict": "PASS",
        "cases": [],
    }

    try:
        with CandidateProcess(command, adapter_id) as candidate:
            reset = candidate.exchange({"action": "reset"})
            if reset != {"status": "reset"}:
                raise ConformanceError("candidate did not acknowledge reset")
            for case_id, case in CASES:
                try:
                    evidence = case(candidate)
                except Exception as exc:  # conformance must report, not abort at first case
                    report["verdict"] = "FAIL"
                    report["cases"].append(
                        {
                            "case_id": case_id,
                            "status": "FAIL",
                            "detail": str(exc)[:512],
                        }
                    )
                else:
                    report["cases"].append(
                        {
                            "case_id": case_id,
                            "status": "PASS",
                            "evidence_sha256": _evidence_digest(evidence),
                        }
                    )
    except Exception as exc:
        report["verdict"] = "ERROR"
        report["transport_error"] = str(exc)[:512]

    schema = json.loads(REPORT_SCHEMA.read_text(encoding="utf-8"))
    jsonschema.validate(report, schema)
    return report


def self_test() -> None:
    reference = [sys.executable, str(REFERENCE_ADAPTER)]
    passing = run_conformance(reference, "reference-adapter")
    if passing["verdict"] != "PASS":
        raise ConformanceError(f"reference adapter failed: {passing}")

    duplicate = run_conformance(
        [sys.executable, str(REFERENCE_ADAPTER), "--mode", "duplicate-effects"],
        "broken-duplicate-effects",
    )
    if duplicate["verdict"] != "FAIL":
        raise ConformanceError("duplicate-effect adapter was not rejected")

    leaking = run_conformance(
        [sys.executable, str(REFERENCE_ADAPTER), "--mode", "secret-leak"],
        "broken-secret-leak",
    )
    if leaking["verdict"] not in {"FAIL", "ERROR"}:
        raise ConformanceError("secret-leaking adapter was not rejected")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--command", help="candidate command using JSON-lines conformance control")
    parser.add_argument("--adapter-id", default="candidate")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()

    if args.self_test:
        self_test()
        print("RUNNER_CONFORMANCE_KIT_OK")
        return 0
    if not args.command:
        parser.error("--command is required unless --self-test is used")

    report = run_conformance(shlex.split(args.command), args.adapter_id)
    serialized = json.dumps(report, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.write_text(serialized, encoding="utf-8")
    else:
        print(serialized, end="")
    return 0 if report["verdict"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
