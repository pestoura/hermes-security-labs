from __future__ import annotations

import hashlib
import json
import re
from collections import Counter
from typing import Any, Mapping


class CrosswalkError(ValueError):
    """Fail-closed framework crosswalk or methodology contract violation."""


CANONICAL_PHASES = (
    "scope_authorize",
    "discover",
    "analyze",
    "validate",
    "assess_impact",
    "report",
    "remediate_retest",
)

AUTHORIZATION_MODES = {"CONTROL_PLANE_ONLY", "AUTHORIZED_EXECUTION", "NON_EXECUTION"}
RELATIONS = {"aligned_with", "supports", "informed_by", "overlaps"}
CONFIDENCE_BANDS = {
    "low": (0.30, 0.60),
    "medium": (0.60, 0.85),
    "high": (0.85, 1.0000001),
}
ALLOWED_DOMAINS = {"general", "web_application"}
FORBIDDEN_AUTHORITY_KEYS = {
    "authorization_ref",
    "execution_authorized",
    "execution_allowed",
    "grant_authorization",
    "approved_for_execution",
}
FORBIDDEN_CLAIM_WORDS = {"certified", "compliant", "compliance"}


def _canonical_json(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()


def _walk_keys(value: Any) -> set[str]:
    keys: set[str] = set()
    if isinstance(value, Mapping):
        for key, item in value.items():
            keys.add(str(key))
            keys.update(_walk_keys(item))
    elif isinstance(value, list):
        for item in value:
            keys.update(_walk_keys(item))
    return keys


def _words(value: str) -> set[str]:
    return set(re.findall(r"[a-z]+", value.lower()))


def validate_methodology(methodology: Mapping[str, Any]) -> dict[str, Any]:
    if methodology.get("schema_version") != "1.0":
        raise CrosswalkError("unsupported methodology schema version")
    if methodology.get("methodology_id") != "svp2-security-validation-methodology":
        raise CrosswalkError("unexpected methodology id")
    version = methodology.get("methodology_version")
    if not isinstance(version, str) or not version:
        raise CrosswalkError("methodology version is required")
    if methodology.get("status") != "candidate":
        raise CrosswalkError("only candidate methodology status is supported")

    phases = methodology.get("phases")
    if not isinstance(phases, list) or len(phases) != len(CANONICAL_PHASES):
        raise CrosswalkError("canonical methodology requires exactly seven phases")

    phase_ids = [phase.get("phase_id") for phase in phases if isinstance(phase, Mapping)]
    if tuple(phase_ids) != CANONICAL_PHASES:
        raise CrosswalkError("canonical methodology phase order is fixed")
    if [phase.get("order") for phase in phases] != list(range(1, len(CANONICAL_PHASES) + 1)):
        raise CrosswalkError("methodology phase order must be contiguous")

    known = set(CANONICAL_PHASES)
    for phase in phases:
        if not isinstance(phase, Mapping):
            raise CrosswalkError("phase must be an object")
        mode = phase.get("authorization_mode")
        execution_possible = phase.get("execution_possible")
        if mode not in AUTHORIZATION_MODES:
            raise CrosswalkError("unsupported authorization mode")
        if not isinstance(execution_possible, bool):
            raise CrosswalkError("execution_possible must be boolean")
        if execution_possible and mode != "AUTHORIZED_EXECUTION":
            raise CrosswalkError("execution-capable phases require AUTHORIZED_EXECUTION mode")
        if not execution_possible and mode == "AUTHORIZED_EXECUTION":
            raise CrosswalkError("AUTHORIZED_EXECUTION mode requires an execution-capable phase")
        required_inputs = phase.get("required_inputs")
        exit_evidence = phase.get("exit_evidence")
        allowed_next = phase.get("allowed_next")
        if not isinstance(required_inputs, list) or not required_inputs:
            raise CrosswalkError("each phase requires explicit inputs")
        if not isinstance(exit_evidence, list) or not exit_evidence:
            raise CrosswalkError("each phase requires explicit exit evidence")
        if not isinstance(allowed_next, list):
            raise CrosswalkError("allowed_next must be a list")
        if set(allowed_next).difference(known):
            raise CrosswalkError("allowed_next references an unknown phase")
        if execution_possible and "active_authorization" not in required_inputs:
            raise CrosswalkError("execution-capable phases require active_authorization input")
        if not phase.get("purpose") or not phase.get("title"):
            raise CrosswalkError("each phase requires title and purpose")

    scope = phases[0]
    if scope.get("authorization_mode") != "CONTROL_PLANE_ONLY" or scope.get("execution_possible"):
        raise CrosswalkError("scope_authorize is control-plane only and non-executable")

    runtime_status = methodology.get("runtime_status")
    expected_runtime = {
        "external_framework_sync": "NOT_RUN",
        "planner_integration": "NOT_IMPLEMENTED",
        "reporting_integration": "NOT_IMPLEMENTED",
        "execution_authority": "CONTROL_PLANE_ONLY",
    }
    if runtime_status != expected_runtime:
        raise CrosswalkError("methodology runtime non-claims changed")

    return dict(methodology)


def _confidence_matches(label: str, score: Any) -> bool:
    if label not in CONFIDENCE_BANDS or isinstance(score, bool) or not isinstance(score, (int, float)):
        return False
    low, high = CONFIDENCE_BANDS[label]
    return low <= float(score) < high


def validate_crosswalk(
    dataset: Mapping[str, Any],
    methodology: Mapping[str, Any],
) -> dict[str, Any]:
    validated_methodology = validate_methodology(methodology)
    if dataset.get("schema_version") != "1.0":
        raise CrosswalkError("unsupported crosswalk schema version")
    if dataset.get("dataset_id") != "svp2-framework-crosswalk":
        raise CrosswalkError("unexpected crosswalk dataset id")
    if not dataset.get("dataset_version"):
        raise CrosswalkError("dataset version is required")

    expected_ref = (
        f"{validated_methodology['methodology_id']}@"
        f"{validated_methodology['methodology_version']}"
    )
    if dataset.get("methodology_ref") != expected_ref:
        raise CrosswalkError("crosswalk methodology reference is not pinned")

    frameworks = dataset.get("frameworks")
    if not isinstance(frameworks, list) or len(frameworks) < 2:
        raise CrosswalkError("at least two framework baselines are required")
    framework_by_id: dict[str, Mapping[str, Any]] = {}
    for framework in frameworks:
        if not isinstance(framework, Mapping):
            raise CrosswalkError("framework registry entry must be an object")
        framework_id = framework.get("framework_id")
        if not isinstance(framework_id, str) or not framework_id or framework_id in framework_by_id:
            raise CrosswalkError("framework ids must be unique and non-empty")
        if not framework.get("framework_version") or not framework.get("source_locator"):
            raise CrosswalkError("framework version and source locator are required")
        if not str(framework["source_locator"]).startswith("https://"):
            raise CrosswalkError("framework source locator must use https")
        if framework.get("source_status") != "manually_reviewed":
            raise CrosswalkError("framework source must be explicitly manually reviewed")
        framework_by_id[framework_id] = framework

    mappings = dataset.get("mappings")
    if not isinstance(mappings, list) or not mappings:
        raise CrosswalkError("crosswalk mappings are required")
    seen_mapping_ids: set[str] = set()
    valid_phases = set(CANONICAL_PHASES)
    for mapping in mappings:
        if not isinstance(mapping, Mapping):
            raise CrosswalkError("mapping must be an object")
        mapping_id = mapping.get("mapping_id")
        if not isinstance(mapping_id, str) or not mapping_id or mapping_id in seen_mapping_ids:
            raise CrosswalkError("mapping ids must be unique and non-empty")
        seen_mapping_ids.add(mapping_id)
        if mapping.get("phase_id") not in valid_phases:
            raise CrosswalkError("mapping references unknown methodology phase")
        if mapping.get("framework_id") not in framework_by_id:
            raise CrosswalkError("mapping references unknown framework")
        if mapping.get("relation") not in RELATIONS:
            raise CrosswalkError("unsupported mapping relation")
        if mapping.get("advisory_only") is not True:
            raise CrosswalkError("framework mappings are advisory only")
        if not _confidence_matches(str(mapping.get("confidence")), mapping.get("confidence_score")):
            raise CrosswalkError("confidence label and score are inconsistent")
        domains = mapping.get("applicability", {}).get("domains") if isinstance(mapping.get("applicability"), Mapping) else None
        if not isinstance(domains, list) or not domains or set(domains).difference(ALLOWED_DOMAINS):
            raise CrosswalkError("mapping applicability domains are invalid")
        if not mapping.get("target_ref") or not mapping.get("target_label") or not mapping.get("rationale"):
            raise CrosswalkError("mapping target and rationale are required")
        words = _words(f"{mapping['target_label']} {mapping['rationale']}")
        if words.intersection(FORBIDDEN_CLAIM_WORDS):
            raise CrosswalkError("mapping may not make certification or compliance claims")

    forbidden_keys = _walk_keys(dataset).intersection(FORBIDDEN_AUTHORITY_KEYS)
    if forbidden_keys:
        raise CrosswalkError("crosswalk data may not carry execution authority fields")

    expected_runtime = {
        "authoritative_external_sync": "NOT_RUN",
        "automatic_framework_updates": "NOT_IMPLEMENTED",
        "planner_consumer_integration": "NOT_IMPLEMENTED",
        "reporting_consumer_integration": "NOT_IMPLEMENTED",
        "execution_effect": "NONE",
    }
    if dataset.get("runtime_status") != expected_runtime:
        raise CrosswalkError("crosswalk runtime non-claims changed")

    return dict(dataset)


def coverage_summary(
    dataset: Mapping[str, Any],
    methodology: Mapping[str, Any],
) -> dict[str, Any]:
    validated = validate_crosswalk(dataset, methodology)
    phase_set = set(CANONICAL_PHASES)
    frameworks = [framework["framework_id"] for framework in validated["frameworks"]]
    mappings = validated["mappings"]
    gaps: dict[str, list[str]] = {}
    coverage: dict[str, int] = {}
    for framework_id in sorted(frameworks):
        mapped = {mapping["phase_id"] for mapping in mappings if mapping["framework_id"] == framework_id}
        gaps[framework_id] = sorted(phase_set - mapped)
        coverage[framework_id] = len(mapped)
    confidence_counts = Counter(mapping["confidence"] for mapping in mappings)
    return {
        "methodology_ref": validated["methodology_ref"],
        "dataset_version": validated["dataset_version"],
        "phase_count": len(CANONICAL_PHASES),
        "framework_count": len(frameworks),
        "mapping_count": len(mappings),
        "mapped_phase_count_by_framework": coverage,
        "gaps_by_framework": gaps,
        "confidence_counts": {key: confidence_counts.get(key, 0) for key in ("high", "medium", "low")},
        "claim_semantics": "advisory_alignment_only",
    }


def snapshot_digest(dataset: Mapping[str, Any], methodology: Mapping[str, Any]) -> str:
    validated_dataset = validate_crosswalk(dataset, methodology)
    validated_methodology = validate_methodology(methodology)
    normalized_dataset = dict(validated_dataset)
    normalized_dataset["frameworks"] = sorted(
        [dict(item) for item in validated_dataset["frameworks"]],
        key=lambda item: item["framework_id"],
    )
    normalized_dataset["mappings"] = sorted(
        [dict(item) for item in validated_dataset["mappings"]],
        key=lambda item: item["mapping_id"],
    )
    payload = {"methodology": validated_methodology, "crosswalk": normalized_dataset}
    return hashlib.sha256(_canonical_json(payload)).hexdigest()
