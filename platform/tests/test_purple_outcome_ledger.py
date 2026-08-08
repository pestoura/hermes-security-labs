from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
PATH = ROOT / "platform/purple-team/outcome_ledger.py"
spec = importlib.util.spec_from_file_location("purple_outcome_ledger", PATH)
assert spec and spec.loader
module = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = module
spec.loader.exec_module(module)


def test_each_emulation_step_has_exactly_one_explicit_outcome() -> None:
    ledger = module.OutcomeLedger(["step-1", "step-2"])
    ledger.record({"step_id": "step-1", "state": "DETECTED", "observed": True})
    ledger.record({"step_id": "step-2", "state": "NOT_OBSERVED", "observed": False})
    result = ledger.finalize()
    assert result["complete"] is True
    assert result["expected_step_count"] == result["recorded_step_count"] == 2


def test_duplicate_outcome_for_same_step_is_rejected() -> None:
    ledger = module.OutcomeLedger(["step-1"])
    ledger.record({"step_id": "step-1", "state": "DETECTED", "observed": True})
    with pytest.raises(module.OutcomeLedgerError, match="DUPLICATE_STEP_OUTCOME"):
        ledger.record({"step_id": "step-1", "state": "PREVENTED", "observed": True})


def test_missing_step_outcome_blocks_finalization() -> None:
    ledger = module.OutcomeLedger(["step-1", "step-2"])
    ledger.record({"step_id": "step-1", "state": "DETECTED", "observed": True})
    with pytest.raises(module.OutcomeLedgerError, match="MISSING_STEP_OUTCOMES:step-2"):
        ledger.finalize()


def test_unobserved_step_cannot_be_recorded_as_prevented() -> None:
    ledger = module.OutcomeLedger(["step-1"])
    with pytest.raises(module.OutcomeLedgerError, match="ABSENCE_OF_OBSERVATION_CANNOT_BE_PREVENTION"):
        ledger.record({"step_id": "step-1", "state": "PREVENTED", "observed": False})


def test_unplanned_step_cannot_enter_ledger() -> None:
    ledger = module.OutcomeLedger(["step-1"])
    with pytest.raises(module.OutcomeLedgerError, match="UNPLANNED_EMULATION_STEP"):
        ledger.record({"step_id": "step-2", "state": "DETECTED", "observed": True})
