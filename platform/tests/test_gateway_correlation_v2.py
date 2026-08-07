"""Versioned correlation contract tests for the typed gateway.

These tests are schema/contract only. They do not authorize, dispatch, execute,
connect to a runner or touch a target/network.
"""

from __future__ import annotations

import copy
import importlib.util
import sys
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[2]
GATEWAY_DIR = ROOT / "platform/gateway-protocol"

CAMPAIGN_UUID = "3f2a1c64-1e8b-4a2b-9c7d-1c2b3a4d5e6f"
RUN_UUID = "5c9d7e2a-8b41-4f6d-9a03-2d4e6f8a1b2c"
STEP_UUID = "7b1e4d3c-2a95-4c8e-8f10-3e5d7c9b1a24"
ATTEMPT_UUID = "9a3c5e71-4d62-4b18-8e27-5f7a9c1d3b46"
DIGEST = "a" * 64
TARGET_DIGEST = "b" * 64


def _load(module_name: str, path: Path) -> Any:
    spec = importlib.util.spec_from_file_location(module_name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


gateway = _load("gateway_protocol_correlation_v2_test", GATEWAY_DIR / "gateway_protocol.py")
admission = _load("gateway_admission_correlation_v2_test", GATEWAY_DIR / "admission.py")


def _correlation(*, uuid_values: bool) -> dict[str, str]:
    if uuid_values:
        return {
            "campaign_id": CAMPAIGN_UUID,
            "run_id": RUN_UUID,
            "step_id": STEP_UUID,
            "attempt_id": ATTEMPT_UUID,
        }
    return {
        "campaign_id": "campaign-legacy-001",
        "run_id": "run-legacy-001",
        "step_id": "step-legacy-001",
        "attempt_id": "attempt-legacy-001",
    }


def _runtime_observation() -> dict[str, Any]:
    return {
        "state": "IN_SYNC",
        "canonical_root": "platform/registry.yaml",
        "canonical_sha256": DIGEST,
        "observed_sha256": DIGEST,
        "observed_at": "2026-08-10T10:00:00Z",
    }


def _operation() -> dict[str, Any]:
    return {
        "id": "web.discovery.headers",
        "version": "1.0.0",
        "parameters": {"follow_redirects": False},
    }


def _target() -> dict[str, str]:
    return {"type": "lab-asset", "value": "juice-shop-demo"}


def _admission_request(*, version: str, uuid_values: bool) -> dict[str, Any]:
    return {
        "schema_version": version,
        "request_id": "gateway-correlation-contract-test",
        **_correlation(uuid_values=uuid_values),
        "requested_at": "2026-08-10T10:00:00Z",
        "profile": "normal",
        "operation": _operation(),
        "target": _target(),
        "roe_step_request_id": "roe-step-correlation-test",
        "contract_payload_sha256": DIGEST,
        "runtime_observation": _runtime_observation(),
        "capability_attestations": ["web.discovery.headers"],
    }


def _gateway_request(*, version: str, uuid_values: bool) -> dict[str, Any]:
    return {
        "schema_version": version,
        "request_id": "gateway-correlation-contract-test",
        **_correlation(uuid_values=uuid_values),
        "requested_at": "2026-08-10T10:00:00Z",
        "profile": "normal",
        "operation": _operation(),
        "target": _target(),
        "roe_decision": {
            "allowed": True,
            "codes": ["ALLOW"],
            "contract_id": "roe-contract-test",
            "campaign_id": CAMPAIGN_UUID if uuid_values else "campaign-legacy-001",
            "step_request_id": "roe-step-correlation-test",
            "authorized_operation_id": "web.discovery.headers",
            "authorized_target_sha256": TARGET_DIGEST,
            "contract_payload_sha256": DIGEST,
            "intrusiveness_ceiling": "L1",
        },
        "runtime_observation": _runtime_observation(),
        "capability_attestations": ["web.discovery.headers"],
    }


def test_legacy_admission_v1_keeps_non_uuid_compatibility() -> None:
    request = _admission_request(version="1.0.0", uuid_values=False)
    admission.validate_admission_request(request)
    assert admission.admission_request_schema_version(request) == "1.0.0"


def test_canonical_admission_v2_requires_uuid_correlation() -> None:
    request = _admission_request(version="2.0.0", uuid_values=True)
    admission.validate_admission_request(request)
    assert admission.admission_request_schema_version(request) == "2.0.0"


@pytest.mark.parametrize("field", ["campaign_id", "run_id", "step_id", "attempt_id"])
def test_canonical_admission_v2_rejects_each_non_uuid_correlation_field(field: str) -> None:
    request = _admission_request(version="2.0.0", uuid_values=True)
    request[field] = f"{field}-legacy-value"
    with pytest.raises(admission.AdmissionError, match="ADMISSION_SCHEMA_INVALID"):
        admission.validate_admission_request(request)


def test_unknown_admission_version_is_refused_explicitly() -> None:
    request = _admission_request(version="9.0.0", uuid_values=True)
    with pytest.raises(admission.AdmissionError, match="ADMISSION_SCHEMA_UNSUPPORTED"):
        admission.validate_admission_request(request)


def test_explicit_v1_to_v2_promotion_changes_only_schema_version() -> None:
    legacy = _admission_request(version="1.0.0", uuid_values=True)
    promoted = admission.promote_legacy_request_to_v2(legacy)

    assert promoted["schema_version"] == "2.0.0"
    for field in ("campaign_id", "run_id", "step_id", "attempt_id"):
        assert promoted[field] == legacy[field]
    assert {k: v for k, v in promoted.items() if k != "schema_version"} == {
        k: v for k, v in legacy.items() if k != "schema_version"
    }
    assert legacy["schema_version"] == "1.0.0"


def test_v1_to_v2_promotion_never_generates_uuid_for_legacy_ids() -> None:
    legacy = _admission_request(version="1.0.0", uuid_values=False)
    before = copy.deepcopy(legacy)

    with pytest.raises(admission.AdmissionError, match="ADMISSION_V2_MIGRATION_REQUIRED"):
        admission.promote_legacy_request_to_v2(legacy)

    assert legacy == before


def test_promotion_rejects_non_v1_source() -> None:
    canonical = _admission_request(version="2.0.0", uuid_values=True)
    with pytest.raises(
        admission.AdmissionError, match="ADMISSION_V2_MIGRATION_SOURCE_INVALID"
    ):
        admission.promote_legacy_request_to_v2(canonical)


def test_legacy_internal_gateway_v1_remains_structurally_compatible() -> None:
    request = _gateway_request(version="1.0.0", uuid_values=False)
    gateway.validate_request_structure(request)
    assert gateway.gateway_request_schema_version(request) == "1.0.0"


def test_internal_gateway_v2_accepts_uuid_correlation() -> None:
    request = _gateway_request(version="2.0.0", uuid_values=True)
    gateway.validate_request_structure(request)
    assert gateway.gateway_request_schema_version(request) == "2.0.0"


@pytest.mark.parametrize("field", ["campaign_id", "run_id", "step_id", "attempt_id"])
def test_internal_gateway_v2_rejects_each_non_uuid_correlation_field(field: str) -> None:
    request = _gateway_request(version="2.0.0", uuid_values=True)
    request[field] = f"{field}-legacy-value"
    if field == "campaign_id":
        request["roe_decision"]["campaign_id"] = f"{field}-legacy-value"
    with pytest.raises(gateway.GatewayValidationError, match="REQUEST_SCHEMA_INVALID"):
        gateway.validate_request_structure(request)


def test_unknown_internal_gateway_version_is_refused_explicitly() -> None:
    request = _gateway_request(version="9.0.0", uuid_values=True)
    with pytest.raises(gateway.GatewayValidationError, match="REQUEST_SCHEMA_UNSUPPORTED"):
        gateway.validate_request_structure(request)


def test_v2_schema_files_are_distinct_from_legacy_contracts() -> None:
    assert (GATEWAY_DIR / "admission-request.schema.json").exists()
    assert (GATEWAY_DIR / "admission-request-v2.schema.json").exists()
    assert (GATEWAY_DIR / "gateway-request.schema.json").exists()
    assert (GATEWAY_DIR / "gateway-request-v2.schema.json").exists()
