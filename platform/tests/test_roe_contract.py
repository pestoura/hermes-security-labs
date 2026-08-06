from __future__ import annotations

import copy
import importlib.util
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pytest

MODULE_PATH = (
    Path(__file__).resolve().parents[1] / "roe-contract" / "roe_contract.py"
)
SPEC = importlib.util.spec_from_file_location("roe_contract", MODULE_PATH)
assert SPEC and SPEC.loader
roe_contract = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = roe_contract
SPEC.loader.exec_module(roe_contract)


def _contract() -> dict[str, Any]:
    contract: dict[str, Any] = {
        "schema_version": "1.0.0",
        "contract_id": "roe-contract-001",
        "campaign_id": "campaign-001",
        "revision": 1,
        "state": "active",
        "issued_at": "2026-08-01T08:00:00Z",
        "valid_from": "2026-08-01T09:00:00Z",
        "valid_until": "2026-08-31T18:00:00Z",
        "issuer": {
            "party_id": "hexor-security",
            "legal_name": "Hexor Security",
        },
        "customer": {
            "party_id": "customer-example",
            "legal_name": "Customer Example",
        },
        "authorization": {
            "allowed_targets": [
                {
                    "type": "domain",
                    "value": "demo.example.test",
                    "match": "subdomains",
                },
                {
                    "type": "cidr",
                    "value": "192.0.2.0/24",
                    "match": "contained",
                },
                {
                    "type": "uri-prefix",
                    "value": "https://portal.example.test/app",
                    "match": "contained",
                },
                {
                    "type": "lab-asset",
                    "value": "juice-shop-demo",
                    "match": "exact",
                },
            ],
            "excluded_targets": [
                {
                    "type": "domain",
                    "value": "admin.demo.example.test",
                    "match": "exact",
                },
                {
                    "type": "ip",
                    "value": "192.0.2.200",
                    "match": "exact",
                },
            ],
            "allowed_capabilities": [
                "web.discovery.*",
                "web.validation.sql-injection",
            ],
            "prohibited_capabilities": [
                "web.validation.denial-of-service",
            ],
            "intrusiveness_ceiling": "L4",
            "execution_windows": [
                {
                    "window_id": "window-primary",
                    "start": "2026-08-01T09:00:00Z",
                    "end": "2026-08-31T18:00:00Z",
                }
            ],
            "approvers": [
                {
                    "approval_id": "approval-customer",
                    "subject_id": "customer-security-owner",
                    "side": "customer",
                    "role": "Security Owner",
                    "approved_at": "2026-08-01T08:30:00Z",
                    "valid_until": "2026-08-31T18:00:00Z",
                    "levels": ["L0", "L1", "L2", "L3", "L4"],
                },
                {
                    "approval_id": "approval-provider",
                    "subject_id": "hexor-engagement-lead",
                    "side": "provider",
                    "role": "Engagement Lead",
                    "approved_at": "2026-08-01T08:35:00Z",
                    "valid_until": "2026-08-31T18:00:00Z",
                    "levels": ["L3", "L4"],
                },
            ],
            "emergency_contacts": [
                {
                    "contact_id": "customer-soc",
                    "name": "Customer SOC",
                    "channel": "phone",
                    "value": "+351000000000",
                    "authority": ["pause", "stop", "revoke"],
                }
            ],
            "limits": {
                "requests_per_second": 10,
                "max_concurrency": 2,
                "max_data_bytes": 1048576,
                "max_duration_seconds": 3600,
            },
            "stop_conditions": [
                {
                    "condition_id": "customer-impact",
                    "description": "Unexpected customer impact",
                    "severity": "stop",
                    "automatic": True,
                }
            ],
            "high_risk_actions": {
                "credential_use": {
                    "status": "allowed",
                    "minimum_level": "L3",
                    "conditions": ["customer-provided test credentials only"],
                },
                "lateral_movement": {
                    "status": "allowed",
                    "minimum_level": "L4",
                    "conditions": ["dual approval and rollback plan"],
                },
                "persistence": {"status": "denied", "minimum_level": "L4"},
                "evasion": {"status": "denied", "minimum_level": "L4"},
                "destructive_actions": {"status": "denied", "minimum_level": "L4"},
                "data_exfiltration": {"status": "denied", "minimum_level": "L4"},
                "denial_of_service": {"status": "denied", "minimum_level": "L4"},
                "mass_data_access": {"status": "denied", "minimum_level": "L4"},
            },
        },
    }
    contract["signature"] = {
        "algorithm": "Ed25519",
        "key_id": "customer-signing-key-01",
        "payload_sha256": roe_contract.payload_sha256(contract),
        "value": "dGVzdC1zaWduYXR1cmU=",
    }
    return contract


def _request(level: str = "L2") -> dict[str, Any]:
    return {
        "schema_version": "1.0.0",
        "request_id": "request-001",
        "campaign_id": "campaign-001",
        "requested_at": "2026-08-10T10:00:00Z",
        "campaign_state": "RUNNING",
        "kill_switch": False,
        "active_stop_conditions": [],
        "target": {
            "type": "domain",
            "value": "api.demo.example.test",
        },
        "capability": "web.discovery.headers",
        "intrusiveness_level": level,
        "approval_ids": ["approval-customer"],
        "requested_controls": [],
        "estimated_limits": {
            "requests_per_second": 2,
            "concurrency": 1,
            "data_bytes": 4096,
            "duration_seconds": 60,
        },
    }


def _verifier(payload: bytes, signature: dict[str, Any]) -> bool:
    return bool(payload) and signature["value"] == "dGVzdC1zaWduYXR1cmU="


def _codes(
    contract: dict[str, Any],
    request: dict[str, Any],
    verifier: Any = _verifier,
) -> tuple[str, ...]:
    return roe_contract.authorize_step(contract, request, verifier).codes


def _resign(contract: dict[str, Any]) -> None:
    contract["signature"]["payload_sha256"] = roe_contract.payload_sha256(contract)


def test_valid_l2_request_is_allowed() -> None:
    decision = roe_contract.authorize_step(_contract(), _request(), _verifier)

    assert decision.allowed is True
    assert decision.codes == ("ALLOW",)
    assert decision.contract_id == "roe-contract-001"


def test_active_contract_fails_closed_without_signature_verifier() -> None:
    assert _codes(_contract(), _request(), None) == (
        "SIGNATURE_VERIFIER_UNAVAILABLE",
    )


def test_signature_payload_tampering_is_refused_before_scope_evaluation() -> None:
    contract = _contract()
    contract["authorization"]["limits"]["max_concurrency"] = 99

    assert _codes(contract, _request()) == ("SIGNATURE_PAYLOAD_MISMATCH",)


def test_invalid_external_signature_is_refused() -> None:
    assert _codes(_contract(), _request(), lambda _payload, _signature: False) == (
        "SIGNATURE_INVALID",
    )


def test_exclusion_overrides_a_broader_allow_rule() -> None:
    request = _request()
    request["target"]["value"] = "admin.demo.example.test"

    assert _codes(_contract(), request) == ("TARGET_EXCLUDED",)


def test_ip_exclusion_overrides_cidr_allow_rule() -> None:
    request = _request()
    request["target"] = {"type": "ip", "value": "192.0.2.200"}

    assert _codes(_contract(), request) == ("TARGET_EXCLUDED",)


def test_target_outside_scope_is_refused() -> None:
    request = _request()
    request["target"]["value"] = "outside.example.test"

    assert _codes(_contract(), request) == ("TARGET_OUT_OF_SCOPE",)


def test_uri_prefix_requires_same_origin_and_path_boundary() -> None:
    allowed = _request()
    allowed["target"] = {
        "type": "uri-prefix",
        "value": "https://portal.example.test/app/orders",
    }
    assert roe_contract.authorize_step(_contract(), allowed, _verifier).allowed

    escaped = copy.deepcopy(allowed)
    escaped["target"]["value"] = "https://portal.example.test/application"
    assert _codes(_contract(), escaped) == ("TARGET_OUT_OF_SCOPE",)


@pytest.mark.parametrize(
    ("state", "code"),
    [
        ("draft", "CONTRACT_NOT_ACTIVE"),
        ("expired", "CONTRACT_EXPIRED"),
        ("revoked", "CONTRACT_REVOKED"),
    ],
)
def test_non_active_contract_states_block_execution(state: str, code: str) -> None:
    contract = _contract()
    contract["state"] = state
    _resign(contract)

    assert _codes(contract, _request()) == (code,)


def test_expired_timestamp_blocks_execution_even_if_state_is_active() -> None:
    request = _request()
    request["requested_at"] = "2026-09-01T10:00:00Z"

    assert "CONTRACT_EXPIRED" in _codes(_contract(), request)


def test_campaign_mismatch_is_refused() -> None:
    request = _request()
    request["campaign_id"] = "campaign-other"

    assert _codes(_contract(), request) == ("CAMPAIGN_MISMATCH",)


@pytest.mark.parametrize(
    "campaign_state",
    ["AUTHORIZED", "READY", "PAUSED", "STOPPING", "STOPPED", "COMPLETED"],
)
def test_execution_only_occurs_in_running_state(campaign_state: str) -> None:
    request = _request()
    request["campaign_state"] = campaign_state

    assert _codes(_contract(), request) == ("CAMPAIGN_NOT_RUNNING",)


def test_kill_switch_blocks_execution_in_an_active_campaign() -> None:
    request = _request()
    request["kill_switch"] = True

    assert _codes(_contract(), request) == ("KILL_SWITCH_ACTIVE",)


def test_any_active_stop_condition_blocks_execution() -> None:
    request = _request()
    request["active_stop_conditions"] = ["customer-impact"]

    assert _codes(_contract(), request) == ("STOP_CONDITION_ACTIVE",)


def test_unknown_stop_condition_fails_closed_and_is_deterministic() -> None:
    request = _request()
    request["active_stop_conditions"] = ["unregistered-stop"]

    assert _codes(_contract(), request) == (
        "UNKNOWN_STOP_CONDITION",
        "STOP_CONDITION_ACTIVE",
    )


def test_prohibited_capability_precedes_allowlist() -> None:
    contract = _contract()
    contract["authorization"]["allowed_capabilities"].append("web.validation.*")
    _resign(contract)
    request = _request()
    request["capability"] = "web.validation.denial-of-service"

    assert _codes(contract, request) == ("CAPABILITY_PROHIBITED",)


def test_intrusiveness_ceiling_is_enforced() -> None:
    contract = _contract()
    contract["authorization"]["intrusiveness_ceiling"] = "L2"
    _resign(contract)

    assert "INTRUSIVENESS_EXCEEDED" in _codes(contract, _request("L3"))


def test_l3_requires_valid_approval_and_rollback_plan() -> None:
    request = _request("L3")
    request["approval_ids"] = []
    codes = _codes(_contract(), request)

    assert codes == ("APPROVAL_REQUIRED", "APPROVAL_SEPARATION_REQUIRED", "ROLLBACK_PLAN_REQUIRED")


def test_l4_requires_dual_approval_from_distinct_sides() -> None:
    request = _request("L4")
    request["approval_ids"] = ["approval-customer"]
    request["rollback_plan_ref"] = "evidence/rollback/plan-001"

    assert _codes(_contract(), request) == (
        "APPROVAL_REQUIRED",
        "APPROVAL_SEPARATION_REQUIRED",
    )

    request["approval_ids"].append("approval-provider")
    assert roe_contract.authorize_step(_contract(), request, _verifier).allowed


def test_high_risk_action_requires_explicit_allowance_and_minimum_level() -> None:
    request = _request("L2")
    request["requested_controls"] = ["credential_use"]

    assert _codes(_contract(), request) == (
        "HIGH_RISK_LEVEL_TOO_LOW:credential_use",
    )

    request = _request("L4")
    request["approval_ids"] = ["approval-customer", "approval-provider"]
    request["rollback_plan_ref"] = "evidence/rollback/plan-001"
    request["requested_controls"] = ["persistence"]
    assert _codes(_contract(), request) == (
        "HIGH_RISK_ACTION_DENIED:persistence",
    )


def test_all_declared_resource_limits_are_enforced() -> None:
    request = _request()
    request["estimated_limits"] = {
        "requests_per_second": 11,
        "concurrency": 3,
        "data_bytes": 1048577,
        "duration_seconds": 3601,
    }

    assert _codes(_contract(), request) == (
        "LIMIT_EXCEEDED:requests_per_second",
        "LIMIT_EXCEEDED:concurrency",
        "LIMIT_EXCEEDED:data_bytes",
        "LIMIT_EXCEEDED:duration_seconds",
    )


@pytest.mark.parametrize(
    "forbidden",
    ["token", "password", "cookie", "private_key", "authorization_header"],
)
def test_secret_bearing_field_names_are_rejected_recursively(forbidden: str) -> None:
    request = _request()
    request["target"][forbidden] = "must-not-be-accepted"

    assert _codes(_contract(), request) == (
        f"FORBIDDEN_FIELD:target.{forbidden}",
    )


def test_unknown_properties_fail_schema_validation() -> None:
    request = _request()
    request["bypass"] = True

    assert _codes(_contract(), request) == ("REQUEST_SCHEMA_INVALID",)


def test_invalid_contract_window_fails_closed() -> None:
    contract = _contract()
    contract["valid_until"] = contract["valid_from"]
    _resign(contract)

    assert _codes(contract, _request()) == ("CONTRACT_WINDOW_INVALID",)


def test_duplicate_approver_subject_is_rejected() -> None:
    contract = _contract()
    duplicate = copy.deepcopy(contract["authorization"]["approvers"][0])
    duplicate["approval_id"] = "approval-duplicate"
    contract["authorization"]["approvers"].append(duplicate)
    _resign(contract)

    assert _codes(contract, _request()) == ("DUPLICATE_APPROVER_SUBJECT",)


def test_decision_contains_no_signature_or_raw_contract_material() -> None:
    decision = roe_contract.authorize_step(_contract(), _request(), _verifier)

    serialized = repr(decision)
    assert "dGVzdC1zaWduYXR1cmU=" not in serialized
    assert "Customer Example" not in serialized
    assert datetime.now(timezone.utc).tzinfo is not None
