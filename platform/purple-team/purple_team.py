from __future__ import annotations

from copy import deepcopy
from typing import Any, Mapping

OUTCOME_STATES = {"PREVENTED", "DETECTED", "OBSERVED_NOT_DETECTED", "DETECTED_NOT_ACTIONABLE", "NOT_OBSERVED"}
DETECTION_STATES = {"DETECTED", "DETECTED_NOT_ACTIONABLE"}
EVIDENCE_STATES = {"PREVENTED", "DETECTED", "DETECTED_NOT_ACTIONABLE"}
FORBIDDEN_EXERCISE_FIELDS = {"command", "argv", "shell", "payload", "credential", "secret", "token"}


class PurpleTeamError(ValueError):
    """Fail-closed purple-team outcome contract violation."""


def record_outcome(
    *,
    step_id: str,
    state: str,
    observed: bool,
    evidence_ids: list[str],
    d3fend_refs: list[str] | None = None,
    time_to_detect_seconds: float | None = None,
    time_to_contain_seconds: float | None = None,
) -> dict[str, Any]:
    if not step_id or state not in OUTCOME_STATES:
        raise PurpleTeamError("step and supported outcome state are required")
    if state == "NOT_OBSERVED" and observed is not False:
        raise PurpleTeamError("NOT_OBSERVED requires observed=false")
    if observed is False and state != "NOT_OBSERVED":
        raise PurpleTeamError("absence of observation cannot imply prevention or detection")
    if state in EVIDENCE_STATES and not evidence_ids:
        raise PurpleTeamError("prevention and detection outcomes require evidence")
    if state in DETECTION_STATES and time_to_detect_seconds is None:
        raise PurpleTeamError("detected outcomes require time-to-detect")
    for value in (time_to_detect_seconds, time_to_contain_seconds):
        if value is not None and (isinstance(value, bool) or not isinstance(value, (int, float)) or value < 0):
            raise PurpleTeamError("time metrics must be non-negative numbers")
    return {
        "schema_version": "1.0",
        "step_id": step_id,
        "state": state,
        "observed": observed,
        "evidence_ids": sorted(set(evidence_ids)),
        "d3fend_refs": sorted(set(d3fend_refs or [])),
        "time_to_detect_seconds": None if time_to_detect_seconds is None else float(time_to_detect_seconds),
        "time_to_contain_seconds": None if time_to_contain_seconds is None else float(time_to_contain_seconds),
    }


def build_resilience_exercise(
    *,
    critical_function: str,
    injects: list[Mapping[str, Any]],
    recovery_criteria: list[str],
    lessons_learned: list[str] | None = None,
) -> dict[str, Any]:
    if not critical_function or not injects or not recovery_criteria:
        raise PurpleTeamError("exercise requires critical function, injects and recovery criteria")
    normalized: list[dict[str, Any]] = []
    for inject in injects:
        if FORBIDDEN_EXERCISE_FIELDS.intersection(inject):
            raise PurpleTeamError("exercise injects cannot contain execution or secret material")
        if not inject.get("scenario") or not inject.get("expected_response"):
            raise PurpleTeamError("inject requires scenario and expected response")
        normalized.append(deepcopy(dict(inject)))
    return {
        "critical_function": critical_function,
        "injects": normalized,
        "recovery_criteria": list(recovery_criteria),
        "lessons_learned": list(lessons_learned or []),
        "state": "EXERCISE_PLAN_ONLY",
        "executable": False,
        "authorization_source": "CONTROL_PLANE_ONLY",
    }
