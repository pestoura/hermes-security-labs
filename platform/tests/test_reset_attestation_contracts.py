"""Deterministic repository-only contracts for reset attestation, known-state proof,
zero-residue invariants, fail-closed partial/ambiguous reset and replay/tamper checks.

Repository-only. No Docker, target, network, systemd, trust, signer or provider is
invoked. All fixtures are sanitized state snapshots and stable policy booleans.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
PATH = ROOT / "platform/lab-registry-v2/reset_attestation_contracts.py"
spec = importlib.util.spec_from_file_location("reset_attestation_contracts", PATH)
assert spec and spec.loader
contracts = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = contracts
spec.loader.exec_module(contracts)


def _state(*, users: int = 1) -> dict:
    return {
        "services": {"app": "ready", "database": "ready"},
        "fixtures": {"users": users, "orders": 3},
        "network": {"egress": "deny", "connections": 0},
    }


def _record(*, attempt_id: str = "reset-1", users: int = 1, residue: bool = False) -> dict:
    return {
        "reset_attempt_id": attempt_id,
        "lifecycle_before": {"lifecycle": "RUNNING"},
        "lifecycle_after": _state(users=users),
        "observed_at": "2026-08-08T22:00:00Z",
        "network_present": bool(residue),
        "volume_present": False,
        "residue_resources": ["orphan-volume"] if residue else [],
    }


def test_convergent_reset_with_zero_residue_is_verified() -> None:
    first = _record(attempt_id="reset-a")
    second = _record(attempt_id="reset-b")
    result = contracts.contract_reset_attestation([first, second])

    assert result.deterministic is True
    assert result.residue_clear is True
    assert result.total_executions == 2
    assert result.definitive_executions == 2
    assert result.codes == (
        "RESET_STATE_IDENTICAL",
        "ZERO_RESIDUE_VERIFIED",
        "RESET_ENVELOPE_CONVERGED",
    )
    assert result.verified_attestation_sha256 == result.canonical_sha256
    report = contracts.render_reset_contract_report(result)
    assert report["production_lab_runtime"] == "NOT_RUN"
    assert report["codes"] == list(result.codes)


def test_residue_present_fails_closed_to_non_convergent_envelope() -> None:
    first = _record(attempt_id="reset-a")
    second = _record(attempt_id="reset-b", residue=True)
    result = contracts.contract_reset_attestation([first, second])

    assert result.deterministic is True
    assert result.residue_clear is False
    assert result.definitive_executions == 1
    assert result.codes == ("RESET_STATE_IDENTICAL", "RESIDUE_PRESENT")
    assert result.verified_attestation_sha256 is None


def test_divergent_post_reset_state_fails_closed() -> None:
    first = _record(attempt_id="reset-a", users=1)
    second = _record(attempt_id="reset-b", users=2)
    result = contracts.contract_reset_attestation([first, second])

    assert result.deterministic is False
    assert result.residue_clear is True
    assert result.codes == ("RESET_STATE_DIVERGED", "ZERO_RESIDUE_VERIFIED")
    assert result.verified_attestation_sha256 is None


def test_single_execution_cannot_claim_reset_contract() -> None:
    with pytest.raises(contracts.ResetContractError, match="AT_LEAST_TWO_RESET_EXECUTIONS_REQUIRED"):
        contracts.contract_reset_attestation([_record()])


@pytest.mark.parametrize("field", list(contracts.FORBIDDEN_RECORD_FIELDS))
def test_forbidden_record_field_is_rejected(field: str) -> None:
    record = _record()
    record[field] = "synthetic"
    with pytest.raises(contracts.ResetContractError, match="FORBIDDEN_RECORD_FIELD"):
        contracts.contract_reset_attestation([record, _record(attempt_id="reset-b")])


def test_duplicate_attempt_id_is_rejected() -> None:
    record = _record(attempt_id="same-id")
    with pytest.raises(contracts.ResetContractError, match="DUPLICATE_RESET_ATTEMPT_ID"):
        contracts.contract_reset_attestation([record, record])


def test_missing_required_record_field_is_rejected() -> None:
    record = _record()
    del record["network_present"]
    with pytest.raises(contracts.ResetContractError, match="RESET_RECORD_MISSING_FIELDS"):
        contracts.contract_reset_attestation([record, _record(attempt_id="reset-b")])


def test_non_boolean_residue_presence_is_rejected() -> None:
    record = _record()
    record["network_present"] = "yes"
    with pytest.raises(contracts.ResetContractError, match="RESET_RECORD_BAD_NETWORK_PRESENT"):
        contracts.contract_reset_attestation([record, _record(attempt_id="reset-b")])


def test_post_reset_state_with_forbidden_field_is_rejected() -> None:
    record = _record()
    record["lifecycle_after"]["runtime"] = {"secret": "x"}
    with pytest.raises(contracts.ResetContractError, match="ATTESTATION_FORBIDDEN_STATE_FIELD"):
        contracts.contract_reset_attestation([record, _record(attempt_id="reset-b")])


def test_known_state_proof_reproduces_expected_digest() -> None:
    expected = contracts.canonical_state_sha256(_state())
    integrity = contracts.known_state_proof(
        expected_sha256=expected,
        observed_states=[_state(), _state(users=1)],
    )
    assert integrity.tamper_detected is False
    assert integrity.codes == ("KNOWN_STATE_REPRODUCED",)
    report = contracts.render_replay_report(integrity)
    assert report["tamper_detected"] is False
    assert report["production_lab_runtime"] == "NOT_RUN"


def test_known_state_proof_detects_drift() -> None:
    expected = contracts.canonical_state_sha256(_state(users=1))
    integrity = contracts.known_state_proof(
        expected_sha256=expected,
        observed_states=[_state(users=1), _state(users=2)],
    )
    assert integrity.tamper_detected is True
    assert integrity.codes == ("KNOWN_STATE_DRIFT",)


def test_replay_integrity_detects_tampered_replay() -> None:
    expected = contracts.canonical_state_sha256(_state(users=1))
    integrity = contracts.replay_integrity_check(
        expected_sha256=expected,
        replayed_records=[_record(attempt_id="reset-a"), _record(attempt_id="reset-b")],
        tamper_seed=_state(users=99),
    )
    assert integrity.tamper_detected is True
    assert integrity.codes == ("KNOWN_STATE_DRIFT",)


def test_replay_integrity_clean_replay_passes() -> None:
    expected = contracts.canonical_state_sha256(_state(users=1))
    integrity = contracts.replay_integrity_check(
        expected_sha256=expected,
        replayed_records=[_record(attempt_id="reset-a"), _record(attempt_id="reset-b")],
    )
    assert integrity.tamper_detected is False


def test_replay_with_no_records_fails_closed() -> None:
    expected = contracts.canonical_state_sha256(_state())
    with pytest.raises(contracts.ResetContractError, match="REPLAY_REQUIRES_RECORDS"):
        contracts.replay_integrity_check(expected_sha256=expected, replayed_records=[])


def test_attestation_tamper_replay_check_rejects_mismatch() -> None:
    expected = "a" * 64
    integrity = contracts.verify_reset_attestation_not_tampered(
        evidence_sha256="b" * 64,
        expected_sha256=expected,
    )
    assert integrity.tamper_detected is True
    assert integrity.codes == ("ATTESTATION_TAMPER_DETECTED",)


def test_attestation_tamper_replay_check_accepts_match() -> None:
    expected = "a" * 64
    integrity = contracts.verify_reset_attestation_not_tampered(
        evidence_sha256="a" * 64,
        expected_sha256=expected,
    )
    assert integrity.tamper_detected is False
    assert integrity.codes == ("ATTESTATION_INTACT",)


def test_bad_sha256_length_fails_closed() -> None:
    with pytest.raises(contracts.ResetContractError, match="KNOWN_STATE_BAD_EXPECTED_SHA256"):
        contracts.known_state_proof(expected_sha256="deadbeef", observed_states=[_state()])
    with pytest.raises(contracts.ResetContractError, match="REPLAY_BAD_EXPECTED_SHA256"):
        contracts.replay_integrity_check(expected_sha256="x", replayed_records=[_record()])
    with pytest.raises(contracts.ResetContractError, match="ATTESTATION_BAD_EVIDENCE_SHA256"):
        contracts.verify_reset_attestation_not_tampered(evidence_sha256="x", expected_sha256="a" * 64)
