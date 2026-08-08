from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
PATH = ROOT / "platform/assurance/failure_evidence.py"
spec = importlib.util.spec_from_file_location("failure_evidence", PATH)
assert spec and spec.loader
module = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = module
spec.loader.exec_module(module)


def _suite() -> dict:
    return {
        name: {
            "status": "pass",
            "evidence_id": f"ev_failure_{index:02d}",
            "observed_at": "2026-08-08T22:00:00Z",
        }
        for index, name in enumerate(sorted(module.FAILURE_CASES))
    }


def test_complete_failure_suite_returns_stable_evidence_digest() -> None:
    first = module.validate_failure_evidence(_suite())
    second = module.validate_failure_evidence(dict(reversed(list(_suite().items()))))
    assert first == second
    assert len(first) == 64


def test_missing_case_cannot_support_maturity_promotion() -> None:
    suite = _suite()
    suite.pop("disk_full")
    with pytest.raises(module.FailureEvidenceError, match="MISSING_FAILURE_CASES"):
        module.validate_failure_evidence(suite)


def test_pass_without_evidence_reference_is_rejected() -> None:
    suite = _suite()
    suite["timeout"].pop("evidence_id")
    with pytest.raises(module.FailureEvidenceError, match="FAILURE_EVIDENCE_ID_INVALID:timeout"):
        module.validate_failure_evidence(suite)


def test_same_evidence_cannot_be_reused_for_multiple_failure_cases() -> None:
    suite = _suite()
    suite["restart"]["evidence_id"] = suite["timeout"]["evidence_id"]
    with pytest.raises(module.FailureEvidenceError, match="FAILURE_EVIDENCE_REUSE_DETECTED"):
        module.validate_failure_evidence(suite)


def test_non_passing_failure_case_fails_closed() -> None:
    suite = _suite()
    suite["network_loss"]["status"] = "fail"
    with pytest.raises(module.FailureEvidenceError, match="FAILURE_CASE_NOT_PASSING:network_loss"):
        module.validate_failure_evidence(suite)
