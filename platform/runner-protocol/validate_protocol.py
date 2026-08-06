#!/usr/bin/env python3
"""Validate Runner Protocol v2 messages and contract-level invariants.

This module is deliberately side-effect free. It validates repository contracts and
computes deterministic fingerprints; it does not dispatch, cancel or execute work.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from collections.abc import Iterable, Mapping
from datetime import datetime
from pathlib import Path
from typing import Any

import jsonschema
import yaml

ROOT = Path(__file__).resolve().parent
SCHEMA_PATH = ROOT / "schemas" / "runner-protocol-v2.schema.json"
COMPATIBILITY_PATH = ROOT / "compatibility.yaml"

RETRYABLE_CODES = frozenset(
    {"TRANSIENT_DEPENDENCY", "RUNNER_UNAVAILABLE", "TIMEOUT_SOFT"}
)
FORBIDDEN_SECRET_KEYS = frozenset(
    {
        "token",
        "password",
        "secret",
        "cookie",
        "authorization",
        "api_key",
        "credential",
        "private_key",
    }
)
EXPECTED_RUNNER_FAMILIES = frozenset({"api", "devsecops", "ai-mcp"})


class ProtocolValidationError(ValueError):
    """Raised when a message violates schema or semantic contract rules."""


def load_schema() -> dict[str, Any]:
    """Load and validate the canonical JSON Schema itself."""
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    jsonschema.Draft202012Validator.check_schema(schema)
    return schema


def _validator() -> jsonschema.Draft202012Validator:
    return jsonschema.Draft202012Validator(
        load_schema(), format_checker=jsonschema.FormatChecker()
    )


def _format_path(path: Iterable[Any]) -> str:
    parts = [str(part) for part in path]
    return ".".join(parts) if parts else "<root>"


def _leaf_errors(
    error: jsonschema.ValidationError,
) -> Iterable[jsonschema.ValidationError]:
    """Yield actionable leaf errors instead of an opaque oneOf summary."""
    if error.context:
        for child in error.context:
            yield from _leaf_errors(child)
        return
    yield error


def validate_schema(message: Mapping[str, Any]) -> None:
    """Validate one protocol message against the canonical schema bundle."""
    root_errors = _validator().iter_errors(message)
    errors = [leaf for root in root_errors for leaf in _leaf_errors(root)]
    if errors:
        diagnostics = {
            (_format_path(error.absolute_path), error.message) for error in errors
        }
        details = "; ".join(
            f"{path}: {message}" for path, message in sorted(diagnostics)
        )
        raise ProtocolValidationError(details)


def _walk_forbidden_keys(value: Any, path: tuple[str, ...] = ()) -> None:
    if isinstance(value, Mapping):
        for key, child in value.items():
            normalized = str(key).lower()
            if normalized in FORBIDDEN_SECRET_KEYS:
                location = ".".join((*path, str(key)))
                raise ProtocolValidationError(
                    f"raw secret field {location!r} is forbidden; use a secret reference"
                )
            _walk_forbidden_keys(child, (*path, str(key)))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            _walk_forbidden_keys(child, (*path, str(index)))


def _parse_time(value: str, field: str) -> datetime:
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ProtocolValidationError(f"{field} is not a valid RFC 3339 timestamp") from exc


def _validate_error(error: Mapping[str, Any]) -> None:
    code = str(error["code"])
    retryable = bool(error["retryable"])
    expected = code in RETRYABLE_CODES
    if retryable != expected:
        raise ProtocolValidationError(
            f"error {code} retryable={retryable} conflicts with the stable taxonomy"
        )
    _walk_forbidden_keys(error, ("error",))


def validate_semantics(message: Mapping[str, Any]) -> None:
    """Validate invariants that JSON Schema cannot express safely."""
    validate_schema(message)
    _walk_forbidden_keys(message)

    message_type = message["message_type"]
    if message_type == "runner.step.request":
        budget = message["timeout_budget"]
        soft = int(budget["soft_timeout_ms"])
        hard = int(budget["hard_timeout_ms"])
        grace = int(message["cancellation_policy"]["grace_period_ms"])
        if hard <= soft:
            raise ProtocolValidationError(
                "hard_timeout_ms must be greater than soft_timeout_ms"
            )
        if grace > hard:
            raise ProtocolValidationError(
                "grace_period_ms must fit inside the hard timeout budget"
            )

    error = message.get("error")
    if isinstance(error, Mapping):
        _validate_error(error)

    if message_type == "runner.outcome":
        started = _parse_time(str(message["started_at"]), "started_at")
        finished = _parse_time(str(message["finished_at"]), "finished_at")
        if finished < started:
            raise ProtocolValidationError("finished_at cannot precede started_at")

        status = message["status"]
        if status == "TIMED_OUT" and message["error"]["code"] != "TIMEOUT_HARD":
            raise ProtocolValidationError(
                "TIMED_OUT outcomes must use the TIMEOUT_HARD error code"
            )
        if status == "REFUSED" and message["error"]["category"] not in {
            "validation",
            "compatibility",
            "authorization",
            "conflict",
        }:
            raise ProtocolValidationError(
                "REFUSED outcomes require a pre-execution refusal category"
            )


def request_fingerprint(request: Mapping[str, Any]) -> str:
    """Return the canonical fingerprint for one logical step effect.

    ``attempt_id``, ``emitted_at`` and the idempotency key itself are excluded so a
    retry of the same logical step retains the same fingerprint.
    """
    validate_semantics(request)
    if request["message_type"] != "runner.step.request":
        raise ProtocolValidationError("fingerprints apply only to runner.step.request")

    correlation = request["correlation"]
    canonical = {
        "protocol_major": str(request["protocol_version"]).split(".", 1)[0],
        "campaign_id": correlation["campaign_id"],
        "run_id": correlation["run_id"],
        "step_id": correlation["step_id"],
        "authorization_ref": request["authorization_ref"],
        "operation": request["operation"],
        "timeout_budget": request["timeout_budget"],
        "retry_policy": request["retry_policy"],
        "cancellation_policy": request["cancellation_policy"],
        "progress_mode": request.get("progress_mode", "optional"),
    }
    encoded = json.dumps(
        canonical, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def classify_idempotency(
    existing_fingerprint: str | None, request: Mapping[str, Any]
) -> str:
    """Classify a request without executing it or mutating a replay ledger."""
    candidate = request_fingerprint(request)
    if existing_fingerprint is None:
        return "NEW"
    if existing_fingerprint == candidate:
        return "REPLAY_SAME"
    return "IDEMPOTENCY_CONFLICT"


def validate_progress_sequence(events: Iterable[Mapping[str, Any]]) -> None:
    """Validate one attempt's ordered progress stream."""
    expected_correlation: Mapping[str, Any] | None = None
    previous_sequence = 0
    previous_percent = 0.0

    for event in events:
        validate_semantics(event)
        if event["message_type"] != "runner.progress":
            raise ProtocolValidationError("progress stream contains a non-progress message")
        correlation = event["correlation"]
        if expected_correlation is None:
            expected_correlation = correlation
        elif correlation != expected_correlation:
            raise ProtocolValidationError(
                "all progress events must belong to the same correlation tuple"
            )

        sequence = int(event["sequence"])
        if sequence <= previous_sequence:
            raise ProtocolValidationError("progress sequence must increase strictly")
        previous_sequence = sequence

        if "percent" in event:
            percent = float(event["percent"])
            if percent < previous_percent:
                raise ProtocolValidationError("progress percent cannot decrease")
            previous_percent = percent


def validate_compatibility_matrix() -> None:
    """Validate the contract-only compatibility declaration."""
    data = yaml.safe_load(COMPATIBILITY_PATH.read_text(encoding="utf-8"))
    if data["protocol"] != {
        "name": "runner-protocol",
        "version": "2.0.0",
        "status": "contract_only",
    }:
        raise ProtocolValidationError("compatibility protocol identity is inconsistent")

    rules = data["compatibility_rules"]
    required_rules = {
        "major_version": "exact_match",
        "unknown_major": "fail_closed",
        "unknown_message_type": "fail_closed",
        "invalid_schema": "fail_closed",
        "terminal_outcome": "mandatory",
        "terminal_evidence_reference": "mandatory",
        "authorization_source": "hermes_control_plane",
    }
    for key, expected in required_rules.items():
        if rules.get(key) != expected:
            raise ProtocolValidationError(
                f"compatibility rule {key!r} must be {expected!r}"
            )

    families = data["runner_families"]
    ids = {family["id"] for family in families}
    if ids != EXPECTED_RUNNER_FAMILIES:
        raise ProtocolValidationError(
            f"runner family inventory mismatch: {sorted(ids)}"
        )
    for family in families:
        if family["implementation_status"] != "not_started":
            raise ProtocolValidationError(
                f"{family['id']} cannot claim implementation in this contract-only block"
            )
        if family["protocol_status"] != "contract_only":
            raise ProtocolValidationError(
                f"{family['id']} protocol status must remain contract_only"
            )
        if family["conformance"] != "NOT_RUN":
            raise ProtocolValidationError(
                f"{family['id']} conformance must remain NOT_RUN"
            )

    if data["runtime_declaration"] != "NO_RUNTIME_CHANGE":
        raise ProtocolValidationError("runtime declaration must be NO_RUNTIME_CHANGE")


def _load_message(path: Path) -> Mapping[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, Mapping):
        raise ProtocolValidationError(f"{path}: protocol message must be an object")
    return data


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("files", nargs="*", type=Path, help="JSON messages to validate")
    parser.add_argument(
        "--contract-only",
        action="store_true",
        help="validate the schema and compatibility matrix without message files",
    )
    args = parser.parse_args()

    load_schema()
    validate_compatibility_matrix()
    for path in args.files:
        validate_semantics(_load_message(path))
        print(f"RUNNER_PROTOCOL_OK\t{path}")

    if args.contract_only or not args.files:
        print("RUNNER_PROTOCOL_CONTRACT_OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
