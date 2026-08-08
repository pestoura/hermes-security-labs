"""Attack-path evidence classification and profile/plan binding for SVP2-F-01."""
from __future__ import annotations

from typing import Any, Iterable, Mapping


class ThreatGraphBindingError(ValueError):
    pass


def validate_plan_binding(*, profile: Mapping[str, Any], plan: Mapping[str, Any]) -> None:
    if plan.get("profile_id") != profile.get("profile_id"):
        raise ThreatGraphBindingError("PLAN_PROFILE_MISMATCH")
    if plan.get("critical_function") != profile.get("critical_function"):
        raise ThreatGraphBindingError("PLAN_CRITICAL_FUNCTION_MISMATCH")
    if profile.get("executable") is not False:
        raise ThreatGraphBindingError("PROFILE_MUST_BE_NON_EXECUTABLE")
    if plan.get("state") != "PLAN_ONLY" or plan.get("executable") is not False:
        raise ThreatGraphBindingError("PLAN_MUST_BE_NON_EXECUTABLE")
    if plan.get("authorization_source") != "CONTROL_PLANE_ONLY":
        raise ThreatGraphBindingError("CONTROL_PLANE_AUTHORITY_REQUIRED")


def classify_path(
    *,
    edges: Iterable[Mapping[str, Any]],
    path: list[str],
) -> dict[str, Any]:
    if len(path) < 2 or len(path) != len(set(path)):
        raise ThreatGraphBindingError("PATH_INVALID")
    edge_index = {(edge.get("from"), edge.get("to")): edge for edge in edges}
    evidence_ids: set[str] = set()
    hypothetical_segments: list[list[str]] = []
    for source, target in zip(path, path[1:]):
        edge = edge_index.get((source, target))
        if edge is None:
            raise ThreatGraphBindingError("PATH_EDGE_MISSING")
        state = edge.get("state")
        if state == "evidenced":
            ids = edge.get("evidence_ids")
            if not isinstance(ids, list) or not ids:
                raise ThreatGraphBindingError("EVIDENCED_EDGE_WITHOUT_EVIDENCE")
            evidence_ids.update(str(item) for item in ids)
        elif state == "hypothetical":
            if edge.get("evidence_ids"):
                raise ThreatGraphBindingError("HYPOTHETICAL_EDGE_CLAIMS_EVIDENCE")
            hypothetical_segments.append([source, target])
        else:
            raise ThreatGraphBindingError("EDGE_STATE_INVALID")
    return {
        "classification": "hypothetical" if hypothetical_segments else "evidenced",
        "evidence_ids": sorted(evidence_ids),
        "hypothetical_segments": hypothetical_segments,
    }
