from __future__ import annotations

import base64
import hashlib
import importlib.util
import json
import sys
from copy import deepcopy
from pathlib import Path

import jsonschema
import pytest


ROOT = Path(__file__).resolve().parents[2]
GATEWAY = ROOT / "platform/gateway-protocol"
MODULE = GATEWAY / "runner_event_attestation.py"

spec = importlib.util.spec_from_file_location("runner_event_attestation_test", MODULE)
assert spec and spec.loader
event_attestation = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = event_attestation
spec.loader.exec_module(event_attestation)

CORRELATION = {
    "campaign_id": "11111111-1111-4111-8111-111111111111",
    "run_id": "22222222-2222-4222-8222-222222222222",
    "step_id": "33333333-3333-4333-8333-333333333333",
    "attempt_id": "44444444-4444-4444-8444-444444444444",
}
SOURCE = "runner-lab-01"


def request() -> dict:
    return {
        "message_type": "runner.cancellation.request",
        "protocol_version": "2.0.0",
        "correlation": CORRELATION,
        "emitted_at": "2026-08-08T12:00:00Z",
        "reason": "policy",
        "requested_by": "gateway",
    }


def ack() -> dict:
    return {
        "message_type": "runner.cancellation.ack",
        "protocol_version": "2.0.0",
        "correlation": CORRELATION,
        "emitted_at": "2026-08-08T12:00:05Z",
        "status": "accepted",
    }


def outcome() -> dict:
    return {
        "message_type": "runner.outcome",
        "protocol_version": "2.0.0",
        "correlation": CORRELATION,
        "emitted_at": "2026-08-08T12:00:15Z",
        "status": "CANCELLED",
        "started_at": "2026-08-08T11:59:00Z",
        "finished_at": "2026-08-08T12:00:14Z",
        "evidence_refs": [
            {
                "evidence_id": "55555555-5555-4555-8555-555555555555",
                "kind": "protocol",
                "classification": "INTERNAL",
                "sha256": "a" * 64,
            }
        ],
    }


def claim_payload(claim: dict) -> dict:
    return {
        key: claim[key]
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


def signature_for(claim: dict) -> dict:
    payload = json.dumps(
        claim_payload(claim),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    ).encode()
    return {
        "key_id": "runner-event-test-key",
        "algorithm": "Ed25519",
        "value": base64.b64encode(hashlib.sha256(payload).digest()).decode(),
    }


def verifier(payload: bytes, signature: dict) -> bool:
    expected = base64.b64encode(hashlib.sha256(payload).digest()).decode()
    return (
        signature.get("key_id") == "runner-event-test-key"
        and signature.get("algorithm") == "Ed25519"
        and signature.get("value") == expected
    )


def envelope(
    event: dict,
    *,
    sequence: int,
    issued_at: str,
    expires_at: str,
    previous: str | None,
    source: str = SOURCE,
) -> dict:
    claim = event_attestation.build_event_attestation_claim(
        event=event,
        source_instance_id=source,
        source_sequence=sequence,
        issued_at=issued_at,
        expires_at=expires_at,
        previous_attestation_id=previous,
    )
    return event_attestation.attach_event_signature(claim, signature_for(claim))


def chain() -> tuple[dict, dict]:
    ack_envelope = envelope(
        ack(),
        sequence=1,
        issued_at="2026-08-08T12:00:10Z",
        expires_at="2026-08-08T12:01:10Z",
        previous=None,
    )
    outcome_envelope = envelope(
        outcome(),
        sequence=2,
        issued_at="2026-08-08T12:00:16Z",
        expires_at="2026-08-08T12:01:16Z",
        previous=ack_envelope["attestation_id"],
    )
    return ack_envelope, outcome_envelope


def test_attested_observation_authenticates_events_without_upgrading_base_claims() -> None:
    ack_env, outcome_env = chain()
    result = event_attestation.observe_attested_cancellation(
        cancellation_request=request(),
        acknowledgements=[ack()],
        ack_attestation=ack_env,
        ack_verifier=verifier,
        ack_allowed_sources={SOURCE},
        ack_expected_next_sequence=1,
        ack_expected_previous_attestation_id=None,
        outcomes=[outcome()],
        outcome_attestation=outcome_env,
        outcome_verifier=verifier,
        outcome_allowed_sources={SOURCE},
        outcome_expected_next_sequence=2,
        outcome_expected_previous_attestation_id=ack_env["attestation_id"],
        observed_at="2026-08-08T12:00:20Z",
    )
    assert result["base_observation"]["state"] == "CANCELLED_DECLARED"
    assert result["base_observation"]["transport_authenticity"] == "NOT_VERIFIED"
    assert result["base_observation"]["terminal_outcome_authenticity"] == "NOT_VERIFIED"
    assert result["ack_event_ref"]["source_authenticity"] == "EXTERNALLY_VERIFIED"
    assert result["outcome_event_ref"]["source_authenticity"] == "EXTERNALLY_VERIFIED"
    assert result["observed_event_authenticity"] == "EXTERNALLY_VERIFIED"
    assert result["authenticity_effect"] == "ANNOTATION_ONLY"
    assert result["dispatch_performed_by_attestor"] is False
    assert result["authorization_effect"] == "NONE"
    assert result["execution_authority"] == "NONE"


def test_verified_event_ref_matches_strict_schema() -> None:
    ack_env, _ = chain()
    verified = event_attestation.verify_runner_event(
        event=ack(),
        attestation=ack_env,
        verifier=verifier,
        allowed_source_instances={SOURCE},
        expected_next_sequence=1,
        expected_previous_attestation_id=None,
        verified_at="2026-08-08T12:00:20Z",
    )
    schema = json.loads(
        (GATEWAY / "verified-runner-event-ref.schema.json").read_text(encoding="utf-8")
    )
    jsonschema.validate(verified, schema, format_checker=jsonschema.FormatChecker())
    assert "EVENT_AUTHENTICITY_DOES_NOT_PROVE_PROCESS_EFFECT" in verified["limitations"]


def test_source_spoof_and_missing_verifier_fail_closed() -> None:
    ack_env, _ = chain()
    with pytest.raises(
        event_attestation.RunnerEventAttestationError,
        match="RUNNER_EVENT_SOURCE_NOT_ALLOWED",
    ):
        event_attestation.verify_runner_event(
            event=ack(),
            attestation=ack_env,
            verifier=verifier,
            allowed_source_instances={"other-runner"},
            expected_next_sequence=1,
            expected_previous_attestation_id=None,
            verified_at="2026-08-08T12:00:20Z",
        )
    with pytest.raises(
        event_attestation.RunnerEventAttestationError,
        match="RUNNER_EVENT_VERIFIER_UNAVAILABLE",
    ):
        event_attestation.verify_runner_event(
            event=ack(),
            attestation=ack_env,
            verifier=None,
            allowed_source_instances={SOURCE},
            expected_next_sequence=1,
            expected_previous_attestation_id=None,
            verified_at="2026-08-08T12:00:20Z",
        )


def test_message_digest_tampering_fails_closed() -> None:
    ack_env, _ = chain()
    changed = ack()
    changed["status"] = "already_terminal"
    with pytest.raises(
        event_attestation.RunnerEventAttestationError,
        match="RUNNER_EVENT_DIGEST_MISMATCH",
    ):
        event_attestation.verify_runner_event(
            event=changed,
            attestation=ack_env,
            verifier=verifier,
            allowed_source_instances={SOURCE},
            expected_next_sequence=1,
            expected_previous_attestation_id=None,
            verified_at="2026-08-08T12:00:20Z",
        )


def test_attestation_claim_tampering_breaks_signature() -> None:
    ack_env, _ = chain()
    changed = deepcopy(ack_env)
    changed["source_instance_id"] = "runner-lab-02"
    payload = claim_payload(changed)
    changed["attestation_id"] = f"revt_{hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(',', ':'), ensure_ascii=True).encode()).hexdigest()[:32]}"
    with pytest.raises(
        event_attestation.RunnerEventAttestationError,
        match="RUNNER_EVENT_SIGNATURE_INVALID",
    ):
        event_attestation.verify_runner_event(
            event=ack(),
            attestation=changed,
            verifier=verifier,
            allowed_source_instances={"runner-lab-02"},
            expected_next_sequence=1,
            expected_previous_attestation_id=None,
            verified_at="2026-08-08T12:00:20Z",
        )


def test_sequence_replay_and_predecessor_mismatch_fail_closed() -> None:
    ack_env, outcome_env = chain()
    with pytest.raises(
        event_attestation.RunnerEventAttestationError,
        match="RUNNER_EVENT_SEQUENCE_REPLAY_OR_GAP",
    ):
        event_attestation.verify_runner_event(
            event=outcome(),
            attestation=outcome_env,
            verifier=verifier,
            allowed_source_instances={SOURCE},
            expected_next_sequence=3,
            expected_previous_attestation_id=outcome_env["attestation_id"],
            verified_at="2026-08-08T12:00:20Z",
        )
    with pytest.raises(
        event_attestation.RunnerEventAttestationError,
        match="RUNNER_EVENT_PREDECESSOR_MISMATCH",
    ):
        event_attestation.verify_runner_event(
            event=outcome(),
            attestation=outcome_env,
            verifier=verifier,
            allowed_source_instances={SOURCE},
            expected_next_sequence=2,
            expected_previous_attestation_id="revt_" + "f" * 32,
            verified_at="2026-08-08T12:00:20Z",
        )
    assert ack_env["source_sequence"] == 1


def test_stale_or_expired_attestation_and_stale_event_fail_closed() -> None:
    old_ack = ack()
    old_ack["emitted_at"] = "2026-08-08T11:50:00Z"
    stale_event_env = envelope(
        old_ack,
        sequence=1,
        issued_at="2026-08-08T12:00:10Z",
        expires_at="2026-08-08T12:01:10Z",
        previous=None,
    )
    with pytest.raises(
        event_attestation.RunnerEventAttestationError, match="RUNNER_EVENT_STALE"
    ):
        event_attestation.verify_runner_event(
            event=old_ack,
            attestation=stale_event_env,
            verifier=verifier,
            allowed_source_instances={SOURCE},
            expected_next_sequence=1,
            expected_previous_attestation_id=None,
            verified_at="2026-08-08T12:00:20Z",
            max_event_age_seconds=60,
        )

    ack_env = envelope(
        ack(),
        sequence=1,
        issued_at="2026-08-08T12:00:10Z",
        expires_at="2026-08-08T12:00:15Z",
        previous=None,
    )
    with pytest.raises(
        event_attestation.RunnerEventAttestationError,
        match="RUNNER_EVENT_ATTESTATION_EXPIRED",
    ):
        event_attestation.verify_runner_event(
            event=ack(),
            attestation=ack_env,
            verifier=verifier,
            allowed_source_instances={SOURCE},
            expected_next_sequence=1,
            expected_previous_attestation_id=None,
            verified_at="2026-08-08T12:00:20Z",
        )


def test_event_attestation_presence_must_match_observed_event() -> None:
    ack_env, _ = chain()
    with pytest.raises(
        event_attestation.RunnerEventAttestationError,
        match="RUNNER_ACK_ATTESTATION_PRESENCE_MISMATCH",
    ):
        event_attestation.observe_attested_cancellation(
            cancellation_request=request(),
            acknowledgements=None,
            ack_attestation=ack_env,
            ack_verifier=verifier,
            ack_allowed_sources={SOURCE},
            ack_expected_next_sequence=1,
            ack_expected_previous_attestation_id=None,
            outcomes=None,
            outcome_attestation=None,
            outcome_verifier=None,
            outcome_allowed_sources={SOURCE},
            outcome_expected_next_sequence=1,
            outcome_expected_previous_attestation_id=None,
            observed_at="2026-08-08T12:00:20Z",
        )


def test_no_events_observed_needs_no_signature_and_creates_no_authority() -> None:
    result = event_attestation.observe_attested_cancellation(
        cancellation_request=request(),
        acknowledgements=None,
        ack_attestation=None,
        ack_verifier=None,
        ack_allowed_sources=set(),
        ack_expected_next_sequence=1,
        ack_expected_previous_attestation_id=None,
        outcomes=None,
        outcome_attestation=None,
        outcome_verifier=None,
        outcome_allowed_sources=set(),
        outcome_expected_next_sequence=1,
        outcome_expected_previous_attestation_id=None,
        observed_at="2026-08-08T12:00:20Z",
    )
    assert result["base_observation"]["state"] == "WAITING_ACK"
    assert result["observed_event_authenticity"] == "NO_EVENTS_OBSERVED"
    assert result["ack_event_ref"] is None
    assert result["outcome_event_ref"] is None
    assert result["authorization_effect"] == "NONE"
    assert result["execution_authority"] == "NONE"
