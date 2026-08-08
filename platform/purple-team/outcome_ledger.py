"""One-outcome-per-emulation-step ledger for SVP2-F-02."""
from __future__ import annotations

from copy import deepcopy
from typing import Any, Iterable, Mapping

OUTCOME_STATES = {
    "PREVENTED",
    "DETECTED",
    "OBSERVED_NOT_DETECTED",
    "DETECTED_NOT_ACTIONABLE",
    "NOT_OBSERVED",
}


class OutcomeLedgerError(ValueError):
    pass


class OutcomeLedger:
    def __init__(self, expected_step_ids: Iterable[str]) -> None:
        expected = tuple(expected_step_ids)
        if not expected or any(not isinstance(step, str) or not step for step in expected):
            raise OutcomeLedgerError("EXPECTED_STEPS_REQUIRED")
        if len(set(expected)) != len(expected):
            raise OutcomeLedgerError("EXPECTED_STEPS_MUST_BE_UNIQUE")
        self._expected = expected
        self._outcomes: dict[str, dict[str, Any]] = {}

    def record(self, outcome: Mapping[str, Any]) -> None:
        step_id = outcome.get("step_id")
        state = outcome.get("state")
        if step_id not in self._expected:
            raise OutcomeLedgerError("UNPLANNED_EMULATION_STEP")
        if state not in OUTCOME_STATES:
            raise OutcomeLedgerError("OUTCOME_STATE_INVALID")
        if step_id in self._outcomes:
            raise OutcomeLedgerError("DUPLICATE_STEP_OUTCOME")
        if state == "NOT_OBSERVED" and outcome.get("observed") is not False:
            raise OutcomeLedgerError("NOT_OBSERVED_REQUIRES_OBSERVED_FALSE")
        if outcome.get("observed") is False and state != "NOT_OBSERVED":
            raise OutcomeLedgerError("ABSENCE_OF_OBSERVATION_CANNOT_BE_PREVENTION")
        self._outcomes[str(step_id)] = deepcopy(dict(outcome))

    def finalize(self) -> dict[str, Any]:
        missing = [step for step in self._expected if step not in self._outcomes]
        if missing:
            raise OutcomeLedgerError(f"MISSING_STEP_OUTCOMES:{','.join(missing)}")
        ordered = [deepcopy(self._outcomes[step]) for step in self._expected]
        return {
            "schema_version": "1.0",
            "expected_step_count": len(self._expected),
            "recorded_step_count": len(ordered),
            "complete": True,
            "outcomes": ordered,
        }
