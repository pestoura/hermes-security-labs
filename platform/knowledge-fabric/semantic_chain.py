from __future__ import annotations

import hashlib
import json
import re
from typing import Any, Mapping, Sequence


class SemanticChainError(ValueError):
    """Fail-closed semantic-chain contract violation."""


RELATION_RULES: dict[str, tuple[str, str]] = {
    "VULNERABILITY_TO_CWE": ("vulnerability", "cwe"),
    "CWE_TO_CAPEC": ("cwe", "capec"),
    "CAPEC_TO_ATTACK": ("capec", "attack"),
}
CHAIN_ORDER = tuple(RELATION_RULES)
ENTITY_TYPES = {"vulnerability", "cwe", "capec", "attack"}
RELATION_KEYS = {
    "schema_version",
    "relation_id",
    "knowledge_snapshot_id",
    "relation_kind",
    "from_entity",
    "to_entity",
    "confidence",
    "provenance_record_ids",
    "rationale",
}
ENTITY_KEYS = {"type", "id"}
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
SNAPSHOT_RE = re.compile(r"^ks_[a-f0-9]{32}$")
RECORD_RE = re.compile(r"^kr_[a-f0-9]{32}$")
RELATION_ID_RE = re.compile(r"^sr_[a-f0-9]{32}$")
ENTITY_PATTERNS = {
    "vulnerability": re.compile(r"^CVE-[0-9]{4}-[0-9]{4,}$", re.IGNORECASE),
    "cwe": re.compile(r"^CWE-[0-9]+$", re.IGNORECASE),
    "capec": re.compile(r"^CAPEC-[0-9]+$", re.IGNORECASE),
    "attack": re.compile(r"^T[0-9]{4}(?:\.[0-9]{3})?$", re.IGNORECASE),
}
MAX_RELATIONS = 1000
MAX_PROVENANCE_PER_RELATION = 64


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
    forbidden = _walk_keys(value).intersection(FORBIDDEN_KEYS)
    if forbidden:
        raise SemanticChainError(
            f"{label} may not contain authority, execution or secret fields"
        )


def _require_exact_keys(
    value: Mapping[str, Any], expected: set[str], label: str
) -> None:
    actual = {str(key) for key in value}
    if actual != expected:
        missing = sorted(expected - actual)
        extra = sorted(actual - expected)
        raise SemanticChainError(
            f"{label} fields mismatch: missing={missing}, extra={extra}"
        )


def _validate_confidence(value: Any, label: str = "confidence") -> float:
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not 0.0 <= float(value) <= 1.0
    ):
        raise SemanticChainError(f"{label} must be between 0 and 1")
    return float(value)


def _validate_entity(entity: Mapping[str, Any], expected_type: str | None = None) -> dict[str, str]:
    if not isinstance(entity, Mapping):
        raise SemanticChainError("entity must be an object")
    _require_exact_keys(entity, ENTITY_KEYS, "entity")
    entity_type = entity.get("type")
    entity_id = entity.get("id")
    if entity_type not in ENTITY_TYPES:
        raise SemanticChainError("unsupported semantic entity type")
    if expected_type is not None and entity_type != expected_type:
        raise SemanticChainError(
            f"entity type must be {expected_type!r} for this relation"
        )
    if not isinstance(entity_id, str) or not ENTITY_PATTERNS[entity_type].fullmatch(entity_id):
        raise SemanticChainError(
            f"invalid {entity_type} identifier"
        )
    return {"type": entity_type, "id": entity_id.upper()}


def _relation_seed(
    *,
    knowledge_snapshot_id: str,
    relation_kind: str,
    from_entity: Mapping[str, str],
    to_entity: Mapping[str, str],
    confidence: float,
    provenance_record_ids: Sequence[str],
    rationale: str,
) -> dict[str, Any]:
    return {
        "knowledge_snapshot_id": knowledge_snapshot_id,
        "relation_kind": relation_kind,
        "from_entity": dict(from_entity),
        "to_entity": dict(to_entity),
        "confidence": float(confidence),
        "provenance_record_ids": sorted(provenance_record_ids),
        "rationale": rationale,
    }


def build_relation(
    *,
    knowledge_snapshot_id: str,
    relation_kind: str,
    from_entity: Mapping[str, Any],
    to_entity: Mapping[str, Any],
    confidence: float,
    provenance_record_ids: Sequence[str],
    rationale: str,
) -> dict[str, Any]:
    if relation_kind not in RELATION_RULES:
        raise SemanticChainError("unsupported semantic relation kind")
    if not isinstance(knowledge_snapshot_id, str) or not SNAPSHOT_RE.fullmatch(
        knowledge_snapshot_id
    ):
        raise SemanticChainError("knowledge_snapshot_id must be a canonical snapshot id")

    expected_from, expected_to = RELATION_RULES[relation_kind]
    normalized_from = _validate_entity(from_entity, expected_from)
    normalized_to = _validate_entity(to_entity, expected_to)
    normalized_confidence = _validate_confidence(confidence)

    if (
        not isinstance(provenance_record_ids, Sequence)
        or isinstance(provenance_record_ids, (str, bytes))
        or not provenance_record_ids
        or len(provenance_record_ids) > MAX_PROVENANCE_PER_RELATION
    ):
        raise SemanticChainError("one to 64 provenance records are required")
    provenance = list(provenance_record_ids)
    if len(set(provenance)) != len(provenance):
        raise SemanticChainError("provenance record ids must be unique")
    if any(not isinstance(item, str) or not RECORD_RE.fullmatch(item) for item in provenance):
        raise SemanticChainError("provenance record ids must be canonical knowledge-record ids")
    if not isinstance(rationale, str) or not rationale.strip():
        raise SemanticChainError("mapping rationale is required")

    seed = _relation_seed(
        knowledge_snapshot_id=knowledge_snapshot_id,
        relation_kind=relation_kind,
        from_entity=normalized_from,
        to_entity=normalized_to,
        confidence=normalized_confidence,
        provenance_record_ids=provenance,
        rationale=rationale.strip(),
    )
    relation = {
        "schema_version": "1.0",
        "relation_id": f"sr_{_digest(seed)[:32]}",
        **seed,
    }
    return validate_relation(relation)


def validate_relation(relation: Mapping[str, Any]) -> dict[str, Any]:
    if not isinstance(relation, Mapping):
        raise SemanticChainError("semantic relation must be an object")
    _reject_forbidden_fields(relation, "semantic relation")
    _require_exact_keys(relation, RELATION_KEYS, "semantic relation")
    if relation.get("schema_version") != "1.0":
        raise SemanticChainError("unsupported semantic relation schema version")
    relation_id = relation.get("relation_id")
    if not isinstance(relation_id, str) or not RELATION_ID_RE.fullmatch(relation_id):
        raise SemanticChainError("invalid semantic relation id")
    snapshot_id = relation.get("knowledge_snapshot_id")
    if not isinstance(snapshot_id, str) or not SNAPSHOT_RE.fullmatch(snapshot_id):
        raise SemanticChainError("invalid knowledge snapshot id")
    relation_kind = relation.get("relation_kind")
    if relation_kind not in RELATION_RULES:
        raise SemanticChainError("unsupported semantic relation kind")

    expected_from, expected_to = RELATION_RULES[relation_kind]
    from_entity = _validate_entity(relation.get("from_entity"), expected_from)
    to_entity = _validate_entity(relation.get("to_entity"), expected_to)
    confidence = _validate_confidence(relation.get("confidence"))

    provenance = relation.get("provenance_record_ids")
    if (
        not isinstance(provenance, list)
        or not provenance
        or len(provenance) > MAX_PROVENANCE_PER_RELATION
        or len(set(provenance)) != len(provenance)
        or any(not isinstance(item, str) or not RECORD_RE.fullmatch(item) for item in provenance)
    ):
        raise SemanticChainError("invalid provenance record set")
    rationale = relation.get("rationale")
    if not isinstance(rationale, str) or not rationale.strip():
        raise SemanticChainError("mapping rationale is required")

    seed = _relation_seed(
        knowledge_snapshot_id=snapshot_id,
        relation_kind=relation_kind,
        from_entity=from_entity,
        to_entity=to_entity,
        confidence=confidence,
        provenance_record_ids=provenance,
        rationale=rationale.strip(),
    )
    if relation_id != f"sr_{_digest(seed)[:32]}":
        raise SemanticChainError("relation id does not match canonical relation content")
    return {"schema_version": "1.0", "relation_id": relation_id, **seed}


def _validated_relation_set(
    relations: Sequence[Mapping[str, Any]], knowledge_snapshot_id: str
) -> list[dict[str, Any]]:
    if (
        not isinstance(relations, Sequence)
        or isinstance(relations, (str, bytes))
        or len(relations) > MAX_RELATIONS
    ):
        raise SemanticChainError("semantic relation set exceeds the bounded contract")
    validated = [validate_relation(item) for item in relations]
    relation_ids = [item["relation_id"] for item in validated]
    if len(set(relation_ids)) != len(relation_ids):
        raise SemanticChainError("semantic relation ids must be unique")
    if any(item["knowledge_snapshot_id"] != knowledge_snapshot_id for item in validated):
        raise SemanticChainError("all semantic relations must belong to the requested snapshot")

    assertions: set[tuple[str, str, str]] = set()
    for item in validated:
        key = (
            item["relation_kind"],
            item["from_entity"]["id"],
            item["to_entity"]["id"],
        )
        if key in assertions:
            raise SemanticChainError(
                "duplicate semantic assertion must be reconciled before chain resolution"
            )
        assertions.add(key)
    return validated


def _candidate_view(relation: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "relation_id": relation["relation_id"],
        "to_entity": dict(relation["to_entity"]),
        "confidence": relation["confidence"],
        "provenance_record_ids": list(relation["provenance_record_ids"]),
    }


def resolve_chain(
    *,
    vulnerability_id: str,
    knowledge_snapshot_id: str,
    relations: Sequence[Mapping[str, Any]],
    minimum_confidence: float = 0.0,
) -> dict[str, Any]:
    if not isinstance(knowledge_snapshot_id, str) or not SNAPSHOT_RE.fullmatch(
        knowledge_snapshot_id
    ):
        raise SemanticChainError("knowledge_snapshot_id must be a canonical snapshot id")
    start = _validate_entity(
        {"type": "vulnerability", "id": vulnerability_id}, "vulnerability"
    )
    threshold = _validate_confidence(minimum_confidence, "minimum_confidence")
    validated = _validated_relation_set(relations, knowledge_snapshot_id)

    hops: list[dict[str, Any]] = []
    current = start
    gap: dict[str, Any] | None = None
    ambiguity: dict[str, Any] | None = None

    for stage, relation_kind in enumerate(CHAIN_ORDER, start=1):
        candidates = [
            item
            for item in validated
            if item["relation_kind"] == relation_kind
            and item["from_entity"] == current
        ]
        candidates.sort(
            key=lambda item: (
                item["to_entity"]["id"],
                item["relation_id"],
            )
        )

        if not candidates:
            gap = {
                "stage": stage,
                "relation_kind": relation_kind,
                "from_entity": dict(current),
                "reason": "NO_MAPPING_IN_SNAPSHOT",
            }
            status = "GAP"
            break
        if len(candidates) > 1:
            ambiguity = {
                "stage": stage,
                "relation_kind": relation_kind,
                "from_entity": dict(current),
                "reason": "MULTIPLE_MAPPINGS_IN_SNAPSHOT",
                "candidates": [_candidate_view(item) for item in candidates],
            }
            status = "AMBIGUOUS"
            break

        selected = candidates[0]
        hop = {
            "stage": stage,
            "relation_id": selected["relation_id"],
            "relation_kind": relation_kind,
            "from_entity": dict(selected["from_entity"]),
            "to_entity": dict(selected["to_entity"]),
            "confidence": selected["confidence"],
            "provenance_record_ids": list(selected["provenance_record_ids"]),
            "rationale": selected["rationale"],
        }
        hops.append(hop)
        current = dict(selected["to_entity"])
    else:
        status = "COMPLETE"

    chain_confidence = min((hop["confidence"] for hop in hops), default=None)
    quality = (
        "INCOMPLETE"
        if status != "COMPLETE"
        else "BELOW_THRESHOLD"
        if chain_confidence is not None and chain_confidence < threshold
        else "MEETS_THRESHOLD"
    )
    planning_recommendation = (
        "ADVISORY_CANDIDATE"
        if status == "COMPLETE" and quality == "MEETS_THRESHOLD"
        else "REVIEW_REQUIRED"
    )

    result_body = {
        "schema_version": "1.0",
        "knowledge_snapshot_id": knowledge_snapshot_id,
        "vulnerability_id": start["id"],
        "status": status,
        "hops": hops,
        "gap": gap,
        "ambiguity": ambiguity,
        "chain_confidence": chain_confidence,
        "minimum_confidence": threshold,
        "quality": quality,
        "planning_effect": "ADVISORY_ONLY",
        "planning_recommendation": planning_recommendation,
        "executable": False,
        "execution_authority": "NONE",
    }
    chain_id = f"sc_{_digest(result_body)[:32]}"
    return {"chain_id": chain_id, **result_body}
