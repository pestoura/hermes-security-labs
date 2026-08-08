"""Repository-only trust-store generation, freshness and anti-rollback contract.

The existing trust store validates the current file and re-reads it for every
signature verification. This module adds an auditable lifecycle envelope around
successive public-key trust-store snapshots. It does not distribute keys, sign
anything, write a trust store, activate a generation or grant authorization.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

ROOT = Path(__file__).resolve().parent


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


trust_store = _load_module("roe_trust_store_lifecycle_base", ROOT / "trust_store.py")

SCHEMA_VERSION = "1.0.0"
GENERATION_ID_RE = re.compile(r"^tsg_[a-f0-9]{32}$")
SHA256_RE = re.compile(r"^[a-f0-9]{64}$")
MAX_KEYS = 10_000
MAX_AGE_SECONDS = 31_536_000
ALLOWED_TRANSITIONS = {
    "active": {"active", "retired", "revoked"},
    "retired": {"retired", "revoked"},
    "revoked": {"revoked"},
}

GENERATION_FIELDS = {
    "schema_version",
    "generation_id",
    "sequence",
    "generated_at",
    "previous_generation_id",
    "trust_store_sha256",
    "keys",
    "source",
    "activation_effect",
    "authorization_effect",
    "execution_authority",
}
KEY_FIELDS = {
    "key_id",
    "algorithm",
    "state",
    "public_key_sha256",
    "not_before",
    "not_after",
}


class TrustStoreLifecycleError(ValueError):
    """Fail-closed trust-store lifecycle contract violation."""


def _digest(value: Any) -> str:
    encoded = json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=True
    ).encode()
    return hashlib.sha256(encoded).hexdigest()


def _parse_time(value: Any, label: str) -> datetime:
    if not isinstance(value, str) or not value:
        raise TrustStoreLifecycleError(f"{label} must be an RFC3339 timestamp")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise TrustStoreLifecycleError(f"{label} must be an RFC3339 timestamp") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise TrustStoreLifecycleError(f"{label} must include timezone")
    return parsed.astimezone(timezone.utc)


def _format_time(value: datetime | None) -> str | None:
    if value is None:
        return None
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _exact_fields(value: Mapping[str, Any], expected: set[str], label: str) -> None:
    actual = {str(key) for key in value}
    if actual != expected:
        raise TrustStoreLifecycleError(
            f"{label} fields mismatch: missing={sorted(expected-actual)}, extra={sorted(actual-expected)}"
        )


def _generation_seed(generation: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "sequence": generation["sequence"],
        "generated_at": generation["generated_at"],
        "previous_generation_id": generation["previous_generation_id"],
        "trust_store_sha256": generation["trust_store_sha256"],
        "keys": generation["keys"],
        "source": generation["source"],
    }


def build_generation(
    *,
    trust_store_path: Path,
    sequence: int,
    generated_at: str,
    previous_generation_id: str | None,
) -> dict[str, Any]:
    """Build a content-addressed generation manifest from a validated trust store."""

    if isinstance(sequence, bool) or not isinstance(sequence, int) or sequence < 1:
        raise TrustStoreLifecycleError("generation sequence must be a positive integer")
    _parse_time(generated_at, "generated_at")
    if previous_generation_id is not None and (
        not isinstance(previous_generation_id, str)
        or not GENERATION_ID_RE.fullmatch(previous_generation_id)
    ):
        raise TrustStoreLifecycleError("invalid previous generation id")
    if sequence == 1 and previous_generation_id is not None:
        raise TrustStoreLifecycleError("initial generation cannot have a predecessor")
    if sequence > 1 and previous_generation_id is None:
        raise TrustStoreLifecycleError("non-initial generation requires predecessor")

    path = Path(trust_store_path)
    try:
        raw = path.read_bytes()
    except OSError as exc:
        raise TrustStoreLifecycleError("TRUST_STORE_UNAVAILABLE") from exc
    try:
        loaded = trust_store.load_trust_store(path)
    except trust_store.TrustStoreError as exc:
        raise TrustStoreLifecycleError(str(exc)) from exc
    if len(loaded) > MAX_KEYS:
        raise TrustStoreLifecycleError("trust store exceeds lifecycle key bound")

    keys = []
    for key_id, key in sorted(loaded.items()):
        keys.append(
            {
                "key_id": key_id,
                "algorithm": key.algorithm,
                "state": key.state,
                "public_key_sha256": hashlib.sha256(key.public_key_der).hexdigest(),
                "not_before": _format_time(key.not_before),
                "not_after": _format_time(key.not_after),
            }
        )
    seed = {
        "sequence": sequence,
        "generated_at": generated_at,
        "previous_generation_id": previous_generation_id,
        "trust_store_sha256": hashlib.sha256(raw).hexdigest(),
        "keys": keys,
        "source": "EXTERNAL_TRUST_STORE_SNAPSHOT",
    }
    return {
        "schema_version": SCHEMA_VERSION,
        "generation_id": f"tsg_{_digest(seed)[:32]}",
        **seed,
        "activation_effect": "NONE",
        "authorization_effect": "NONE",
        "execution_authority": "NONE",
    }


def validate_generation(generation: Mapping[str, Any]) -> dict[str, Any]:
    """Validate a supplied lifecycle manifest and its content-addressed identity."""

    if not isinstance(generation, Mapping):
        raise TrustStoreLifecycleError("generation must be an object")
    _exact_fields(generation, GENERATION_FIELDS, "generation")
    if generation.get("schema_version") != SCHEMA_VERSION:
        raise TrustStoreLifecycleError("unsupported generation schema")
    if generation.get("source") != "EXTERNAL_TRUST_STORE_SNAPSHOT":
        raise TrustStoreLifecycleError("unsupported generation source")
    if (
        generation.get("activation_effect") != "NONE"
        or generation.get("authorization_effect") != "NONE"
        or generation.get("execution_authority") != "NONE"
    ):
        raise TrustStoreLifecycleError("lifecycle manifest cannot activate keys or grant authority")

    sequence = generation.get("sequence")
    if isinstance(sequence, bool) or not isinstance(sequence, int) or sequence < 1:
        raise TrustStoreLifecycleError("invalid generation sequence")
    _parse_time(generation.get("generated_at"), "generated_at")
    predecessor = generation.get("previous_generation_id")
    if sequence == 1:
        if predecessor is not None:
            raise TrustStoreLifecycleError("initial generation cannot have predecessor")
    elif not isinstance(predecessor, str) or not GENERATION_ID_RE.fullmatch(predecessor):
        raise TrustStoreLifecycleError("non-initial generation requires predecessor")

    store_hash = generation.get("trust_store_sha256")
    if not isinstance(store_hash, str) or not SHA256_RE.fullmatch(store_hash):
        raise TrustStoreLifecycleError("invalid trust-store digest")
    keys = generation.get("keys")
    if not isinstance(keys, list) or not keys or len(keys) > MAX_KEYS:
        raise TrustStoreLifecycleError("generation requires a bounded key inventory")

    normalized: list[dict[str, Any]] = []
    ids: set[str] = set()
    for item in keys:
        if not isinstance(item, Mapping):
            raise TrustStoreLifecycleError("generation key must be an object")
        _exact_fields(item, KEY_FIELDS, "generation key")
        key_id = item.get("key_id")
        algorithm = item.get("algorithm")
        state = item.get("state")
        fingerprint = item.get("public_key_sha256")
        if not isinstance(key_id, str) or not key_id:
            raise TrustStoreLifecycleError("invalid generation key id")
        if key_id in ids:
            raise TrustStoreLifecycleError("generation key ids must be unique")
        ids.add(key_id)
        if algorithm not in trust_store.SUPPORTED_ALGORITHMS:
            raise TrustStoreLifecycleError("unsupported generation key algorithm")
        if state not in trust_store.KEY_STATES:
            raise TrustStoreLifecycleError("invalid generation key state")
        if not isinstance(fingerprint, str) or not SHA256_RE.fullmatch(fingerprint):
            raise TrustStoreLifecycleError("invalid public-key fingerprint")
        for field in ("not_before", "not_after"):
            if item.get(field) is not None:
                _parse_time(item[field], field)
        if item.get("not_before") is not None and item.get("not_after") is not None:
            if not _parse_time(item["not_before"], "not_before") < _parse_time(
                item["not_after"], "not_after"
            ):
                raise TrustStoreLifecycleError("invalid key validity window")
        normalized.append(dict(item))

    if normalized != sorted(normalized, key=lambda item: item["key_id"]):
        raise TrustStoreLifecycleError("generation key inventory must be canonically ordered")
    expected_id = f"tsg_{_digest(_generation_seed(generation))[:32]}"
    if generation.get("generation_id") != expected_id:
        raise TrustStoreLifecycleError("generation id does not match canonical content")
    return dict(generation)


def assess_transition(
    *,
    previous: Mapping[str, Any] | None,
    current: Mapping[str, Any],
    evaluated_at: str,
    max_age_seconds: int = 3600,
) -> dict[str, Any]:
    """Assess generation freshness, monotonicity and safe public-key transitions."""

    now = _parse_time(evaluated_at, "evaluated_at")
    if (
        isinstance(max_age_seconds, bool)
        or not isinstance(max_age_seconds, int)
        or not 1 <= max_age_seconds <= MAX_AGE_SECONDS
    ):
        raise TrustStoreLifecycleError("invalid trust-store freshness policy")
    current_gen = validate_generation(current)
    previous_gen = validate_generation(previous) if previous is not None else None

    codes: list[str] = []
    current_time = _parse_time(current_gen["generated_at"], "current.generated_at")
    freshness_state = "FRESH"
    if current_time > now:
        freshness_state = "FUTURE"
        codes.append("TRUST_STORE_GENERATION_FUTURE")
    elif (now - current_time).total_seconds() > max_age_seconds:
        freshness_state = "STALE"
        codes.append("TRUST_STORE_GENERATION_STALE")

    rollback_detected = False
    removed_key_ids: list[str] = []
    added_key_ids: list[str] = []
    state_changes: list[dict[str, str]] = []

    if previous_gen is None:
        if current_gen["sequence"] != 1 or current_gen["previous_generation_id"] is not None:
            codes.append("TRUST_STORE_INITIAL_GENERATION_INVALID")
    else:
        if current_gen["sequence"] != previous_gen["sequence"] + 1:
            rollback_detected = True
            codes.append("TRUST_STORE_SEQUENCE_NON_MONOTONIC")
        if current_gen["previous_generation_id"] != previous_gen["generation_id"]:
            rollback_detected = True
            codes.append("TRUST_STORE_PREDECESSOR_MISMATCH")
        previous_time = _parse_time(previous_gen["generated_at"], "previous.generated_at")
        if current_time <= previous_time:
            rollback_detected = True
            codes.append("TRUST_STORE_GENERATED_AT_NON_MONOTONIC")

        previous_keys = {item["key_id"]: item for item in previous_gen["keys"]}
        current_keys = {item["key_id"]: item for item in current_gen["keys"]}
        for key_id, old in previous_keys.items():
            new = current_keys.get(key_id)
            if new is None:
                removed_key_ids.append(key_id)
                if old["state"] == "active":
                    codes.append("TRUST_STORE_ACTIVE_KEY_REMOVED")
                continue
            if new["algorithm"] != old["algorithm"]:
                codes.append("TRUST_STORE_KEY_ALGORITHM_MUTATION")
            if new["public_key_sha256"] != old["public_key_sha256"]:
                codes.append("TRUST_STORE_KEY_MATERIAL_MUTATION")
            if new["not_before"] != old["not_before"] or new["not_after"] != old["not_after"]:
                codes.append("TRUST_STORE_KEY_VALIDITY_MUTATION")
            if new["state"] not in ALLOWED_TRANSITIONS[old["state"]]:
                codes.append("TRUST_STORE_KEY_STATE_RESURRECTION")
            if new["state"] != old["state"]:
                state_changes.append(
                    {"key_id": key_id, "from": old["state"], "to": new["state"]}
                )
        added_key_ids = sorted(set(current_keys) - set(previous_keys))

    active_key_count = sum(item["state"] == "active" for item in current_gen["keys"])
    if active_key_count == 0:
        codes.append("TRUST_STORE_NO_ACTIVE_KEYS")

    decision = "ACCEPT_FOR_REVIEW" if not codes else "REFUSE"
    body = {
        "schema_version": SCHEMA_VERSION,
        "previous_generation_id": None if previous_gen is None else previous_gen["generation_id"],
        "current_generation_id": current_gen["generation_id"],
        "evaluated_at": evaluated_at,
        "decision": decision,
        "codes": sorted(set(codes)),
        "freshness_state": freshness_state,
        "rollback_detected": rollback_detected,
        "active_key_count": active_key_count,
        "added_key_ids": sorted(added_key_ids),
        "removed_key_ids": sorted(removed_key_ids),
        "state_changes": sorted(state_changes, key=lambda item: item["key_id"]),
        "automatic_activation": False,
        "activation_effect": "NONE",
        "authorization_effect": "NONE",
        "execution_authority": "NONE",
        "limitations": [
            "GENERATION_ACCEPTANCE_DOES_NOT_ACTIVATE_TRUST_STORE",
            "GENERATION_MANIFEST_AUTHENTICITY_NOT_EXTERNALLY_ATTESTED",
            "PRODUCTION_DISTRIBUTION_AND_REVOCATION_PROPAGATION_NOT_PERFORMED",
        ],
    }
    return {"assessment_id": f"tsa_{_digest(body)[:32]}", **body}
