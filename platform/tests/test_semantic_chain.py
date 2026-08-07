from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import jsonschema
import pytest


ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "knowledge-fabric" / "semantic_chain.py"
RELATION_SCHEMA = ROOT / "knowledge-fabric" / "semantic-relation.schema.json"
CHAIN_SCHEMA = ROOT / "knowledge-fabric" / "semantic-chain.schema.json"

spec = importlib.util.spec_from_file_location("semantic_chain", MODULE_PATH)
assert spec and spec.loader
sc = importlib.util.module_from_spec(spec)
spec.loader.exec_module(sc)

SNAPSHOT = "ks_" + "a" * 32
OTHER_SNAPSHOT = "ks_" + "b" * 32
P1 = "kr_" + "1" * 32
P2 = "kr_" + "2" * 32
P3 = "kr_" + "3" * 32
P4 = "kr_" + "4" * 32


def _relation(
    kind: str,
    from_type: str,
    from_id: str,
    to_type: str,
    to_id: str,
    confidence: float,
    provenance: list[str],
    *,
    snapshot: str = SNAPSHOT,
) -> dict:
    return sc.build_relation(
        knowledge_snapshot_id=snapshot,
        relation_kind=kind,
        from_entity={"type": from_type, "id": from_id},
        to_entity={"type": to_type, "id": to_id},
        confidence=confidence,
        provenance_record_ids=provenance,
        rationale=f"reviewed mapping {from_id} -> {to_id}",
    )


def _complete_relations() -> list[dict]:
    return [
        _relation(
            "VULNERABILITY_TO_CWE",
            "vulnerability",
            "CVE-2026-12345",
            "cwe",
            "CWE-79",
            0.92,
            [P1],
        ),
        _relation(
            "CWE_TO_CAPEC",
            "cwe",
            "CWE-79",
            "capec",
            "CAPEC-63",
            0.81,
            [P2],
        ),
        _relation(
            "CAPEC_TO_ATTACK",
            "capec",
            "CAPEC-63",
            "attack",
            "T1059.007",
            0.74,
            [P3],
        ),
    ]


def test_relation_and_chain_outputs_validate_against_strict_schemas() -> None:
    relation_schema = json.loads(RELATION_SCHEMA.read_text(encoding="utf-8"))
    chain_schema = json.loads(CHAIN_SCHEMA.read_text(encoding="utf-8"))
    relations = _complete_relations()
    for relation in relations:
        jsonschema.validate(relation, relation_schema)

    chain = sc.resolve_chain(
        vulnerability_id="CVE-2026-12345",
        knowledge_snapshot_id=SNAPSHOT,
        relations=relations,
        minimum_confidence=0.7,
    )
    jsonschema.validate(chain, chain_schema)


def test_complete_chain_is_deterministic_independent_of_input_order() -> None:
    relations = _complete_relations()
    forward = sc.resolve_chain(
        vulnerability_id="CVE-2026-12345",
        knowledge_snapshot_id=SNAPSHOT,
        relations=relations,
        minimum_confidence=0.7,
    )
    reverse = sc.resolve_chain(
        vulnerability_id="CVE-2026-12345",
        knowledge_snapshot_id=SNAPSHOT,
        relations=list(reversed(relations)),
        minimum_confidence=0.7,
    )
    assert forward == reverse
    assert forward["status"] == "COMPLETE"
    assert [hop["relation_kind"] for hop in forward["hops"]] == list(sc.CHAIN_ORDER)
    assert forward["hops"][-1]["to_entity"] == {"type": "attack", "id": "T1059.007"}


def test_chain_confidence_is_the_weakest_hop_not_an_average() -> None:
    chain = sc.resolve_chain(
        vulnerability_id="CVE-2026-12345",
        knowledge_snapshot_id=SNAPSHOT,
        relations=_complete_relations(),
        minimum_confidence=0.7,
    )
    assert chain["chain_confidence"] == 0.74
    assert chain["quality"] == "MEETS_THRESHOLD"
    assert chain["planning_recommendation"] == "ADVISORY_CANDIDATE"


def test_low_confidence_complete_chain_requires_review() -> None:
    chain = sc.resolve_chain(
        vulnerability_id="CVE-2026-12345",
        knowledge_snapshot_id=SNAPSHOT,
        relations=_complete_relations(),
        minimum_confidence=0.8,
    )
    assert chain["status"] == "COMPLETE"
    assert chain["chain_confidence"] == 0.74
    assert chain["quality"] == "BELOW_THRESHOLD"
    assert chain["planning_recommendation"] == "REVIEW_REQUIRED"


def test_missing_first_hop_is_a_first_class_gap() -> None:
    chain = sc.resolve_chain(
        vulnerability_id="CVE-2026-12345",
        knowledge_snapshot_id=SNAPSHOT,
        relations=[],
    )
    assert chain["status"] == "GAP"
    assert chain["hops"] == []
    assert chain["gap"] == {
        "stage": 1,
        "relation_kind": "VULNERABILITY_TO_CWE",
        "from_entity": {"type": "vulnerability", "id": "CVE-2026-12345"},
        "reason": "NO_MAPPING_IN_SNAPSHOT",
    }
    assert chain["ambiguity"] is None
    assert chain["quality"] == "INCOMPLETE"


def test_missing_later_hop_preserves_only_evidenced_prefix() -> None:
    relations = _complete_relations()[:2]
    chain = sc.resolve_chain(
        vulnerability_id="CVE-2026-12345",
        knowledge_snapshot_id=SNAPSHOT,
        relations=relations,
    )
    assert chain["status"] == "GAP"
    assert len(chain["hops"]) == 2
    assert chain["gap"]["stage"] == 3
    assert chain["gap"]["from_entity"] == {"type": "capec", "id": "CAPEC-63"}


def test_multiple_targets_are_reported_as_ambiguity_without_selection() -> None:
    relations = _complete_relations()
    relations.append(
        _relation(
            "VULNERABILITY_TO_CWE",
            "vulnerability",
            "CVE-2026-12345",
            "cwe",
            "CWE-80",
            0.99,
            [P4],
        )
    )
    chain = sc.resolve_chain(
        vulnerability_id="CVE-2026-12345",
        knowledge_snapshot_id=SNAPSHOT,
        relations=relations,
    )
    assert chain["status"] == "AMBIGUOUS"
    assert chain["hops"] == []
    assert chain["gap"] is None
    assert chain["ambiguity"]["stage"] == 1
    assert [
        item["to_entity"]["id"] for item in chain["ambiguity"]["candidates"]
    ] == ["CWE-79", "CWE-80"]
    assert chain["planning_recommendation"] == "REVIEW_REQUIRED"


def test_higher_confidence_candidate_is_not_silently_selected() -> None:
    relations = [
        _relation(
            "VULNERABILITY_TO_CWE",
            "vulnerability",
            "CVE-2026-12345",
            "cwe",
            "CWE-79",
            0.51,
            [P1],
        ),
        _relation(
            "VULNERABILITY_TO_CWE",
            "vulnerability",
            "CVE-2026-12345",
            "cwe",
            "CWE-80",
            0.99,
            [P2],
        ),
    ]
    chain = sc.resolve_chain(
        vulnerability_id="CVE-2026-12345",
        knowledge_snapshot_id=SNAPSHOT,
        relations=relations,
    )
    assert chain["status"] == "AMBIGUOUS"
    assert len(chain["ambiguity"]["candidates"]) == 2
    assert chain["hops"] == []


def test_snapshot_mixing_fails_closed() -> None:
    relations = _complete_relations()
    relations[1] = _relation(
        "CWE_TO_CAPEC",
        "cwe",
        "CWE-79",
        "capec",
        "CAPEC-63",
        0.81,
        [P2],
        snapshot=OTHER_SNAPSHOT,
    )
    with pytest.raises(sc.SemanticChainError, match="requested snapshot"):
        sc.resolve_chain(
            vulnerability_id="CVE-2026-12345",
            knowledge_snapshot_id=SNAPSHOT,
            relations=relations,
        )


def test_duplicate_semantic_assertion_requires_reconciliation() -> None:
    first = _relation(
        "VULNERABILITY_TO_CWE",
        "vulnerability",
        "CVE-2026-12345",
        "cwe",
        "CWE-79",
        0.7,
        [P1],
    )
    second = _relation(
        "VULNERABILITY_TO_CWE",
        "vulnerability",
        "CVE-2026-12345",
        "cwe",
        "CWE-79",
        0.8,
        [P2],
    )
    with pytest.raises(sc.SemanticChainError, match="reconciled"):
        sc.resolve_chain(
            vulnerability_id="CVE-2026-12345",
            knowledge_snapshot_id=SNAPSHOT,
            relations=[first, second],
        )


def test_relation_type_direction_is_enforced() -> None:
    with pytest.raises(sc.SemanticChainError, match="entity type must be"):
        _relation(
            "CWE_TO_CAPEC",
            "vulnerability",
            "CVE-2026-12345",
            "capec",
            "CAPEC-63",
            0.8,
            [P1],
        )


def test_forged_relation_id_is_rejected() -> None:
    relation = _complete_relations()[0]
    relation["relation_id"] = "sr_" + "f" * 32
    with pytest.raises(sc.SemanticChainError, match="canonical relation content"):
        sc.validate_relation(relation)


def test_extra_authority_field_is_rejected() -> None:
    relation = _complete_relations()[0]
    relation["authorization_ref"] = "forbidden"
    with pytest.raises(sc.SemanticChainError, match="authority"):
        sc.validate_relation(relation)


def test_boolean_confidence_is_rejected() -> None:
    with pytest.raises(sc.SemanticChainError, match="confidence"):
        sc.build_relation(
            knowledge_snapshot_id=SNAPSHOT,
            relation_kind="VULNERABILITY_TO_CWE",
            from_entity={"type": "vulnerability", "id": "CVE-2026-12345"},
            to_entity={"type": "cwe", "id": "CWE-79"},
            confidence=True,
            provenance_record_ids=[P1],
            rationale="invalid boolean confidence",
        )


def test_duplicate_provenance_is_rejected() -> None:
    with pytest.raises(sc.SemanticChainError, match="unique"):
        sc.build_relation(
            knowledge_snapshot_id=SNAPSHOT,
            relation_kind="VULNERABILITY_TO_CWE",
            from_entity={"type": "vulnerability", "id": "CVE-2026-12345"},
            to_entity={"type": "cwe", "id": "CWE-79"},
            confidence=0.8,
            provenance_record_ids=[P1, P1],
            rationale="duplicate provenance",
        )


def test_invalid_framework_identifiers_are_rejected() -> None:
    with pytest.raises(sc.SemanticChainError, match="invalid cwe identifier"):
        _relation(
            "VULNERABILITY_TO_CWE",
            "vulnerability",
            "CVE-2026-12345",
            "cwe",
            "79",
            0.8,
            [P1],
        )


def test_relation_set_is_bounded() -> None:
    relation = _complete_relations()[0]
    with pytest.raises(sc.SemanticChainError, match="bounded"):
        sc.resolve_chain(
            vulnerability_id="CVE-2026-12345",
            knowledge_snapshot_id=SNAPSHOT,
            relations=[relation] * (sc.MAX_RELATIONS + 1),
        )


def test_semantic_chain_never_grants_execution_authority() -> None:
    for relations in (_complete_relations(), [], _complete_relations()[:2]):
        chain = sc.resolve_chain(
            vulnerability_id="CVE-2026-12345",
            knowledge_snapshot_id=SNAPSHOT,
            relations=relations,
        )
        assert chain["planning_effect"] == "ADVISORY_ONLY"
        assert chain["executable"] is False
        assert chain["execution_authority"] == "NONE"


def test_chain_id_changes_when_threshold_changes_decision_context() -> None:
    low = sc.resolve_chain(
        vulnerability_id="CVE-2026-12345",
        knowledge_snapshot_id=SNAPSHOT,
        relations=_complete_relations(),
        minimum_confidence=0.7,
    )
    high = sc.resolve_chain(
        vulnerability_id="CVE-2026-12345",
        knowledge_snapshot_id=SNAPSHOT,
        relations=_complete_relations(),
        minimum_confidence=0.8,
    )
    assert low["chain_id"] != high["chain_id"]
    assert low["planning_recommendation"] == "ADVISORY_CANDIDATE"
    assert high["planning_recommendation"] == "REVIEW_REQUIRED"
