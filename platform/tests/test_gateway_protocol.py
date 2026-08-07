from __future__ import annotations

import copy
import hashlib
import importlib.util
import sys
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[2]
MODULE_PATH = ROOT / "platform/gateway-protocol/gateway_protocol.py"
SPEC = importlib.util.spec_from_file_location("gateway_protocol", MODULE_PATH)
assert SPEC and SPEC.loader
gateway = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = gateway
SPEC.loader.exec_module(gateway)

REGISTRY_PATH = ROOT / "platform/gateway-protocol/operation-registry.yaml"
RUNTIME_PATH = ROOT / "platform/registry.yaml"


def _runtime_digest() -> str:
    return hashlib.sha256(RUNTIME_PATH.read_bytes()).hexdigest()


def _request(operation_id: str = "system.health.read") -> dict[str, Any]:
    target = {"type": "lab-asset", "value": "juice-shop-demo"}
    digest = _runtime_digest()
    capabilities = {
        "system.health.read": ["system.health.read"],
        "runtime.inventory.read": ["runtime.inventory.read"],
        "web.discovery.headers": ["web.discovery.headers"],
        "web.discovery.tls": ["web.discovery.tls"],
        "web.validation.sql-injection": ["web.validation.sql-injection"],
        "lab.lifecycle.stop": ["lab.lifecycle.stop"],
    }
    parameters: dict[str, Any] = {}
    profile = "normal"
    if operation_id == "web.validation.sql-injection":
        parameters = {"validation_case_id": "case-synthetic-001"}
        profile = "controlled"
    elif operation_id == "lab.lifecycle.stop":
        parameters = {"reason_code": "KILL_SWITCH"}
        profile = "controlled"
    return {
        "schema_version": "1.0.0",
        "request_id": "gateway-request-001",
        "campaign_id": "campaign-001",
        "run_id": "run-001",
        "step_id": "step-001",
        "attempt_id": "attempt-001",
        "requested_at": "2026-08-07T00:00:00Z",
        "profile": profile,
        "operation": {
            "id": operation_id,
            "version": "1.0.0",
            "parameters": parameters,
        },
        "target": target,
        "roe_decision": {
            "allowed": True,
            "codes": ["ALLOW"],
            "contract_id": "roe-contract-001",
            "campaign_id": "campaign-001",
            "step_request_id": "roe-step-request-001",
            "authorized_operation_id": operation_id,
            "authorized_target_sha256": gateway.canonical_target_digest(target),
            "contract_payload_sha256": "a" * 64,
            "intrusiveness_ceiling": "L4",
        },
        "runtime_observation": {
            "state": "IN_SYNC",
            "canonical_root": "platform/registry.yaml",
            "canonical_sha256": digest,
            "observed_sha256": digest,
            "observed_at": "2026-08-07T00:00:00Z",
        },
        "capability_attestations": capabilities[operation_id],
    }


def _codes(request: dict[str, Any]) -> tuple[str, ...]:
    return gateway.authorize_typed_operation(
        request,
        registry_path=REGISTRY_PATH,
        runtime_registry_path=RUNTIME_PATH,
    ).codes


def _mutated_registry(tmp_path: Path) -> tuple[dict[str, Any], Path]:
    registry = yaml.safe_load(REGISTRY_PATH.read_text(encoding="utf-8"))
    path = tmp_path / "registry.yaml"
    return registry, path


def test_normal_typed_read_operation_is_allowed() -> None:
    decision = gateway.authorize_typed_operation(
        _request(),
        registry_path=REGISTRY_PATH,
        runtime_registry_path=RUNTIME_PATH,
    )

    assert decision.allowed is True
    assert decision.codes == ("ALLOW_TYPED_OPERATION",)
    assert decision.operation_id == "system.health.read"


def test_controlled_synthetic_validation_contract_is_allowed() -> None:
    decision = gateway.authorize_typed_operation(
        _request("web.validation.sql-injection"),
        registry_path=REGISTRY_PATH,
        runtime_registry_path=RUNTIME_PATH,
    )

    assert decision.allowed is True
    assert decision.operation_id == "web.validation.sql-injection"


def test_unknown_operation_is_refused() -> None:
    request = _request()
    request["operation"]["id"] = "unknown.operation"
    request["roe_decision"]["authorized_operation_id"] = "unknown.operation"

    assert _codes(request) == ("OPERATION_UNKNOWN",)


def test_operation_version_mismatch_is_refused() -> None:
    request = _request()
    request["operation"]["version"] = "2.0.0"

    assert _codes(request) == ("OPERATION_VERSION_MISMATCH",)


def test_operation_parameters_are_validated_by_declared_schema() -> None:
    request = _request("web.validation.sql-injection")
    request["operation"]["parameters"] = {}

    assert _codes(request) == ("OPERATION_PARAMETERS_INVALID",)


def test_normal_profile_cannot_invoke_controlled_operation() -> None:
    request = _request("web.validation.sql-injection")
    request["profile"] = "normal"

    assert _codes(request) == ("OPERATION_NOT_ALLOWED_IN_PROFILE",)


def test_missing_capability_attestation_is_refused() -> None:
    request = _request()
    request["capability_attestations"] = []

    assert _codes(request) == ("CAPABILITY_ATTESTATION_MISSING",)


def test_non_allow_roe_decision_is_refused() -> None:
    request = _request()
    request["roe_decision"]["allowed"] = False
    request["roe_decision"]["codes"] = ["TARGET_OUT_OF_SCOPE"]

    assert _codes(request) == ("ROE_DECISION_NOT_ALLOW",)


def test_roe_campaign_binding_is_enforced() -> None:
    request = _request()
    request["roe_decision"]["campaign_id"] = "campaign-other"

    assert _codes(request) == ("ROE_CAMPAIGN_MISMATCH",)


def test_roe_operation_binding_is_enforced() -> None:
    request = _request()
    request["roe_decision"]["authorized_operation_id"] = "runtime.inventory.read"

    assert _codes(request) == ("ROE_OPERATION_MISMATCH",)


def test_roe_target_digest_binding_is_enforced() -> None:
    request = _request()
    request["target"]["value"] = "different-lab"

    assert _codes(request) == ("ROE_TARGET_MISMATCH",)


def test_roe_intrusiveness_ceiling_is_enforced() -> None:
    request = _request("web.validation.sql-injection")
    request["roe_decision"]["intrusiveness_ceiling"] = "L1"

    assert _codes(request) == ("ROE_INTRUSIVENESS_EXCEEDED",)


def test_runtime_drift_blocks_decision() -> None:
    request = _request()
    request["runtime_observation"]["state"] = "DRIFT_DETECTED"

    assert _codes(request) == ("RUNTIME_DRIFT_DETECTED",)


def test_unknown_runtime_state_blocks_decision() -> None:
    request = _request()
    request["runtime_observation"]["state"] = "UNKNOWN"

    assert _codes(request) == ("RUNTIME_STATE_UNKNOWN",)


def test_canonical_runtime_digest_mismatch_is_refused() -> None:
    request = _request()
    request["runtime_observation"]["canonical_sha256"] = "b" * 64
    request["runtime_observation"]["observed_sha256"] = "b" * 64

    assert _codes(request) == ("RUNTIME_CANONICAL_DIGEST_MISMATCH",)


def test_observed_runtime_digest_mismatch_is_refused() -> None:
    request = _request()
    request["runtime_observation"]["observed_sha256"] = "b" * 64

    assert _codes(request) == ("RUNTIME_OBSERVED_DIGEST_MISMATCH",)


def test_unknown_request_property_is_refused_before_authorization() -> None:
    request = _request()
    request["bypass"] = True

    assert _codes(request) == ("REQUEST_SCHEMA_INVALID",)


def test_command_shell_and_environment_fields_are_refused_recursively() -> None:
    for field in ("command", "execute_command", "shell", "argv", "cwd", "environment"):
        request = _request()
        request["operation"]["parameters"][field] = "not-accepted"
        assert _codes(request) == (f"FORBIDDEN_FIELD:operation.parameters.{field}",)


def test_decision_never_contains_target_parameters_or_roe_digest() -> None:
    request = _request("web.validation.sql-injection")
    decision = gateway.authorize_typed_operation(
        request,
        registry_path=REGISTRY_PATH,
        runtime_registry_path=RUNTIME_PATH,
    )

    serialized = repr(decision)
    assert "case-synthetic-001" not in serialized
    assert "juice-shop-demo" not in serialized
    assert "a" * 64 not in serialized


def test_registry_has_no_generic_execution_operation() -> None:
    registry = gateway.load_registry(REGISTRY_PATH)

    assert registry["generic_execution"] == "forbidden"
    assert all(
        token not in operation["id"].split(".")
        for operation in registry["operations"]
        for token in ("command", "exec", "shell", "terminal")
    )
    assert registry["profiles"]["normal"]["generic_execution"] is False


def test_duplicate_operation_identity_is_rejected(tmp_path: Path) -> None:
    registry, path = _mutated_registry(tmp_path)
    registry["operations"].append(copy.deepcopy(registry["operations"][0]))
    path.write_text(yaml.safe_dump(registry), encoding="utf-8")

    try:
        gateway.load_registry(path)
    except gateway.GatewayValidationError as exc:
        assert str(exc) == "DUPLICATE_OPERATION_IDENTITY"
    else:
        raise AssertionError("duplicate operation was accepted")


def test_profile_reference_to_unknown_operation_is_rejected(tmp_path: Path) -> None:
    registry, path = _mutated_registry(tmp_path)
    registry["profiles"]["normal"]["operations"].append("unknown.operation")
    path.write_text(yaml.safe_dump(registry), encoding="utf-8")

    try:
        gateway.load_registry(path)
    except gateway.GatewayValidationError as exc:
        assert str(exc) == "PROFILE_OPERATION_UNRESOLVED"
    else:
        raise AssertionError("unknown profile operation was accepted")


def test_normal_profile_cannot_be_extended_with_l2_operation(tmp_path: Path) -> None:
    registry, path = _mutated_registry(tmp_path)
    registry["profiles"]["normal"]["operations"].append(
        "web.validation.sql-injection"
    )
    path.write_text(yaml.safe_dump(registry), encoding="utf-8")

    try:
        gateway.load_registry(path)
    except gateway.GatewayValidationError as exc:
        assert str(exc) == "NORMAL_PROFILE_TOO_INTRUSIVE"
    else:
        raise AssertionError("intrusive normal profile was accepted")


def test_registry_handler_reference_cannot_become_a_path(tmp_path: Path) -> None:
    registry, path = _mutated_registry(tmp_path)
    registry["operations"][0]["handler_ref"] = "candidate/unsafe"
    path.write_text(yaml.safe_dump(registry), encoding="utf-8")

    assert _registry_error(path) == "REGISTRY_SCHEMA_INVALID"


def test_registry_parameter_schema_cannot_accept_command_field(tmp_path: Path) -> None:
    registry, path = _mutated_registry(tmp_path)
    registry["operations"][0]["parameters_schema"] = {
        "type": "object",
        "properties": {"command": {"type": "string"}},
    }
    path.write_text(yaml.safe_dump(registry), encoding="utf-8")

    assert _registry_error(path) == "FORBIDDEN_FIELD:properties.command"


def _registry_error(path: Path) -> str:
    try:
        gateway.load_registry(path)
    except gateway.GatewayValidationError as exc:
        return str(exc)
    raise AssertionError("invalid registry was accepted")
