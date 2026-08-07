from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any, Mapping

ENTITY_TYPES = {
    "cve", "cpe", "purl", "cwe", "capec", "attack", "atlas", "kev", "epss",
    "csaf", "vex", "oscal", "owasp", "asset", "sbom",
}


class KnowledgeError(ValueError):
    """Fail-closed security knowledge contract violation."""


def digest(value: Mapping[str, Any]) -> str:
    raw = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()
    return hashlib.sha256(raw).hexdigest()


@dataclass(frozen=True)
class Provenance:
    source_name: str
    source_version: str
    retrieved_at: str
    locator: str

    def as_dict(self) -> dict[str, str]:
        if not all((self.source_name, self.source_version, self.retrieved_at, self.locator)):
            raise KnowledgeError("complete provenance is required")
        return {
            "name": self.source_name,
            "version": self.source_version,
            "retrieved_at": self.retrieved_at,
            "locator": self.locator,
        }


def build_record(
    *,
    entity_type: str,
    entity_id: str,
    provenance: Provenance,
    raw_sha256: str,
    ingested_at: str,
) -> dict[str, Any]:
    if entity_type not in ENTITY_TYPES:
        raise KnowledgeError("unsupported entity type")
    if not entity_id:
        raise KnowledgeError("entity id is required")
    if len(raw_sha256) != 64 or any(c not in "0123456789abcdef" for c in raw_sha256):
        raise KnowledgeError("raw_sha256 must be lowercase sha256")
    source = provenance.as_dict()
    seed = {"entity_type": entity_type, "entity_id": entity_id, "source": source, "raw_sha256": raw_sha256}
    return {
        "schema_version": "1.0",
        "record_id": f"kr_{digest(seed)[:32]}",
        "entity": {"type": entity_type, "id": entity_id},
        "source": source,
        "ingested_at": ingested_at,
        "raw_sha256": raw_sha256,
        "immutable_raw": True,
    }


def derive_relation(
    *,
    source_record_ids: list[str],
    relation: str,
    from_entity: str,
    to_entity: str,
    confidence: float,
    rationale: str,
) -> dict[str, Any]:
    if not source_record_ids or len(set(source_record_ids)) != len(source_record_ids):
        raise KnowledgeError("derivation requires unique provenance records")
    if not relation or not from_entity or not to_entity or not rationale:
        raise KnowledgeError("complete derivation metadata is required")
    if isinstance(confidence, bool) or not isinstance(confidence, (int, float)) or not 0.0 <= confidence <= 1.0:
        raise KnowledgeError("confidence must be between 0 and 1")
    return {
        "relation": relation,
        "from": from_entity,
        "to": to_entity,
        "confidence": float(confidence),
        "provenance_record_ids": sorted(source_record_ids),
        "rationale": rationale,
    }


def persist_conflict(*, key: str, assertions: list[Mapping[str, Any]]) -> dict[str, Any]:
    if not key or len(assertions) < 2:
        raise KnowledgeError("conflict requires a key and at least two assertions")
    sources = [assertion.get("source_record_id") for assertion in assertions]
    if any(not source for source in sources) or len(set(sources)) != len(sources):
        raise KnowledgeError("conflicting assertions require distinct provenance")
    return {
        "key": key,
        "status": "unresolved",
        "assertions": [dict(item) for item in assertions],
        "selected_assertion": None,
    }


def resolve_conflict(conflict: Mapping[str, Any], *, source_record_id: str, policy_id: str) -> dict[str, Any]:
    if conflict.get("status") != "unresolved":
        raise KnowledgeError("only unresolved conflicts may be resolved")
    assertions = conflict.get("assertions")
    if not isinstance(assertions, list) or source_record_id not in {a.get("source_record_id") for a in assertions if isinstance(a, Mapping)}:
        raise KnowledgeError("selected assertion must exist in conflict")
    if not policy_id:
        raise KnowledgeError("explicit precedence policy is required")
    value = dict(conflict)
    value["status"] = "resolved"
    value["selected_assertion"] = source_record_id
    value["precedence_policy_id"] = policy_id
    return value


def applicable(*, selectors: Mapping[str, str]) -> bool:
    allowed = {"asset", "sbom", "cpe", "purl"}
    if not selectors or set(selectors).difference(allowed):
        return False
    return all(bool(value) for value in selectors.values())
