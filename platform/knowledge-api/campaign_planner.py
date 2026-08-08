from __future__ import annotations

import hashlib
import json
import re
from copy import deepcopy
from typing import Any, Mapping, Sequence


class CampaignPlannerError(ValueError):
    """Fail-closed campaign-planner contract violation."""


SNAPSHOT_ID_RE = re.compile(r"^ks_[a-f0-9]{32}$")
RECORD_ID_RE = re.compile(r"^kr_[a-f0-9]{32}$")
CONTEXT_ID_RE = re.compile(r"^kpc_[a-f0-9]{32}$")
CANDIDATE_ID_RE = re.compile(r"^kpcand_[a-f0-9]{32}$")
PLAN_ID_RE = re.compile(r"^kp_[a-f0-9]{32}$")
TECHNIQUE_ID_RE = re.compile(r"^T[0-9]{4}(?:\.[0-9]{3})?$")
CVE_ID_RE = re.compile(r"^CVE-[0-9]{4}-[0-9]{4,}$")
SAFE_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/-]{0,127}$")
SHA256_RE = re.compile(r"^[a-f0-9]{64}$")

INTRUSIVENESS = {"L0": 0, "L1": 1, "L2": 2, "L3": 3, "L4": 4}
MAX_ITEMS = 512
MAX_CANDIDATES = 2_000
MAX_RECORD_REFS = 64

FORBIDDEN_FIELDS = {
    "command", "argv", "shell", "cwd", "environment", "entrypoint",
    "payload", "parameters", "target", "credential", "secret", "token",
    "password", "cookie", "api_key", "authorization_receipt", "authorization_ref",
    "authorized", "execution_allowed", "execution_authorized", "roe_decision",
    "runner_request",
}

CONTEXT_FIELDS = {
    "schema_version", "context_id", "campaign_id", "knowledge_snapshot_id",
    "capability_registry_version", "roe_contract_id", "roe_contract_payload_sha256",
    "asset_ids", "threat_technique_ids", "vulnerability_ids", "allowed_capability_ids",
    "max_intrusiveness_level", "minimum_confidence", "constraint_effect",
    "authorization_effect", "execution_authority",
}
CANDIDATE_FIELDS = {
    "schema_version", "candidate_id", "operation_id", "capability_id",
    "intrusiveness_level", "asset_ids", "technique_ids", "vulnerability_ids",
    "knowledge_record_ids", "confidence", "rationale", "executable",
    "authorization_effect",
}
PLAN_FIELDS = {
    "schema_version", "plan_id", "campaign_id", "planning_context_id",
    "selected_steps", "excluded_candidates", "proposal_state", "executable",
    "planning_constraints_are_authorization", "authorization_effect",
    "requires_fresh_authorization", "execution_authority", "limitations",
}


def _digest(value: Any) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()
    return hashlib.sha256(encoded).hexdigest()


def _walk_keys(value: Any) -> set[str]:
    keys: set[str] = set()
    if isinstance(value, Mapping):
        for key, item in value.items():
            keys.add(str(key).lower())
            keys.update(_walk_keys(item))
    elif isinstance(value, list):
        for item in value:
            keys.update(_walk_keys(item))
    return keys


def _reject_forbidden_fields(value: Any, label: str) -> None:
    if _walk_keys(value).intersection(FORBIDDEN_FIELDS):
        raise CampaignPlannerError(
            f"{label} may not contain execution, target, secret or authorization fields"
        )


def _exact_fields(value: Mapping[str, Any], expected: set[str], label: str) -> None:
    actual = {str(key) for key in value}
    if actual != expected:
        raise CampaignPlannerError(
            f"{label} fields mismatch: missing={sorted(expected - actual)}, extra={sorted(actual - expected)}"
        )


def _safe_id(value: Any, label: str) -> str:
    if not isinstance(value, str) or not SAFE_ID_RE.fullmatch(value):
        raise CampaignPlannerError(f"invalid {label}")
    return value


def _bounded_unique_strings(
    values: Sequence[str], *, label: str, pattern: re.Pattern[str] | None = None,
    allow_empty: bool = True, limit: int = MAX_ITEMS,
) -> list[str]:
    if isinstance(values, (str, bytes)) or not isinstance(values, Sequence):
        raise CampaignPlannerError(f"{label} must be a bounded list")
    items = list(values)
    if len(items) > limit or (not allow_empty and not items):
        raise CampaignPlannerError(f"{label} must be a bounded list")
    if len(set(items)) != len(items):
        raise CampaignPlannerError(f"{label} must be unique")
    for item in items:
        if not isinstance(item, str) or not item or (pattern is not None and not pattern.fullmatch(item)):
            raise CampaignPlannerError(f"invalid {label} item")
    return sorted(items)


def _confidence(value: Any) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise CampaignPlannerError("confidence must be numeric")
    result = float(value)
    if not 0.0 <= result <= 1.0:
        raise CampaignPlannerError("confidence must be between 0 and 1")
    return result


def _context_seed(**values: Any) -> dict[str, Any]:
    return {
        "campaign_id": values["campaign_id"],
        "knowledge_snapshot_id": values["knowledge_snapshot_id"],
        "capability_registry_version": values["capability_registry_version"],
        "roe_contract_id": values["roe_contract_id"],
        "roe_contract_payload_sha256": values["roe_contract_payload_sha256"],
        "asset_ids": sorted(values["asset_ids"]),
        "threat_technique_ids": sorted(values["threat_technique_ids"]),
        "vulnerability_ids": sorted(values["vulnerability_ids"]),
        "allowed_capability_ids": sorted(values["allowed_capability_ids"]),
        "max_intrusiveness_level": values["max_intrusiveness_level"],
        "minimum_confidence": float(values["minimum_confidence"]),
    }


def build_planning_context(
    *, campaign_id: str, knowledge_snapshot_id: str, capability_registry_version: str,
    roe_contract_id: str, roe_contract_payload_sha256: str, asset_ids: Sequence[str],
    threat_technique_ids: Sequence[str], vulnerability_ids: Sequence[str],
    allowed_capability_ids: Sequence[str], max_intrusiveness_level: str,
    minimum_confidence: float,
) -> dict[str, Any]:
    campaign_id = _safe_id(campaign_id, "campaign id")
    if not isinstance(knowledge_snapshot_id, str) or not SNAPSHOT_ID_RE.fullmatch(knowledge_snapshot_id):
        raise CampaignPlannerError("invalid knowledge snapshot id")
    capability_registry_version = _safe_id(capability_registry_version, "capability registry version")
    roe_contract_id = _safe_id(roe_contract_id, "RoE contract id")
    if not isinstance(roe_contract_payload_sha256, str) or not SHA256_RE.fullmatch(roe_contract_payload_sha256):
        raise CampaignPlannerError("invalid RoE contract payload sha256")
    assets = _bounded_unique_strings(asset_ids, label="asset ids", allow_empty=False)
    techniques = _bounded_unique_strings(
        threat_technique_ids, label="threat technique ids", pattern=TECHNIQUE_ID_RE
    )
    vulnerabilities = _bounded_unique_strings(
        vulnerability_ids, label="vulnerability ids", pattern=CVE_ID_RE
    )
    capabilities = _bounded_unique_strings(
        allowed_capability_ids, label="allowed capability ids", allow_empty=False
    )
    for capability in capabilities:
        _safe_id(capability, "capability id")
    if max_intrusiveness_level not in INTRUSIVENESS:
        raise CampaignPlannerError("invalid planning intrusiveness ceiling")
    threshold = _confidence(minimum_confidence)
    seed = _context_seed(
        campaign_id=campaign_id,
        knowledge_snapshot_id=knowledge_snapshot_id,
        capability_registry_version=capability_registry_version,
        roe_contract_id=roe_contract_id,
        roe_contract_payload_sha256=roe_contract_payload_sha256,
        asset_ids=assets,
        threat_technique_ids=techniques,
        vulnerability_ids=vulnerabilities,
        allowed_capability_ids=capabilities,
        max_intrusiveness_level=max_intrusiveness_level,
        minimum_confidence=threshold,
    )
    return {
        "schema_version": "1.0",
        "context_id": f"kpc_{_digest(seed)[:32]}",
        **seed,
        "constraint_effect": "PLANNING_FILTER_ONLY",
        "authorization_effect": "NONE",
        "execution_authority": "CONTROL_PLANE_ONLY",
    }


def _validate_context(context: Mapping[str, Any]) -> dict[str, Any]:
    if not isinstance(context, Mapping):
        raise CampaignPlannerError("planning context must be an object")
    _reject_forbidden_fields(context, "planning context")
    _exact_fields(context, CONTEXT_FIELDS, "planning context")
    if context.get("schema_version") != "1.0":
        raise CampaignPlannerError("unsupported planning context schema")
    if context.get("constraint_effect") != "PLANNING_FILTER_ONLY":
        raise CampaignPlannerError("planning constraints cannot become authorization")
    if context.get("authorization_effect") != "NONE":
        raise CampaignPlannerError("planning context cannot grant authorization")
    if context.get("execution_authority") != "CONTROL_PLANE_ONLY":
        raise CampaignPlannerError("execution authority boundary changed")
    expected = build_planning_context(
        campaign_id=context["campaign_id"],
        knowledge_snapshot_id=context["knowledge_snapshot_id"],
        capability_registry_version=context["capability_registry_version"],
        roe_contract_id=context["roe_contract_id"],
        roe_contract_payload_sha256=context["roe_contract_payload_sha256"],
        asset_ids=context["asset_ids"],
        threat_technique_ids=context["threat_technique_ids"],
        vulnerability_ids=context["vulnerability_ids"],
        allowed_capability_ids=context["allowed_capability_ids"],
        max_intrusiveness_level=context["max_intrusiveness_level"],
        minimum_confidence=context["minimum_confidence"],
    )
    if context.get("context_id") != expected["context_id"]:
        raise CampaignPlannerError("planning context id does not match canonical content")
    return expected


def _candidate_seed(**values: Any) -> dict[str, Any]:
    return {
        "operation_id": values["operation_id"],
        "capability_id": values["capability_id"],
        "intrusiveness_level": values["intrusiveness_level"],
        "asset_ids": sorted(values["asset_ids"]),
        "technique_ids": sorted(values["technique_ids"]),
        "vulnerability_ids": sorted(values["vulnerability_ids"]),
        "knowledge_record_ids": sorted(values["knowledge_record_ids"]),
        "confidence": float(values["confidence"]),
        "rationale": values["rationale"].strip(),
    }


def build_candidate(
    *, operation_id: str, capability_id: str, intrusiveness_level: str,
    asset_ids: Sequence[str], technique_ids: Sequence[str], vulnerability_ids: Sequence[str],
    knowledge_record_ids: Sequence[str], confidence: float, rationale: str,
) -> dict[str, Any]:
    operation_id = _safe_id(operation_id, "operation id")
    capability_id = _safe_id(capability_id, "capability id")
    if intrusiveness_level not in INTRUSIVENESS:
        raise CampaignPlannerError("invalid candidate intrusiveness level")
    assets = _bounded_unique_strings(asset_ids, label="candidate asset ids", allow_empty=False)
    techniques = _bounded_unique_strings(
        technique_ids, label="candidate technique ids", pattern=TECHNIQUE_ID_RE
    )
    vulnerabilities = _bounded_unique_strings(
        vulnerability_ids, label="candidate vulnerability ids", pattern=CVE_ID_RE
    )
    records = _bounded_unique_strings(
        knowledge_record_ids, label="candidate knowledge record ids", pattern=RECORD_ID_RE,
        allow_empty=False, limit=MAX_RECORD_REFS,
    )
    score = _confidence(confidence)
    if not isinstance(rationale, str) or not rationale.strip():
        raise CampaignPlannerError("candidate rationale is required")
    seed = _candidate_seed(
        operation_id=operation_id,
        capability_id=capability_id,
        intrusiveness_level=intrusiveness_level,
        asset_ids=assets,
        technique_ids=techniques,
        vulnerability_ids=vulnerabilities,
        knowledge_record_ids=records,
        confidence=score,
        rationale=rationale,
    )
    return {
        "schema_version": "1.0",
        "candidate_id": f"kpcand_{_digest(seed)[:32]}",
        **seed,
        "executable": False,
        "authorization_effect": "NONE",
    }


def _validate_candidate(candidate: Mapping[str, Any]) -> dict[str, Any]:
    if not isinstance(candidate, Mapping):
        raise CampaignPlannerError("candidate must be an object")
    _reject_forbidden_fields(candidate, "candidate")
    _exact_fields(candidate, CANDIDATE_FIELDS, "candidate")
    if candidate.get("schema_version") != "1.0":
        raise CampaignPlannerError("unsupported candidate schema")
    if candidate.get("executable") is not False or candidate.get("authorization_effect") != "NONE":
        raise CampaignPlannerError("candidate cannot be executable or grant authorization")
    candidate_id = candidate.get("candidate_id")
    if not isinstance(candidate_id, str) or not CANDIDATE_ID_RE.fullmatch(candidate_id):
        raise CampaignPlannerError("invalid candidate id")
    expected = build_candidate(
        operation_id=candidate["operation_id"],
        capability_id=candidate["capability_id"],
        intrusiveness_level=candidate["intrusiveness_level"],
        asset_ids=candidate["asset_ids"],
        technique_ids=candidate["technique_ids"],
        vulnerability_ids=candidate["vulnerability_ids"],
        knowledge_record_ids=candidate["knowledge_record_ids"],
        confidence=candidate["confidence"],
        rationale=candidate["rationale"],
    )
    if expected["candidate_id"] != candidate_id:
        raise CampaignPlannerError("candidate id does not match canonical content")
    return expected


def _candidate_reasons(context: Mapping[str, Any], candidate: Mapping[str, Any]) -> list[str]:
    reasons: list[str] = []
    if candidate["capability_id"] not in context["allowed_capability_ids"]:
        reasons.append("CAPABILITY_NOT_ALLOWED_BY_PLANNING_CONTEXT")
    if INTRUSIVENESS[candidate["intrusiveness_level"]] > INTRUSIVENESS[context["max_intrusiveness_level"]]:
        reasons.append("INTRUSIVENESS_ABOVE_PLANNING_CEILING")
    if not set(candidate["asset_ids"]).issubset(set(context["asset_ids"])):
        reasons.append("ASSET_OUTSIDE_PLANNING_SCOPE")
    if candidate["confidence"] < context["minimum_confidence"]:
        reasons.append("CONFIDENCE_BELOW_PLANNING_MINIMUM")
    constrained = bool(context["threat_technique_ids"] or context["vulnerability_ids"])
    technique_match = set(candidate["technique_ids"]).intersection(context["threat_technique_ids"])
    vulnerability_match = set(candidate["vulnerability_ids"]).intersection(context["vulnerability_ids"])
    if constrained and not technique_match and not vulnerability_match:
        reasons.append("NO_THREAT_CONTEXT_MATCH")
    return sorted(reasons)


def derive_plan(*, context: Mapping[str, Any], candidates: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    validated_context = _validate_context(context)
    if isinstance(candidates, (str, bytes)) or not isinstance(candidates, Sequence):
        raise CampaignPlannerError("candidates must be a bounded list")
    if len(candidates) > MAX_CANDIDATES:
        raise CampaignPlannerError("candidate set exceeds the bounded contract")
    validated = [_validate_candidate(item) for item in candidates]
    candidate_ids = [item["candidate_id"] for item in validated]
    if len(set(candidate_ids)) != len(candidate_ids):
        raise CampaignPlannerError("candidate ids must be unique")

    selected: list[dict[str, Any]] = []
    excluded: list[dict[str, Any]] = []
    for candidate in validated:
        reasons = _candidate_reasons(validated_context, candidate)
        if reasons:
            excluded.append({"candidate_id": candidate["candidate_id"], "reasons": reasons})
            continue
        technique_matches = sorted(
            set(candidate["technique_ids"]).intersection(validated_context["threat_technique_ids"])
        )
        vulnerability_matches = sorted(
            set(candidate["vulnerability_ids"]).intersection(validated_context["vulnerability_ids"])
        )
        selected.append({
            "candidate_id": candidate["candidate_id"],
            "operation_id": candidate["operation_id"],
            "capability_id": candidate["capability_id"],
            "intrusiveness_level": candidate["intrusiveness_level"],
            "asset_ids": deepcopy(candidate["asset_ids"]),
            "knowledge_record_ids": deepcopy(candidate["knowledge_record_ids"]),
            "confidence": candidate["confidence"],
            "matched_technique_ids": technique_matches,
            "matched_vulnerability_ids": vulnerability_matches,
            "selection_reason": candidate["rationale"],
        })

    selected.sort(key=lambda item: (
        -(len(item["matched_technique_ids"]) + len(item["matched_vulnerability_ids"])),
        -float(item["confidence"]),
        INTRUSIVENESS[item["intrusiveness_level"]],
        item["operation_id"],
        item["candidate_id"],
    ))
    for index, item in enumerate(selected, start=1):
        item["selection_rank"] = index
    excluded.sort(key=lambda item: item["candidate_id"])

    seed = {
        "campaign_id": validated_context["campaign_id"],
        "planning_context_id": validated_context["context_id"],
        "selected_steps": selected,
        "excluded_candidates": excluded,
    }
    return {
        "schema_version": "1.0",
        "plan_id": f"kp_{_digest(seed)[:32]}",
        **seed,
        "proposal_state": "PROPOSAL_ONLY",
        "executable": False,
        "planning_constraints_are_authorization": False,
        "authorization_effect": "NONE",
        "requires_fresh_authorization": True,
        "execution_authority": "CONTROL_PLANE_ONLY",
        "limitations": [
            "SUPPLIED_ROE_CONTEXT_IS_NOT_VERIFIED_AUTHORIZATION",
            "PLANNING_FILTERS_DO_NOT_GRANT_EXECUTION_AUTHORITY",
            "PLAN_REQUIRES_FRESH_CONTROL_PLANE_AUTHORIZATION_BEFORE_EXECUTION",
        ],
    }


def _validate_plan(plan: Mapping[str, Any]) -> None:
    if not isinstance(plan, Mapping):
        raise CampaignPlannerError("plan must be an object")
    _reject_forbidden_fields(plan, "plan")
    _exact_fields(plan, PLAN_FIELDS, "plan")
    plan_id = plan.get("plan_id")
    if not isinstance(plan_id, str) or not PLAN_ID_RE.fullmatch(plan_id):
        raise CampaignPlannerError("invalid plan id")
    if plan.get("schema_version") != "1.0":
        raise CampaignPlannerError("unsupported plan schema")
    if plan.get("proposal_state") != "PROPOSAL_ONLY" or plan.get("executable") is not False:
        raise CampaignPlannerError("only non-executable proposals may be diffed")
    if plan.get("authorization_effect") != "NONE" or plan.get("execution_authority") != "CONTROL_PLANE_ONLY":
        raise CampaignPlannerError("plan authority boundary changed")
    if plan.get("planning_constraints_are_authorization") is not False:
        raise CampaignPlannerError("planning constraints cannot become authorization")
    if plan.get("requires_fresh_authorization") is not True:
        raise CampaignPlannerError("plan must require fresh authorization")
    if not isinstance(plan.get("campaign_id"), str) or not plan["campaign_id"]:
        raise CampaignPlannerError("invalid plan campaign id")
    if not isinstance(plan.get("planning_context_id"), str) or not CONTEXT_ID_RE.fullmatch(plan["planning_context_id"]):
        raise CampaignPlannerError("invalid planning context id")
    if not isinstance(plan.get("selected_steps"), list) or not isinstance(plan.get("excluded_candidates"), list):
        raise CampaignPlannerError("plan candidate collections must be lists")
    seed = {
        "campaign_id": plan["campaign_id"],
        "planning_context_id": plan["planning_context_id"],
        "selected_steps": plan["selected_steps"],
        "excluded_candidates": plan["excluded_candidates"],
    }
    if plan_id != f"kp_{_digest(seed)[:32]}":
        raise CampaignPlannerError("plan id does not match canonical content")


def diff_plans(*, previous: Mapping[str, Any], current: Mapping[str, Any]) -> dict[str, Any]:
    _validate_plan(previous)
    _validate_plan(current)
    if previous.get("campaign_id") != current.get("campaign_id"):
        raise CampaignPlannerError("plan diff requires the same campaign")
    previous_ids = [item["candidate_id"] for item in previous["selected_steps"]]
    current_ids = [item["candidate_id"] for item in current["selected_steps"]]
    if len(set(previous_ids)) != len(previous_ids) or len(set(current_ids)) != len(current_ids):
        raise CampaignPlannerError("plan selected candidate ids must be unique")
    previous_set = set(previous_ids)
    current_set = set(current_ids)
    body = {
        "schema_version": "1.0",
        "campaign_id": current["campaign_id"],
        "previous_plan_id": previous["plan_id"],
        "current_plan_id": current["plan_id"],
        "added_candidate_ids": sorted(current_set - previous_set),
        "removed_candidate_ids": sorted(previous_set - current_set),
        "common_order_changed": (
            [item for item in previous_ids if item in current_set]
            != [item for item in current_ids if item in previous_set]
        ),
        "effect": "PROPOSAL_DIFF_ONLY",
        "authorization_effect": "NONE",
        "execution_authority": "CONTROL_PLANE_ONLY",
    }
    return {"diff_id": f"kpd_{_digest(body)[:32]}", **body}


def proposal_is_executable(plan: Mapping[str, Any]) -> bool:
    del plan
    return False
