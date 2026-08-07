from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from typing import Any, Iterable, Mapping

KINDS = {"runbook", "lab", "runtime_image", "detection"}
REUSE = {"binding", "fixture", "variant", "new_content"}
LIFECYCLE = {"PROPOSED", "REVIEWED", "LAB_VALIDATED", "CANDIDATE", "STABLE", "QUARANTINED", "RETIRED"}
PROMOTABLE = {"REVIEWED", "LAB_VALIDATED", "CANDIDATE", "STABLE"}


class ContentFactoryError(ValueError):
    """Fail-closed continuous-content contract violation."""


def _digest(value: Mapping[str, Any]) -> str:
    raw = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()
    return hashlib.sha256(raw).hexdigest()


def incremental_events(*, previous: Iterable[str], current: Iterable[str]) -> list[dict[str, str]]:
    before = set(previous)
    after = set(current)
    events = [{"event": "added", "item": item} for item in sorted(after - before)]
    events.extend({"event": "removed", "item": item} for item in sorted(before - after))
    return events


def build_candidate(
    *,
    kind: str,
    source_events: Iterable[str],
    reuse_strategy: str,
    metrics: Mapping[str, Any],
    duplicate_of: str | None = None,
    learning_proposal: bool = False,
) -> dict[str, Any]:
    events = sorted(set(source_events))
    if kind not in KINDS or reuse_strategy not in REUSE or not events:
        raise ContentFactoryError("candidate requires supported kind, reuse strategy and source events")
    required_metrics = {
        "coverage_delta", "positive_control", "negative_control", "reproducibility",
        "false_positive_rate", "false_negative_rate", "cost_delta", "staleness_days",
    }
    if set(metrics) != required_metrics:
        raise ContentFactoryError("candidate metrics are incomplete")
    for bounded in ("reproducibility", "false_positive_rate", "false_negative_rate"):
        value = metrics[bounded]
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not 0.0 <= float(value) <= 1.0:
            raise ContentFactoryError(f"{bounded} must be between 0 and 1")
    if isinstance(metrics["staleness_days"], bool) or not isinstance(metrics["staleness_days"], int) or metrics["staleness_days"] < 0:
        raise ContentFactoryError("staleness_days must be a non-negative integer")
    seed = {"kind": kind, "source_events": events, "reuse_strategy": reuse_strategy, "metrics": dict(metrics), "duplicate_of": duplicate_of}
    return {
        "schema_version": "1.0",
        "candidate_id": f"cc_{_digest(seed)[:32]}",
        "kind": kind,
        "source_events": events,
        "reuse_strategy": reuse_strategy,
        "lifecycle": "PROPOSED",
        "human_reviewed": False,
        "auto_merge": False,
        "learning_proposal": learning_proposal,
        "duplicate_of": duplicate_of,
        "metrics": deepcopy(dict(metrics)),
    }


def promotion_failures(candidate: Mapping[str, Any], *, target: str, max_cost_delta: float = 100.0, max_staleness_days: int = 30) -> list[str]:
    if target not in LIFECYCLE:
        raise ContentFactoryError("unsupported lifecycle target")
    failures: list[str] = []
    metrics = candidate.get("metrics")
    if not isinstance(metrics, Mapping):
        return ["metrics"]
    if candidate.get("duplicate_of"):
        failures.append("duplicate")
    if target in PROMOTABLE and candidate.get("human_reviewed") is not True:
        failures.append("human_review")
    if target in {"CANDIDATE", "STABLE"}:
        if metrics.get("positive_control") is not True:
            failures.append("positive_control")
        if metrics.get("negative_control") is not True:
            failures.append("negative_control")
    if target == "STABLE":
        if metrics.get("coverage_delta", -1) < 0:
            failures.append("coverage_regression")
        if metrics.get("reproducibility", 0.0) < 0.95:
            failures.append("reproducibility")
        if metrics.get("false_positive_rate", 1.0) > 0.05:
            failures.append("false_positive_rate")
        if metrics.get("false_negative_rate", 1.0) > 0.05:
            failures.append("false_negative_rate")
        if metrics.get("cost_delta", max_cost_delta + 1) > max_cost_delta:
            failures.append("cost")
        if metrics.get("staleness_days", max_staleness_days + 1) > max_staleness_days:
            failures.append("staleness")
    return sorted(set(failures))


def record_human_review(candidate: Mapping[str, Any], *, reviewer: str) -> dict[str, Any]:
    if not reviewer:
        raise ContentFactoryError("reviewer is required")
    value = deepcopy(dict(candidate))
    value["human_reviewed"] = True
    value["reviewed_by"] = reviewer
    if value.get("lifecycle") == "PROPOSED":
        value["lifecycle"] = "REVIEWED"
    return value


def promote(candidate: Mapping[str, Any], *, target: str) -> dict[str, Any]:
    failures = promotion_failures(candidate, target=target)
    if failures:
        raise ContentFactoryError("promotion gates failed: " + ",".join(failures))
    value = deepcopy(dict(candidate))
    value["lifecycle"] = target
    value["auto_merge"] = False
    return value


def quarantine(candidate: Mapping[str, Any], *, reason: str) -> dict[str, Any]:
    if not reason:
        raise ContentFactoryError("quarantine reason is required")
    value = deepcopy(dict(candidate))
    value["lifecycle"] = "QUARANTINED"
    value["quarantine_reason"] = reason
    value["auto_merge"] = False
    return value


def retire(candidate: Mapping[str, Any], *, reason: str) -> dict[str, Any]:
    if not reason:
        raise ContentFactoryError("retirement reason is required")
    value = deepcopy(dict(candidate))
    value["lifecycle"] = "RETIRED"
    value["retirement_reason"] = reason
    value["auto_merge"] = False
    return value
