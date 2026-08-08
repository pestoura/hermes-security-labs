from __future__ import annotations

import hashlib
import json
import re
from copy import deepcopy
from typing import Any, Mapping, Sequence


class OperationalQueryError(ValueError):
    """Fail-closed operational-query contract violation."""


SNAPSHOT_ID_RE = re.compile(r"^ks_[a-f0-9]{32}$")
QUERY_ID_RE = re.compile(r"^koq_[a-f0-9]{32}$")
POLICY_ID_RE = re.compile(r"^koap_[a-f0-9]{32}$")
RESULT_ID_RE = re.compile(r"^kor_[a-f0-9]{32}$")
INDEX_ID_RE = re.compile(r"^koi_[a-f0-9]{32}$")
EVIDENCE_ID_RE = re.compile(r"^ev_[A-Za-z0-9._:-]{1,120}$")
SAFE_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/-]{0,127}$")
TECHNIQUE_ID_RE = re.compile(r"^T[0-9]{4}(?:\.[0-9]{3})?$")
CVE_ID_RE = re.compile(r"^CVE-[0-9]{4}-[0-9]{4,}$")
CONTROL_ID_RE = re.compile(r"^[A-Z]{2,4}-[0-9]{1,3}(?:\([0-9]+\))?$", re.IGNORECASE)

MAX_INDEX_ENTRIES = 20_000
MAX_SCOPE_IDS = 2_000
MAX_ITEMS = 5_000

QUESTION_CATALOGUE = {
    "CONTROLS_FOR_TECHNIQUE": {
        "required_parameter": "technique_id",
        "index_kinds": ("CONTROL_MAPPING",),
        "scope_mode": "UNSCOPED_KNOWLEDGE",
    },
    "ASSETS_UNVALIDATED_FOR_VULNERABILITY": {
        "required_parameter": "vulnerability_id",
        "index_kinds": ("ASSET", "VALIDATION"),
        "scope_mode": "ASSET",
    },
    "FINDINGS_FOR_ASSET": {
        "required_parameter": "asset_id",
        "index_kinds": ("FINDING",),
        "scope_mode": "ASSET",
    },
    "CAMPAIGNS_USING_SNAPSHOT": {
        "required_parameter": None,
        "index_kinds": ("CAMPAIGN",),
        "scope_mode": "CAMPAIGN",
    },
}
INDEX_KINDS = {"ASSET", "CONTROL_MAPPING", "VALIDATION", "FINDING", "CAMPAIGN"}

FORBIDDEN_FIELDS = {
    "raw", "raw_evidence", "evidence_payload", "stdout", "stderr", "body",
    "request", "response", "headers", "payload", "content", "artifact_content",
    "command", "argv", "shell", "target", "credential", "credentials", "secret",
    "token", "password", "cookie", "api_key", "authorization_receipt",
    "authorization_ref", "execution_allowed", "execution_authorized",
}

INDEX_FIELDS = {
    "schema_version", "index_id", "kind", "knowledge_snapshot_id", "asset_ids",
    "technique_ids", "vulnerability_ids", "control_ids", "campaign_id", "finding_id",
    "evidence_ids", "confidence", "summary", "sanitization_state",
}
ACCESS_FIELDS = {
    "schema_version", "policy_id", "principal_id", "allowed_asset_ids",
    "allowed_campaign_ids", "allowed_index_kinds", "allow_unscoped_knowledge",
    "effect", "execution_authority",
}
QUERY_FIELDS = {
    "schema_version", "query_id", "question_id", "knowledge_snapshot_id",
    "principal_id", "minimum_confidence", "parameters", "read_only",
    "assurance_effect", "execution_authority",
}
RESULT_FIELDS = {
    "schema_version", "result_id", "query_id", "question_id", "knowledge_snapshot_id",
    "access_policy_id", "access_decision", "items", "index_scope_ids",
    "evidence_scope_ids", "read_only", "raw_evidence_exposed", "assurance_effect",
    "compliance_effect", "execution_authority", "limitations",
}


def _digest(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()
    ).hexdigest()


def _walk_keys(value: Any) -> set[str]:
    result: set[str] = set()
    if isinstance(value, Mapping):
        for key, item in value.items():
            result.add(str(key).lower())
            result.update(_walk_keys(item))
    elif isinstance(value, list):
        for item in value:
            result.update(_walk_keys(item))
    return result


def _reject_forbidden_fields(value: Any, label: str) -> None:
    if _walk_keys(value).intersection(FORBIDDEN_FIELDS):
        raise OperationalQueryError(
            f"{label} contains raw, secret, target, execution or authorization material"
        )


def _exact_fields(value: Mapping[str, Any], expected: set[str], label: str) -> None:
    actual = {str(key) for key in value}
    if actual != expected:
        raise OperationalQueryError(
            f"{label} fields mismatch: missing={sorted(expected - actual)}, extra={sorted(actual - expected)}"
        )


def _safe_id(value: Any, label: str) -> str:
    if not isinstance(value, str) or not SAFE_ID_RE.fullmatch(value):
        raise OperationalQueryError(f"invalid {label}")
    return value


def _unique_ids(values: Any, *, label: str, limit: int = MAX_SCOPE_IDS) -> list[str]:
    if not isinstance(values, list) or len(values) > limit or len(set(values)) != len(values):
        raise OperationalQueryError(f"{label} must be a bounded unique list")
    for item in values:
        _safe_id(item, label)
    return sorted(values)


def _confidence(value: Any) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise OperationalQueryError("confidence must be numeric")
    result = float(value)
    if not 0.0 <= result <= 1.0:
        raise OperationalQueryError("confidence must be between 0 and 1")
    return result


def question_catalogue() -> tuple[str, ...]:
    return tuple(sorted(QUESTION_CATALOGUE))


def build_access_policy(
    *, principal_id: str, allowed_asset_ids: Sequence[str], allowed_campaign_ids: Sequence[str],
    allowed_index_kinds: Sequence[str], allow_unscoped_knowledge: bool,
) -> dict[str, Any]:
    principal = _safe_id(principal_id, "principal id")
    assets = _unique_ids(list(allowed_asset_ids), label="asset scope")
    campaigns = _unique_ids(list(allowed_campaign_ids), label="campaign scope")
    if isinstance(allowed_index_kinds, (str, bytes)) or not isinstance(allowed_index_kinds, Sequence):
        raise OperationalQueryError("allowed index kinds must be a list")
    original_kinds = list(allowed_index_kinds)
    kinds = sorted(set(original_kinds))
    if len(kinds) != len(original_kinds) or not set(kinds).issubset(INDEX_KINDS):
        raise OperationalQueryError("invalid allowed index kinds")
    if not isinstance(allow_unscoped_knowledge, bool):
        raise OperationalQueryError("allow_unscoped_knowledge must be boolean")
    seed = {
        "principal_id": principal,
        "allowed_asset_ids": assets,
        "allowed_campaign_ids": campaigns,
        "allowed_index_kinds": kinds,
        "allow_unscoped_knowledge": allow_unscoped_knowledge,
    }
    return {
        "schema_version": "1.0",
        "policy_id": f"koap_{_digest(seed)[:32]}",
        **seed,
        "effect": "READ_FILTER_ONLY",
        "execution_authority": "NONE",
    }


def _validate_access_policy(policy: Mapping[str, Any]) -> dict[str, Any]:
    if not isinstance(policy, Mapping):
        raise OperationalQueryError("access policy must be an object")
    _reject_forbidden_fields(policy, "access policy")
    _exact_fields(policy, ACCESS_FIELDS, "access policy")
    if policy.get("schema_version") != "1.0" or policy.get("effect") != "READ_FILTER_ONLY":
        raise OperationalQueryError("unsupported access policy")
    if policy.get("execution_authority") != "NONE":
        raise OperationalQueryError("query access policy cannot grant execution authority")
    expected = build_access_policy(
        principal_id=policy["principal_id"],
        allowed_asset_ids=policy["allowed_asset_ids"],
        allowed_campaign_ids=policy["allowed_campaign_ids"],
        allowed_index_kinds=policy["allowed_index_kinds"],
        allow_unscoped_knowledge=policy["allow_unscoped_knowledge"],
    )
    if policy.get("policy_id") != expected["policy_id"]:
        raise OperationalQueryError("access policy id does not match canonical content")
    return expected


def build_query(
    *, question_id: str, knowledge_snapshot_id: str, principal_id: str,
    minimum_confidence: float, parameters: Mapping[str, str],
) -> dict[str, Any]:
    if question_id not in QUESTION_CATALOGUE:
        raise OperationalQueryError("unsupported canonical question")
    if not isinstance(knowledge_snapshot_id, str) or not SNAPSHOT_ID_RE.fullmatch(knowledge_snapshot_id):
        raise OperationalQueryError("invalid knowledge snapshot id")
    principal = _safe_id(principal_id, "principal id")
    threshold = _confidence(minimum_confidence)
    if not isinstance(parameters, Mapping):
        raise OperationalQueryError("query parameters must be an object")
    _reject_forbidden_fields(parameters, "query parameters")
    required = QUESTION_CATALOGUE[question_id]["required_parameter"]
    expected_keys = set() if required is None else {required}
    if set(parameters) != expected_keys:
        raise OperationalQueryError("query parameters do not match canonical question")
    normalized = {str(key): str(value) for key, value in sorted(parameters.items())}
    if required == "technique_id" and not TECHNIQUE_ID_RE.fullmatch(normalized[required]):
        raise OperationalQueryError("invalid ATT&CK technique id")
    if required == "vulnerability_id" and not CVE_ID_RE.fullmatch(normalized[required]):
        raise OperationalQueryError("invalid CVE id")
    if required == "asset_id":
        _safe_id(normalized[required], "asset id")
    seed = {
        "question_id": question_id,
        "knowledge_snapshot_id": knowledge_snapshot_id,
        "principal_id": principal,
        "minimum_confidence": threshold,
        "parameters": normalized,
    }
    return {
        "schema_version": "1.0",
        "query_id": f"koq_{_digest(seed)[:32]}",
        **seed,
        "read_only": True,
        "assurance_effect": "NONE",
        "execution_authority": "NONE",
    }


def _validate_query(query: Mapping[str, Any]) -> dict[str, Any]:
    if not isinstance(query, Mapping):
        raise OperationalQueryError("query must be an object")
    _reject_forbidden_fields(query, "query")
    _exact_fields(query, QUERY_FIELDS, "query")
    if query.get("schema_version") != "1.0" or query.get("read_only") is not True:
        raise OperationalQueryError("operational query must be read-only")
    if query.get("assurance_effect") != "NONE" or query.get("execution_authority") != "NONE":
        raise OperationalQueryError("operational query cannot create assurance or execution authority")
    expected = build_query(
        question_id=query["question_id"],
        knowledge_snapshot_id=query["knowledge_snapshot_id"],
        principal_id=query["principal_id"],
        minimum_confidence=query["minimum_confidence"],
        parameters=query["parameters"],
    )
    if query.get("query_id") != expected["query_id"]:
        raise OperationalQueryError("query id does not match canonical content")
    return expected


def build_index_entry(
    *, kind: str, knowledge_snapshot_id: str, asset_ids: Sequence[str] = (),
    technique_ids: Sequence[str] = (), vulnerability_ids: Sequence[str] = (),
    control_ids: Sequence[str] = (), campaign_id: str | None = None,
    finding_id: str | None = None, evidence_ids: Sequence[str] = (),
    confidence: float = 1.0, summary: str,
) -> dict[str, Any]:
    if kind not in INDEX_KINDS:
        raise OperationalQueryError("unsupported sanitized index kind")
    if not isinstance(knowledge_snapshot_id, str) or not SNAPSHOT_ID_RE.fullmatch(knowledge_snapshot_id):
        raise OperationalQueryError("invalid knowledge snapshot id")
    assets = _unique_ids(list(asset_ids), label="index asset ids")
    techniques = sorted(set(technique_ids))
    if len(techniques) != len(list(technique_ids)) or any(
        not isinstance(item, str) or not TECHNIQUE_ID_RE.fullmatch(item) for item in techniques
    ):
        raise OperationalQueryError("invalid index technique ids")
    vulnerabilities = sorted(set(vulnerability_ids))
    if len(vulnerabilities) != len(list(vulnerability_ids)) or any(
        not isinstance(item, str) or not CVE_ID_RE.fullmatch(item) for item in vulnerabilities
    ):
        raise OperationalQueryError("invalid index vulnerability ids")
    controls = sorted(set(control_ids))
    if len(controls) != len(list(control_ids)) or any(
        not isinstance(item, str) or not CONTROL_ID_RE.fullmatch(item) for item in controls
    ):
        raise OperationalQueryError("invalid control ids")
    campaign = None if campaign_id is None else _safe_id(campaign_id, "campaign id")
    finding = None if finding_id is None else _safe_id(finding_id, "finding id")
    evidences = sorted(set(evidence_ids))
    if len(evidences) != len(list(evidence_ids)) or len(evidences) > MAX_SCOPE_IDS or any(
        not isinstance(item, str) or not EVIDENCE_ID_RE.fullmatch(item) for item in evidences
    ):
        raise OperationalQueryError("invalid evidence ids")
    score = _confidence(confidence)
    if not isinstance(summary, str) or not summary.strip() or len(summary) > 1024:
        raise OperationalQueryError("sanitized summary is required and bounded")

    if kind in {"ASSET", "VALIDATION", "FINDING"} and len(assets) != 1:
        raise OperationalQueryError(f"{kind} index requires exactly one asset id")
    if kind == "CONTROL_MAPPING" and (not techniques or not controls):
        raise OperationalQueryError("CONTROL_MAPPING index requires technique and control ids")
    if kind == "VALIDATION" and not vulnerabilities:
        raise OperationalQueryError("VALIDATION index requires vulnerability ids")
    if kind == "FINDING" and finding is None:
        raise OperationalQueryError("FINDING index requires finding id")
    if kind == "CAMPAIGN" and campaign is None:
        raise OperationalQueryError("CAMPAIGN index requires campaign id")

    seed = {
        "kind": kind,
        "knowledge_snapshot_id": knowledge_snapshot_id,
        "asset_ids": assets,
        "technique_ids": techniques,
        "vulnerability_ids": vulnerabilities,
        "control_ids": controls,
        "campaign_id": campaign,
        "finding_id": finding,
        "evidence_ids": evidences,
        "confidence": score,
        "summary": summary.strip(),
    }
    return {
        "schema_version": "1.0",
        "index_id": f"koi_{_digest(seed)[:32]}",
        **seed,
        "sanitization_state": "SANITIZED_METADATA_ONLY",
    }


def _validate_index_entry(entry: Mapping[str, Any], snapshot_id: str) -> dict[str, Any]:
    if not isinstance(entry, Mapping):
        raise OperationalQueryError("index entry must be an object")
    _reject_forbidden_fields(entry, "index entry")
    _exact_fields(entry, INDEX_FIELDS, "index entry")
    if entry.get("schema_version") != "1.0" or entry.get("sanitization_state") != "SANITIZED_METADATA_ONLY":
        raise OperationalQueryError("only sanitized metadata indexes are queryable")
    if entry.get("knowledge_snapshot_id") != snapshot_id:
        raise OperationalQueryError("index entry snapshot does not match query snapshot")
    expected = build_index_entry(
        kind=entry["kind"], knowledge_snapshot_id=entry["knowledge_snapshot_id"],
        asset_ids=entry["asset_ids"], technique_ids=entry["technique_ids"],
        vulnerability_ids=entry["vulnerability_ids"], control_ids=entry["control_ids"],
        campaign_id=entry["campaign_id"], finding_id=entry["finding_id"],
        evidence_ids=entry["evidence_ids"], confidence=entry["confidence"],
        summary=entry["summary"],
    )
    if entry.get("index_id") != expected["index_id"]:
        raise OperationalQueryError("index id does not match canonical sanitized content")
    return expected


def _entry_allowed(entry: Mapping[str, Any], policy: Mapping[str, Any]) -> bool:
    if entry["kind"] not in policy["allowed_index_kinds"]:
        return False
    if entry["asset_ids"]:
        return set(entry["asset_ids"]).issubset(set(policy["allowed_asset_ids"]))
    if entry["campaign_id"] is not None:
        return entry["campaign_id"] in policy["allowed_campaign_ids"]
    return bool(policy["allow_unscoped_knowledge"])


def _answer_items(query: Mapping[str, Any], entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    question = query["question_id"]
    params = query["parameters"]
    eligible = [item for item in entries if item["confidence"] >= query["minimum_confidence"]]

    if question == "CONTROLS_FOR_TECHNIQUE":
        technique = params["technique_id"]
        controls = sorted({
            control
            for item in eligible
            if item["kind"] == "CONTROL_MAPPING" and technique in item["technique_ids"]
            for control in item["control_ids"]
        })
        return [{"control_id": control} for control in controls]

    if question == "FINDINGS_FOR_ASSET":
        asset = params["asset_id"]
        rows = [
            {"finding_id": item["finding_id"], "summary": item["summary"], "confidence": item["confidence"]}
            for item in eligible
            if item["kind"] == "FINDING" and asset in item["asset_ids"] and item["finding_id"] is not None
        ]
        return sorted(rows, key=lambda row: row["finding_id"])

    if question == "CAMPAIGNS_USING_SNAPSHOT":
        campaigns = sorted({
            item["campaign_id"]
            for item in eligible
            if item["kind"] == "CAMPAIGN" and item["campaign_id"] is not None
        })
        return [{"campaign_id": campaign} for campaign in campaigns]

    vulnerability = params["vulnerability_id"]
    assets = sorted({
        item["asset_ids"][0]
        for item in eligible
        if item["kind"] == "ASSET"
    })
    validated_assets = {
        item["asset_ids"][0]
        for item in eligible
        if item["kind"] == "VALIDATION" and vulnerability in item["vulnerability_ids"]
    }
    return [{"asset_id": asset} for asset in assets if asset not in validated_assets]


def execute_query(
    *, query: Mapping[str, Any], access_policy: Mapping[str, Any],
    sanitized_index: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    validated_query = _validate_query(query)
    policy = _validate_access_policy(access_policy)
    if validated_query["principal_id"] != policy["principal_id"]:
        raise OperationalQueryError("query principal does not match access policy")
    if isinstance(sanitized_index, (str, bytes)) or not isinstance(sanitized_index, Sequence) or len(sanitized_index) > MAX_INDEX_ENTRIES:
        raise OperationalQueryError("sanitized index exceeds the bounded contract")
    entries = [
        _validate_index_entry(item, validated_query["knowledge_snapshot_id"])
        for item in sanitized_index
    ]
    ids = [item["index_id"] for item in entries]
    if len(set(ids)) != len(ids):
        raise OperationalQueryError("sanitized index ids must be unique")

    definition = QUESTION_CATALOGUE[validated_query["question_id"]]
    required_kinds = set(definition["index_kinds"])
    scoped = [
        item for item in entries
        if item["kind"] in required_kinds and _entry_allowed(item, policy)
    ]
    access_decision = "ALLOW"
    if not required_kinds.issubset(set(policy["allowed_index_kinds"])):
        access_decision = "DENY"
    elif definition["scope_mode"] == "UNSCOPED_KNOWLEDGE" and not policy["allow_unscoped_knowledge"]:
        access_decision = "DENY"
    elif definition["scope_mode"] == "ASSET" and not policy["allowed_asset_ids"]:
        access_decision = "DENY"
    elif definition["scope_mode"] == "CAMPAIGN" and not policy["allowed_campaign_ids"]:
        access_decision = "DENY"

    items = [] if access_decision == "DENY" else _answer_items(validated_query, scoped)
    if len(items) > MAX_ITEMS:
        raise OperationalQueryError("query result exceeds the bounded contract")
    index_scope_ids = [] if access_decision == "DENY" else sorted(item["index_id"] for item in scoped)
    evidence_scope_ids = [] if access_decision == "DENY" else sorted({
        evidence for item in scoped for evidence in item["evidence_ids"]
    })
    body = {
        "schema_version": "1.0",
        "query_id": validated_query["query_id"],
        "question_id": validated_query["question_id"],
        "knowledge_snapshot_id": validated_query["knowledge_snapshot_id"],
        "access_policy_id": policy["policy_id"],
        "access_decision": access_decision,
        "items": deepcopy(items),
        "index_scope_ids": index_scope_ids,
        "evidence_scope_ids": evidence_scope_ids,
        "read_only": True,
        "raw_evidence_exposed": False,
        "assurance_effect": "NONE",
        "compliance_effect": "NONE",
        "execution_authority": "NONE",
        "limitations": [
            "ABSENCE_OF_RESULTS_IS_NOT_A_PASS_VERDICT",
            "SANITIZED_METADATA_ONLY_NO_RAW_EVIDENCE",
            "QUERY_RESULT_DOES_NOT_ESTABLISH_CONTROL_EFFECTIVENESS_OR_COMPLIANCE",
            "NEGATIVE_RESULTS_ARE_LIMITED_TO_THE_SUPPLIED_AUTHORIZED_INDEX_SCOPE",
        ],
    }
    return {"result_id": f"kor_{_digest(body)[:32]}", **body}


def validate_result(result: Mapping[str, Any]) -> None:
    if not isinstance(result, Mapping):
        raise OperationalQueryError("result must be an object")
    _reject_forbidden_fields(result, "result")
    _exact_fields(result, RESULT_FIELDS, "result")
    result_id = result.get("result_id")
    if not isinstance(result_id, str) or not RESULT_ID_RE.fullmatch(result_id):
        raise OperationalQueryError("invalid result id")
    body = {key: deepcopy(value) for key, value in result.items() if key != "result_id"}
    if result_id != f"kor_{_digest(body)[:32]}":
        raise OperationalQueryError("result id does not match canonical content")
    if result.get("read_only") is not True or result.get("raw_evidence_exposed") is not False:
        raise OperationalQueryError("operational result boundary changed")
    if result.get("assurance_effect") != "NONE" or result.get("compliance_effect") != "NONE" or result.get("execution_authority") != "NONE":
        raise OperationalQueryError(
            "query result cannot create assurance, compliance or execution authority"
        )
