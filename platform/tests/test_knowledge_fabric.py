from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import jsonschema
import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
KNOWLEDGE_DIR = ROOT / "platform" / "knowledge-fabric"

spec = importlib.util.spec_from_file_location("knowledge_fabric", KNOWLEDGE_DIR / "knowledge_fabric.py")
assert spec and spec.loader
module = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = module
spec.loader.exec_module(module)

KnowledgeError = module.KnowledgeError
Provenance = module.Provenance
applicable = module.applicable
build_record = module.build_record
derive_relation = module.derive_relation
persist_conflict = module.persist_conflict
resolve_conflict = module.resolve_conflict


def _record():
    return build_record(
        entity_type="cve",
        entity_id="CVE-2099-0001",
        provenance=Provenance("NVD", "2099.1", "2026-08-07T00:00:00Z", "source://nvd/CVE-2099-0001"),
        raw_sha256="a" * 64,
        ingested_at="2026-08-07T00:00:01Z",
    )


def test_canonical_record_validates_against_schema() -> None:
    schema = json.loads((KNOWLEDGE_DIR / "knowledge-record.schema.json").read_text())
    jsonschema.Draft202012Validator(schema).validate(_record())


def test_raw_record_is_explicitly_immutable_and_provenanced() -> None:
    record = _record()
    assert record["immutable_raw"] is True
    assert set(record["source"]) == {"name", "version", "retrieved_at", "locator"}
    assert record["raw_sha256"] == "a" * 64


def test_derivation_requires_provenance_rationale_and_bounded_confidence() -> None:
    relation = derive_relation(
        source_record_ids=[_record()["record_id"]],
        relation="maps_to",
        from_entity="CVE-2099-0001",
        to_entity="CWE-79",
        confidence=0.8,
        rationale="synthetic mapping evidence",
    )
    assert relation["confidence"] == 0.8
    with pytest.raises(KnowledgeError):
        derive_relation(source_record_ids=[], relation="maps_to", from_entity="a", to_entity="b", confidence=0.8, rationale="x")
    with pytest.raises(KnowledgeError):
        derive_relation(source_record_ids=["kr_a"], relation="maps_to", from_entity="a", to_entity="b", confidence=1.1, rationale="x")


def test_conflicts_are_persisted_unresolved_and_never_silently_won() -> None:
    conflict_key = "CVE-2099-0001" + ".severity"
    conflict = persist_conflict(
        key=conflict_key,
        assertions=[
            {"source_record_id": "kr_a", "value": "high"},
            {"source_record_id": "kr_b", "value": "critical"},
        ],
    )
    assert conflict["status"] == "unresolved"
    assert conflict["selected_assertion"] is None
    with pytest.raises(KnowledgeError):
        resolve_conflict(conflict, source_record_id="kr_a", policy_id="")
    resolved = resolve_conflict(conflict, source_record_id="kr_b", policy_id="precedence/nvd-v1")
    assert resolved["selected_assertion"] == "kr_b"
    assert resolved["precedence_policy_id"] == "precedence/nvd-v1"


def test_applicability_is_limited_to_asset_sbom_cpe_and_purl() -> None:
    assert applicable(selectors={"cpe": "cpe:2.3:a:synthetic"}) is True
    assert applicable(selectors={"purl": "pkg:pypi/example@1.0"}) is True
    assert applicable(selectors={"hostname": "example"}) is False
    assert applicable(selectors={}) is False


def test_external_sync_and_graph_store_are_not_claimed() -> None:
    policy = yaml.safe_load((KNOWLEDGE_DIR / "source-policy.yaml").read_text())
    assert policy["conflicts"]["silent_resolution_allowed"] is False
    assert policy["precedence"]["default_winner"] == "none"
    assert policy["runtime_status"] == {
        "external_sync": "NOT_RUN",
        "taxii_sync": "NOT_RUN",
        "nvd_sync": "NOT_RUN",
        "kev_sync": "NOT_RUN",
        "epss_sync": "NOT_RUN",
        "graph_store": "NOT_IMPLEMENTED",
    }
