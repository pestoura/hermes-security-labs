"""Canonical admission boundary tests for the typed gateway.

All signing key material is generated in-memory at test time; the repository
never stores private keys, and trust-store fixtures contain public
verification material only, in temporary directories.
"""

from __future__ import annotations

import base64
import copy
import importlib.util
import json
import sys
from pathlib import Path
from typing import Any

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ed25519

ROOT = Path(__file__).resolve().parents[2]
GATEWAY_DIR = ROOT / "platform/gateway-protocol"
CONTRACT_DIR = ROOT / "platform/roe-contract"
REGISTRY_PATH = GATEWAY_DIR / "operation-registry.yaml"
RUNTIME_PATH = ROOT / "platform/registry.yaml"

KEY_ID = "-".join(("roe", "signing", "admission", "ed25519"))
CAMPAIGN_ID = "campaign-admission-001"
STEP_REQUEST_ID = "roe-step-request-admission-001"
OPERATION_ID = "web.discovery.headers"


def _load(module_name: str, path: Path) -> Any:
    spec = importlib.util.spec_from_file_location(module_name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


admission = _load("admission_under_test", GATEWAY_DIR / "admission.py")
roe_contract = _load("roe_contract_admission_test", CONTRACT_DIR / "roe_contract.py")


# --------------------------------------------------------------------------
# fixtures
# --------------------------------------------------------------------------


def _trust_store(tmp_path: Path) -> tuple[Path, Any]:
    private_key = ed25519.Ed25519PrivateKey.generate()
    der = private_key.public_key().public_bytes(
        encoding=serialization.Encoding.DER,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    path = tmp_path / "trust-store.json"
    path.write_text(
        json.dumps(
            {
                "schema_version": "1.0.0",
                "keys": [
                    {
                        "key_id": KEY_ID,
                        "algorithm": "Ed25519",
                        "state": "active",
                        "public_key": base64.b64encode(der).decode("ascii"),
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    return path, private_key


def _kill_switch(tmp_path: Path, state: str = "released", **fields: Any) -> Path:
    path = tmp_path / "kill-switch.json"
    document: dict[str, Any] = {"schema_version": "1.0.0", "state": state}
    document.update(fields)
    path.write_text(json.dumps(document), encoding="utf-8")
    return path


def _contract() -> dict[str, Any]:
    return {
        "schema_version": "1.0.0",
        "contract_id": "roe-contract-admission-001",
        "campaign_id": CAMPAIGN_ID,
        "revision": 1,
        "state": "active",
        "issued_at": "2026-08-01T08:00:00Z",
        "valid_from": "2026-08-01T09:00:00Z",
        "valid_until": "2026-08-31T18:00:00Z",
        "issuer": {"party_id": "hexor-security", "legal_name": "Hexor Security"},
        "customer": {"party_id": "lab-owner", "legal_name": "Lab Owner"},
        "authorization": {
            "allowed_targets": [
                {"type": "lab-asset", "value": "juice-shop-demo", "match": "exact"}
            ],
            "excluded_targets": [],
            "allowed_capabilities": ["web.discovery.*"],
            "prohibited_capabilities": ["web.validation.denial-of-service"],
            "intrusiveness_ceiling": "L2",
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
                    "subject_id": "lab-owner-security",
                    "side": "customer",
                    "role": "Security Owner",
                    "approved_at": "2026-08-01T08:30:00Z",
                    "valid_until": "2026-08-31T18:00:00Z",
                    "levels": ["L0", "L1", "L2"],
                }
            ],
            "emergency_contacts": [
                {
                    "contact_id": "lab-soc",
                    "name": "Lab SOC",
                    "channel": "phone",
                    "value": "+351****0000",
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
                    "condition_id": "lab-impact",
                    "description": "Unexpected laboratory impact",
                    "severity": "stop",
                    "automatic": True,
                }
            ],
            "high_risk_actions": {
                control: {
                    "status": "denied",
                    "minimum_level": "L4",
                    "conditions": [],
                }
                for control in (
                    "credential_use",
                    "lateral_movement",
                    "persistence",
                    "evasion",
                    "destructive_actions",
                    "data_exfiltration",
                    "denial_of_service",
                    "mass_data_access",
                )
            },
        },
    }


def _sign(contract: dict[str, Any], private_key: Any) -> dict[str, Any]:
    contract.pop("signature", None)
    raw = private_key.sign(roe_contract.canonical_payload(contract))
    contract["signature"] = {
        "algorithm": "Ed25519",
        "key_id": KEY_ID,
        "payload_sha256": roe_contract.payload_sha256(contract),
        "value": base64.b64encode(raw).decode("ascii"),
    }
    return contract


def _step_request() -> dict[str, Any]:
    return {
        "schema_version": "1.0.0",
        "request_id": STEP_REQUEST_ID,
        "campaign_id": CAMPAIGN_ID,
        "requested_at": "2026-08-10T10:00:00Z",
        "campaign_state": "RUNNING",
        "kill_switch": False,
        "active_stop_conditions": [],
        "target": {"type": "lab-asset", "value": "juice-shop-demo"},
        "capability": OPERATION_ID,
        "intrusiveness_level": "L1",
        "approval_ids": ["approval-customer"],
        "requested_controls": [],
        "estimated_limits": {
            "requests_per_second": 1,
            "concurrency": 1,
            "data_bytes": 1024,
            "duration_seconds": 60,
        },
    }


def _admission_request(contract: dict[str, Any]) -> dict[str, Any]:
    import hashlib

    digest = hashlib.sha256(RUNTIME_PATH.read_bytes()).hexdigest()
    return {
        "schema_version": "1.0.0",
        "request_id": "gateway-admission-001",
        "campaign_id": CAMPAIGN_ID,
        "run_id": "run-001",
        "step_id": "step-001",
        "attempt_id": "attempt-001",
        "requested_at": "2026-08-10T10:00:00Z",
        "profile": "normal",
        "operation": {
            "id": OPERATION_ID,
            "version": "1.0.0",
            "parameters": {"follow_redirects": False},
        },
        "target": {"type": "lab-asset", "value": "juice-shop-demo"},
        "roe_step_request_id": STEP_REQUEST_ID,
        "contract_payload_sha256": roe_contract.payload_sha256(contract),
        "runtime_observation": {
            "state": "IN_SYNC",
            "canonical_root": "platform/registry.yaml",
            "canonical_sha256": digest,
            "observed_sha256": digest,
            "observed_at": "2026-08-10T10:00:00Z",
        },
        "capability_attestations": [OPERATION_ID],
    }


@pytest.fixture()
def scenario(tmp_path: Path) -> dict[str, Any]:
    store, private_key = _trust_store(tmp_path)
    contract = _sign(_contract(), private_key)
    return {
        "store": store,
        "private_key": private_key,
        "contract": contract,
        "step": _step_request(),
        "request": _admission_request(contract),
        "kill_switch": _kill_switch(tmp_path),
        "tmp_path": tmp_path,
    }


def _decide(scenario: dict[str, Any], **overrides: Any) -> Any:
    kwargs: dict[str, Any] = {
        "trust_store_path": scenario["store"],
        "kill_switch_path": scenario["kill_switch"],
        "registry_path": REGISTRY_PATH,
        "runtime_registry_path": RUNTIME_PATH,
    }
    kwargs.update(overrides)
    return admission.authorize_admission(
        scenario["request"], scenario["contract"], scenario["step"], **kwargs
    )


# --------------------------------------------------------------------------
# positive path
# --------------------------------------------------------------------------


def test_signed_contract_and_consistent_step_are_admitted(scenario: dict[str, Any]) -> None:
    decision = _decide(scenario)

    assert decision.admitted is True
    assert decision.codes == ("ADMIT_TYPED_OPERATION",)
    assert decision.operation_id == OPERATION_ID
    assert decision.roe_step_request_id == STEP_REQUEST_ID
    assert decision.roe_decision_source == "DERIVED"


def test_decision_never_exposes_target_parameters_or_signature(
    scenario: dict[str, Any],
) -> None:
    rendered = repr(_decide(scenario))

    assert "juice-shop-demo" not in rendered
    assert "follow_redirects" not in rendered
    assert scenario["contract"]["signature"]["value"] not in rendered


# --------------------------------------------------------------------------
# adversarial: forged caller-supplied decisions
# --------------------------------------------------------------------------


@pytest.mark.parametrize("field", admission.CALLER_SUPPLIED_DECISION_FIELDS)
def test_caller_supplied_roe_decision_field_is_refused(
    scenario: dict[str, Any], field: str
) -> None:
    scenario["request"][field] = {
        "allowed": True,
        "codes": ["ALLOW"],
        "contract_id": "forged",
        "campaign_id": CAMPAIGN_ID,
        "step_request_id": STEP_REQUEST_ID,
        "authorized_operation_id": OPERATION_ID,
        "authorized_target_sha256": "a" * 64,
        "contract_payload_sha256": "b" * 64,
        "intrusiveness_ceiling": "L4",
    }

    decision = _decide(scenario)

    assert decision.admitted is False
    assert decision.codes == ("ROE_DECISION_CALLER_SUPPLIED",)


def test_forged_allow_cannot_rescue_a_refusing_contract(scenario: dict[str, Any]) -> None:
    scenario["contract"]["state"] = "revoked"
    _sign(scenario["contract"], scenario["private_key"])
    scenario["request"]["contract_payload_sha256"] = roe_contract.payload_sha256(
        scenario["contract"]
    )
    scenario["request"]["roe_decision"] = {"allowed": True, "codes": ["ALLOW"]}

    decision = _decide(scenario)

    assert decision.admitted is False
    assert "ROE_REFUSED:CONTRACT_REVOKED" not in decision.codes
    assert decision.codes == ("ROE_DECISION_CALLER_SUPPLIED",)


def test_revoked_contract_is_refused_with_derived_codes(scenario: dict[str, Any]) -> None:
    scenario["contract"]["state"] = "revoked"
    _sign(scenario["contract"], scenario["private_key"])
    scenario["request"]["contract_payload_sha256"] = roe_contract.payload_sha256(
        scenario["contract"]
    )

    decision = _decide(scenario)

    assert decision.admitted is False
    assert decision.codes == ("ROE_REFUSED:CONTRACT_REVOKED",)


# --------------------------------------------------------------------------
# binding mismatches
# --------------------------------------------------------------------------


def test_step_request_identifier_mismatch_is_refused(scenario: dict[str, Any]) -> None:
    scenario["request"]["roe_step_request_id"] = "roe-step-request-other"

    assert _decide(scenario).codes == ("ROE_STEP_REQUEST_MISMATCH",)


def test_campaign_mismatch_between_gateway_and_step_is_refused(
    scenario: dict[str, Any],
) -> None:
    scenario["request"]["campaign_id"] = "campaign-other-001"

    decision = _decide(scenario)

    assert decision.admitted is False
    assert set(decision.codes) == {
        "ROE_CAMPAIGN_MISMATCH",
        "ROE_CONTRACT_CAMPAIGN_MISMATCH",
    }


def test_target_mismatch_between_gateway_and_step_is_refused(
    scenario: dict[str, Any],
) -> None:
    scenario["request"]["target"] = {"type": "lab-asset", "value": "other-lab"}

    assert _decide(scenario).codes == ("ROE_TARGET_MISMATCH",)


def test_contract_payload_hash_mismatch_is_refused(scenario: dict[str, Any]) -> None:
    scenario["request"]["contract_payload_sha256"] = "c" * 64

    assert _decide(scenario).codes == ("ROE_CONTRACT_PAYLOAD_MISMATCH",)


def test_capability_mismatch_between_step_and_operation_is_refused(
    scenario: dict[str, Any],
) -> None:
    scenario["step"]["capability"] = "web.discovery.tls"

    assert _decide(scenario).codes == ("ROE_CAPABILITY_MISMATCH",)


def test_intrusiveness_mismatch_between_step_and_operation_is_refused(
    scenario: dict[str, Any],
) -> None:
    scenario["step"]["intrusiveness_level"] = "L0"
    scenario["request"]["operation"]["id"] = OPERATION_ID

    assert _decide(scenario).codes == ("ROE_INTRUSIVENESS_MISMATCH",)


def test_unknown_operation_is_refused(scenario: dict[str, Any]) -> None:
    scenario["request"]["operation"]["id"] = "web.discovery.unknown"
    scenario["step"]["capability"] = "web.discovery.unknown"

    decision = _decide(scenario)

    assert decision.admitted is False
    assert "OPERATION_UNKNOWN" in decision.codes


# --------------------------------------------------------------------------
# kill switch and trust store
# --------------------------------------------------------------------------


def test_missing_kill_switch_source_is_refused(scenario: dict[str, Any]) -> None:
    assert _decide(scenario, kill_switch_path=None).codes == (
        "KILL_SWITCH_SOURCE_REQUIRED",
    )


def test_engaged_kill_switch_is_refused(scenario: dict[str, Any]) -> None:
    engaged = _kill_switch(scenario["tmp_path"], state="engaged")

    assert _decide(scenario, kill_switch_path=engaged).codes == (
        "ROE_REFUSED:KILL_SWITCH_ACTIVE",
    )


def test_absent_kill_switch_file_is_refused(scenario: dict[str, Any]) -> None:
    missing = scenario["tmp_path"] / "absent-kill-switch.json"

    assert _decide(scenario, kill_switch_path=missing).codes == (
        "ROE_REFUSED:KILL_SWITCH_UNAVAILABLE",
    )


def test_missing_trust_store_source_is_refused(scenario: dict[str, Any]) -> None:
    assert _decide(scenario, trust_store_path=None).codes == (
        "SIGNATURE_VERIFIER_UNAVAILABLE",
    )


def test_absent_trust_store_file_is_refused(scenario: dict[str, Any]) -> None:
    missing = scenario["tmp_path"] / "absent-trust-store.json"

    assert _decide(scenario, trust_store_path=missing).codes == (
        "ROE_REFUSED:TRUST_STORE_UNAVAILABLE",
    )


def test_signature_from_untrusted_key_is_refused(scenario: dict[str, Any]) -> None:
    _sign(scenario["contract"], ed25519.Ed25519PrivateKey.generate())
    scenario["request"]["contract_payload_sha256"] = roe_contract.payload_sha256(
        scenario["contract"]
    )

    assert _decide(scenario).codes == ("ROE_REFUSED:SIGNATURE_INVALID",)


def test_tampered_contract_body_is_refused(scenario: dict[str, Any]) -> None:
    tampered = copy.deepcopy(scenario["contract"])
    tampered["authorization"]["intrusiveness_ceiling"] = "L4"
    scenario["contract"] = tampered

    decision = _decide(scenario)

    assert decision.admitted is False
    assert decision.codes[0].startswith("ROE_REFUSED:SIGNATURE_")


# --------------------------------------------------------------------------
# structural rejections
# --------------------------------------------------------------------------


def test_command_style_fields_are_refused(scenario: dict[str, Any]) -> None:
    scenario["request"]["operation"]["parameters"] = {"command": "id"}

    decision = _decide(scenario)

    assert decision.admitted is False
    assert decision.codes[0].startswith("FORBIDDEN_FIELD:")


def test_schema_violation_is_refused(scenario: dict[str, Any]) -> None:
    scenario["request"].pop("runtime_observation")

    assert _decide(scenario).codes == ("ADMISSION_SCHEMA_INVALID",)


def test_runtime_drift_is_refused(scenario: dict[str, Any]) -> None:
    scenario["request"]["runtime_observation"]["state"] = "DRIFT_DETECTED"

    assert _decide(scenario).codes == ("RUNTIME_DRIFT_DETECTED",)


def test_integration_error_is_fail_closed(scenario: dict[str, Any]) -> None:
    scenario["step"] = {"request_id": STEP_REQUEST_ID, "campaign_id": CAMPAIGN_ID}

    decision = _decide(scenario)

    assert decision.admitted is False
    assert decision.codes == ("ROE_REFUSED:REQUEST_SCHEMA_INVALID",)


def test_admission_schema_forbids_a_roe_decision_property() -> None:
    schema = json.loads(
        (GATEWAY_DIR / "admission-request.schema.json").read_text(encoding="utf-8")
    )

    assert schema["additionalProperties"] is False
    assert "roe_decision" not in schema["properties"]
