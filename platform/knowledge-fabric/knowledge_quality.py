from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from typing import Any, Mapping, Sequence


class KnowledgeQualityError(ValueError):
    """Fail-closed knowledge-quality and curation contract violation."""


SNAPSHOT_ID_RE = re.compile(r"^ks_[a-f0-9]{32}$")
RECORD_ID_RE = re.compile(r"^kr_[a-f0-9]{32}$")
CASE_ID_RE = re.compile(r"^kqcase_[a-f0-9]{32}$")
DECISION_ID_RE = re.compile(r"^kqdec_[a-f0-9]{32}$")
CURATOR_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._@-]{2,127}$")
POLICY_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/-]{2,127}$")

MAX_RECORDS = 10000
MAX_RELATIONS = 20000
MAX_CONFLICTS = 5000
MAX_CANDIDATES = 64

RECORD_KEYS = {
    "schema_version",
    "record_id",
    "entity",
    "source",
    "ingested_at",
    "raw_sha256",
    "immutable_raw",
}
ENTITY_KEYS = {"type", "id"}
SOURCE_KEYS = {"name", "version", "retrieved_at", "locator"}
RELATION_KEYS = {
    "relation",
    "from",
    "to",
    "confidence",
    "provenance_record_ids",
    "rationale",
}

FORBIDDEN_KEYS = {
    "authorization",
    "authorization_ref",
    "authorization_receipt",
    "authorization_receipt_ref",
    "execution_allowed",
    "execution_authorized",
    "roe_decision",
    "command",
    "argv",
    "shell",
    "payload",
    "credential",
    "secret",
    "token",
    "password",
    "cookie",
    "api_key",
}


def _canonical_json(value: Any) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    ).encode()


def _digest(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value)).hexdigest()


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
    if _walk_keys(value).intersection(FORBIDDEN_KEYS):
        raise KnowledgeQualityError(
            f"{label} may not contain authority, execution or secret fields"
        )


def _require_exact_keys(value: Mapping[str, Any], expected: set[str], label: str) -> None:
    actual = {str(key) for key in value}
    if actual != expected:
        missing = sorted(expected - actual)
        extra = sorted(actual - expected)
        raise KnowledgeQualityError(
            f"{label} fields mismatch: missing={missing}, extra={extra}"
        )


def _parse_utc(value: Any, label: str) -> datetime:
    if not isinstance(value, str) or not value:
        raise KnowledgeQualityError(f"{label} must be a date-time")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise KnowledgeQualityError(f"{label} must be an ISO-8601 date-time") from exc
    if parsed.tzinfo is None:
        raise KnowledgeQualityError(f"{label} must include a timezone")
    return parsed.astimezone(timezone.utc)


def _validate_snapshot(snapshot: Mapping[str, Any]) -> dict[str, Any]:
    if not isinstance(snapshot, Mapping):
        raise KnowledgeQualityError("snapshot must be an object")
    _reject_forbidden_fields(snapshot, "snapshot")
    required = {
        "schema_version",
        "snapshot_id",
        "created_at",
        "source_record_ids",
        "snapshot_sha256",
        "immutable",
    }
    _require_exact_keys(snapshot, required, "snapshot")
    if snapshot.get("schema_version") != "1.0" or snapshot.get("immutable") is not True:
        raise KnowledgeQualityError("unsupported or mutable knowledge snapshot")
    snapshot_id = snapshot.get("snapshot_id")
    if not isinstance(snapshot_id, str) or not SNAPSHOT_ID_RE.fullmatch(snapshot_id):
        raise KnowledgeQualityError("invalid knowledge snapshot id")
    _parse_utc(snapshot.get("created_at"), "snapshot.created_at")
    record_ids = snapshot.get("source_record_ids")
    if (
        not isinstance(record_ids, list)
        or not record_ids
        or len(record_ids) > MAX_RECORDS
        or len(set(record_ids)) != len(record_ids)
        or any(not isinstance(item, str) or not RECORD_ID_RE.fullmatch(item) for item in record_ids)
    ):
        raise KnowledgeQualityError("snapshot requires unique canonical record ids")
    digest = snapshot.get("snapshot_sha256")
    if not isinstance(digest, str) or not re.fullmatch(r"^[a-f0-9]{64}$", digest):
        raise KnowledgeQualityError("invalid snapshot sha256")
    return dict(snapshot)


def _validate_record(record: Mapping[str, Any]) -> dict[str, Any]:
    if not isinstance(record, Mapping):
        raise KnowledgeQualityError("knowledge record must be an object")
    _reject_forbidden_fields(record, "knowledge record")
    _require_exact_keys(record, RECORD_KEYS, "knowledge record")
    if record.get("schema_version") != "1.0" or record.get("immutable_raw") is not True:
        raise KnowledgeQualityError("unsupported or mutable knowledge record")
    record_id = record.get("record_id")
    if not isinstance(record_id, str) or not RECORD_ID_RE.fullmatch(record_id):
        raise KnowledgeQualityError("invalid knowledge record id")
    entity = record.get("entity")
    if not isinstance(entity, Mapping):
        raise KnowledgeQualityError("knowledge entity must be an object")
    _require_exact_keys(entity, ENTITY_KEYS, "knowledge entity")
    if not all(isinstance(entity.get(key), str) and entity[key] for key in ENTITY_KEYS):
        raise KnowledgeQualityError("knowledge entity type and id are required")
    source = record.get("source")
    if not isinstance(source, Mapping):
        raise KnowledgeQualityError("knowledge source must be an object")
    _require_exact_keys(source, SOURCE_KEYS, "knowledge source")
    if not all(isinstance(source.get(key), str) and source[key] for key in SOURCE_KEYS):
        raise KnowledgeQualityError("complete source provenance is required")
    _parse_utc(source["retrieved_at"], "source.retrieved_at")
    _parse_utc(record.get("ingested_at"), "record.ingested_at")
    raw_sha = record.get("raw_sha256")
    if not isinstance(raw_sha, str) or not re.fullmatch(r"^[a-f0-9]{64}$", raw_sha):
        raise KnowledgeQualityError("invalid raw sha256")
    return dict(record)


def _validate_relation(relation: Mapping[str, Any], snapshot_record_ids: set[str]) -> dict[str, Any]:
    if not isinstance(relation, Mapping):
        raise KnowledgeQualityError("relation must be an object")
    _reject_forbidden_fields(relation, "relation")
    _require_exact_keys(relation, RELATION_KEYS, "relation")
    for key in ("relation", "from", "to", "rationale"):
        if not isinstance(relation.get(key), str) or not relation[key]:
            raise KnowledgeQualityError("relation metadata is incomplete")
    confidence = relation.get("confidence")
    if (
        isinstance(confidence, bool)
        or not isinstance(confidence, (int, float))
        or not 0.0 <= float(confidence) <= 1.0
    ):
        raise KnowledgeQualityError("relation confidence must be between 0 and 1")
    provenance = relation.get("provenance_record_ids")
    if (
        not isinstance(provenance, list)
        or not provenance
        or len(provenance) > MAX_CANDIDATES
        or len(set(provenance)) != len(provenance)
        or any(not isinstance(item, str) or not RECORD_ID_RE.fullmatch(item) for item in provenance)
    ):
        raise KnowledgeQualityError("relation provenance must be unique canonical records")
    if not set(provenance).issubset(snapshot_record_ids):
        raise KnowledgeQualityError("relation provenance must belong to assessed snapshot")
    return {
        "relation": relation["relation"],
        "from": relation["from"],
        "to": relation["to"],
        "confidence": float(confidence),
        "provenance_record_ids": sorted(provenance),
        "rationale": relation["rationale"],
    }


def _conflict_source_ids(conflict: Mapping[str, Any]) -> list[str]:
    if not isinstance(conflict, Mapping):
        raise KnowledgeQualityError("conflict must be an object")
    _reject_forbidden_fields(conflict, "conflict")
    if conflict.get("status") not in {"unresolved", "resolved"}:
        raise KnowledgeQualityError("unsupported conflict status")
    if not isinstance(conflict.get("key"), str) or not conflict["key"]:
        raise KnowledgeQualityError("conflict key is required")
    assertions = conflict.get("assertions")
    if not isinstance(assertions, list) or len(assertions) < 2 or len(assertions) > MAX_CANDIDATES:
        raise KnowledgeQualityError("conflict requires a bounded assertion set")
    source_ids = [item.get("source_record_id") for item in assertions if isinstance(item, Mapping)]
    if len(source_ids) != len(assertions) or len(set(source_ids)) != len(source_ids):
        raise KnowledgeQualityError("conflict assertions require unique source records")
    if any(not isinstance(item, str) or not RECORD_ID_RE.fullmatch(item) for item in source_ids):
        raise KnowledgeQualityError("conflict assertions require canonical source record ids")
    selected = conflict.get("selected_assertion")
    if conflict["status"] == "unresolved" and selected is not None:
        raise KnowledgeQualityError("unresolved conflict cannot select an assertion")
    if conflict["status"] == "resolved" and selected not in source_ids:
        raise KnowledgeQualityError("resolved conflict must select an existing assertion")
    return sorted(source_ids)


def assess_quality(
    *,
    snapshot: Mapping[str, Any],
    records: Sequence[Mapping[str, Any]],
    relations: Sequence[Mapping[str, Any]],
    conflicts: Sequence[Mapping[str, Any]],
    freshness_policy_seconds: Mapping[str, int],
    minimum_relation_confidence: float,
    as_of: str,
) -> dict[str, Any]:
    validated_snapshot = _validate_snapshot(snapshot)
    now = _parse_utc(as_of, "as_of")
    expected_ids = set(validated_snapshot["source_record_ids"])

    if (
        not isinstance(records, Sequence)
        or isinstance(records, (str, bytes))
        or len(records) > MAX_RECORDS
    ):
        raise KnowledgeQualityError("record set exceeds the bounded contract")
    validated_records = [_validate_record(item) for item in records]
    record_ids = [item["record_id"] for item in validated_records]
    if len(set(record_ids)) != len(record_ids):
        raise KnowledgeQualityError("record ids must be unique")
    if not set(record_ids).issubset(expected_ids):
        raise KnowledgeQualityError("provided records must belong to assessed snapshot")

    if not isinstance(freshness_policy_seconds, Mapping) or not freshness_policy_seconds:
        raise KnowledgeQualityError("explicit freshness policy is required")
    normalized_policy: dict[str, int] = {}
    for source_name, seconds in freshness_policy_seconds.items():
        if (
            not isinstance(source_name, str)
            or not source_name
            or isinstance(seconds, bool)
            or not isinstance(seconds, int)
            or seconds <= 0
        ):
            raise KnowledgeQualityError("freshness policy requires positive seconds per source")
        normalized_policy[source_name] = seconds
    record_sources = {item["source"]["name"] for item in validated_records}
    if not record_sources.issubset(normalized_policy):
        raise KnowledgeQualityError("freshness policy must cover every provided record source")

    if (
        isinstance(minimum_relation_confidence, bool)
        or not isinstance(minimum_relation_confidence, (int, float))
        or not 0.0 <= float(minimum_relation_confidence) <= 1.0
    ):
        raise KnowledgeQualityError("minimum relation confidence must be between 0 and 1")
    threshold = float(minimum_relation_confidence)

    if (
        not isinstance(relations, Sequence)
        or isinstance(relations, (str, bytes))
        or len(relations) > MAX_RELATIONS
    ):
        raise KnowledgeQualityError("relation set exceeds the bounded contract")
    validated_relations = [
        _validate_relation(item, expected_ids) for item in relations
    ]

    if (
        not isinstance(conflicts, Sequence)
        or isinstance(conflicts, (str, bytes))
        or len(conflicts) > MAX_CONFLICTS
    ):
        raise KnowledgeQualityError("conflict set exceeds the bounded contract")
    unresolved = 0
    conflict_keys: set[str] = set()
    for conflict in conflicts:
        source_ids = _conflict_source_ids(conflict)
        if not set(source_ids).issubset(expected_ids):
            raise KnowledgeQualityError("conflict assertions must belong to assessed snapshot")
        if conflict["key"] in conflict_keys:
            raise KnowledgeQualityError("conflict keys must be unique")
        conflict_keys.add(conflict["key"])
        if conflict["status"] == "unresolved":
            unresolved += 1

    missing_ids = sorted(expected_ids - set(record_ids))
    completeness_ratio = len(record_ids) / len(expected_ids)

    stale_record_ids: list[str] = []
    fresh_record_ids: list[str] = []
    for record in sorted(validated_records, key=lambda item: item["record_id"]):
        retrieved = _parse_utc(record["source"]["retrieved_at"], "source.retrieved_at")
        if retrieved > now:
            raise KnowledgeQualityError("record retrieval time cannot be in the future")
        age = int((now - retrieved).total_seconds())
        if age > normalized_policy[record["source"]["name"]]:
            stale_record_ids.append(record["record_id"])
        else:
            fresh_record_ids.append(record["record_id"])

    confidences = [item["confidence"] for item in validated_relations]
    below_threshold = sum(1 for value in confidences if value < threshold)
    confidence_metrics = {
        "relation_count": len(confidences),
        "minimum": min(confidences) if confidences else None,
        "maximum": max(confidences) if confidences else None,
        "mean": (
            round(sum(confidences) / len(confidences), 6)
            if confidences
            else None
        ),
        "below_policy_count": below_threshold,
        "policy_minimum": threshold,
    }

    quality_state = (
        "REVIEW_REQUIRED"
        if missing_ids or stale_record_ids or below_threshold or unresolved
        else "QUALITY_POLICY_MET"
    )
    body = {
        "schema_version": "1.0",
        "knowledge_snapshot_id": validated_snapshot["snapshot_id"],
        "as_of": as_of,
        "quality_state": quality_state,
        "completeness": {
            "expected_record_count": len(expected_ids),
            "provided_record_count": len(record_ids),
            "missing_record_ids": missing_ids,
            "ratio": round(completeness_ratio, 6),
        },
        "freshness": {
            "fresh_record_ids": fresh_record_ids,
            "stale_record_ids": stale_record_ids,
            "policy_seconds": dict(sorted(normalized_policy.items())),
        },
        "confidence": confidence_metrics,
        "conflicts": {
            "total": len(conflicts),
            "unresolved": unresolved,
            "resolved": len(conflicts) - unresolved,
        },
        "assurance_effect": "NONE",
        "execution_authority": "NONE",
        "limitations": [
            "QUALITY_POLICY_MET_IS_NOT_A_SECURITY_VERDICT",
            "QUALITY_METRICS_DO_NOT_ESTABLISH_SOURCE_AUTHORITY",
            "ABSENCE_OF_QUALITY_FINDINGS_DOES_NOT_IMPLY_ASSURANCE",
        ],
    }
    return {"quality_report_id": f"kqr_{_digest(body)[:32]}", **body}


def build_curation_case(
    *,
    knowledge_snapshot_id: str,
    finding_type: str,
    subject_ref: str,
    candidate_source_record_ids: Sequence[str],
    rationale: str,
) -> dict[str, Any]:
    if not isinstance(knowledge_snapshot_id, str) or not SNAPSHOT_ID_RE.fullmatch(knowledge_snapshot_id):
        raise KnowledgeQualityError("invalid knowledge snapshot id")
    if finding_type not in {"CONFLICT", "LOW_CONFIDENCE", "STALE", "INCOMPLETE"}:
        raise KnowledgeQualityError("unsupported curation finding type")
    if not isinstance(subject_ref, str) or not subject_ref:
        raise KnowledgeQualityError("curation subject is required")
    if (
        not isinstance(candidate_source_record_ids, Sequence)
        or isinstance(candidate_source_record_ids, (str, bytes))
        or not candidate_source_record_ids
        or len(candidate_source_record_ids) > MAX_CANDIDATES
    ):
        raise KnowledgeQualityError("curation case requires bounded candidate records")
    candidates = list(candidate_source_record_ids)
    if len(set(candidates)) != len(candidates) or any(
        not isinstance(item, str) or not RECORD_ID_RE.fullmatch(item) for item in candidates
    ):
        raise KnowledgeQualityError("curation candidates must be unique canonical record ids")
    if not isinstance(rationale, str) or not rationale.strip():
        raise KnowledgeQualityError("curation rationale is required")
    seed = {
        "knowledge_snapshot_id": knowledge_snapshot_id,
        "finding_type": finding_type,
        "subject_ref": subject_ref,
        "candidate_source_record_ids": sorted(candidates),
        "rationale": rationale.strip(),
    }
    return {
        "schema_version": "1.0",
        "case_id": f"kqcase_{_digest(seed)[:32]}",
        **seed,
        "state": "OPEN",
        "automatic_resolution": False,
        "execution_authority": "NONE",
    }


def _validate_case(case: Mapping[str, Any]) -> dict[str, Any]:
    if not isinstance(case, Mapping):
        raise KnowledgeQualityError("curation case must be an object")
    _reject_forbidden_fields(case, "curation case")
    required = {
        "schema_version",
        "case_id",
        "knowledge_snapshot_id",
        "finding_type",
        "subject_ref",
        "candidate_source_record_ids",
        "rationale",
        "state",
        "automatic_resolution",
        "execution_authority",
    }
    _require_exact_keys(case, required, "curation case")
    if case.get("schema_version") != "1.0" or case.get("state") != "OPEN":
        raise KnowledgeQualityError("only open v1 curation cases may be resolved")
    if case.get("automatic_resolution") is not False or case.get("execution_authority") != "NONE":
        raise KnowledgeQualityError("curation case authority boundary changed")
    case_id = case.get("case_id")
    if not isinstance(case_id, str) or not CASE_ID_RE.fullmatch(case_id):
        raise KnowledgeQualityError("invalid curation case id")
    if not isinstance(case.get("knowledge_snapshot_id"), str) or not SNAPSHOT_ID_RE.fullmatch(case["knowledge_snapshot_id"]):
        raise KnowledgeQualityError("invalid curation snapshot id")
    candidates = case.get("candidate_source_record_ids")
    if (
        not isinstance(candidates, list)
        or not candidates
        or len(candidates) > MAX_CANDIDATES
        or len(set(candidates)) != len(candidates)
        or any(not isinstance(item, str) or not RECORD_ID_RE.fullmatch(item) for item in candidates)
    ):
        raise KnowledgeQualityError("invalid curation candidates")
    return dict(case)


def record_curator_decision(
    *,
    case: Mapping[str, Any],
    curator_id: str,
    decision: str,
    selected_source_record_id: str | None,
    rationale: str,
    decided_at: str,
) -> dict[str, Any]:
    validated_case = _validate_case(case)
    if not isinstance(curator_id, str) or not CURATOR_ID_RE.fullmatch(curator_id):
        raise KnowledgeQualityError("invalid curator identity")
    if decision not in {"SELECT_ASSERTION", "DEFER", "REJECT_ALL"}:
        raise KnowledgeQualityError("unsupported curator decision")
    candidates = validated_case["candidate_source_record_ids"]
    if decision == "SELECT_ASSERTION":
        if selected_source_record_id not in candidates:
            raise KnowledgeQualityError("selected assertion must be a case candidate")
    elif selected_source_record_id is not None:
        raise KnowledgeQualityError("non-selection decisions cannot select an assertion")
    if not isinstance(rationale, str) or not rationale.strip():
        raise KnowledgeQualityError("curator decision rationale is required")
    _parse_utc(decided_at, "decided_at")
    body = {
        "schema_version": "1.0",
        "case_id": validated_case["case_id"],
        "knowledge_snapshot_id": validated_case["knowledge_snapshot_id"],
        "decision_basis": "CURATOR",
        "curator_id": curator_id,
        "precedence_policy_id": None,
        "decision": decision,
        "selected_source_record_id": selected_source_record_id,
        "rationale": rationale.strip(),
        "decided_at": decided_at,
        "automatic_resolution": False,
        "historical_rewrite": False,
        "effect": "KNOWLEDGE_CURATION_ONLY",
        "execution_authority": "NONE",
    }
    return {"decision_id": f"kqdec_{_digest(body)[:32]}", **body}


def record_policy_decision(
    *,
    case: Mapping[str, Any],
    precedence_policy_id: str,
    selected_source_record_id: str,
    rationale: str,
    decided_at: str,
) -> dict[str, Any]:
    validated_case = _validate_case(case)
    if not isinstance(precedence_policy_id, str) or not POLICY_ID_RE.fullmatch(precedence_policy_id):
        raise KnowledgeQualityError("invalid precedence policy id")
    if selected_source_record_id not in validated_case["candidate_source_record_ids"]:
        raise KnowledgeQualityError("selected assertion must be a case candidate")
    if not isinstance(rationale, str) or not rationale.strip():
        raise KnowledgeQualityError("policy decision rationale is required")
    _parse_utc(decided_at, "decided_at")
    body = {
        "schema_version": "1.0",
        "case_id": validated_case["case_id"],
        "knowledge_snapshot_id": validated_case["knowledge_snapshot_id"],
        "decision_basis": "PRECEDENCE_POLICY",
        "curator_id": None,
        "precedence_policy_id": precedence_policy_id,
        "decision": "SELECT_ASSERTION",
        "selected_source_record_id": selected_source_record_id,
        "rationale": rationale.strip(),
        "decided_at": decided_at,
        "automatic_resolution": False,
        "historical_rewrite": False,
        "effect": "KNOWLEDGE_CURATION_ONLY",
        "execution_authority": "NONE",
    }
    return {"decision_id": f"kqdec_{_digest(body)[:32]}", **body}
