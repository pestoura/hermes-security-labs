"""Canonical TB1 -> gateway -> Runner Protocol v2 handoff tests.

All signing keys are generated in memory. Temporary files contain public
verification material only. Nothing here dispatches or executes a runner,
target, scanner, network call or subprocess.
"""

from __future__ import annotations

import base64
import copy
import hashlib
import importlib.util
import json
import sys
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ed25519

ROOT = Path(__file__).resolve().parents[2]
GATEWAY_DIR = ROOT / "platform/gateway-protocol"
CONTRACT_DIR = ROOT / "platform/roe-contract"
RUNTIME_PATH = ROOT / "platform/registry.yaml"
RUNNER_SDK_SRC = ROOT / "platform/runner-protocol/src"

if str(RUNNER_SDK_SRC) not in sys.path:
    sys.path.insert(0, str(RUNNER_SDK_SRC))

from runner_protocol_v2 import request_fingerprint, validate_semantics  # noqa: E402

CAMPAIGN_UUID = "3f2a1c64-1e8b-4a2b-9c7d-1c2b3a4d5e6f"
RUN_UUID = "5c9d7e2a-8b41-4f6d-9a03-2d4e6f8a1b2c"
RUN_UUID_OTHER = "2e5a7b93-6f84-4d3a-8b19-7c9d1e3f5a68"
STEP_UUID = "7b1e4d3c-2a95-4c8e-8f10-3e5d7c9b1a24"
ATTEMPT_UUID = "9a3c5e71-4d62-4b18-8e27-5f7a9c1d3b46"
ATTEMPT_UUID_RETRY = "1d4f6a82-5e73-4c29-9f38-6a8b0d2e4c57"
ROE_KEY_ID = "roe-signing-handoff-ed25519"
AUTH_KEY_ID = "tb1-authorization-handoff-ed25519"
STEP_REQUEST_ID = "roe-step-request-handoff-001"
OPERATION_ID = "web.discovery.headers"


def _load(module_name: str, path: Path) -> Any:
    spec = importlib.util.spec_from_file_location(module_name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


roe_contract = _load("roe_contract_handoff_test", CONTRACT_DIR / "roe_contract.py")
handoff = _load("runner_handoff_under_test", GATEWAY_DIR / "runner_handoff.py")
gateway_protocol = handoff.gateway_protocol
auth = handoff.authorization_contract


def _iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat(timespec="seconds").replace(
        "+00:00", "Z"
    )


def _public_der(private_key: Any) -> str:
    der = private_key.public_key().public_bytes(
        encoding=serialization.Encoding.DER,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    return base64.b64encode(der).decode("ascii")


def _roe_trust_store(tmp_path: Path, private_key: Any) -> Path:
    path = tmp_path / "roe-trust-store.json"
    path.write_text(
        json.dumps(
            {
                "schema_version": "1.0.0",
                "keys": [
                    {
                        "key_id": ROE_KEY_ID,
                        "algorithm": "Ed25519",
                        "state": "active",
                        "public_key": _public_der(private_key),
                        "not_before": "2000-01-01T00:00:00Z",
                        "not_after": "2100-01-01T00:00:00Z",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    return path


def _auth_trust_store(
    tmp_path: Path,
    private_key: Any,
    *,
    state: str = "active",
    purpose: str = "tb1-authorization",
) -> Path:
    path = tmp_path / "authorization-trust-store.json"
    path.write_text(
        json.dumps(
            {
                "schema_version": "1.0.0",
                "domain": "hex0r.tb1.authorization.v1",
                "purpose": purpose,
                "keys": [
                    {
                        "key_id": AUTH_KEY_ID,
                        "algorithm": "Ed25519",
                        "state": state,
                        "purpose": purpose,
                        "public_key": _public_der(private_key),
                        "not_before": "2000-01-01T00:00:00Z",
                        "not_after": "2100-01-01T00:00:00Z",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    return path


def _kill_switch(tmp_path: Path, state: str = "released", **fields: Any) -> Path:
    path = tmp_path / "kill-switch.json"
    document: dict[str, Any] = {"schema_version": "1.0.0", "state": state}
    document.update(fields)
    path.write_text(json.dumps(document), encoding="utf-8")
    return path


def _contract() -> dict[str, Any]:
    return {
        "schema_version": "1.0.0",
        "contract_id": "roe-contract-handoff-001",
        "campaign_id": CAMPAIGN_UUID,
        "revision": 1,
        "state": "active",
        "issued_at": "2026-08-01T08:00:00Z",
        "valid_from": "2026-08-01T09:00:00Z",
        "valid_until": "2099-08-31T18:00:00Z",
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
                    "end": "2099-08-31T18:00:00Z",
                }
            ],
            "approvers": [
                {
                    "approval_id": "approval-customer",
                    "subject_id": "lab-owner-security",
                    "side": "customer",
                    "role": "Security Owner",
                    "approved_at": "2026-08-01T08:30:00Z",
                    "valid_until": "2099-08-31T18:00:00Z",
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
                name: {"status": "denied", "minimum_level": "L4", "conditions": []}
                for name in (
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


def _sign_contract(contract: dict[str, Any], private_key: Any) -> dict[str, Any]:
    contract = copy.deepcopy(contract)
    contract.pop("signature", None)
    raw = private_key.sign(roe_contract.canonical_payload(contract))
    contract["signature"] = {
        "algorithm": "Ed25519",
        "key_id": ROE_KEY_ID,
        "payload_sha256": roe_contract.payload_sha256(contract),
        "value": base64.b64encode(raw).decode("ascii"),
    }
    return contract


def _step_request() -> dict[str, Any]:
    return {
        "schema_version": "1.0.0",
        "request_id": STEP_REQUEST_ID,
        "campaign_id": CAMPAIGN_UUID,
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
    digest = hashlib.sha256(RUNTIME_PATH.read_bytes()).hexdigest()
    return {
        "schema_version": "1.0.0",
        "request_id": "gateway-handoff-001",
        "campaign_id": CAMPAIGN_UUID,
        "run_id": RUN_UUID,
        "step_id": STEP_UUID,
        "attempt_id": ATTEMPT_UUID,
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


def _receipt(
    request: dict[str, Any],
    contract: dict[str, Any],
    step_request: dict[str, Any],
    private_key: Any,
    **overrides: Any,
) -> dict[str, Any]:
    now = datetime.now(timezone.utc)
    receipt: dict[str, Any] = {
        "schema_version": "1.0.0",
        "domain": "hex0r.tb1.authorization.v1",
        "issuer": "hermes-control-plane",
        "authorization_id": str(uuid.uuid4()),
        "issued_at": _iso(now - timedelta(seconds=30)),
        "expires_at": _iso(now + timedelta(minutes=5)),
        "campaign_id": request["campaign_id"],
        "run_id": request["run_id"],
        "step_id": request["step_id"],
        "roe_contract_id": contract["contract_id"],
        "roe_contract_payload_sha256": request["contract_payload_sha256"],
        "roe_step_request_id": step_request["request_id"],
        "operation_id": request["operation"]["id"],
        "operation_version": request["operation"]["version"],
        "operation_parameters_sha256": auth.canonical_parameters_sha256(
            request["operation"]["parameters"]
        ),
        "capability_id": step_request["capability"],
        "target_sha256": gateway_protocol.canonical_target_digest(request["target"]),
        "intrusiveness_level": step_request["intrusiveness_level"],
    }
    receipt.update(overrides)
    receipt["authorization_ref"] = auth.build_authorization_ref(receipt)
    receipt["signature"] = {
        "algorithm": "Ed25519",
        "key_id": AUTH_KEY_ID,
        "value": base64.b64encode(
            private_key.sign(auth.canonical_signed_payload(receipt))
        ).decode("ascii"),
    }
    return receipt


@pytest.fixture()
def scenario(tmp_path: Path) -> dict[str, Any]:
    roe_key = ed25519.Ed25519PrivateKey.generate()
    auth_key = ed25519.Ed25519PrivateKey.generate()
    contract = _sign_contract(_contract(), roe_key)
    step_request = _step_request()
    request = _admission_request(contract)
    config = handoff.RunnerHandoffConfig(
        trust_store_path=_roe_trust_store(tmp_path, roe_key),
        authorization_trust_store_path=_auth_trust_store(tmp_path, auth_key),
        kill_switch_path=_kill_switch(tmp_path),
    )
    return {
        "tmp_path": tmp_path,
        "roe_key": roe_key,
        "auth_key": auth_key,
        "contract": contract,
        "step_request": step_request,
        "request": request,
        "config": config,
        "receipt": _receipt(request, contract, step_request, auth_key),
    }


def _call(scenario: dict[str, Any], **overrides: Any) -> Any:
    return handoff.build_step_request(
        overrides.get("request", scenario["request"]),
        overrides.get("contract", scenario["contract"]),
        overrides.get("step_request", scenario["step_request"]),
        overrides.get("config", scenario["config"]),
        authorization_receipt=overrides.get("receipt", scenario["receipt"]),
    )


def test_valid_control_plane_receipt_builds_valid_runner_request(scenario) -> None:
    result = _call(scenario)
    assert result.request_built is True
    assert result.codes == ("HANDOFF_STEP_REQUEST_BUILT",)
    assert result.admission_codes == ("ADMIT_TYPED_OPERATION",)
    assert result.runner_request is not None
    validate_semantics(result.runner_request)
    assert result.runner_request["authorization_ref"] == scenario["receipt"]["authorization_ref"]
    assert result.authorization_ref == scenario["receipt"]["authorization_ref"]


def test_handoff_preserves_all_runner_correlation_ids(scenario) -> None:
    message = _call(scenario).runner_request
    assert message["correlation"] == {
        "campaign_id": CAMPAIGN_UUID,
        "run_id": RUN_UUID,
        "step_id": STEP_UUID,
        "attempt_id": ATTEMPT_UUID,
    }


def test_receipt_contains_digests_not_raw_target_or_parameters(scenario) -> None:
    serialized = json.dumps(scenario["receipt"], sort_keys=True)
    assert "juice-shop-demo" not in serialized
    assert "follow_redirects" not in serialized
    assert scenario["receipt"]["target_sha256"] == gateway_protocol.canonical_target_digest(
        scenario["request"]["target"]
    )
    assert scenario["receipt"]["operation_parameters_sha256"] == auth.canonical_parameters_sha256(
        scenario["request"]["operation"]["parameters"]
    )


def test_missing_receipt_refuses_without_runner_request(scenario) -> None:
    result = handoff.build_step_request(
        scenario["request"],
        scenario["contract"],
        scenario["step_request"],
        scenario["config"],
        authorization_receipt=None,
    )
    assert result.request_built is False
    assert result.runner_request is None
    assert result.codes == ("AUTH_RECEIPT_REQUIRED",)


def test_missing_authorization_trust_store_refuses(scenario) -> None:
    config = handoff.RunnerHandoffConfig(
        trust_store_path=scenario["config"].trust_store_path,
        authorization_trust_store_path=None,
        kill_switch_path=scenario["config"].kill_switch_path,
    )
    result = _call(scenario, config=config)
    assert result.request_built is False
    assert result.runner_request is None
    assert result.codes == ("AUTH_TRUST_STORE_REQUIRED",)


@pytest.mark.parametrize(
    "field",
    [
        "admission_decision",
        "authorization_receipt",
        "authorization_ref",
        "authorized",
        "roe_decision",
        "roe_decision_ref",
        "idempotency_key",
        "timeout_budget",
        "retry_policy",
        "cancellation_policy",
        "progress_mode",
        "runner_request",
    ],
)
def test_request_embedded_authority_or_policy_is_refused(scenario, field: str) -> None:
    request = copy.deepcopy(scenario["request"])
    request[field] = {"allowed": True, "codes": ["ALLOW"]}
    result = _call(scenario, request=request)
    assert result.request_built is False
    assert result.runner_request is None
    assert result.codes == ("HANDOFF_CALLER_SUPPLIED_AUTHORIZATION",)


def test_forged_naked_authorization_ref_never_bypasses_receipt(scenario) -> None:
    request = copy.deepcopy(scenario["request"])
    request["authorization_ref"] = scenario["receipt"]["authorization_ref"]
    result = _call(scenario, request=request, receipt=None)
    assert result.request_built is False
    assert result.runner_request is None
    assert result.codes == ("HANDOFF_CALLER_SUPPLIED_AUTHORIZATION",)


def test_forged_receipt_signature_is_refused(scenario) -> None:
    receipt = copy.deepcopy(scenario["receipt"])
    other = ed25519.Ed25519PrivateKey.generate()
    receipt["signature"]["value"] = base64.b64encode(
        other.sign(auth.canonical_signed_payload(receipt))
    ).decode("ascii")
    result = _call(scenario, receipt=receipt)
    assert result.request_built is False
    assert result.runner_request is None
    assert result.codes == ("AUTH_SIGNATURE_INVALID",)


def test_roe_trust_store_cannot_validate_tb1_receipt(scenario) -> None:
    config = handoff.RunnerHandoffConfig(
        trust_store_path=scenario["config"].trust_store_path,
        authorization_trust_store_path=scenario["config"].trust_store_path,
        kill_switch_path=scenario["config"].kill_switch_path,
    )
    result = _call(scenario, config=config)
    assert result.request_built is False
    assert result.runner_request is None
    assert result.codes[0].startswith("AUTH_TRUST_STORE_")


@pytest.mark.parametrize(
    "state, expected",
    [("revoked", "AUTH_SIGNATURE_KEY_REVOKED"), ("retired", "AUTH_SIGNATURE_KEY_NOT_ACTIVE")],
)
def test_non_active_tb1_authorization_key_refuses(
    scenario, tmp_path: Path, state: str, expected: str
) -> None:
    store = _auth_trust_store(tmp_path, scenario["auth_key"], state=state)
    config = handoff.RunnerHandoffConfig(
        trust_store_path=scenario["config"].trust_store_path,
        authorization_trust_store_path=store,
        kill_switch_path=scenario["config"].kill_switch_path,
    )
    result = _call(scenario, config=config)
    assert result.request_built is False
    assert result.runner_request is None
    assert result.codes == (expected,)


@pytest.mark.parametrize(
    "field, value, expected",
    [
        ("campaign_id", "1f2a3b4c-5d6e-4789-8a01-2b3c4d5e6f70", "AUTH_CAMPAIGN_MISMATCH"),
        ("run_id", RUN_UUID_OTHER, "AUTH_RUN_MISMATCH"),
        ("step_id", "4a5b6c7d-8e9f-4012-8a34-5b6c7d8e9f01", "AUTH_STEP_MISMATCH"),
        ("roe_contract_id", "other-contract", "AUTH_ROE_CONTRACT_MISMATCH"),
        ("roe_contract_payload_sha256", "c" * 64, "AUTH_ROE_PAYLOAD_MISMATCH"),
        ("roe_step_request_id", "other-step-request", "AUTH_ROE_STEP_REQUEST_MISMATCH"),
        ("operation_id", "web.discovery.tls", "AUTH_OPERATION_MISMATCH"),
        ("operation_version", "9.9.9", "AUTH_OPERATION_VERSION_MISMATCH"),
        ("operation_parameters_sha256", "e" * 64, "AUTH_OPERATION_PARAMETERS_MISMATCH"),
        ("capability_id", "web.discovery.tls", "AUTH_CAPABILITY_MISMATCH"),
        ("target_sha256", "d" * 64, "AUTH_TARGET_MISMATCH"),
        ("intrusiveness_level", "L2", "AUTH_INTRUSIVENESS_MISMATCH"),
    ],
)
def test_validly_signed_receipt_with_context_mismatch_refuses(
    scenario, field: str, value: str, expected: str
) -> None:
    receipt = _receipt(
        scenario["request"],
        scenario["contract"],
        scenario["step_request"],
        scenario["auth_key"],
        **{field: value},
    )
    result = _call(scenario, receipt=receipt)
    assert result.request_built is False
    assert result.runner_request is None
    assert result.codes == (expected,)


def test_invalid_roe_signature_still_refuses_after_valid_tb1_receipt(scenario) -> None:
    contract = copy.deepcopy(scenario["contract"])
    other = ed25519.Ed25519PrivateKey.generate()
    contract["signature"]["value"] = base64.b64encode(
        other.sign(roe_contract.canonical_payload(contract))
    ).decode("ascii")
    result = _call(scenario, contract=contract)
    assert result.request_built is False
    assert result.runner_request is None
    assert result.codes[0] == "ADMISSION_REFUSED"


def test_engaged_kill_switch_refuses_even_with_valid_tb1_receipt(
    scenario, tmp_path: Path
) -> None:
    config = handoff.RunnerHandoffConfig(
        trust_store_path=scenario["config"].trust_store_path,
        authorization_trust_store_path=scenario["config"].authorization_trust_store_path,
        kill_switch_path=_kill_switch(
            tmp_path,
            state="engaged",
            engaged_at="2026-08-10T09:00:00Z",
            engaged_by="lab-soc",
            reason="operator halt",
        ),
    )
    result = _call(scenario, config=config)
    assert result.request_built is False
    assert result.runner_request is None
    assert result.codes[0] == "ADMISSION_REFUSED"


@pytest.mark.parametrize(
    "policy, expected",
    [
        (handoff.RunnerDispatchPolicy(soft_timeout_ms=5000, hard_timeout_ms=5000), "DISPATCH_POLICY_TIMEOUT_ORDER_INVALID"),
        (handoff.RunnerDispatchPolicy(grace_period_ms=400000), "DISPATCH_POLICY_GRACE_OUT_OF_BOUNDS"),
        (handoff.RunnerDispatchPolicy(max_attempts=9), "DISPATCH_POLICY_ATTEMPTS_OUT_OF_BOUNDS"),
        (handoff.RunnerDispatchPolicy(retryable_error_codes=("EXECUTION_FAILED",)), "DISPATCH_POLICY_RETRY_CODES_INVALID"),
        (handoff.RunnerDispatchPolicy(cancellation_mode="force"), "DISPATCH_POLICY_CANCELLATION_MODE_INVALID"),
        (handoff.RunnerDispatchPolicy(progress_mode="always"), "DISPATCH_POLICY_PROGRESS_MODE_INVALID"),
    ],
)
def test_invalid_service_dispatch_policy_refuses_before_message_build(
    scenario, policy, expected: str
) -> None:
    config = handoff.RunnerHandoffConfig(
        trust_store_path=scenario["config"].trust_store_path,
        authorization_trust_store_path=scenario["config"].authorization_trust_store_path,
        kill_switch_path=scenario["config"].kill_switch_path,
        dispatch_policy=policy,
    )
    result = _call(scenario, config=config)
    assert result.request_built is False
    assert result.runner_request is None
    assert result.codes == (expected,)


def test_service_dispatch_policy_is_carried_into_message(scenario) -> None:
    config = handoff.RunnerHandoffConfig(
        trust_store_path=scenario["config"].trust_store_path,
        authorization_trust_store_path=scenario["config"].authorization_trust_store_path,
        kill_switch_path=scenario["config"].kill_switch_path,
        dispatch_policy=handoff.RunnerDispatchPolicy(
            soft_timeout_ms=1000,
            hard_timeout_ms=4000,
            max_attempts=3,
            retryable_error_codes=("TIMEOUT_SOFT",),
            cancellation_mode="cooperative_then_force",
            grace_period_ms=500,
            progress_mode="required",
        ),
    )
    message = _call(scenario, config=config).runner_request
    assert message["timeout_budget"] == {"soft_timeout_ms": 1000, "hard_timeout_ms": 4000}
    assert message["retry_policy"] == {"max_attempts": 3, "retryable_error_codes": ["TIMEOUT_SOFT"]}
    assert message["cancellation_policy"] == {"mode": "cooperative_then_force", "grace_period_ms": 500}
    assert message["progress_mode"] == "required"


def test_new_attempt_reuses_receipt_reference_and_idempotency(scenario) -> None:
    first = _call(scenario)
    retry_request = copy.deepcopy(scenario["request"])
    retry_request["attempt_id"] = ATTEMPT_UUID_RETRY
    retry = _call(scenario, request=retry_request)
    assert retry.request_built is True
    assert retry.authorization_ref == first.authorization_ref
    assert retry.idempotency_key == first.idempotency_key
    assert retry.request_fingerprint == first.request_fingerprint


def test_different_run_requires_different_control_plane_receipt(scenario) -> None:
    request = copy.deepcopy(scenario["request"])
    request["run_id"] = RUN_UUID_OTHER
    refused = _call(scenario, request=request)
    assert refused.request_built is False
    assert refused.codes == ("AUTH_RUN_MISMATCH",)

    receipt = _receipt(
        request,
        scenario["contract"],
        scenario["step_request"],
        scenario["auth_key"],
    )
    allowed = _call(scenario, request=request, receipt=receipt)
    assert allowed.request_built is True
    assert allowed.authorization_ref != scenario["receipt"]["authorization_ref"]


def test_changed_parameters_require_new_control_plane_receipt(scenario) -> None:
    first = _call(scenario)
    changed_request = copy.deepcopy(scenario["request"])
    changed_request["operation"]["parameters"]["follow_redirects"] = True

    refused = _call(scenario, request=changed_request)
    assert refused.request_built is False
    assert refused.runner_request is None
    assert refused.codes == ("AUTH_OPERATION_PARAMETERS_MISMATCH",)

    changed_receipt = _receipt(
        changed_request,
        scenario["contract"],
        scenario["step_request"],
        scenario["auth_key"],
    )
    allowed = _call(scenario, request=changed_request, receipt=changed_receipt)
    assert allowed.request_built is True
    assert allowed.authorization_ref != first.authorization_ref
    assert allowed.idempotency_key != first.idempotency_key
    assert allowed.request_fingerprint != first.request_fingerprint


def test_invalid_attempt_uuid_refuses_without_synthetic_mapping(scenario) -> None:
    request = copy.deepcopy(scenario["request"])
    request["attempt_id"] = "attempt-001"
    result = _call(scenario, request=request)
    assert result.request_built is False
    assert result.runner_request is None
    assert result.codes == ("CORRELATION_NOT_UUID:attempt_id",)


def test_secret_like_operation_input_is_refused(scenario) -> None:
    request = copy.deepcopy(scenario["request"])
    request["operation"]["parameters"]["password"] = "forbidden-test-marker"
    result = _call(scenario, request=request)
    assert result.request_built is False
    assert result.runner_request is None


def test_result_repr_and_summary_never_leak_restricted_payload(scenario) -> None:
    result = _call(scenario)
    assert result.request_built is True
    assert result.runner_request is not None
    assert result.runner_request["operation"]["input"]["target"]["value"] == "juice-shop-demo"

    serialized = repr(result) + json.dumps(result.sanitized_summary(), sort_keys=True)
    for forbidden in (
        "juice-shop-demo",
        "follow_redirects",
        "parameters",
        "signature",
        "public_key",
        "trust-store",
        "password",
        "private_key",
    ):
        assert forbidden not in serialized


def test_result_positive_state_is_message_build_not_dispatch(scenario) -> None:
    result = _call(scenario)
    fields = {field.name for field in result.__dataclass_fields__.values()}
    assert "request_built" in fields
    for forbidden in ("dispatched", "executed", "sent", "delivered", "submitted"):
        assert forbidden not in fields


def test_runner_sdk_fingerprint_matches_result(scenario) -> None:
    result = _call(scenario)
    assert result.runner_request is not None
    assert request_fingerprint(result.runner_request) == result.request_fingerprint
