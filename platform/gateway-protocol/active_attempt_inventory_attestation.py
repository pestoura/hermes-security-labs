"""External-attestation boundary for active Runner attempt inventories.

The existing cancellation planner deliberately treats its supplied inventory as
``NOT_VERIFIED``. This module preserves that invariant and adds a separate,
server-side verification envelope for the exact canonical inventory content.

It never signs data, embeds trust material, grants authorization, dispatches a
cancellation request, terminates a process, connects to a Runner or touches a
target. Trust configuration and signature verification remain external to this
repository contract and use a dedicated inventory-attestation trust purpose.
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import importlib.util
import json
import re
import sys
from collections.abc import Callable, Mapping, Sequence
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

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


cancellation = _load_module(
    "kill_switch_cancellation_attestation",
    ROOT / "kill_switch_cancellation.py",
)

SCHEMA_VERSION = "1.0.0"
TRUST_DOMAIN = "RUNNER_SUPERVISOR_INVENTORY_ATTESTATION_V1"
SOURCE_KIND = "RUNTIME_SUPERVISOR"
SOURCE_AUTHENTICITY = "EXTERNALLY_VERIFIED"
SOURCE_COMPLETENESS = "SOURCE_DECLARED_COMPLETE_NOT_INDEPENDENTLY_VERIFIED"
MAX_ATTESTATION_AGE_SECONDS = 300
MAX_ATTESTATION_TTL_SECONDS = 300
MAX_INVENTORY_AGE_SECONDS = 60
MAX_SEQUENCE = 2**63 - 1

_SOURCE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
_HEX_64 = re.compile(r"^[a-f0-9]{64}$")
_ATTESTATION_ID = re.compile(r"^raiatt_[a-f0-9]{32}$")

SIGNATURE_FIELDS = {"key_id", "algorithm", "value"}
ALGORITHMS = {"Ed25519", "ECDSA-P256-SHA256"}
ATTESTATION_FIELDS = {
    "schema_version",
    "attestation_id",
    "trust_domain",
    "source_kind",
    "source_instance_id",
    "source_sequence",
    "issued_at",
    "expires_at",
    "previous_attestation_id",
    "inventory_id",
    "inventory_sha256",
    "signature",
}
CLAIM_FIELDS = ATTESTATION_FIELDS - {"signature"}
FORBIDDEN_FIELDS = {
    "target",
    "operation",
    "parameters",
    "command",
    "argv",
    "shell",
    "cwd",
    "environment",
    "credential",
    "credentials",
    "secret",
    "token",
    "password",
    "cookie",
    "api_key",
    "authorization_ref",
    "authorization_receipt",
    "authorized",
    "execution_allowed",
}

SignatureVerifier = Callable[[bytes, Mapping[str, Any]], bool]


class ActiveAttemptInventoryAttestationError(ValueError):
    """Fail-closed inventory-attestation contract violation."""


def _canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    ).encode("utf-8")


def _digest(value: Any) -> str:
    return hashlib.sha256(_canonical_bytes(value)).hexdigest()


def _parse_time(value: Any, code: str) -> datetime:
    if not isinstance(value, str) or not value:
        raise ActiveAttemptInventoryAttestationError(code)
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ActiveAttemptInventoryAttestationError(code) from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ActiveAttemptInventoryAttestationError(code)
    return parsed.astimezone(timezone.utc)


def _walk_keys(value: Any) -> set[str]:
    keys: set[str] = set()
    if isinstance(value, Mapping):
        for key, child in value.items():
            keys.add(str(key).lower())
            keys.update(_walk_keys(child))
    elif isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        for child in value:
            keys.update(_walk_keys(child))
    return keys


def _reject_forbidden_fields(value: Any) -> None:
    if _walk_keys(value).intersection(FORBIDDEN_FIELDS):
        raise ActiveAttemptInventoryAttestationError(
            "INVENTORY_ATTESTATION_FORBIDDEN_FIELD"
        )


def _exact_fields(
    value: Mapping[str, Any],
    expected: set[str],
    code: str,
) -> None:
    if {str(key) for key in value} != expected:
        raise ActiveAttemptInventoryAttestationError(code)


def _validate_source_id(value: Any) -> str:
    if not isinstance(value, str) or _SOURCE_ID.fullmatch(value) is None:
        raise ActiveAttemptInventoryAttestationError(
            "INVENTORY_ATTESTATION_SOURCE_INVALID"
        )
    return value


def _validate_sequence(value: Any, code: str) -> int:
    if (
        isinstance(value, bool)
        or not isinstance(value, int)
        or not 1 <= value <= MAX_SEQUENCE
    ):
        raise ActiveAttemptInventoryAttestationError(code)
    return value


def _validate_policy(value: Any, *, maximum: int, code: str) -> int:
    if (
        isinstance(value, bool)
        or not isinstance(value, int)
        or not 1 <= value <= maximum
    ):
        raise ActiveAttemptInventoryAttestationError(code)
    return value


def _validate_signature(signature: Any) -> Mapping[str, Any]:
    if not isinstance(signature, Mapping):
        raise ActiveAttemptInventoryAttestationError(
            "INVENTORY_ATTESTATION_SIGNATURE_INVALID"
        )
    _exact_fields(
        signature,
        SIGNATURE_FIELDS,
        "INVENTORY_ATTESTATION_SIGNATURE_INVALID",
    )
    key_id = signature.get("key_id")
    algorithm = signature.get("algorithm")
    value = signature.get("value")
    if not isinstance(key_id, str) or not 1 <= len(key_id) <= 128:
        raise ActiveAttemptInventoryAttestationError(
            "INVENTORY_ATTESTATION_SIGNATURE_INVALID"
        )
    if algorithm not in ALGORITHMS:
        raise ActiveAttemptInventoryAttestationError(
            "INVENTORY_ATTESTATION_ALGORITHM_UNSUPPORTED"
        )
    if not isinstance(value, str) or not value or len(value) > 8192:
        raise ActiveAttemptInventoryAttestationError(
            "INVENTORY_ATTESTATION_SIGNATURE_INVALID"
        )
    try:
        base64.b64decode(value, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise ActiveAttemptInventoryAttestationError(
            "INVENTORY_ATTESTATION_SIGNATURE_INVALID"
        ) from exc
    return signature


def _claim_payload(attestation: Mapping[str, Any]) -> dict[str, Any]:
    return {
        field: attestation[field]
        for field in (
            "schema_version",
            "trust_domain",
            "source_kind",
            "source_instance_id",
            "source_sequence",
            "issued_at",
            "expires_at",
            "previous_attestation_id",
            "inventory_id",
            "inventory_sha256",
        )
    }


def _attestation_id(payload: Mapping[str, Any]) -> str:
    return f"raiatt_{_digest(payload)[:32]}"


def _inventory_sha256(inventory: Mapping[str, Any]) -> tuple[dict[str, Any], str]:
    validated = cancellation._validate_inventory(inventory)  # noqa: SLF001
    return validated, _digest(validated)


def build_attestation_claim(
    *,
    inventory: Mapping[str, Any],
    source_instance_id: str,
    source_sequence: int,
    issued_at: str,
    expires_at: str,
    previous_attestation_id: str | None,
) -> dict[str, Any]:
    """Build the unsigned canonical claim an external signer must sign."""

    _reject_forbidden_fields(inventory)
    validated_inventory, inventory_sha256 = _inventory_sha256(inventory)
    source_id = _validate_source_id(source_instance_id)
    sequence = _validate_sequence(
        source_sequence,
        "INVENTORY_ATTESTATION_SEQUENCE_INVALID",
    )
    issued = _parse_time(issued_at, "INVENTORY_ATTESTATION_ISSUED_AT_INVALID")
    expires = _parse_time(expires_at, "INVENTORY_ATTESTATION_EXPIRES_AT_INVALID")
    if expires <= issued:
        raise ActiveAttemptInventoryAttestationError(
            "INVENTORY_ATTESTATION_WINDOW_INVALID"
        )
    if previous_attestation_id is not None and (
        not isinstance(previous_attestation_id, str)
        or _ATTESTATION_ID.fullmatch(previous_attestation_id) is None
    ):
        raise ActiveAttemptInventoryAttestationError(
            "INVENTORY_ATTESTATION_PREDECESSOR_INVALID"
        )
    if sequence == 1 and previous_attestation_id is not None:
        raise ActiveAttemptInventoryAttestationError(
            "INVENTORY_ATTESTATION_PREDECESSOR_UNEXPECTED"
        )
    if sequence > 1 and previous_attestation_id is None:
        raise ActiveAttemptInventoryAttestationError(
            "INVENTORY_ATTESTATION_PREDECESSOR_REQUIRED"
        )

    payload = {
        "schema_version": SCHEMA_VERSION,
        "trust_domain": TRUST_DOMAIN,
        "source_kind": SOURCE_KIND,
        "source_instance_id": source_id,
        "source_sequence": sequence,
        "issued_at": issued_at,
        "expires_at": expires_at,
        "previous_attestation_id": previous_attestation_id,
        "inventory_id": validated_inventory["inventory_id"],
        "inventory_sha256": inventory_sha256,
    }
    return {"attestation_id": _attestation_id(payload), **payload}


def attach_attestation_signature(
    claim: Mapping[str, Any],
    signature: Mapping[str, Any],
) -> dict[str, Any]:
    """Attach externally produced signature material without generating a key."""

    if not isinstance(claim, Mapping):
        raise ActiveAttemptInventoryAttestationError(
            "INVENTORY_ATTESTATION_CLAIM_INVALID"
        )
    _exact_fields(
        claim,
        CLAIM_FIELDS,
        "INVENTORY_ATTESTATION_CLAIM_INVALID",
    )
    _validate_signature(signature)
    payload = _claim_payload(claim)
    if claim.get("attestation_id") != _attestation_id(payload):
        raise ActiveAttemptInventoryAttestationError(
            "INVENTORY_ATTESTATION_ID_MISMATCH"
        )
    return {**dict(claim), "signature": dict(signature)}


def verify_inventory_attestation(
    *,
    attestation: Mapping[str, Any],
    inventory: Mapping[str, Any],
    verifier: SignatureVerifier | None,
    allowed_source_instances: set[str] | frozenset[str],
    evaluated_at: str,
    expected_next_sequence: int,
    expected_previous_attestation_id: str | None,
    max_attestation_age_seconds: int = 60,
    max_attestation_ttl_seconds: int = 120,
    max_inventory_age_seconds: int = 30,
) -> dict[str, Any]:
    """Verify source identity, freshness, anti-replay and exact inventory binding."""

    if not isinstance(attestation, Mapping):
        raise ActiveAttemptInventoryAttestationError(
            "INVENTORY_ATTESTATION_INVALID"
        )
    _reject_forbidden_fields(attestation)
    _exact_fields(
        attestation,
        ATTESTATION_FIELDS,
        "INVENTORY_ATTESTATION_INVALID",
    )
    if attestation.get("schema_version") != SCHEMA_VERSION:
        raise ActiveAttemptInventoryAttestationError(
            "INVENTORY_ATTESTATION_SCHEMA_UNSUPPORTED"
        )
    if attestation.get("trust_domain") != TRUST_DOMAIN:
        raise ActiveAttemptInventoryAttestationError(
            "INVENTORY_ATTESTATION_TRUST_DOMAIN_MISMATCH"
        )
    if attestation.get("source_kind") != SOURCE_KIND:
        raise ActiveAttemptInventoryAttestationError(
            "INVENTORY_ATTESTATION_SOURCE_KIND_MISMATCH"
        )

    source_id = _validate_source_id(attestation.get("source_instance_id"))
    if (
        not isinstance(allowed_source_instances, (set, frozenset))
        or not allowed_source_instances
        or source_id not in allowed_source_instances
    ):
        raise ActiveAttemptInventoryAttestationError(
            "INVENTORY_ATTESTATION_SOURCE_NOT_ALLOWED"
        )

    sequence = _validate_sequence(
        attestation.get("source_sequence"),
        "INVENTORY_ATTESTATION_SEQUENCE_INVALID",
    )
    expected_sequence = _validate_sequence(
        expected_next_sequence,
        "INVENTORY_ATTESTATION_EXPECTED_SEQUENCE_INVALID",
    )
    if sequence != expected_sequence:
        raise ActiveAttemptInventoryAttestationError(
            "INVENTORY_ATTESTATION_SEQUENCE_REPLAY_OR_GAP"
        )
    previous = attestation.get("previous_attestation_id")
    if sequence == 1:
        if previous is not None or expected_previous_attestation_id is not None:
            raise ActiveAttemptInventoryAttestationError(
                "INVENTORY_ATTESTATION_PREDECESSOR_MISMATCH"
            )
    elif (
        expected_previous_attestation_id is None
        or previous != expected_previous_attestation_id
    ):
        raise ActiveAttemptInventoryAttestationError(
            "INVENTORY_ATTESTATION_PREDECESSOR_MISMATCH"
        )

    attestation_age = _validate_policy(
        max_attestation_age_seconds,
        maximum=MAX_ATTESTATION_AGE_SECONDS,
        code="INVENTORY_ATTESTATION_AGE_POLICY_INVALID",
    )
    attestation_ttl = _validate_policy(
        max_attestation_ttl_seconds,
        maximum=MAX_ATTESTATION_TTL_SECONDS,
        code="INVENTORY_ATTESTATION_TTL_POLICY_INVALID",
    )
    inventory_age = _validate_policy(
        max_inventory_age_seconds,
        maximum=MAX_INVENTORY_AGE_SECONDS,
        code="INVENTORY_ATTESTATION_INVENTORY_AGE_POLICY_INVALID",
    )

    now = _parse_time(evaluated_at, "INVENTORY_ATTESTATION_EVALUATED_AT_INVALID")
    issued = _parse_time(
        attestation.get("issued_at"),
        "INVENTORY_ATTESTATION_ISSUED_AT_INVALID",
    )
    expires = _parse_time(
        attestation.get("expires_at"),
        "INVENTORY_ATTESTATION_EXPIRES_AT_INVALID",
    )
    if expires <= issued or (expires - issued).total_seconds() > attestation_ttl:
        raise ActiveAttemptInventoryAttestationError(
            "INVENTORY_ATTESTATION_WINDOW_INVALID"
        )
    if issued > now:
        raise ActiveAttemptInventoryAttestationError(
            "INVENTORY_ATTESTATION_FUTURE"
        )
    if now >= expires:
        raise ActiveAttemptInventoryAttestationError(
            "INVENTORY_ATTESTATION_EXPIRED"
        )
    if (now - issued).total_seconds() > attestation_age:
        raise ActiveAttemptInventoryAttestationError(
            "INVENTORY_ATTESTATION_STALE"
        )

    validated_inventory, inventory_sha256 = _inventory_sha256(inventory)
    if attestation.get("inventory_id") != validated_inventory["inventory_id"]:
        raise ActiveAttemptInventoryAttestationError(
            "INVENTORY_ATTESTATION_INVENTORY_ID_MISMATCH"
        )
    if (
        not isinstance(attestation.get("inventory_sha256"), str)
        or _HEX_64.fullmatch(str(attestation.get("inventory_sha256"))) is None
        or attestation.get("inventory_sha256") != inventory_sha256
    ):
        raise ActiveAttemptInventoryAttestationError(
            "INVENTORY_ATTESTATION_INVENTORY_DIGEST_MISMATCH"
        )

    generated = _parse_time(
        validated_inventory["generated_at"],
        "INVENTORY_ATTESTATION_INVENTORY_TIME_INVALID",
    )
    if generated > issued:
        raise ActiveAttemptInventoryAttestationError(
            "INVENTORY_ATTESTATION_INVENTORY_FUTURE"
        )
    if (issued - generated).total_seconds() > inventory_age:
        raise ActiveAttemptInventoryAttestationError(
            "INVENTORY_ATTESTATION_INVENTORY_STALE"
        )

    payload = _claim_payload(attestation)
    if attestation.get("attestation_id") != _attestation_id(payload):
        raise ActiveAttemptInventoryAttestationError(
            "INVENTORY_ATTESTATION_ID_MISMATCH"
        )
    signature = _validate_signature(attestation.get("signature"))
    if verifier is None:
        raise ActiveAttemptInventoryAttestationError(
            "INVENTORY_ATTESTATION_VERIFIER_UNAVAILABLE"
        )
    try:
        verified = verifier(_canonical_bytes(payload), signature)
    except Exception as exc:  # noqa: BLE001 - trust defects fail closed
        raise ActiveAttemptInventoryAttestationError(
            "INVENTORY_ATTESTATION_SIGNATURE_UNTRUSTWORTHY"
        ) from exc
    if verified is not True:
        raise ActiveAttemptInventoryAttestationError(
            "INVENTORY_ATTESTATION_SIGNATURE_INVALID"
        )

    seed = {
        "attestation_id": attestation["attestation_id"],
        "inventory_id": validated_inventory["inventory_id"],
        "source_instance_id": source_id,
        "source_sequence": sequence,
        "verified_at": evaluated_at,
        "source_authenticity": SOURCE_AUTHENTICITY,
        "inventory_freshness": "FRESH",
        "source_completeness": SOURCE_COMPLETENESS,
    }
    return {
        "schema_version": SCHEMA_VERSION,
        "verification_id": f"raiver_{_digest(seed)[:32]}",
        **seed,
        "authorization_effect": "NONE",
        "execution_authority": "NONE",
        "limitations": [
            "SOURCE_COMPLETENESS_NOT_INDEPENDENTLY_VERIFIED",
            "ATTESTATION_TRUST_CONFIGURATION_EXTERNAL",
            "VERIFIED_INVENTORY_DOES_NOT_CREATE_EXECUTION_AUTHORITY",
        ],
    }


def plan_attested_kill_switch_cancellations(
    *,
    attestation: Mapping[str, Any],
    inventory: Mapping[str, Any],
    verifier: SignatureVerifier | None,
    allowed_source_instances: set[str] | frozenset[str],
    expected_next_sequence: int,
    expected_previous_attestation_id: str | None,
    kill_switch_path: Path | None,
    evaluated_at: str,
    max_attestation_age_seconds: int = 60,
    max_attestation_ttl_seconds: int = 120,
    max_inventory_age_seconds: int = 30,
    released_state_max_age_seconds: int = 300,
) -> dict[str, Any]:
    """Verify the exact inventory, then build cancellation messages without dispatch."""

    verified_ref = verify_inventory_attestation(
        attestation=attestation,
        inventory=inventory,
        verifier=verifier,
        allowed_source_instances=allowed_source_instances,
        evaluated_at=evaluated_at,
        expected_next_sequence=expected_next_sequence,
        expected_previous_attestation_id=expected_previous_attestation_id,
        max_attestation_age_seconds=max_attestation_age_seconds,
        max_attestation_ttl_seconds=max_attestation_ttl_seconds,
        max_inventory_age_seconds=max_inventory_age_seconds,
    )
    plan = cancellation.plan_kill_switch_cancellations(
        kill_switch_path=kill_switch_path,
        inventory=inventory,
        emitted_at=evaluated_at,
        released_state_max_age_seconds=released_state_max_age_seconds,
    )
    return {
        "schema_version": SCHEMA_VERSION,
        "verified_inventory_ref": verified_ref,
        "cancellation_plan": plan,
        "dispatch_performed": False,
        "authorization_effect": "NONE",
        "execution_authority": "NONE",
    }
