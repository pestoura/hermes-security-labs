from __future__ import annotations

import hashlib
import importlib.util
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
GATE_PATH = ROOT / "platform/gateway-protocol/deployment_gate.py"
REGISTRY_PATH = ROOT / "platform/gateway-protocol/operation-registry.yaml"
RUNTIME_PATH = ROOT / "platform/registry.yaml"

spec = importlib.util.spec_from_file_location("gateway_deployment_gate", GATE_PATH)
assert spec and spec.loader
gate = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = gate
spec.loader.exec_module(gate)


def _registry():
    return yaml.safe_load(REGISTRY_PATH.read_text(encoding="utf-8"))


def test_green_canonical_runtime_and_typed_registry_pass() -> None:
    runtime = RUNTIME_PATH.read_bytes()
    result = gate.evaluate_deployment_gate(
        canonical_runtime=runtime,
        observed_sha256=hashlib.sha256(runtime).hexdigest(),
        operation_registry=_registry(),
    )
    assert result.allowed is True
    assert result.codes == ("DEPLOYMENT_GATE_PASS",)


def test_runtime_drift_blocks_deployment_without_reconciliation() -> None:
    result = gate.evaluate_deployment_gate(
        canonical_runtime=b"canonical",
        observed_sha256="0" * 64,
        operation_registry=_registry(),
    )
    assert result.allowed is False
    assert "RUNTIME_DRIFT_DETECTED" in result.codes


def test_open_or_missing_operation_schema_blocks_deployment() -> None:
    registry = _registry()
    registry["operations"][0]["parameters_schema"]["additionalProperties"] = True
    result = gate.evaluate_deployment_gate(
        canonical_runtime=b"canonical",
        observed_sha256=hashlib.sha256(b"canonical").hexdigest(),
        operation_registry=registry,
    )
    assert result.allowed is False
    assert "OPERATION_SCHEMA_OPEN:system.health.read" in result.codes


def test_generic_execution_cannot_be_reintroduced_by_profile() -> None:
    registry = _registry()
    registry["profiles"]["normal"]["generic_execution"] = True
    result = gate.evaluate_deployment_gate(
        canonical_runtime=b"canonical",
        observed_sha256=hashlib.sha256(b"canonical").hexdigest(),
        operation_registry=registry,
    )
    assert result.allowed is False
    assert "PROFILE_GENERIC_EXECUTION_ENABLED:normal" in result.codes
