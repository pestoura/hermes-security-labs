from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[2]
MODULE_PATH = ROOT / "platform/lab-lifecycle/lifecycle_protocol.py"
SPEC = importlib.util.spec_from_file_location("lifecycle_protocol", MODULE_PATH)
assert SPEC and SPEC.loader
lifecycle = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = lifecycle
SPEC.loader.exec_module(lifecycle)


def _contract(level: str = "L2", profile: str = "isolated") -> dict[str, Any]:
    exceptions = []
    if profile == "restricted":
        exceptions = [
            {
                "exception_id": "exception-package-index",
                "destination": "packages.example.test",
                "protocol": "https",
                "port": 443,
                "owner_id": "engagement-owner",
                "approver_id": "customer-approver",
                "valid_from": "2026-08-07T00:00:00Z",
                "valid_until": "2026-08-07T02:00:00Z",
                "reason": "Approved package retrieval during setup",
            }
        ]
    recovery = {"snapshot_ref": None, "rollback_plan_ref": None}
    if level in {"L3", "L4"}:
        recovery = {
            "snapshot_ref": "snapshots/lab-001/pre-run",
            "rollback_plan_ref": "evidence/rollback/lab-001",
        }
    return {
        "schema_version": "1.0.0",
        "contract_id": "lab-contract-001",
        "lab_id": "lab-001",
        "campaign_id": "campaign-001",
        "family": "web-api",
        "intrusiveness_level": level,
        "network": {
            "network_id": "network-lab-001",
            "profile": profile,
            "egress_exceptions": exceptions,
        },
        "isolation": {
            "privileged": False,
            "host_network": False,
            "docker_socket": False,
            "host_mounts": [],
            "shared_network": False,
        },
        "limits": {
            "ttl_seconds": 3600,
            "cpu_limit": 2,
            "memory_mb": 2048,
            "data_budget_bytes": 1048576,
        },
        "recovery": recovery,
        "expires_at": "2026-08-07T03:00:00Z",
    }


def _request(
    from_state: str,
    to_state: str,
    profile: str = "isolated",
) -> dict[str, Any]:
    effective = None
    if to_state in {"READY", "RUNNING"}:
        effective = {
            "network_id": "network-lab-001",
            "profile": profile,
            "egress_destinations": [],
        }
    return {
        "schema_version": "1.0.0",
        "request_id": f"request-{from_state.lower()}-{to_state.lower()}",
        "contract_id": "lab-contract-001",
        "lab_id": "lab-001",
        "campaign_id": "campaign-001",
        "requested_at": "2026-08-07T01:00:00Z",
        "from_state": from_state,
        "to_state": to_state,
        "idempotency_key": f"idem-{from_state.lower()}-{to_state.lower()}",
        "effective_network": effective,
        "zero_residue_proof": None,
        "runtime_observation": {
            "state": "OBSERVED",
            "observed_at": "2026-08-07T01:00:00Z",
        },
    }


def _proof(
    zero: bool = True,
    scanner_state: str = "COMPLETE",
) -> dict[str, Any]:
    resources = {
        "containers": [],
        "networks": [],
        "volumes": [],
        "processes": [],
        "mounts": [],
    }
    if not zero:
        resources["containers"] = ["container-residue"]
    proof = {
        "schema_version": "1.0.0",
        "proof_id": "proof-001",
        "lab_id": "lab-001",
        "campaign_id": "campaign-001",
        "cleanup_attempt_id": "cleanup-attempt-001",
        "observed_at": "2026-08-07T01:10:00Z",
        "scanner_state": scanner_state,
        "resources": resources,
        "temporary_paths": [],
        "network_absent": zero,
    }
    proof["verification_sha256"] = lifecycle.residue_verification_digest(proof)
    return proof


def _decision(contract: dict[str, Any], request: dict[str, Any]):
    return lifecycle.authorize_transition(contract, request)


@pytest.mark.parametrize(
    ("from_state", "to_state"),
    [
        ("DECLARED", "PROVISIONING"),
        ("PROVISIONING", "READY"),
        ("READY", "RUNNING"),
        ("RUNNING", "RESETTING"),
        ("RESETTING", "READY"),
        ("RUNNING", "DESTROYING"),
        ("DESTROYING", "VERIFYING_RESIDUE"),
        ("RUNNING", "ROLLING_BACK"),
        ("ROLLING_BACK", "VERIFYING_RESIDUE"),
    ],
)
def test_declared_non_terminal_transitions_are_allowed(
    from_state: str,
    to_state: str,
) -> None:
    decision = _decision(_contract(), _request(from_state, to_state))
    assert decision.allowed is True
    assert decision.resulting_state == to_state


def test_undeclared_transition_is_refused() -> None:
    decision = _decision(_contract(), _request("DECLARED", "RUNNING"))
    assert decision.codes == ("TRANSITION_NOT_ALLOWED",)


def test_contract_lab_and_campaign_bindings_are_enforced() -> None:
    request = _request("DECLARED", "PROVISIONING")
    request["contract_id"] = "other-contract"
    request["lab_id"] = "other-lab"
    request["campaign_id"] = "other-campaign"
    assert _decision(_contract(), request).codes == (
        "CONTRACT_MISMATCH",
        "LAB_MISMATCH",
        "CAMPAIGN_MISMATCH",
    )


def test_expired_contract_is_refused() -> None:
    request = _request("DECLARED", "PROVISIONING")
    request["requested_at"] = "2026-08-07T03:00:00Z"
    assert _decision(_contract(), request).codes == ("CONTRACT_EXPIRED",)


def test_ready_requires_observed_effective_network() -> None:
    request = _request("PROVISIONING", "READY")
    request["effective_network"] = None
    request["runtime_observation"]["state"] = "NOT_RUN"
    assert _decision(_contract(), request).codes == (
        "EFFECTIVE_NETWORK_REQUIRED",
        "RUNTIME_OBSERVATION_NOT_RUN",
    )


def test_synthetic_runtime_observation_does_not_prove_ready() -> None:
    request = _request("PROVISIONING", "READY")
    request["runtime_observation"]["state"] = "SYNTHETIC"
    assert _decision(_contract(), request).codes == (
        "RUNTIME_OBSERVATION_SYNTHETIC",
    )


def test_network_id_and_profile_must_match_contract() -> None:
    request = _request("PROVISIONING", "READY")
    request["effective_network"]["network_id"] = "other-network"
    request["effective_network"]["profile"] = "restricted"
    assert _decision(_contract(), request).codes == (
        "NETWORK_ID_MISMATCH",
        "NETWORK_PROFILE_MISMATCH",
    )


def test_isolated_profile_rejects_any_egress_destination() -> None:
    request = _request("PROVISIONING", "READY")
    request["effective_network"]["egress_destinations"] = ["example.test"]
    assert _decision(_contract(), request).codes == (
        "ISOLATED_EGRESS_PRESENT",
    )


def test_restricted_profile_accepts_only_active_declared_destination() -> None:
    request = _request("PROVISIONING", "READY", "restricted")
    request["effective_network"]["egress_destinations"] = [
        "packages.example.test"
    ]
    assert _decision(_contract(profile="restricted"), request).allowed

    request["effective_network"]["egress_destinations"] = [
        "outside.example.test"
    ]
    assert _decision(_contract(profile="restricted"), request).codes == (
        "EGRESS_DESTINATION_UNAUTHORIZED",
    )


def test_isolated_contract_cannot_declare_egress_exception() -> None:
    contract = _contract()
    contract["network"]["egress_exceptions"] = _contract(
        profile="restricted"
    )["network"]["egress_exceptions"]
    assert _decision(contract, _request("DECLARED", "PROVISIONING")).codes == (
        "ISOLATED_PROFILE_HAS_EXCEPTION",
    )


def test_invalid_or_expired_egress_exception_is_refused() -> None:
    contract = _contract(profile="restricted")
    contract["network"]["egress_exceptions"][0]["valid_until"] = (
        "2026-08-08T00:00:00Z"
    )
    assert _decision(contract, _request("DECLARED", "PROVISIONING")).codes == (
        "EGRESS_EXCEPTION_WINDOW_INVALID",
    )


def test_l3_and_l4_require_snapshot_and_rollback_references() -> None:
    contract = _contract("L3")
    contract["recovery"] = {"snapshot_ref": None, "rollback_plan_ref": None}
    assert _decision(contract, _request("DECLARED", "PROVISIONING")).codes == (
        "HIGH_IMPACT_RECOVERY_REQUIRED",
    )


def test_schema_forbids_privileged_host_network_socket_and_shared_network() -> None:
    fields = ("privileged", "host_network", "docker_socket", "shared_network")
    for field in fields:
        contract = _contract()
        contract["isolation"][field] = True
        assert _decision(contract, _request("READY", "RUNNING")).codes == (
            "CONTRACT_SCHEMA_INVALID",
        )


def test_schema_forbids_host_mounts() -> None:
    contract = _contract()
    contract["isolation"]["host_mounts"] = ["/host"]
    assert _decision(contract, _request("READY", "RUNNING")).codes == (
        "CONTRACT_SCHEMA_INVALID",
    )


def test_verified_requires_complete_zero_residue_proof() -> None:
    request = _request("VERIFYING_RESIDUE", "VERIFIED")
    decision = _decision(_contract(), request)
    assert decision.codes == ("ZERO_RESIDUE_PROOF_REQUIRED",)
    assert decision.resulting_state == "QUARANTINED"


def test_complete_zero_residue_proof_allows_verified() -> None:
    request = _request("VERIFYING_RESIDUE", "VERIFIED")
    request["zero_residue_proof"] = _proof()
    decision = _decision(_contract(), request)
    assert decision.allowed is True
    assert decision.resulting_state == "VERIFIED"


def test_partial_or_unavailable_scanner_never_proves_zero_residue() -> None:
    for scanner_state in ("PARTIAL", "UNAVAILABLE"):
        request = _request("VERIFYING_RESIDUE", "VERIFIED")
        request["zero_residue_proof"] = _proof(scanner_state=scanner_state)
        decision = _decision(_contract(), request)
        assert "RESIDUE_SCANNER_INCOMPLETE" in decision.codes
        assert "ZERO_RESIDUE_NOT_PROVEN" in decision.codes
        assert decision.resulting_state == "QUARANTINED"


def test_detected_resource_or_network_residue_quarantines() -> None:
    request = _request("VERIFYING_RESIDUE", "VERIFIED")
    request["zero_residue_proof"] = _proof(zero=False)
    decision = _decision(_contract(), request)
    assert "LAB_NETWORK_REMAINS" in decision.codes
    assert "RESIDUE_DETECTED" in decision.codes
    assert "ZERO_RESIDUE_NOT_PROVEN" in decision.codes
    assert decision.resulting_state == "QUARANTINED"


def test_proof_digest_tampering_is_refused_and_quarantines() -> None:
    request = _request("VERIFYING_RESIDUE", "VERIFIED")
    request["zero_residue_proof"] = _proof()
    request["zero_residue_proof"]["network_absent"] = False
    decision = _decision(_contract(), request)
    assert "ZERO_RESIDUE_DIGEST_MISMATCH" in decision.codes
    assert "ZERO_RESIDUE_NOT_PROVEN" in decision.codes
    assert decision.resulting_state == "QUARANTINED"


def test_proof_identity_binding_is_enforced() -> None:
    request = _request("VERIFYING_RESIDUE", "VERIFIED")
    request["zero_residue_proof"] = _proof()
    request["zero_residue_proof"]["lab_id"] = "other-lab"
    request["zero_residue_proof"]["campaign_id"] = "other-campaign"
    request["zero_residue_proof"]["verification_sha256"] = (
        lifecycle.residue_verification_digest(request["zero_residue_proof"])
    )
    decision = _decision(_contract(), request)
    assert decision.codes == (
        "PROOF_LAB_MISMATCH",
        "PROOF_CAMPAIGN_MISMATCH",
        "ZERO_RESIDUE_NOT_PROVEN",
    )
    assert decision.resulting_state == "QUARANTINED"


def test_quarantine_requires_non_zero_or_incomplete_proof() -> None:
    request = _request("VERIFYING_RESIDUE", "QUARANTINED")
    request["zero_residue_proof"] = _proof()
    assert _decision(_contract(), request).codes == (
        "QUARANTINE_REASON_ABSENT",
    )

    request["zero_residue_proof"] = _proof(zero=False)
    decision = _decision(_contract(), request)
    assert decision.allowed is False
    assert decision.resulting_state == "QUARANTINED"


def test_quarantined_lab_cannot_transition_or_be_reused() -> None:
    request = _request("QUARANTINED", "PROVISIONING")
    decision = _decision(_contract(), request)
    assert "TRANSITION_NOT_ALLOWED" in decision.codes
    assert "QUARANTINED_REUSE_BLOCKED" in decision.codes


@pytest.mark.parametrize(
    "field",
    ["token", "password", "private_key", "host_path"],
)
def test_secret_or_host_path_fields_are_rejected_recursively(
    field: str,
) -> None:
    request = _request("DECLARED", "PROVISIONING")
    request["runtime_observation"][field] = "not-accepted"
    assert _decision(_contract(), request).codes == (
        f"FORBIDDEN_FIELD:runtime_observation.{field}",
    )


def test_unknown_contract_and_request_fields_fail_schema_validation() -> None:
    contract = _contract()
    contract["bypass"] = True
    assert _decision(contract, _request("DECLARED", "PROVISIONING")).codes == (
        "CONTRACT_SCHEMA_INVALID",
    )

    request = _request("DECLARED", "PROVISIONING")
    request["bypass"] = True
    assert _decision(_contract(), request).codes == (
        "TRANSITION_SCHEMA_INVALID",
    )


def test_decision_contains_no_network_destinations_or_proof_resources() -> None:
    request = _request("VERIFYING_RESIDUE", "VERIFIED")
    request["zero_residue_proof"] = _proof()
    decision = _decision(_contract(), request)
    serialized = repr(decision)
    assert "container-residue" not in serialized
    assert "packages.example.test" not in serialized
