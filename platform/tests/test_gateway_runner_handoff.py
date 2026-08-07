"""Canonical gateway -> Runner Protocol v2 handoff boundary tests.

All signing key material is generated in-memory at test time. The repository
stores no private keys; trust-store fixtures contain public verification
material only, inside temporary directories. Nothing here executes a runner, a
target, a laboratory, a scanner, a network call or a subprocess.
"""

from __future__ import annotations

import base64
import copy
import hashlib
import importlib.util
import json
import sys
from pathlib import Path
from typing import Any

import pytest
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
STEP_UUID = "7b1e4d3c-2a95-4c8e-8f10-3e5d7c9b1a24"
ATTEMPT_UUID = "9a3c5e71-4d62-4b18-8e27-5f7a9c1d3b46"
ATTEMPT_UUID_RETRY = "1d4f6a82-5e73-4c29-9f38-6a8b0d2e4c57"
KEY_ID = "-".join(("roe", "signing", "handoff", "ed25519"))
KEY_NOT_BEFORE = "2000-01-01T00:00:00Z"
KEY_NOT_AFTER = "2100-01-01T00:00:00Z"
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


# --------------------------------------------------------------------------
# fixtures
# --------------------------------------------------------------------------


def _trust_store(
    tmp_path: Path,
    *,
    not_before: str = KEY_NOT_BEFORE,
    not_after: str = KEY_NOT_AFTER,
) -> tuple[Path, Any]:
    private_key = ed25519.Ed25519PrivateKey.generate()
    from cryptography.hazmat.primitives import serialization

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
                        "not_before": not_before,
                        "not_after": not_after,
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
        "contract_id": "roe-contract-handoff-001",
        "campaign_id": CAMPAIGN_UUID,
        "revision": 1,
        "state": "active",
        "issued_at": "2026-08-01T08:00:00Z",
        "valid_from": "2026-08-01T09:00:00Z",
        "valid_until": "2126-08-31T18:00:00Z",
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
                    "end": "2126-08-31T18:00:00Z",
                }
            ],
            "approvers": [
                {
                    "approval_id": "approval-customer",
                    "subject_id": "lab-owner-security",
                    "side": "customer",
                    "role": "Security Owner",
                    "approved_at": "2026-08-01T08:30:00Z",
                    "valid_until": "2126-08-31T18:00:00Z",
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


@pytest.fixture()
def scenario(tmp_path: Path) -> dict[str, Any]:
    store, private_key = _trust_store(tmp_path)
    contract = _sign(_contract(), private_key)
    return {
        "tmp_path": tmp_path,
        "private_key": private_key,
        "contract": contract,
        "step_request": _step_request(),
        "request": _admission_request(contract),
        "config": handoff.RunnerHandoffConfig(
            trust_store_path=store,
            kill_switch_path=_kill_switch(tmp_path),
        ),
    }


def _call(scenario: dict[str, Any], **overrides: Any) -> Any:
    return handoff.build_step_request(
        overrides.get("request", scenario["request"]),
        overrides.get("contract", scenario["contract"]),
        overrides.get("step_request", scenario["step_request"]),
        overrides.get("config", scenario["config"]),
    )


# --------------------------------------------------------------------------
# positive path
# --------------------------------------------------------------------------


def test_admitted_handoff_builds_a_valid_runner_step_request(scenario) -> None:
    result = _call(scenario)

    assert result.dispatched is True
    assert result.codes == ("HANDOFF_STEP_REQUEST_BUILT",)
    assert result.admission_codes == ("ADMIT_TYPED_OPERATION",)
    message = result.runner_request
    assert message is not None
    validate_semantics(message)
    assert message["message_type"] == "runner.step.request"
    assert message["protocol_version"] == "2.0.0"
    assert message["operation"]["capability_id"] == OPERATION_ID
    assert message["emitted_at"].endswith("Z")


def test_all_four_correlation_identifiers_are_preserved_exactly(scenario) -> None:
    message = _call(scenario).runner_request

    assert message["correlation"] == {
        "campaign_id": CAMPAIGN_UUID,
        "run_id": RUN_UUID,
        "step_id": STEP_UUID,
        "attempt_id": ATTEMPT_UUID,
    }


def test_dispatch_policy_comes_from_service_configuration(scenario) -> None:
    config = handoff.RunnerHandoffConfig(
        trust_store_path=scenario["config"].trust_store_path,
        kill_switch_path=scenario["config"].kill_switch_path,
        dispatch_policy=handoff.RunnerDispatchPolicy(
            soft_timeout_ms=1_000,
            hard_timeout_ms=4_000,
            max_attempts=3,
            retryable_error_codes=("TIMEOUT_SOFT",),
            cancellation_mode="cooperative_then_force",
            grace_period_ms=500,
            progress_mode="required",
        ),
    )
    message = _call(scenario, config=config).runner_request

    assert message["timeout_budget"] == {
        "soft_timeout_ms": 1_000,
        "hard_timeout_ms": 4_000,
    }
    assert message["retry_policy"] == {
        "max_attempts": 3,
        "retryable_error_codes": ["TIMEOUT_SOFT"],
    }
    assert message["cancellation_policy"] == {
        "mode": "cooperative_then_force",
        "grace_period_ms": 500,
    }
    assert message["progress_mode"] == "required"


@pytest.mark.parametrize(
    "policy, code",
    [
        (
            handoff.RunnerDispatchPolicy(soft_timeout_ms=5_000, hard_timeout_ms=5_000),
            "DISPATCH_POLICY_TIMEOUT_ORDER_INVALID",
        ),
        (
            handoff.RunnerDispatchPolicy(grace_period_ms=400_000),
            "DISPATCH_POLICY_GRACE_OUT_OF_BOUNDS",
        ),
        (
            handoff.RunnerDispatchPolicy(max_attempts=9),
            "DISPATCH_POLICY_ATTEMPTS_OUT_OF_BOUNDS",
        ),
        (
            handoff.RunnerDispatchPolicy(retryable_error_codes=("EXECUTION_FAILED",)),
            "DISPATCH_POLICY_RETRY_CODES_INVALID",
        ),
        (
            handoff.RunnerDispatchPolicy(cancellation_mode="force"),
            "DISPATCH_POLICY_CANCELLATION_MODE_INVALID",
        ),
        (
            handoff.RunnerDispatchPolicy(progress_mode="always"),
            "DISPATCH_POLICY_PROGRESS_MODE_INVALID",
        ),
    ],
)
def test_out_of_bound_dispatch_policy_refuses_before_admission(
    scenario, policy, code
) -> None:
    config = handoff.RunnerHandoffConfig(
        trust_store_path=scenario["config"].trust_store_path,
        kill_switch_path=scenario["config"].kill_switch_path,
        dispatch_policy=policy,
    )
    result = _call(scenario, config=config)

    assert result.dispatched is False
    assert result.runner_request is None
    assert result.codes == (code,)


# --------------------------------------------------------------------------
# authorization is derived, never supplied
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "field",
    [
        "admission_decision",
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
def test_caller_supplied_authorization_or_policy_field_is_refused(
    scenario, field
) -> None:
    request = copy.deepcopy(scenario["request"])
    request[field] = {"allowed": True, "codes": ["ALLOW"]}

    result = _call(scenario, request=request)

    assert result.dispatched is False
    assert result.runner_request is None
    assert result.codes == ("HANDOFF_CALLER_SUPPLIED_AUTHORIZATION",)


def test_forged_caller_allow_on_revoked_contract_never_dispatches(scenario) -> None:
    contract = copy.deepcopy(scenario["contract"])
    contract["state"] = "revoked"
    contract = _sign(contract, scenario["private_key"])
    request = copy.deepcopy(scenario["request"])
    request["contract_payload_sha256"] = roe_contract.payload_sha256(contract)
    request["roe_decision"] = {"allowed": True, "codes": ["ALLOW"]}

    result = _call(scenario, request=request, contract=contract)

    assert result.dispatched is False
    assert result.runner_request is None
    assert result.codes == ("HANDOFF_CALLER_SUPPLIED_AUTHORIZATION",)


def test_revoked_contract_refuses_without_runner_request(scenario) -> None:
    contract = copy.deepcopy(scenario["contract"])
    contract["state"] = "revoked"
    contract = _sign(contract, scenario["private_key"])
    request = copy.deepcopy(scenario["request"])
    request["contract_payload_sha256"] = roe_contract.payload_sha256(contract)

    result = _call(scenario, request=request, contract=contract)

    assert result.dispatched is False
    assert result.runner_request is None
    assert result.codes[0] == "ADMISSION_REFUSED"
    assert any(code.startswith("ROE_REFUSED:") for code in result.admission_codes)


def test_invalid_signature_refuses(scenario) -> None:
    contract = copy.deepcopy(scenario["contract"])
    other_key = ed25519.Ed25519PrivateKey.generate()
    raw = other_key.sign(roe_contract.canonical_payload(contract))
    contract["signature"]["value"] = base64.b64encode(raw).decode("ascii")

    result = _call(scenario, contract=contract)

    assert result.dispatched is False
    assert result.runner_request is None
    assert result.codes[0] == "ADMISSION_REFUSED"


def test_expired_trust_store_key_refuses(tmp_path: Path) -> None:
    expired_dir = tmp_path / "expired"
    expired_dir.mkdir(parents=True, exist_ok=True)
    store_path, private_key = _trust_store(
        expired_dir, not_after="2001-01-01T00:00:00Z"
    )
    contract = _sign(_contract(), private_key)
    request = _admission_request(contract)
    config = handoff.RunnerHandoffConfig(
        trust_store_path=store_path,
        kill_switch_path=_kill_switch(tmp_path),
    )

    result = handoff.build_step_request(request, contract, _step_request(), config)

    assert result.dispatched is False
    assert result.runner_request is None


def test_missing_trust_store_source_refuses(scenario) -> None:
    config = handoff.RunnerHandoffConfig(
        trust_store_path=None,
        kill_switch_path=scenario["config"].kill_switch_path,
    )

    result = _call(scenario, config=config)

    assert result.dispatched is False
    assert result.runner_request is None
    assert result.admission_codes == ("SIGNATURE_VERIFIER_UNAVAILABLE",)


def test_missing_kill_switch_source_refuses(scenario) -> None:
    config = handoff.RunnerHandoffConfig(
        trust_store_path=scenario["config"].trust_store_path,
        kill_switch_path=None,
    )

    result = _call(scenario, config=config)

    assert result.dispatched is False
    assert result.runner_request is None
    assert result.admission_codes == ("KILL_SWITCH_SOURCE_REQUIRED",)


def test_engaged_kill_switch_refuses(scenario, tmp_path: Path) -> None:
    engaged = _kill_switch(
        tmp_path,
        state="engaged",
        engaged_at="2026-08-10T09:00:00Z",
        engaged_by="lab-soc",
        reason="operator halt",
    )
    config = handoff.RunnerHandoffConfig(
        trust_store_path=scenario["config"].trust_store_path,
        kill_switch_path=engaged,
    )

    result = _call(scenario, config=config)

    assert result.dispatched is False
    assert result.runner_request is None
    assert result.codes[0] == "ADMISSION_REFUSED"


def test_unreadable_kill_switch_refuses(scenario, tmp_path: Path) -> None:
    config = handoff.RunnerHandoffConfig(
        trust_store_path=scenario["config"].trust_store_path,
        kill_switch_path=tmp_path / "absent-kill-switch.json",
    )

    result = _call(scenario, config=config)

    assert result.dispatched is False
    assert result.runner_request is None


@pytest.mark.parametrize(
    "mutation",
    [
        {"target": {"type": "lab-asset", "value": "other-lab-asset"}},
        {"campaign_id": "0c6c0d70-4d54-4ad8-9f57-6a2e7b8c9d01"},
        {"operation": {"id": "web.discovery.tls", "version": "1.0.0", "parameters": {}}},
    ],
)
def test_binding_mismatch_refuses_without_runner_request(scenario, mutation) -> None:
    request = copy.deepcopy(scenario["request"])
    request.update(copy.deepcopy(mutation))

    result = _call(scenario, request=request)

    assert result.dispatched is False
    assert result.runner_request is None


def test_capability_mismatch_refuses(scenario) -> None:
    step_request = copy.deepcopy(scenario["step_request"])
    step_request["capability"] = "web.discovery.tls"

    result = _call(scenario, step_request=step_request)

    assert result.dispatched is False
    assert result.runner_request is None


def test_intrusiveness_mismatch_refuses(scenario) -> None:
    step_request = copy.deepcopy(scenario["step_request"])
    step_request["intrusiveness_level"] = "L2"

    result = _call(scenario, step_request=step_request)

    assert result.dispatched is False
    assert result.runner_request is None


# --------------------------------------------------------------------------
# correlation UUID gap is exposed fail-closed
# --------------------------------------------------------------------------


@pytest.mark.parametrize("field", ["campaign_id", "run_id", "step_id", "attempt_id"])
def test_non_uuid_correlation_refuses_without_inventing_identifiers(
    scenario, field
) -> None:
    request = copy.deepcopy(scenario["request"])
    contract = copy.deepcopy(scenario["contract"])
    step_request = copy.deepcopy(scenario["step_request"])
    request[field] = "run-001"
    if field == "campaign_id":
        contract["campaign_id"] = "run-001"
        contract = _sign(contract, scenario["private_key"])
        step_request["campaign_id"] = "run-001"
        request["contract_payload_sha256"] = roe_contract.payload_sha256(contract)

    result = _call(
        scenario, request=request, contract=contract, step_request=step_request
    )

    assert result.dispatched is False
    assert result.runner_request is None
    assert f"CORRELATION_NOT_UUID:{field}" in result.codes


# --------------------------------------------------------------------------
# authorization_ref semantics
# --------------------------------------------------------------------------


def test_authorization_ref_is_deterministic_and_content_addressed(scenario) -> None:
    first = _call(scenario).authorization_ref
    second = _call(scenario).authorization_ref

    assert first == second
    assert first.startswith(handoff.AUTHORIZATION_REF_PREFIX)
    digest = first[len(handoff.AUTHORIZATION_REF_PREFIX) :]
    assert len(digest) == 64 and set(digest) <= set("0123456789abcdef")


def test_authorization_ref_carries_no_raw_target_or_secret_material(scenario) -> None:
    result = _call(scenario)
    serialized = json.dumps(
        {
            "authorization_ref": result.authorization_ref,
            "idempotency_key": result.idempotency_key,
        }
    )

    assert "juice-shop-demo" not in serialized
    assert scenario["contract"]["signature"]["value"] not in serialized
    for forbidden in ("token", "password", "secret", "private_key"):
        assert forbidden not in serialized


def test_authorization_ref_changes_with_the_authorization_context(scenario) -> None:
    baseline = _call(scenario).authorization_ref
    step_request = copy.deepcopy(scenario["step_request"])
    step_request["target"] = {"type": "lab-asset", "value": "juice-shop-demo"}
    request = copy.deepcopy(scenario["request"])
    request["operation"] = {
        "id": "web.discovery.tls",
        "version": "1.0.0",
        "parameters": {},
    }
    request["capability_attestations"] = ["web.discovery.tls"]
    step_request["capability"] = "web.discovery.tls"

    other = _call(scenario, request=request, step_request=step_request)

    assert other.dispatched is True
    assert other.authorization_ref != baseline


def test_authorization_ref_is_documented_as_reference_not_bearer_token() -> None:
    source = (GATEWAY_DIR / "runner_handoff.py").read_text(encoding="utf-8")

    assert "not a bearer token" in source
    assert "not a grant" in source
    assert "not a signature" in source
    assert "NOT_IMPLEMENTED" in source


# --------------------------------------------------------------------------
# idempotency
# --------------------------------------------------------------------------


def test_idempotency_key_is_stable_across_a_new_attempt(scenario) -> None:
    first = _call(scenario)
    retry_request = copy.deepcopy(scenario["request"])
    retry_request["attempt_id"] = ATTEMPT_UUID_RETRY
    second = _call(scenario, request=retry_request)

    assert second.dispatched is True
    assert second.runner_request["correlation"]["attempt_id"] == ATTEMPT_UUID_RETRY
    assert second.idempotency_key == first.idempotency_key
    assert second.request_fingerprint == first.request_fingerprint
    assert request_fingerprint(second.runner_request) == request_fingerprint(
        first.runner_request
    )


def test_changed_effect_changes_idempotency_key_and_fingerprint(scenario) -> None:
    baseline = _call(scenario)
    changed = copy.deepcopy(scenario["request"])
    changed["operation"]["parameters"] = {"follow_redirects": True}

    other = _call(scenario, request=changed)

    assert other.dispatched is True
    assert other.idempotency_key != baseline.idempotency_key
    assert other.request_fingerprint != baseline.request_fingerprint


def test_changed_service_policy_changes_the_logical_effect_key(scenario) -> None:
    baseline = _call(scenario)
    config = handoff.RunnerHandoffConfig(
        trust_store_path=scenario["config"].trust_store_path,
        kill_switch_path=scenario["config"].kill_switch_path,
        dispatch_policy=handoff.RunnerDispatchPolicy(hard_timeout_ms=60_000),
    )

    other = _call(scenario, config=config)

    assert other.idempotency_key != baseline.idempotency_key


# --------------------------------------------------------------------------
# runner input hygiene
# --------------------------------------------------------------------------


def test_runner_input_is_derived_only_from_typed_target_and_parameters(
    scenario,
) -> None:
    message = _call(scenario).runner_request
    operation_input = message["operation"]["input"]

    assert set(operation_input) == {
        "operation_id",
        "operation_version",
        "intrusiveness_level",
        "target",
        "parameters",
    }
    assert operation_input["target"] == {
        "type": "lab-asset",
        "value": "juice-shop-demo",
    }
    assert operation_input["parameters"] == {"follow_redirects": False}


@pytest.mark.parametrize(
    "parameter", ["command", "shell", "argv", "cwd", "env", "token", "password"]
)
def test_command_and_secret_like_parameters_never_reach_the_runner(
    scenario, parameter
) -> None:
    request = copy.deepcopy(scenario["request"])
    request["operation"]["parameters"] = {parameter: "value"}

    result = _call(scenario, request=request)

    assert result.dispatched is False
    assert result.runner_request is None


def test_no_secret_like_key_appears_anywhere_in_the_runner_request(scenario) -> None:
    message = _call(scenario).runner_request
    serialized = json.dumps(message)

    for forbidden in (
        "token",
        "password",
        "secret",
        "cookie",
        "authorization\"",
        "api_key",
        "credential",
        "private_key",
        "command",
        "shell",
        "argv",
        "cwd",
        '"env"',
    ):
        assert forbidden not in serialized


def test_result_repr_exposes_no_target_value_or_signature(scenario) -> None:
    result = _call(scenario)
    rendered = repr(
        handoff.RunnerHandoffResult(
            dispatched=result.dispatched,
            codes=result.codes,
            admission_codes=result.admission_codes,
            request_id=result.request_id,
            campaign_id=result.campaign_id,
            operation_id=result.operation_id,
            operation_version=result.operation_version,
            authorization_ref=result.authorization_ref,
            idempotency_key=result.idempotency_key,
            request_fingerprint=result.request_fingerprint,
            runner_request=None,
        )
    )

    assert "juice-shop-demo" not in rendered
    assert scenario["contract"]["signature"]["value"] not in rendered
