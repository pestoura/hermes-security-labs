from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from typing import Any, Mapping

COMPONENTS = {
    "cvss4", "epss", "kev", "asset_criticality", "reachability", "attack_path_importance",
    "threat_relevance", "compensating_controls", "detectability", "remediation_cost",
}
STATES = {"OBSERVED", "VALIDATED", "TRIAGED", "ASSIGNED", "FIXED", "RETEST", "VERIFIED", "CLOSED", "ACCEPTED_RISK", "REGRESSED"}
ALLOWED_TRANSITIONS = {
    "OBSERVED": {"VALIDATED"},
    "VALIDATED": {"TRIAGED"},
    "TRIAGED": {"ASSIGNED", "ACCEPTED_RISK"},
    "ASSIGNED": {"FIXED", "ACCEPTED_RISK"},
    "FIXED": {"RETEST"},
    "RETEST": {"VERIFIED", "REGRESSED"},
    "VERIFIED": {"CLOSED", "REGRESSED"},
    "CLOSED": {"REGRESSED"},
    "ACCEPTED_RISK": {"ASSIGNED", "REGRESSED"},
    "REGRESSED": {"ASSIGNED"},
}


class RiskFindingError(ValueError):
    """Fail-closed risk/finding contract violation."""


def _digest(value: Mapping[str, Any]) -> str:
    raw = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()
    return hashlib.sha256(raw).hexdigest()


def build_risk_assessment(*, components: Mapping[str, Mapping[str, Any]], weights: Mapping[str, float]) -> dict[str, Any]:
    if set(components) != COMPONENTS or set(weights) != COMPONENTS:
        raise RiskFindingError("risk assessment requires the complete canonical component set")
    normalized: dict[str, dict[str, Any]] = {}
    for name, item in components.items():
        if not item.get("source"):
            raise RiskFindingError("every risk component requires a source")
        value = item.get("value")
        if name == "cvss4":
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not 0 <= float(value) <= 10:
                raise RiskFindingError("CVSS 4.0 must be between 0 and 10")
            normalized_value = float(value) / 10.0
        elif name == "kev":
            if not isinstance(value, bool):
                raise RiskFindingError("KEV must be boolean")
            normalized_value = 1.0 if value else 0.0
        else:
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not 0 <= float(value) <= 1:
                raise RiskFindingError(f"{name} must be normalized between 0 and 1")
            normalized_value = float(value)
        normalized[name] = {"value": deepcopy(value), "normalized": normalized_value, "source": item["source"]}
    if any(isinstance(weight, bool) or not isinstance(weight, (int, float)) or weight < 0 for weight in weights.values()):
        raise RiskFindingError("risk weights must be non-negative numbers")
    total_weight = float(sum(weights.values()))
    if abs(total_weight - 1.0) > 1e-9:
        raise RiskFindingError("risk weights must sum to 1.0")
    score = sum(normalized[name]["normalized"] * float(weights[name]) for name in COMPONENTS)
    return {"components": normalized, "weights": {name: float(weights[name]) for name in sorted(weights)}, "composite_score": round(score, 6), "auditable": True}


def create_finding(*, title: str, risk: Mapping[str, Any], root_cause: str, systemic: bool, evidence_before: list[str]) -> dict[str, Any]:
    if not title or not root_cause or not evidence_before:
        raise RiskFindingError("finding requires title, root cause and before evidence")
    seed = {"title": title, "root_cause": root_cause, "evidence_before": sorted(set(evidence_before))}
    return {
        "schema_version": "1.0",
        "finding_id": f"fd_{_digest(seed)[:32]}",
        "title": title,
        "state": "OBSERVED",
        "risk": deepcopy(dict(risk)),
        "root_cause": root_cause,
        "systemic": systemic,
        "evidence_before": sorted(set(evidence_before)),
        "evidence_after": [],
        "remediation_effectiveness": None,
        "history": [{"from": None, "to": "OBSERVED", "actor": "system"}],
        "reopened": False,
    }


def transition(finding: Mapping[str, Any], *, target: str, actor: str, evidence_after: list[str] | None = None, remediation_effectiveness: float | None = None) -> dict[str, Any]:
    current = finding.get("state")
    if current not in STATES or target not in ALLOWED_TRANSITIONS.get(current, set()) or not actor:
        raise RiskFindingError("finding transition is not allowed")
    value = deepcopy(dict(finding))
    if target in {"RETEST", "VERIFIED", "CLOSED"}:
        if not evidence_after:
            raise RiskFindingError("retest and closure states require after evidence")
        value["evidence_after"] = sorted(set(evidence_after))
    if remediation_effectiveness is not None:
        if isinstance(remediation_effectiveness, bool) or not isinstance(remediation_effectiveness, (int, float)) or not 0 <= float(remediation_effectiveness) <= 1:
            raise RiskFindingError("remediation effectiveness must be between 0 and 1")
        value["remediation_effectiveness"] = float(remediation_effectiveness)
    value["state"] = target
    value["history"] = list(value.get("history", [])) + [{"from": current, "to": target, "actor": actor}]
    return value


def record_regression(finding: Mapping[str, Any], *, actor: str, evidence_after: list[str]) -> dict[str, Any]:
    current = finding.get("state")
    if current not in {"RETEST", "VERIFIED", "CLOSED", "ACCEPTED_RISK"}:
        raise RiskFindingError("regression may only reopen an assessed finding")
    if not finding.get("evidence_before") or not evidence_after:
        raise RiskFindingError("regression requires comparable before and after evidence")
    value = deepcopy(dict(finding))
    value["state"] = "REGRESSED"
    value["evidence_after"] = sorted(set(evidence_after))
    value["reopened"] = True
    value["history"] = list(value.get("history", [])) + [{"from": current, "to": "REGRESSED", "actor": actor}]
    return value
