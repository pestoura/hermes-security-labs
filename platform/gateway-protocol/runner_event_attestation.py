"""External authenticity overlay for Runner cancellation ACK/outcome events.

This repository-only contract verifies signed envelopes for already-observed
Runner Protocol v2 events. It does not send messages, signal processes, grant
authorization or independently prove process termination.
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

from runner_protocol_v2 import ProtocolValidationError, validate_semantics

ROOT = Path(__file__).resolve().parent


def _load_module(name: str, path: Path) -> Any:
    existing = sys.modules.get(name)
    if existing is not None:
        return existing
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:  # pragma: no cover
        raise RuntimeError(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


observation = _load_module(
    "cancellation_observation_event_attestation",
    ROOT / "cancellation_observation.py",
)

SCHEMA_VERSION = "1.0.0"
TRUST_DOMAIN = "RUNNER_EVENT_ATTESTATION_V1"
SOURCE_KIND = "RUNNER"
MAX_ATTESTATION_AGE_SECONDS = 300
MAX_ATTESTATION_TTL_SECONDS = 300
MAX_EVENT_AGE_SECONDS = 1800
MAX_SEQUENCE = 2**63 - 1
SOURCE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
ATTESTATION_ID = re.compile(r"^revt_[a-f0-9]{32}$")
SUPPORTED_TYPES = {"runner.cancellation.ack", "runner.outcome"}
ALGORITHMS = {"Ed25519", "ECDSA-P256-SHA256"}
SignatureVerifier = Callable[[bytes, Mapping[str, Any]], bool]


class RunnerEventAttestationError(ValueError):
    """Fail-closed Runner-event attestation violation."""


def _canonical(value: Any) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=True
    ).encode("utf-8")


def _digest(value: Any) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def _parse_time(value: Any, code: str) -> datetime:
    if not isinstance(value, str) or not value:
        raise RunnerEventAttestationError(code)
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise RunnerEventAttestationError(code) from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise RunnerEventAttestationError(code)
    return parsed.astimezone(timezone.utc)


def _sequence(value: Any, code: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= MAX_SEQUENCE:
        raise RunnerEventAttestationError(code)
    return value


def _bounded_int(value: Any, maximum: int, code: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= maximum:
        raise RunnerEventAttestationError(code)
    return value


def _validate_event(event: Mapping[str, Any]) -> dict[str, Any]:
    if not isinstance(event, Mapping):
        raise RunnerEventAttestationError("RUNNER_EVENT_INVALID")
    candidate = dict(event)
    try:
        validate_semantics(candidate)
    except ProtocolValidationError as exc:
        raise RunnerEventAttestationError("RUNNER_EVENT_INVALID") from exc
    if candidate.get("message_type") not in SUPPORTED_TYPES:
        raise RunnerEventAttestationError("RUNNER_EVENT_TYPE_UNSUPPORTED")
    return candidate


def _signature(value: Any) -> Mapping[str, Any]:
    if not isinstance(value, Mapping) or set(value) != {"key_id", "algorithm", "value"}:
        raise RunnerEventAttestationError("RUNNER_EVENT_SIGNATURE_INVALID")
    if not isinstance(value["key_id"], str) or not 1 <= len(value["key_id"]) <= 128:
        raise RunnerEventAttestationError("RUNNER_EVENT_SIGNATURE_INVALID")
    if value["algorithm"] not in ALGORITHMS:
        raise RunnerEventAttestationError("RUNNER_EVENT_ALGORITHM_UNSUPPORTED")
    if not isinstance(value["value"], str) or not value["value"] or len(value["value"]) > 8192:
        raise RunnerEventAttestationError("RUNNER_EVENT_SIGNATURE_INVALID")
    try:
        base64.b64decode(value["value"], validate=True)
    except (binascii.Error, ValueError) as exc:
        raise RunnerEventAttestationError("RUNNER_EVENT_SIGNATURE_INVALID") from exc
    return value


def _payload(attestation: Mapping[str, Any]) -> dict[str, Any]:
    return {
        key: attestation[key]
        for key in (
            "schema_version",
            "trust_domain",
            "source_kind",
            "source_instance_id",
            "source_sequence",
            "issued_at",
            "expires_at",
            "previous_attestation_id",
            "message_type",
            "message_sha256",
            "correlation",
        )
    }


def _id(payload: Mapping[str, Any]) -> str:
    return f"revt_{_digest(payload)[:32]}"


def build_event_attestation_claim(
    *,
    event: Mapping[str, Any],
    source_instance_id: str,
    source_sequence: int,
    issued_at: str,
    expires_at: str,
    previous_attestation_id: str | None,
) -> dict[str, Any]:
    validated = _validate_event(event)
    if not isinstance(source_instance_id, str) or SOURCE_ID.fullmatch(source_instance_id) is None:
        raise RunnerEventAttestationError("RUNNER_EVENT_SOURCE_INVALID")
    sequence = _sequence(source_sequence, "RUNNER_EVENT_SEQUENCE_INVALID")
    issued = _parse_time(issued_at, "RUNNER_EVENT_ISSUED_AT_INVALID")
    expires = _parse_time(expires_at, "RUNNER_EVENT_EXPIRES_AT_INVALID")
    if expires <= issued:
        raise RunnerEventAttestationError("RUNNER_EVENT_ATTESTATION_WINDOW_INVALID")
    if sequence == 1 and previous_attestation_id is not None:
        raise RunnerEventAttestationError("RUNNER_EVENT_PREDECESSOR_UNEXPECTED")
    if sequence > 1 and (
        not isinstance(previous_attestation_id, str)
        or ATTESTATION_ID.fullmatch(previous_attestation_id) is None
    ):
        raise RunnerEventAttestationError("RUNNER_EVENT_PREDECESSOR_REQUIRED")
    payload = {
        "schema_version": SCHEMA_VERSION,
        "trust_domain": TRUST_DOMAIN,
        "source_kind": SOURCE_KIND,
        "source_instance_id": source_instance_id,
        "source_sequence": sequence,
        "issued_at": issued_at,
        "expires_at": expires_at,
        "previous_attestation_id": previous_attestation_id,
        "message_type": validated["message_type"],
        "message_sha256": _digest(validated),
        "correlation": dict(validated["correlation"]),
    }
    return {"attestation_id": _id(payload), **payload}


def attach_event_signature(
    claim: Mapping[str, Any], signature: Mapping[str, Any]
) -> dict[str, Any]:
    if not isinstance(claim, Mapping) or "signature" in claim:
        raise RunnerEventAttestationError("RUNNER_EVENT_CLAIM_INVALID")
    payload = _payload(claim)
    if set(claim) != {"attestation_id", *payload.keys()} or claim.get("attestation_id") != _id(payload):
        raise RunnerEventAttestationError("RUNNER_EVENT_CLAIM_INVALID")
    _signature(signature)
    return {**dict(claim), "signature": dict(signature)}


def verify_runner_event(
    *,
    event: Mapping[str, Any],
    attestation: Mapping[str, Any],
    verifier: SignatureVerifier | None,
    allowed_source_instances: set[str] | frozenset[str],
    expected_next_sequence: int,
    expected_previous_attestation_id: str | None,
    verified_at: str,
    max_attestation_age_seconds: int = 60,
    max_attestation_ttl_seconds: int = 120,
    max_event_age_seconds: int = 300,
) -> dict[str, Any]:
    validated = _validate_event(event)
    if not isinstance(attestation, Mapping):
        raise RunnerEventAttestationError("RUNNER_EVENT_ATTESTATION_INVALID")
    expected_fields = {
        "attestation_id", "schema_version", "trust_domain", "source_kind",
        "source_instance_id", "source_sequence", "issued_at", "expires_at",
        "previous_attestation_id", "message_type", "message_sha256",
        "correlation", "signature",
    }
    if set(attestation) != expected_fields:
        raise RunnerEventAttestationError("RUNNER_EVENT_ATTESTATION_INVALID")
    if attestation.get("schema_version") != SCHEMA_VERSION or attestation.get("trust_domain") != TRUST_DOMAIN:
        raise RunnerEventAttestationError("RUNNER_EVENT_TRUST_DOMAIN_MISMATCH")
    if attestation.get("source_kind") != SOURCE_KIND:
        raise RunnerEventAttestationError("RUNNER_EVENT_SOURCE_KIND_MISMATCH")
    source = attestation.get("source_instance_id")
    if not isinstance(source, str) or SOURCE_ID.fullmatch(source) is None:
        raise RunnerEventAttestationError("RUNNER_EVENT_SOURCE_INVALID")
    if not isinstance(allowed_source_instances, (set, frozenset)) or source not in allowed_source_instances:
        raise RunnerEventAttestationError("RUNNER_EVENT_SOURCE_NOT_ALLOWED")
    sequence = _sequence(attestation.get("source_sequence"), "RUNNER_EVENT_SEQUENCE_INVALID")
    expected = _sequence(expected_next_sequence, "RUNNER_EVENT_EXPECTED_SEQUENCE_INVALID")
    if sequence != expected:
        raise RunnerEventAttestationError("RUNNER_EVENT_SEQUENCE_REPLAY_OR_GAP")
    previous = attestation.get("previous_attestation_id")
    if sequence == 1:
        if previous is not None or expected_previous_attestation_id is not None:
            raise RunnerEventAttestationError("RUNNER_EVENT_PREDECESSOR_MISMATCH")
    elif previous != expected_previous_attestation_id or expected_previous_attestation_id is None:
        raise RunnerEventAttestationError("RUNNER_EVENT_PREDECESSOR_MISMATCH")

    age_limit = _bounded_int(max_attestation_age_seconds, MAX_ATTESTATION_AGE_SECONDS, "RUNNER_EVENT_AGE_POLICY_INVALID")
    ttl_limit = _bounded_int(max_attestation_ttl_seconds, MAX_ATTESTATION_TTL_SECONDS, "RUNNER_EVENT_TTL_POLICY_INVALID")
    event_age_limit = _bounded_int(max_event_age_seconds, MAX_EVENT_AGE_SECONDS, "RUNNER_EVENT_EVENT_AGE_POLICY_INVALID")
    now = _parse_time(verified_at, "RUNNER_EVENT_VERIFIED_AT_INVALID")
    issued = _parse_time(attestation.get("issued_at"), "RUNNER_EVENT_ISSUED_AT_INVALID")
    expires = _parse_time(attestation.get("expires_at"), "RUNNER_EVENT_EXPIRES_AT_INVALID")
    if expires <= issued or (expires - issued).total_seconds() > ttl_limit:
        raise RunnerEventAttestationError("RUNNER_EVENT_ATTESTATION_WINDOW_INVALID")
    if issued > now:
        raise RunnerEventAttestationError("RUNNER_EVENT_ATTESTATION_FUTURE")
    if now >= expires:
        raise RunnerEventAttestationError("RUNNER_EVENT_ATTESTATION_EXPIRED")
    if (now - issued).total_seconds() > age_limit:
        raise RunnerEventAttestationError("RUNNER_EVENT_ATTESTATION_STALE")
    event_time = _parse_time(validated["emitted_at"], "RUNNER_EVENT_EMITTED_AT_INVALID")
    if event_time > issued:
        raise RunnerEventAttestationError("RUNNER_EVENT_AFTER_ATTESTATION")
    if (issued - event_time).total_seconds() > event_age_limit:
        raise RunnerEventAttestationError("RUNNER_EVENT_STALE")
    if attestation.get("message_type") != validated["message_type"]:
        raise RunnerEventAttestationError("RUNNER_EVENT_TYPE_MISMATCH")
    if attestation.get("correlation") != validated["correlation"]:
        raise RunnerEventAttestationError("RUNNER_EVENT_CORRELATION_MISMATCH")
    if attestation.get("message_sha256") != _digest(validated):
        raise RunnerEventAttestationError("RUNNER_EVENT_DIGEST_MISMATCH")
    payload = _payload(attestation)
    if attestation.get("attestation_id") != _id(payload):
        raise RunnerEventAttestationError("RUNNER_EVENT_ATTESTATION_ID_MISMATCH")
    sig = _signature(attestation.get("signature"))
    if verifier is None:
        raise RunnerEventAttestationError("RUNNER_EVENT_VERIFIER_UNAVAILABLE")
    try:
        trusted = verifier(_canonical(payload), sig)
    except Exception as exc:  # noqa: BLE001
        raise RunnerEventAttestationError("RUNNER_EVENT_SIGNATURE_UNTRUSTWORTHY") from exc
    if trusted is not True:
        raise RunnerEventAttestationError("RUNNER_EVENT_SIGNATURE_INVALID")
    seed = {
        "attestation_id": attestation["attestation_id"],
        "message_sha256": attestation["message_sha256"],
        "verified_at": verified_at,
    }
    return {
        "schema_version": SCHEMA_VERSION,
        "verification_id": f"rever_{_digest(seed)[:32]}",
        "attestation_id": attestation["attestation_id"],
        "message_type": validated["message_type"],
        "message_sha256": attestation["message_sha256"],
        "source_instance_id": source,
        "source_sequence": sequence,
        "verified_at": verified_at,
        "source_authenticity": "EXTERNALLY_VERIFIED",
        "authorization_effect": "NONE",
        "execution_authority": "NONE",
        "limitations": [
            "EVENT_AUTHENTICITY_DOES_NOT_PROVE_PROCESS_EFFECT",
            "EVENT_TRUST_CONFIGURATION_EXTERNAL",
            "VERIFIED_EVENT_DOES_NOT_CREATE_EXECUTION_AUTHORITY",
        ],
    }


def _distinct_event(messages: Sequence[Mapping[str, Any]] | None, message_type: str) -> dict[str, Any] | None:
    return observation._one_distinct(  # noqa: SLF001
        messages,
        expected_type=message_type,
        invalid_code="RUNNER_EVENT_INVALID",
        conflict_code="RUNNER_EVENT_CONFLICT",
    )


def observe_attested_cancellation(
    *,
    cancellation_request: Mapping[str, Any],
    acknowledgements: Sequence[Mapping[str, Any]] | None,
    ack_attestation: Mapping[str, Any] | None,
    ack_verifier: SignatureVerifier | None,
    ack_allowed_sources: set[str] | frozenset[str],
    ack_expected_next_sequence: int,
    ack_expected_previous_attestation_id: str | None,
    outcomes: Sequence[Mapping[str, Any]] | None,
    outcome_attestation: Mapping[str, Any] | None,
    outcome_verifier: SignatureVerifier | None,
    outcome_allowed_sources: set[str] | frozenset[str],
    outcome_expected_next_sequence: int,
    outcome_expected_previous_attestation_id: str | None,
    observed_at: str,
    acknowledgement_deadline_seconds: int = 30,
    terminal_deadline_seconds: int = 300,
) -> dict[str, Any]:
    base = observation.observe_cancellation(
        cancellation_request=cancellation_request,
        acknowledgements=acknowledgements,
        outcomes=outcomes,
        observed_at=observed_at,
        acknowledgement_deadline_seconds=acknowledgement_deadline_seconds,
        terminal_deadline_seconds=terminal_deadline_seconds,
    )
    ack_event = _distinct_event(acknowledgements, "runner.cancellation.ack")
    outcome_event = _distinct_event(outcomes, "runner.outcome")
    if (ack_event is None) != (ack_attestation is None):
        raise RunnerEventAttestationError("RUNNER_ACK_ATTESTATION_PRESENCE_MISMATCH")
    if (outcome_event is None) != (outcome_attestation is None):
        raise RunnerEventAttestationError("RUNNER_OUTCOME_ATTESTATION_PRESENCE_MISMATCH")
    ack_ref = None
    outcome_ref = None
    if ack_event is not None:
        ack_ref = verify_runner_event(
            event=ack_event,
            attestation=ack_attestation,
            verifier=ack_verifier,
            allowed_source_instances=ack_allowed_sources,
            expected_next_sequence=ack_expected_next_sequence,
            expected_previous_attestation_id=ack_expected_previous_attestation_id,
            verified_at=observed_at,
        )
    if outcome_event is not None:
        outcome_ref = verify_runner_event(
            event=outcome_event,
            attestation=outcome_attestation,
            verifier=outcome_verifier,
            allowed_source_instances=outcome_allowed_sources,
            expected_next_sequence=outcome_expected_next_sequence,
            expected_previous_attestation_id=outcome_expected_previous_attestation_id,
            verified_at=observed_at,
        )
    return {
        "schema_version": SCHEMA_VERSION,
        "base_observation": base,
        "ack_event_ref": ack_ref,
        "outcome_event_ref": outcome_ref,
        "observed_event_authenticity": "EXTERNALLY_VERIFIED" if (ack_ref or outcome_ref) else "NO_EVENTS_OBSERVED",
        "authenticity_effect": "ANNOTATION_ONLY",
        "dispatch_performed_by_attestor": False,
        "authorization_effect": "NONE",
        "execution_authority": "NONE",
        "limitations": [
            "EVENT_AUTHENTICITY_DOES_NOT_PROVE_PROCESS_EFFECT",
            "ATTESTOR_DOES_NOT_DISPATCH_CANCELLATION",
            "ATTESTOR_DOES_NOT_PROVE_PROCESS_TERMINATION",
            "PRODUCTION_RUNNER_EVENT_TRUST_INTEGRATION_NOT_RUN",
        ],
    }
