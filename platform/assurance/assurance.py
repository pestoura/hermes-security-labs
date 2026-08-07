from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

FAILURE_CASES = {
    "restart",
    "invalid_json",
    "empty_stdout",
    "timeout",
    "network_loss",
    "disk_full",
    "partial_cleanup",
    "concurrency",
    "cancellation",
    "incompatible_version",
}
MATURITY_ORDER = ("M0", "M1", "M2", "M3", "M4", "M5")
REQUIREMENTS = {
    "M0": set(),
    "M1": {"happy_path", "readiness"},
    "M2": {"happy_path", "readiness", "failure_suite"},
    "M3": {"happy_path", "readiness", "failure_suite", "golden_lab", "golden_finding", "reproducibility"},
    "M4": {
        "happy_path", "readiness", "failure_suite", "golden_lab", "golden_finding",
        "reproducibility", "false_positive_rate", "false_negative_rate", "cleanup_score",
    },
    "M5": {
        "happy_path", "readiness", "failure_suite", "golden_lab", "golden_finding",
        "reproducibility", "false_positive_rate", "false_negative_rate", "cleanup_score",
        "production_observation", "retirement_readiness",
    },
}


class AssuranceError(ValueError):
    """Fail-closed assurance contract violation."""


@dataclass(frozen=True)
class Readiness:
    state: str
    observed_at: str
    ttl_seconds: int
    age_seconds: int

    def assert_ready(self) -> None:
        if self.state != "ready":
            raise AssuranceError("readiness is not ready")
        if self.ttl_seconds <= 0 or self.age_seconds < 0 or self.age_seconds > self.ttl_seconds:
            raise AssuranceError("readiness evidence is stale or invalid")


def assert_executable_step_ready(readiness: Readiness | None) -> None:
    if readiness is None:
        raise AssuranceError("readiness evidence is required before executable step")
    readiness.assert_ready()


def validate_failure_suite(results: Mapping[str, Any]) -> None:
    missing = FAILURE_CASES.difference(results)
    unknown = set(results).difference(FAILURE_CASES)
    if missing:
        raise AssuranceError(f"missing failure cases: {','.join(sorted(missing))}")
    if unknown:
        raise AssuranceError(f"unknown failure cases: {','.join(sorted(unknown))}")
    failed = [name for name, result in results.items() if result != "pass"]
    if failed:
        raise AssuranceError(f"failure evidence not passing: {','.join(sorted(failed))}")


def highest_maturity(evidence: Mapping[str, Any]) -> str:
    """Calculate maturity strictly from explicit evidence; missing evidence never promotes."""
    available = {name for name, value in evidence.items() if value is True}
    failure_results = evidence.get("failure_results")
    if isinstance(failure_results, Mapping):
        try:
            validate_failure_suite(failure_results)
        except AssuranceError:
            pass
        else:
            available.add("failure_suite")
    level = "M0"
    for candidate in MATURITY_ORDER[1:]:
        if REQUIREMENTS[candidate].issubset(available):
            level = candidate
        else:
            break
    return level


def assert_maturity_promotion(current: str, target: str, evidence: Mapping[str, Any]) -> None:
    if current not in MATURITY_ORDER or target not in MATURITY_ORDER:
        raise AssuranceError("unknown maturity level")
    if MATURITY_ORDER.index(target) <= MATURITY_ORDER.index(current):
        raise AssuranceError("promotion target must be higher than current")
    observed = highest_maturity(evidence)
    if MATURITY_ORDER.index(observed) < MATURITY_ORDER.index(target):
        raise AssuranceError(f"insufficient evidence for {target}; observed {observed}")


def validate_advertised_operation(operation: Mapping[str, Any]) -> None:
    if operation.get("advertised") is True and operation.get("effect") in {None, "none", "noop"}:
        raise AssuranceError("advertised operation cannot be a no-op")
    if operation.get("advertised") is True and operation.get("effect_evidence_required") is not True:
        raise AssuranceError("advertised operation requires effect evidence")


def trace_attributes(correlation: Mapping[str, str]) -> dict[str, str]:
    required = {"campaign_id", "run_id", "step_id", "attempt_id"}
    if set(correlation) != required or not all(correlation.values()):
        raise AssuranceError("complete correlation is required for trace attributes")
    return {f"hexor.{key}": value for key, value in sorted(correlation.items())}
