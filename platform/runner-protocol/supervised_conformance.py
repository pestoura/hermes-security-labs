#!/usr/bin/env python3
"""Cross-family fixed-worker supervision conformance for Runner Protocol v2.

This harness executes only the three repository-owned synthetic adapters. It does not
accept candidate commands, invoke production runtimes, authorize customer work, or
connect to networks, scanners, pipelines, MCP providers, laboratories, or targets.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import tempfile
import uuid
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import jsonschema

ROOT = Path(__file__).resolve().parent
REPOSITORY_ROOT = ROOT.parents[1]
SDK_SRC = ROOT / "src"
if str(SDK_SRC) not in sys.path:
    sys.path.insert(0, str(SDK_SRC))

from conformance import CandidateProcess, ConformanceError  # noqa: E402
from runner_protocol_v2 import validate_semantics  # noqa: E402

PROTOCOL_VERSION = "2.0.0"
REPORT_SCHEMA = ROOT / "schemas" / "supervised-conformance-report.schema.json"
CONFORMANCE_AUTHORIZATION = "authz/conformance/active"
SECRET_CANARY = "RUNNER_PROTOCOL_CONFORMANCE_SECRET_CANARY_7F3A"

CAMPAIGN_ID = "11111111-1111-4111-8111-111111111111"
RUN_ID = "22222222-2222-4222-8222-222222222222"
STEP_ID = "33333333-3333-4333-8333-333333333333"

FAMILY_ADAPTERS: dict[str, Path] = {
    "api": (
        REPOSITORY_ROOT
        / "security/packs/api/src/api_pentest_runbooks/"
        "supervised_runner_protocol_adapter.py"
    ),
    "devsecops": (
        REPOSITORY_ROOT
        / "security/packs/devsecops/src/devsecops_runbooks/"
        "supervised_runner_protocol_adapter.py"
    ),
    "ai-mcp": (
        REPOSITORY_ROOT
        / "security/packs/ai-mcp/src/ai_mcp_runbooks/"
        "supervised_runner_protocol_adapter.py"
    ),
}

CALLER_SHAPED_INPUT: dict[str, Any] = {
    "target_ref": "lab://supervised-parity",
    "executable": "/bin/sh",
    "argv": ["-c", "exit 99"],
    "cwd": "/",
    "environment": {"UNTRUSTED": "1"},
    "worker_mode": "caller-controlled",
}

RAW_PROCESS_KEYS = frozenset(
    {
        "stdout",
        "stderr",
        "command",
        "executable",
        "argv",
        "cwd",
        "environment",
        "worker_mode",
    }
)


@dataclass(frozen=True)
class CaseSpec:
    case_id: str
    execute: Callable[[CandidateProcess], list[dict[str, Any]]]
    expected_effect_delta: int
    expected_ledger_delta: int


def _stable_uuid(label: str) -> str:
    return str(uuid.uuid5(uuid.NAMESPACE_URL, f"runner-supervised-parity:{label}"))


def _correlation(label: str) -> dict[str, str]:
    return {
        "campaign_id": CAMPAIGN_ID,
        "run_id": RUN_ID,
        "step_id": STEP_ID,
        "attempt_id": _stable_uuid(label),
    }


def _request(
    capability_id: str,
    *,
    label: str,
    idempotency_key: str,
    authorization_ref: str = CONFORMANCE_AUTHORIZATION,
    input_data: Mapping[str, Any] | None = None,
    hard_timeout_ms: int = 1_000,
    grace_period_ms: int = 100,
) -> dict[str, Any]:
    soft_timeout_ms = max(1, min(100, hard_timeout_ms - 1))
    message = {
        "message_type": "runner.step.request",
        "protocol_version": PROTOCOL_VERSION,
        "correlation": _correlation(label),
        "emitted_at": "2026-08-06T15:00:00Z",
        "authorization_ref": authorization_ref,
        "idempotency_key": idempotency_key,
        "operation": {
            "capability_id": capability_id,
            "input": dict(input_data or CALLER_SHAPED_INPUT),
        },
        "timeout_budget": {
            "soft_timeout_ms": soft_timeout_ms,
            "hard_timeout_ms": hard_timeout_ms,
        },
        "retry_policy": {
            "max_attempts": 1,
            "retryable_error_codes": ["RUNNER_UNAVAILABLE"],
        },
        "cancellation_policy": {
            "mode": "cooperative_then_force",
            "grace_period_ms": grace_period_ms,
        },
        "progress_mode": "optional",
    }
    validate_semantics(message)
    return message


def _cancellation(correlation: Mapping[str, str]) -> dict[str, Any]:
    message = {
        "message_type": "runner.cancellation.request",
        "protocol_version": PROTOCOL_VERSION,
        "correlation": dict(correlation),
        "emitted_at": "2026-08-06T15:00:01Z",
        "reason": "operator",
        "requested_by": "control_plane",
    }
    validate_semantics(message)
    return message


def _messages(response: Mapping[str, Any]) -> list[dict[str, Any]]:
    messages = response.get("messages")
    if not isinstance(messages, list) or not messages:
        raise ConformanceError("candidate response must contain a non-empty messages list")
    validated: list[dict[str, Any]] = []
    for message in messages:
        if not isinstance(message, dict):
            raise ConformanceError("candidate messages must be JSON objects")
        validate_semantics(message)
        _assert_sanitized(message)
        validated.append(message)
    return validated


def _stats(candidate: CandidateProcess) -> dict[str, int]:
    response = candidate.exchange({"action": "stats"})
    stats = response.get("stats")
    if not isinstance(stats, dict):
        raise ConformanceError("candidate stats response is missing")
    result: dict[str, int] = {}
    for field in ("effect_count", "ledger_entries", "active_processes"):
        value = stats.get(field)
        if not isinstance(value, int) or value < 0:
            raise ConformanceError(f"{field} must be a non-negative integer")
        result[field] = value
    return result


def _dispatch(
    candidate: CandidateProcess, request: Mapping[str, Any]
) -> list[dict[str, Any]]:
    response = candidate.exchange({"action": "dispatch", "message": dict(request)})
    return _messages(response)


def _assert_sanitized(value: Any) -> None:
    serialized = json.dumps(value, sort_keys=True)
    if SECRET_CANARY in serialized:
        raise ConformanceError("candidate leaked the conformance secret canary")
    if isinstance(value, Mapping):
        for key, child in value.items():
            if str(key).lower() in RAW_PROCESS_KEYS:
                raise ConformanceError(f"candidate exposed raw process field {key!r}")
            _assert_sanitized(child)
    elif isinstance(value, list):
        for child in value:
            _assert_sanitized(child)


def _terminal(
    messages: list[dict[str, Any]],
    *,
    status: str,
    error_code: str | None = None,
) -> dict[str, Any]:
    outcomes = [
        message for message in messages if message.get("message_type") == "runner.outcome"
    ]
    if len(outcomes) != 1:
        raise ConformanceError("expected exactly one terminal outcome")
    outcome = outcomes[0]
    if outcome.get("status") != status:
        raise ConformanceError(
            f"expected terminal status {status}, got {outcome.get('status')}"
        )
    actual_error = (outcome.get("error") or {}).get("code")
    if actual_error != error_code:
        raise ConformanceError(
            f"expected normalized error {error_code!r}, got {actual_error!r}"
        )
    if set(outcome["correlation"]) != {
        "campaign_id",
        "run_id",
        "step_id",
        "attempt_id",
    }:
        raise ConformanceError("terminal outcome lost correlation fields")
    return outcome


def _output_shape(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _output_shape(value[key]) for key in sorted(value)}
    if isinstance(value, list):
        return [_output_shape(item) for item in value]
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, int):
        return "integer"
    if isinstance(value, float):
        return "number"
    if isinstance(value, str):
        return "string"
    raise ConformanceError(f"unsupported report value type {type(value).__name__}")


def _normalized_message(message: Mapping[str, Any]) -> dict[str, Any]:
    normalized: dict[str, Any] = {
        "message_type": message["message_type"],
        "correlation_fields": sorted(message["correlation"]),
        "shape": _output_shape(message),
    }
    for field in ("status", "state", "sequence", "percent"):
        if field in message:
            normalized[field] = message[field]

    error = message.get("error")
    if isinstance(error, Mapping):
        normalized["error"] = {
            "code": error.get("code"),
            "category": error.get("category"),
            "retryable": error.get("retryable"),
        }

    evidence_refs = message.get("evidence_refs")
    if isinstance(evidence_refs, list):
        normalized["evidence"] = [
            {
                "kind": ref.get("kind"),
                "classification": ref.get("classification"),
                "uri_scheme": str(ref.get("uri", "")).partition("://")[0],
                "sha256_present": bool(ref.get("sha256")),
            }
            for ref in evidence_refs
            if isinstance(ref, Mapping)
        ]

    output = message.get("output")
    if isinstance(output, Mapping):
        supervision = output.get("supervision")
        if isinstance(supervision, Mapping):
            returncode = supervision.get("returncode")
            normalized["supervision"] = {
                "status": supervision.get("status"),
                "returncode_class": (
                    "none"
                    if returncode is None
                    else "zero"
                    if returncode == 0
                    else "nonzero"
                ),
                "stdout_hash_present": bool(supervision.get("stdout_sha256")),
                "stderr_hash_present": bool(supervision.get("stderr_sha256")),
                "stdout_truncated": supervision.get("stdout_truncated"),
                "stderr_truncated": supervision.get("stderr_truncated"),
                "force_killed": supervision.get("force_killed"),
                "residue_cleaned": supervision.get("residue_cleaned"),
                "cleanup_failed": supervision.get("cleanup_failed"),
            }
    return normalized


def _case_signature(
    messages: list[dict[str, Any]],
    *,
    effect_delta: int,
    ledger_delta: int,
) -> str:
    normalized = {
        "messages": [_normalized_message(message) for message in messages],
        "effect_delta": effect_delta,
        "ledger_delta": ledger_delta,
    }
    encoded = json.dumps(
        normalized, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _case_success(candidate: CandidateProcess) -> list[dict[str, Any]]:
    request = _request(
        "conformance.process.success",
        label="success",
        idempotency_key="supervised-parity:success:0001",
    )
    messages = _dispatch(candidate, request)
    outcome = _terminal(messages, status="PASS")
    if outcome["correlation"] != request["correlation"]:
        raise ConformanceError("success outcome did not preserve correlation")
    return messages


def _case_replay(candidate: CandidateProcess) -> list[dict[str, Any]]:
    first = _request(
        "conformance.process.success",
        label="replay:first",
        idempotency_key="supervised-parity:replay:0001",
    )
    retry = json.loads(json.dumps(first))
    retry["correlation"]["attempt_id"] = _stable_uuid("replay:retry")
    retry["emitted_at"] = "2026-08-06T15:00:02Z"
    validate_semantics(retry)

    first_messages = _dispatch(candidate, first)
    _terminal(first_messages, status="PASS")
    after_first = _stats(candidate)
    retry_messages = _dispatch(candidate, retry)
    retry_outcome = _terminal(retry_messages, status="PASS")
    after_retry = _stats(candidate)
    if retry_outcome["correlation"] != retry["correlation"]:
        raise ConformanceError("replay outcome did not use retry correlation")
    if after_retry != after_first:
        raise ConformanceError("replay changed effect or ledger state")
    return [*first_messages, *retry_messages]


def _case_idempotency_conflict(
    candidate: CandidateProcess,
) -> list[dict[str, Any]]:
    first = _request(
        "conformance.process.success",
        label="conflict:first",
        idempotency_key="supervised-parity:conflict:0001",
        input_data={"target_ref": "lab://first"},
    )
    changed = json.loads(json.dumps(first))
    changed["correlation"]["attempt_id"] = _stable_uuid("conflict:changed")
    changed["emitted_at"] = "2026-08-06T15:00:03Z"
    changed["operation"]["input"]["target_ref"] = "lab://changed"
    validate_semantics(changed)

    first_messages = _dispatch(candidate, first)
    _terminal(first_messages, status="PASS")
    after_first = _stats(candidate)
    changed_messages = _dispatch(candidate, changed)
    _terminal(
        changed_messages,
        status="REFUSED",
        error_code="IDEMPOTENCY_CONFLICT",
    )
    after_changed = _stats(candidate)
    if after_changed != after_first:
        raise ConformanceError("idempotency conflict changed effect or ledger state")
    return [*first_messages, *changed_messages]


def _case_execution_failure(candidate: CandidateProcess) -> list[dict[str, Any]]:
    request = _request(
        "conformance.process.execution-fail",
        label="execution-failure",
        idempotency_key="supervised-parity:execution-failure:0001",
    )
    messages = _dispatch(candidate, request)
    _terminal(messages, status="ERROR", error_code="EXECUTION_FAILED")
    return messages


def _case_hard_timeout(candidate: CandidateProcess) -> list[dict[str, Any]]:
    request = _request(
        "conformance.process.timeout",
        label="hard-timeout",
        idempotency_key="supervised-parity:timeout:0001",
        hard_timeout_ms=200,
        grace_period_ms=50,
    )
    messages = _dispatch(candidate, request)
    _terminal(messages, status="TIMED_OUT", error_code="TIMEOUT_HARD")
    return messages


def _case_cancellation(candidate: CandidateProcess) -> list[dict[str, Any]]:
    request = _request(
        "conformance.process.cancel",
        label="cancellation",
        idempotency_key="supervised-parity:cancellation:0001",
        hard_timeout_ms=5_000,
        grace_period_ms=50,
    )
    progress_messages = _dispatch(candidate, request)
    if (
        len(progress_messages) != 1
        or progress_messages[0].get("message_type") != "runner.progress"
    ):
        raise ConformanceError("cancellation dispatch did not return progress")

    cancellation = _cancellation(request["correlation"])
    response = candidate.exchange({"action": "cancel", "message": cancellation})
    cancellation_messages = _messages(response)
    if [message["message_type"] for message in cancellation_messages] != [
        "runner.cancellation.ack",
        "runner.outcome",
    ]:
        raise ConformanceError(
            "cancellation must return acknowledgement then terminal outcome"
        )
    if cancellation_messages[0].get("status") != "accepted":
        raise ConformanceError("cancellation acknowledgement was not accepted")
    _terminal(
        cancellation_messages,
        status="CANCELLED",
        error_code="CANCELLED",
    )
    return [*progress_messages, *cancellation_messages]


def _case_residue(candidate: CandidateProcess) -> list[dict[str, Any]]:
    request = _request(
        "conformance.process.residue",
        label="residue",
        idempotency_key="supervised-parity:residue:0001",
    )
    messages = _dispatch(candidate, request)
    _terminal(messages, status="INCONCLUSIVE", error_code="INTERNAL_ERROR")
    return messages


def _case_unsupported_refusal(candidate: CandidateProcess) -> list[dict[str, Any]]:
    request = _request(
        "production.execute",
        label="unsupported-refusal",
        idempotency_key="supervised-parity:unsupported:0001",
    )
    messages = _dispatch(candidate, request)
    _terminal(messages, status="REFUSED", error_code="UNSUPPORTED_CAPABILITY")
    return messages


def _case_authorization_refusal(candidate: CandidateProcess) -> list[dict[str, Any]]:
    request = _request(
        "conformance.process.success",
        label="authorization-refusal",
        idempotency_key="supervised-parity:authorization:0001",
        authorization_ref="authz/customer/not-authorized",
    )
    messages = _dispatch(candidate, request)
    _terminal(messages, status="REFUSED", error_code="AUTHORIZATION_DENIED")
    return messages


CASES: tuple[CaseSpec, ...] = (
    CaseSpec("success", _case_success, 1, 1),
    CaseSpec("replay", _case_replay, 1, 1),
    CaseSpec("idempotency-conflict", _case_idempotency_conflict, 1, 1),
    CaseSpec("execution-failure", _case_execution_failure, 1, 1),
    CaseSpec("hard-timeout", _case_hard_timeout, 1, 1),
    CaseSpec("cancellation", _case_cancellation, 1, 1),
    CaseSpec("residue", _case_residue, 1, 1),
    CaseSpec("unsupported-refusal", _case_unsupported_refusal, 0, 0),
    CaseSpec("authorization-refusal", _case_authorization_refusal, 0, 0),
)


def _adapter_command(adapter: Path, ledger: Path) -> list[str]:
    return [
        str(Path(sys.executable).resolve()),
        str(adapter),
        "--conformance-only",
        "--synthetic-process-only",
        "--durable-ledger",
        str(ledger),
    ]


def _safe_detail(exc: Exception) -> str:
    detail = str(exc).replace("\r", " ").replace("\n", " ")
    detail = detail.replace(SECRET_CANARY, "[REDACTED]")
    return detail[:512] or exc.__class__.__name__


def _run_case_process(
    *,
    family: str,
    adapter: Path,
    case: CaseSpec,
    temp_root: Path,
) -> dict[str, Any]:
    ledger = temp_root / f"{family}-{case.case_id}.sqlite3"
    command = _adapter_command(adapter, ledger)
    with CandidateProcess(command, f"{family}-supervised-synthetic") as candidate:
        reset = candidate.exchange({"action": "reset"})
        if reset != {"status": "reset"}:
            raise ConformanceError("candidate did not acknowledge reset")
        before = _stats(candidate)
        if before != {
            "effect_count": 0,
            "ledger_entries": 0,
            "active_processes": 0,
        }:
            raise ConformanceError("candidate did not start from an empty state")

        messages = case.execute(candidate)
        after = _stats(candidate)
        effect_delta = after["effect_count"] - before["effect_count"]
        ledger_delta = after["ledger_entries"] - before["ledger_entries"]
        if effect_delta != case.expected_effect_delta:
            raise ConformanceError(
                f"effect delta {effect_delta} does not match "
                f"{case.expected_effect_delta}"
            )
        if ledger_delta != case.expected_ledger_delta:
            raise ConformanceError(
                f"ledger delta {ledger_delta} does not match "
                f"{case.expected_ledger_delta}"
            )
        if after["active_processes"] != 0:
            raise ConformanceError("case left an active supervised process")
        return {
            "case_id": case.case_id,
            "status": "PASS",
            "signature_sha256": _case_signature(
                messages,
                effect_delta=effect_delta,
                ledger_delta=ledger_delta,
            ),
            "effect_delta": effect_delta,
            "ledger_delta": ledger_delta,
        }


def _run_family(
    family: str,
    adapter: Path,
    temp_root: Path,
) -> dict[str, Any]:
    if not adapter.is_file():
        raise ConformanceError(f"adapter for {family} is missing")
    cases: list[dict[str, Any]] = []
    verdict = "PASS"
    for case in CASES:
        try:
            result = _run_case_process(
                family=family,
                adapter=adapter,
                case=case,
                temp_root=temp_root,
            )
        except Exception as exc:
            verdict = "FAIL"
            result = {
                "case_id": case.case_id,
                "status": "FAIL",
                "detail": _safe_detail(exc),
                "effect_delta": 0,
                "ledger_delta": 0,
            }
        cases.append(result)

    adapter_sha256 = hashlib.sha256(adapter.read_bytes()).hexdigest()
    profile = {
        "family": family,
        "adapter_sha256": adapter_sha256,
        "flags": [
            "--conformance-only",
            "--synthetic-process-only",
            "--durable-ledger",
        ],
    }
    command_profile_sha256 = hashlib.sha256(
        json.dumps(profile, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    return {
        "family": family,
        "adapter_sha256": adapter_sha256,
        "command_profile_sha256": command_profile_sha256,
        "verdict": verdict,
        "cases": cases,
    }


def build_parity(families: list[dict[str, Any]]) -> list[dict[str, Any]]:
    parity: list[dict[str, Any]] = []
    by_family = {str(item["family"]): item for item in families}
    expected_families = tuple(sorted(FAMILY_ADAPTERS))
    if tuple(sorted(by_family)) != expected_families:
        raise ConformanceError("cross-family report does not contain the fixed inventory")

    for case in CASES:
        family_cases = {
            family: next(
                (
                    item
                    for item in by_family[family]["cases"]
                    if item["case_id"] == case.case_id
                ),
                None,
            )
            for family in expected_families
        }
        if any(item is None for item in family_cases.values()):
            parity.append(
                {
                    "case_id": case.case_id,
                    "status": "FAIL",
                    "detail": "one or more families did not report the case",
                }
            )
            continue

        statuses = {str(item["status"]) for item in family_cases.values() if item}
        signatures = {
            str(item.get("signature_sha256"))
            for item in family_cases.values()
            if item and item.get("signature_sha256")
        }
        if statuses == {"PASS"} and len(signatures) == 1:
            parity.append(
                {
                    "case_id": case.case_id,
                    "status": "PASS",
                    "signature_sha256": next(iter(signatures)),
                }
            )
        else:
            parity.append(
                {
                    "case_id": case.case_id,
                    "status": "FAIL",
                    "detail": "family outcomes or normalized signatures differ",
                }
            )
    return parity


def run_supervised_conformance() -> dict[str, Any]:
    """Run the fixed repository inventory and return a sanitized parity report."""

    with tempfile.TemporaryDirectory(prefix="runner-supervised-parity-") as directory:
        temp_root = Path(directory).resolve()
        families = [
            _run_family(family, FAMILY_ADAPTERS[family], temp_root)
            for family in sorted(FAMILY_ADAPTERS)
        ]

    parity = build_parity(families)
    verdict = (
        "PASS"
        if all(family["verdict"] == "PASS" for family in families)
        and all(case["status"] == "PASS" for case in parity)
        else "FAIL"
    )
    report = {
        "schema_version": "1.0",
        "protocol_version": PROTOCOL_VERSION,
        "verdict": verdict,
        "families": families,
        "parity": parity,
        "safety": {
            "raw_process_output_persisted": False,
            "request_controls_process_spec": False,
            "production_effect_claim": "none",
            "sandbox_status": "NOT_IMPLEMENTED",
            "runtime_declaration": "NO_RUNTIME_CHANGE",
        },
    }
    schema = json.loads(REPORT_SCHEMA.read_text(encoding="utf-8"))
    jsonschema.validate(report, schema)
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    report = run_supervised_conformance()
    serialized = json.dumps(report, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.write_text(serialized, encoding="utf-8")
    else:
        print(serialized, end="")
    return 0 if report["verdict"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
