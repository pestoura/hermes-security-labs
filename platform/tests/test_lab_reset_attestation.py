from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
PATH = ROOT / "platform/lab-registry-v2/reset_attestation.py"
spec = importlib.util.spec_from_file_location("lab_reset_attestation", PATH)
assert spec and spec.loader
attestation = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = attestation
spec.loader.exec_module(attestation)


def _state(*, users: int = 1) -> dict:
    return {
        "services": {"app": "ready", "database": "ready"},
        "fixtures": {"users": users, "orders": 3},
        "network": {"egress": "deny", "connections": 0},
    }


def test_equivalent_states_with_different_key_order_are_identical() -> None:
    first = _state()
    second = {
        "network": {"connections": 0, "egress": "deny"},
        "fixtures": {"orders": 3, "users": 1},
        "services": {"database": "ready", "app": "ready"},
    }
    result = attestation.attest_reset_determinism([first, second])
    assert result.deterministic is True
    assert result.codes == ("RESET_STATE_IDENTICAL",)
    assert result.execution_count == 2


def test_post_reset_drift_is_detected() -> None:
    result = attestation.attest_reset_determinism([_state(users=1), _state(users=2)])
    assert result.deterministic is False
    assert result.codes == ("RESET_STATE_DIVERGED",)


def test_single_execution_cannot_claim_determinism() -> None:
    with pytest.raises(attestation.ResetAttestationError, match="AT_LEAST_TWO_RESET_EXECUTIONS_REQUIRED"):
        attestation.attest_reset_determinism([_state()])


@pytest.mark.parametrize("field", ["secret", "token", "password", "credential", "command", "argv", "host_path", "docker_socket"])
def test_sensitive_or_execution_shaped_state_is_rejected(field: str) -> None:
    value = _state()
    value["runtime"] = {field: "synthetic"}
    with pytest.raises(attestation.ResetAttestationError, match="FORBIDDEN_STATE_FIELD"):
        attestation.canonical_state_sha256(value)
