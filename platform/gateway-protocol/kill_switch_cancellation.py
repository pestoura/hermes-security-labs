"""Fail-closed kill-switch to Runner Protocol cancellation fan-out contract.

This module builds and validates ``runner.cancellation.request`` messages for
already-active attempts. It does not dispatch messages, terminate processes,
connect to a runner or touch a target.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
import uuid
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

ROOT = Path(__file__).resolve().parent
REPOSITORY_ROOT = ROOT.parents[1]
ROE_DIR = REPOSITORY_ROOT / "platform" / "roe-contract"
RUNNER_SDK_SRC = REPOSITORY_ROOT / "platform" / "runner-protocol" / "src"
if str(RUNNER_SDK_SRC) not in sys.path:  # pragma: no cover
    sys.path.insert(0, str(RUNNER_SDK_SRC))

from runner_protocol_v2 import ProtocolValidationError, validate_semantics  # noqa: E402


def _load_module(module_name: str, path: Path) -> Any:
    existing = sys.modules.get(module_name)
    if existing is not None:
        return existing
    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:  # pragma: no cover
        raise RuntimeError(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


kill_switch = _load_module("roe_kill_switch_cancellation", ROE_DIR / "kill_switch.py")

SCHEMA_VERSION = "1.0.0"
INVENTORY_SOURCE = "RUNTIME_SUPERVISOR_SNAPSHOT"
ACTIVE_STATES = {"accepted", "running", "cancelling"}
CANCELLATION_MODES = {"cooperative", "cooperative_then_force"}
MAX_ATTEMPTS = 10_000
MAX_RELEASE_AGE_SECONDS = 86_400

ATTEMPT_FIELDS = {"attempt_ref", "correlation", "state", "cancellation_mode", "grace_period_ms"}
CORRELATION_FIELDS = {"campaign_id", "run_id", "step_id", "attempt_id"}
INVENTORY_FIELDS = {
    "schema_version", "inventory_id", "generated_at", "source", "source_authenticity",
    "attempts", "authorization_effect", "execution_authority",
}
FORBIDDEN_FIELDS = {
    "target", "operation", "parameters", "command", "argv", "shell", "cwd",
    "environment", "credential", "credentials", "secret", "token", "password",
    "cookie", "api_key", "authorization_ref", "authorization_receipt", "authorized",
    "execution_allowed",
}


class KillSwitchCancellationError(ValueError):
    """Fail-closed cancellation planning contract violation."""


def _digest(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()
    ).hexdigest()


def _parse_time(value: Any, label: str) -> datetime:
    if not isinstance(value, str) or not value:
        raise KillSwitchCancellationError(f"{label} must be an RFC3339 timestamp")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise KillSwitchCancellationError(f"{label} must be an RFC3339 timestamp") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise KillSwitchCancellationError(f"{label} must include timezone")
    return parsed.astimezone(timezone.utc)


def _walk_keys(value: Any) -> set[str]:
    keys: set[str] = set()
    if isinstance(value, Mapping):
        for key, child in value.items():
            keys.add(str(key).lower())
            keys.update(_walk_keys(child))
    elif isinstance(value, list):
        for child in value:
            keys.update(_walk_keys(child))
    return keys


def _reject_forbidden_fields(value: Any, label: str) -> None:
    if _walk_keys(value).intersection(FORBIDDEN_FIELDS):
        raise KillSwitchCancellationError(
            f"{label} may not contain target, execution, secret or authorization fields"
        )


def _exact_fields(value: Mapping[str, Any], expected: set[str], label: str) -> None:
    actual = {str(key) for key in value}
    if actual != expected:
        raise KillSwitchCancellationError(
            f"{label} fields mismatch: missing={sorted(expected-actual)}, extra={sorted(actual-expected)}"
        )


def _canonical_uuid(value: Any, label: str) -> str:
    if not isinstance(value, str):
        raise KillSwitchCancellationError(f"invalid {label}")
    try:
        parsed = uuid.UUID(value)
    except ValueError as exc:
        raise KillSwitchCancellationError(f"invalid {label}") from exc
    canonical = str(parsed)
    if canonical != value.lower():
        raise KillSwitchCancellationError(f"non-canonical {label}")
    return canonical


def _normalize_attempt(attempt: Mapping[str, Any]) -> dict[str, Any]:
    if not isinstance(attempt, Mapping):
        raise KillSwitchCancellationError("active attempt must be an object")
    _reject_forbidden_fields(attempt, "active attempt")
    if set(attempt) not in (ATTEMPT_FIELDS - {"attempt_ref"}, ATTEMPT_FIELDS):
        raise KillSwitchCancellationError("active attempt fields mismatch")
    correlation = attempt.get("correlation")
    if not isinstance(correlation, Mapping):
        raise KillSwitchCancellationError("active attempt correlation is required")
    _exact_fields(correlation, CORRELATION_FIELDS, "active attempt correlation")
    normalized_correlation = {
        field: _canonical_uuid(correlation[field], field)
        for field in ("campaign_id", "run_id", "step_id", "attempt_id")
    }
    state = attempt.get("state")
    if state not in ACTIVE_STATES:
        raise KillSwitchCancellationError("inventory may contain active states only")
    cancellation_mode = attempt.get("cancellation_mode")
    if cancellation_mode not in CANCELLATION_MODES:
        raise KillSwitchCancellationError("invalid cancellation mode")
    grace = attempt.get("grace_period_ms")
    if isinstance(grace, bool) or not isinstance(grace, int) or not 0 <= grace <= 300_000:
        raise KillSwitchCancellationError("invalid cancellation grace period")
    seed = {
        "correlation": normalized_correlation,
        "state": state,
        "cancellation_mode": cancellation_mode,
        "grace_period_ms": grace,
    }
    attempt_ref = f"rai_{_digest(seed)[:32]}"
    supplied_ref = attempt.get("attempt_ref")
    if supplied_ref is not None and supplied_ref != attempt_ref:
        raise KillSwitchCancellationError("active attempt ref does not match canonical content")
    return {"attempt_ref": attempt_ref, **seed}


def build_active_attempt_inventory(
    *, attempts: Sequence[Mapping[str, Any]], generated_at: str
) -> dict[str, Any]:
    _parse_time(generated_at, "generated_at")
    if isinstance(attempts, (str, bytes)) or not isinstance(attempts, Sequence):
        raise KillSwitchCancellationError("attempt inventory must be a list")
    if len(attempts) > MAX_ATTEMPTS:
        raise KillSwitchCancellationError("attempt inventory exceeds bounded contract")
    normalized = [_normalize_attempt(item) for item in attempts]
    refs = [item["attempt_ref"] for item in normalized]
    correlations = [
        tuple(item["correlation"][field] for field in ("campaign_id", "run_id", "step_id", "attempt_id"))
        for item in normalized
    ]
    if len(set(refs)) != len(refs) or len(set(correlations)) != len(correlations):
        raise KillSwitchCancellationError("active attempts must be unique")
    normalized.sort(key=lambda item: item["attempt_ref"])
    seed = {
        "generated_at": generated_at,
        "source": INVENTORY_SOURCE,
        "source_authenticity": "NOT_VERIFIED",
        "attempts": normalized,
    }
    return {
        "schema_version": SCHEMA_VERSION,
        "inventory_id": f"raiinv_{_digest(seed)[:32]}",
        **seed,
        "authorization_effect": "NONE",
        "execution_authority": "NONE",
    }


def _validate_inventory(inventory: Mapping[str, Any]) -> dict[str, Any]:
    if not isinstance(inventory, Mapping):
        raise KillSwitchCancellationError("active attempt inventory must be an object")
    _reject_forbidden_fields(inventory, "active attempt inventory")
    _exact_fields(inventory, INVENTORY_FIELDS, "active attempt inventory")
    if inventory.get("schema_version") != SCHEMA_VERSION:
        raise KillSwitchCancellationError("unsupported active attempt inventory schema")
    if inventory.get("source") != INVENTORY_SOURCE:
        raise KillSwitchCancellationError("unsupported active attempt inventory source")
    if inventory.get("source_authenticity") != "NOT_VERIFIED":
        raise KillSwitchCancellationError("inventory source authenticity cannot be promoted")
    if inventory.get("authorization_effect") != "NONE" or inventory.get("execution_authority") != "NONE":
        raise KillSwitchCancellationError("attempt inventory cannot carry execution authority")
    rebuilt = build_active_attempt_inventory(
        attempts=inventory["attempts"], generated_at=inventory["generated_at"]
    )
    if inventory.get("inventory_id") != rebuilt["inventory_id"]:
        raise KillSwitchCancellationError("active attempt inventory id does not match canonical content")
    return rebuilt


def _cancel_request(attempt: Mapping[str, Any], emitted_at: str) -> dict[str, Any]:
    message = {
        "message_type": "runner.cancellation.request",
        "protocol_version": "2.0.0",
        "correlation": deepcopy(attempt["correlation"]),
        "emitted_at": emitted_at,
        "reason": "policy",
        "requested_by": "gateway",
    }
    try:
        validate_semantics(message)
    except ProtocolValidationError as exc:
        raise KillSwitchCancellationError("RUNNER_CANCELLATION_REQUEST_INVALID") from exc
    return message


def _cancel_all(
    attempts: Sequence[Mapping[str, Any]], emitted_at: str
) -> tuple[list[dict[str, Any]], list[str], list[str]]:
    requests: list[dict[str, Any]] = []
    cancelling: list[str] = []
    for attempt in attempts:
        if attempt["state"] == "cancelling":
            cancelling.append(attempt["attempt_ref"])
        else:
            requests.append(_cancel_request(attempt, emitted_at))
    requests.sort(key=lambda item: item["correlation"]["attempt_id"])
    return requests, sorted(cancelling), []


def plan_kill_switch_cancellations(
    *, kill_switch_path: Path | None, inventory: Mapping[str, Any], emitted_at: str,
    released_state_max_age_seconds: int = 300,
) -> dict[str, Any]:
    """Build cancellation requests without dispatching them.

    ``engaged`` cancels matching active attempts. A missing/invalid source or an
    untrustworthy ``released`` state (missing/stale/future timestamp) fails closed
    and requires cancellation of all active attempts in the supplied inventory.
    A campaign-scoped kill switch whose campaign id cannot correlate to Runner v2
    UUIDs also fails closed globally rather than silently missing active work.
    """

    validated = _validate_inventory(inventory)
    now = _parse_time(emitted_at, "emitted_at")
    if (
        isinstance(released_state_max_age_seconds, bool)
        or not isinstance(released_state_max_age_seconds, int)
        or not 1 <= released_state_max_age_seconds <= MAX_RELEASE_AGE_SECONDS
    ):
        raise KillSwitchCancellationError("invalid released-state freshness policy")

    attempts = validated["attempts"]
    codes: list[str] = []
    switch_scope: str | None = None
    switch_campaign_id: str | None = None
    fail_closed = False
    status = None

    if kill_switch_path is None:
        codes.append("KILL_SWITCH_SOURCE_REQUIRED")
        fail_closed = True
    else:
        try:
            status = kill_switch.read_kill_switch(Path(kill_switch_path))
        except Exception as exc:  # noqa: BLE001 - source defects fail closed
            codes.append(str(exc) or "KILL_SWITCH_UNTRUSTWORTHY")
            fail_closed = True

    if not fail_closed and status is not None:
        switch_scope = status.scope
        if status.scope == "campaign":
            try:
                switch_campaign_id = _canonical_uuid(
                    status.campaign_id, "kill switch campaign id"
                )
            except KillSwitchCancellationError:
                codes.append("KILL_SWITCH_CAMPAIGN_CORRELATION_INVALID")
                switch_campaign_id = None
                fail_closed = True
        else:
            switch_campaign_id = None

    requests: list[dict[str, Any]] = []
    already_cancelling: list[str] = []
    unaffected: list[str] = []

    if fail_closed:
        requests, already_cancelling, unaffected = _cancel_all(attempts, emitted_at)
    elif status is not None and status.engaged:
        codes.append("KILL_SWITCH_ACTIVE")
        for attempt in attempts:
            in_scope = status.scope == "global" or (
                status.scope == "campaign"
                and attempt["correlation"]["campaign_id"] == switch_campaign_id
            )
            if not in_scope:
                unaffected.append(attempt["attempt_ref"])
            elif attempt["state"] == "cancelling":
                already_cancelling.append(attempt["attempt_ref"])
            else:
                requests.append(_cancel_request(attempt, emitted_at))
    elif status is not None:
        if status.updated_at is None:
            codes.append("KILL_SWITCH_RELEASE_TIMESTAMP_REQUIRED")
            fail_closed = True
        else:
            updated_at = status.updated_at.astimezone(timezone.utc)
            if updated_at > now:
                codes.append("KILL_SWITCH_RELEASE_TIME_FUTURE")
                fail_closed = True
            elif (now - updated_at).total_seconds() > released_state_max_age_seconds:
                codes.append("KILL_SWITCH_RELEASE_STALE")
                fail_closed = True
            else:
                codes.append("KILL_SWITCH_RELEASED_FRESH")
                unaffected = [item["attempt_ref"] for item in attempts]
        if fail_closed:
            requests, already_cancelling, unaffected = _cancel_all(attempts, emitted_at)

    requests.sort(key=lambda item: item["correlation"]["attempt_id"])
    already_cancelling = sorted(already_cancelling)
    unaffected = sorted(unaffected)
    decision = (
        "CANCEL_REQUIRED"
        if fail_closed or requests or already_cancelling
        else "NO_CANCELLATION_REQUIRED"
    )
    body = {
        "schema_version": SCHEMA_VERSION,
        "inventory_id": validated["inventory_id"],
        "evaluated_at": emitted_at,
        "decision": decision,
        "codes": sorted(set(codes)),
        "kill_switch_scope": switch_scope,
        "kill_switch_campaign_id": switch_campaign_id,
        "fail_closed": fail_closed,
        "cancellation_requests": requests,
        "already_cancelling_attempt_refs": already_cancelling,
        "unaffected_attempt_refs": unaffected,
        "dispatch_performed": False,
        "safety_effect": "RESTRICT_ONLY",
        "authorization_effect": "NONE",
        "execution_authority": "NONE",
        "limitations": [
            "CANCELLATION_MESSAGES_BUILT_NOT_DISPATCHED",
            "ACTIVE_ATTEMPT_INVENTORY_SOURCE_AUTHENTICITY_NOT_VERIFIED",
            "PROCESS_TERMINATION_AND_FORCE_AFTER_GRACE_NOT_PERFORMED",
        ],
    }
    return {"plan_id": f"raicp_{_digest(body)[:32]}", **body}
