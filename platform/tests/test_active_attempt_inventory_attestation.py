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
ATTESTATION_MODULE = GATEWAY / "active_attempt_inventory_attestation.py"
CANCELLATION_MODULE = GATEWAY / "kill_switch_cancellation.py"


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


attestation = load_module("active_attempt_inventory_attestation_test", ATTESTATION_MODULE)
cancellation = load_module("kill_switch_cancellation_attestation_test", CANCELLATION_MODULE)

NOW = "2026-08-08T12:00:00Z"
ISSUED = "2026-08-08T11:59:50Z"
EXPIRES = "2026-08-08T12:00:50Z"
SOURCE = "runner-supervisor-lab-01"

CORRELATION = {
    "campaign_id": "11111111-1111-4111-8111-111111111111",
    "run_id": "22222222-2222-4222-8222-222222222222",
    "step_id": "33333333-3333-4333-8333-333333333333",
    "attempt_id": "44444444-4444-4444-8444-444444444444",
}


def schema(name: str) -> dict:
    return json.loads((GATEWAY / name).read_text(encoding="utf-8"))


def inventory(*, generated_at: str = "2026-08-08T11:59:40Z") -> dict:
    return cancellation.build_active_attempt_inventory(
        attempts=[
            {
                "correlation": CORRELATION,
                "state": "running",
                "cancellation_mode": "cooperative_then_force",
                "grace_period_ms": 5000,
            }
        ],
        generated_at=generated_at,
    )


def signature_for(claim: dict) -> dict:
    payload = {
        field: claim[field]
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
    encoded = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    ).encode("utf-8")
    value = base64.b64encode(hashlib.sha256(encoded).digest()).decode("ascii")
    return {
        "key_id": "inventory-attestation-test-key",
        "algorithm": "Ed25519",
        "value": value,
    }


def verifier(payload: bytes, signature: dict) -> bool:
    expected = base64.b64encode(hashlib.sha256(payload).digest()).decode("ascii")
    return (
        signature.get("key_id") == "inventory-attestation-test-key"
        and signature.get("algorithm") == "Ed25519"
        and signature.get("value") == expected
    )


def envelope(
    snapshot: dict,
    *,
    sequence: int = 1,
    issued_at: str = ISSUED,
    expires_at: str = EXPIRES,
    previous_attestation_id: str | None = None,
    source: str = SOURCE,
) -> dict:
    claim = attestation.build_attestation_claim(
        inventory=snapshot,
        source_instance_id=source,
        source_sequence=sequence,
        issued_at=issued_at,
        expires_at=expires_at,
        previous_attestation_id=previous_attestation_id,
    )
    return attestation.attach_attestation_signature(claim, signature_for(claim))


def write_kill_switch(path: Path, *, state: str = "engaged") -> Path:
    path.write_text(
        json.dumps(
            {
                "schema_version": "1.0.0",
                "state": state,
                "scope": "global",
                "reason_code": "operator-halt",
                "updated_at": "2026-08-08T11:59:55Z",
            }
        ),
        encoding="utf-8",
    )
    return path


def test_fresh_signed_inventory_builds_cancellation_without_dispatch(tmp_path: Path) -> None:
    snapshot = inventory()
    signed = envelope(snapshot)

    jsonschema.validate(
        signed,
        schema("active-attempt-inventory-attestation.schema.json"),
        format_checker=jsonschema.FormatChecker(),
    )
    result = attestation.plan_attested_kill_switch_cancellations(
        attestation=signed,
        inventory=snapshot,
        verifier=verifier,
        allowed_source_instances={SOURCE},
        expected_next_sequence=1,
        expected_previous_attestation_id=None,
        kill_switch_path=write_kill_switch(tmp_path / "switch.json"),
        evaluated_at=NOW,
    )

    verified = result["verified_inventory_ref"]
    plan = result["cancellation_plan"]
    jsonschema.validate(
        verified,
        schema("verified-active-attempt-inventory-ref.schema.json"),
        format_checker=jsonschema.FormatChecker(),
    )
    jsonschema.validate(
        plan,
        schema("kill-switch-cancellation-plan.schema.json"),
        format_checker=jsonschema.FormatChecker(),
    )
    wrapper_schema = schema("attested-kill-switch-cancellation-result.schema.json")
    assert wrapper_schema["additionalProperties"] is False
    assert result["dispatch_performed"] is False
    assert result["authorization_effect"] == "NONE"
    assert result["execution_authority"] == "NONE"
    assert verified["source_authenticity"] == "EXTERNALLY_VERIFIED"
    assert verified["inventory_freshness"] == "FRESH"
    assert (
        verified["source_completeness"]
        == "SOURCE_DECLARED_COMPLETE_NOT_INDEPENDENTLY_VERIFIED"
    )
    assert snapshot["source_authenticity"] == "NOT_VERIFIED"
    assert plan["decision"] == "CANCEL_REQUIRED"
    assert len(plan["cancellation_requests"]) == 1
    assert plan["cancellation_requests"][0]["message_type"] == "runner.cancellation.request"


def test_verifier_is_required_and_false_signature_fails_closed() -> None:
    snapshot = inventory()
    signed = envelope(snapshot)

    with pytest.raises(
        attestation.ActiveAttemptInventoryAttestationError,
        match="INVENTORY_ATTESTATION_VERIFIER_UNAVAILABLE",
    ):
        attestation.verify_inventory_attestation(
            attestation=signed,
            inventory=snapshot,
            verifier=None,
            allowed_source_instances={SOURCE},
            evaluated_at=NOW,
            expected_next_sequence=1,
            expected_previous_attestation_id=None,
        )

    with pytest.raises(
        attestation.ActiveAttemptInventoryAttestationError,
        match="INVENTORY_ATTESTATION_SIGNATURE_INVALID",
    ):
        attestation.verify_inventory_attestation(
            attestation=signed,
            inventory=snapshot,
            verifier=lambda _payload, _signature: False,
            allowed_source_instances={SOURCE},
            evaluated_at=NOW,
            expected_next_sequence=1,
            expected_previous_attestation_id=None,
        )


def test_unexpected_source_instance_is_refused() -> None:
    snapshot = inventory()
    signed = envelope(snapshot)
    with pytest.raises(
        attestation.ActiveAttemptInventoryAttestationError,
        match="INVENTORY_ATTESTATION_SOURCE_NOT_ALLOWED",
    ):
        attestation.verify_inventory_attestation(
            attestation=signed,
            inventory=snapshot,
            verifier=verifier,
            allowed_source_instances={"different-supervisor"},
            evaluated_at=NOW,
            expected_next_sequence=1,
            expected_previous_attestation_id=None,
        )


def test_exact_inventory_digest_binding_detects_tampering() -> None:
    snapshot = inventory()
    signed = envelope(snapshot)
    tampered = deepcopy(snapshot)
    tampered["attempts"][0]["grace_period_ms"] = 1

    with pytest.raises(cancellation.KillSwitchCancellationError):
        attestation.verify_inventory_attestation(
            attestation=signed,
            inventory=tampered,
            verifier=verifier,
            allowed_source_instances={SOURCE},
            evaluated_at=NOW,
            expected_next_sequence=1,
            expected_previous_attestation_id=None,
        )


def test_claim_tampering_breaks_external_signature() -> None:
    snapshot = inventory()
    signed = envelope(snapshot)
    tampered = deepcopy(signed)
    tampered["source_instance_id"] = "runner-supervisor-lab-02"
    payload = {
        field: tampered[field]
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
    tampered["attestation_id"] = f"raiatt_{hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(',', ':'), ensure_ascii=True).encode()).hexdigest()[:32]}"

    with pytest.raises(
        attestation.ActiveAttemptInventoryAttestationError,
        match="INVENTORY_ATTESTATION_SIGNATURE_INVALID",
    ):
        attestation.verify_inventory_attestation(
            attestation=tampered,
            inventory=snapshot,
            verifier=verifier,
            allowed_source_instances={"runner-supervisor-lab-02"},
            evaluated_at=NOW,
            expected_next_sequence=1,
            expected_previous_attestation_id=None,
        )


@pytest.mark.parametrize(
    ("issued_at", "expires_at", "code", "age", "ttl"),
    [
        (
            "2026-08-08T11:58:00Z",
            "2026-08-08T12:01:00Z",
            "INVENTORY_ATTESTATION_STALE",
            30,
            300,
        ),
        (
            "2026-08-08T12:00:10Z",
            "2026-08-08T12:01:00Z",
            "INVENTORY_ATTESTATION_FUTURE",
            60,
            120,
        ),
        (
            "2026-08-08T11:59:00Z",
            "2026-08-08T11:59:59Z",
            "INVENTORY_ATTESTATION_EXPIRED",
            120,
            120,
        ),
    ],
)
def test_stale_future_or_expired_attestation_is_refused(
    issued_at: str,
    expires_at: str,
    code: str,
    age: int,
    ttl: int,
) -> None:
    snapshot = inventory(generated_at="2026-08-08T11:57:55Z" if "58:00" in issued_at else "2026-08-08T11:58:55Z")
    signed = envelope(snapshot, issued_at=issued_at, expires_at=expires_at)
    with pytest.raises(attestation.ActiveAttemptInventoryAttestationError, match=code):
        attestation.verify_inventory_attestation(
            attestation=signed,
            inventory=snapshot,
            verifier=verifier,
            allowed_source_instances={SOURCE},
            evaluated_at=NOW,
            expected_next_sequence=1,
            expected_previous_attestation_id=None,
            max_attestation_age_seconds=age,
            max_attestation_ttl_seconds=ttl,
            max_inventory_age_seconds=60,
        )


def test_stale_inventory_is_refused_even_when_attestation_is_fresh() -> None:
    snapshot = inventory(generated_at="2026-08-08T11:58:00Z")
    signed = envelope(snapshot)
    with pytest.raises(
        attestation.ActiveAttemptInventoryAttestationError,
        match="INVENTORY_ATTESTATION_INVENTORY_STALE",
    ):
        attestation.verify_inventory_attestation(
            attestation=signed,
            inventory=snapshot,
            verifier=verifier,
            allowed_source_instances={SOURCE},
            evaluated_at=NOW,
            expected_next_sequence=1,
            expected_previous_attestation_id=None,
            max_inventory_age_seconds=30,
        )


def test_sequence_and_predecessor_are_server_side_anti_replay_inputs() -> None:
    first_snapshot = inventory(generated_at="2026-08-08T11:59:20Z")
    first = envelope(
        first_snapshot,
        issued_at="2026-08-08T11:59:30Z",
        expires_at="2026-08-08T12:00:30Z",
    )
    second_snapshot = inventory(generated_at="2026-08-08T11:59:40Z")
    second = envelope(
        second_snapshot,
        sequence=2,
        previous_attestation_id=first["attestation_id"],
    )

    verified = attestation.verify_inventory_attestation(
        attestation=second,
        inventory=second_snapshot,
        verifier=verifier,
        allowed_source_instances={SOURCE},
        evaluated_at=NOW,
        expected_next_sequence=2,
        expected_previous_attestation_id=first["attestation_id"],
    )
    assert verified["source_sequence"] == 2

    with pytest.raises(
        attestation.ActiveAttemptInventoryAttestationError,
        match="INVENTORY_ATTESTATION_SEQUENCE_REPLAY_OR_GAP",
    ):
        attestation.verify_inventory_attestation(
            attestation=second,
            inventory=second_snapshot,
            verifier=verifier,
            allowed_source_instances={SOURCE},
            evaluated_at=NOW,
            expected_next_sequence=3,
            expected_previous_attestation_id=second["attestation_id"],
        )

    with pytest.raises(
        attestation.ActiveAttemptInventoryAttestationError,
        match="INVENTORY_ATTESTATION_PREDECESSOR_MISMATCH",
    ):
        attestation.verify_inventory_attestation(
            attestation=second,
            inventory=second_snapshot,
            verifier=verifier,
            allowed_source_instances={SOURCE},
            evaluated_at=NOW,
            expected_next_sequence=2,
            expected_previous_attestation_id="raiatt_" + "f" * 32,
        )


def test_attestation_contract_rejects_execution_and_authority_fields() -> None:
    snapshot = inventory()
    claim = attestation.build_attestation_claim(
        inventory=snapshot,
        source_instance_id=SOURCE,
        source_sequence=1,
        issued_at=ISSUED,
        expires_at=EXPIRES,
        previous_attestation_id=None,
    )
    polluted = deepcopy(claim)
    polluted["authorization_ref"] = "must-not-be-accepted"
    polluted["signature"] = signature_for(claim)
    with pytest.raises(
        attestation.ActiveAttemptInventoryAttestationError,
        match="INVENTORY_ATTESTATION_FORBIDDEN_FIELD",
    ):
        attestation.verify_inventory_attestation(
            attestation=polluted,
            inventory=snapshot,
            verifier=verifier,
            allowed_source_instances={SOURCE},
            evaluated_at=NOW,
            expected_next_sequence=1,
            expected_previous_attestation_id=None,
        )


def test_result_schema_reuses_existing_strict_contracts() -> None:
    result_schema = schema("attested-kill-switch-cancellation-result.schema.json")
    assert result_schema["additionalProperties"] is False
    assert (
        result_schema["properties"]["verified_inventory_ref"]["$ref"]
        == "verified-active-attempt-inventory-ref.schema.json"
    )
    assert (
        result_schema["properties"]["cancellation_plan"]["$ref"]
        == "kill-switch-cancellation-plan.schema.json"
    )
    assert result_schema["properties"]["dispatch_performed"]["const"] is False
    assert result_schema["properties"]["authorization_effect"]["const"] == "NONE"
    assert result_schema["properties"]["execution_authority"]["const"] == "NONE"
