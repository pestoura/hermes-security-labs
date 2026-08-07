from __future__ import annotations

import json
from pathlib import Path

import jsonschema
import pytest


ROOT = Path(__file__).resolve().parents[1] / "knowledge-fabric"
RELATION_SCHEMA = json.loads(
    (ROOT / "semantic-relation.schema.json").read_text(encoding="utf-8")
)
CHAIN_SCHEMA = json.loads(
    (ROOT / "semantic-chain.schema.json").read_text(encoding="utf-8")
)


def _relation() -> dict:
    return {
        "schema_version": "1.0",
        "relation_id": "sr_" + "1" * 32,
        "knowledge_snapshot_id": "ks_" + "a" * 32,
        "relation_kind": "VULNERABILITY_TO_CWE",
        "from_entity": {"type": "vulnerability", "id": "CVE-2026-12345"},
        "to_entity": {"type": "cwe", "id": "CWE-79"},
        "confidence": 0.8,
        "provenance_record_ids": ["kr_" + "1" * 32],
        "rationale": "reviewed mapping",
    }


def test_relation_schema_rejects_wrong_hop_direction() -> None:
    relation = _relation()
    relation["from_entity"] = {"type": "cwe", "id": "CWE-79"}
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(relation, RELATION_SCHEMA)


def test_relation_schema_rejects_noncanonical_framework_id() -> None:
    relation = _relation()
    relation["to_entity"] = {"type": "cwe", "id": "79"}
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(relation, RELATION_SCHEMA)


def test_chain_schema_rejects_complete_chain_with_gap() -> None:
    chain = {
        "chain_id": "sc_" + "1" * 32,
        "schema_version": "1.0",
        "knowledge_snapshot_id": "ks_" + "a" * 32,
        "vulnerability_id": "CVE-2026-12345",
        "status": "COMPLETE",
        "hops": [],
        "gap": {
            "stage": 1,
            "relation_kind": "VULNERABILITY_TO_CWE",
            "from_entity": {"type": "vulnerability", "id": "CVE-2026-12345"},
            "reason": "NO_MAPPING_IN_SNAPSHOT",
        },
        "ambiguity": None,
        "chain_confidence": None,
        "minimum_confidence": 0.0,
        "quality": "INCOMPLETE",
        "planning_effect": "ADVISORY_ONLY",
        "planning_recommendation": "REVIEW_REQUIRED",
        "executable": False,
        "execution_authority": "NONE",
    }
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(chain, CHAIN_SCHEMA)
