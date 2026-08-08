from __future__ import annotations

import importlib.util
import json
from copy import deepcopy
from pathlib import Path

import jsonschema
import pytest


ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "knowledge-fabric" / "control_knowledge.py"
CATALOGUE_SCHEMA = ROOT / "knowledge-fabric" / "control-catalogue.schema.json"
MAPPING_SCHEMA = ROOT / "knowledge-fabric" / "control-mapping.schema.json"
PROJECTION_SCHEMA = ROOT / "knowledge-fabric" / "control-projection.schema.json"

spec = importlib.util.spec_from_file_location("control_knowledge", MODULE_PATH)
assert spec and spec.loader
ctrl = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ctrl)

P1 = "kr_" + "1" * 32
P2 = "kr_" + "2" * 32
P3 = "kr_" + "3" * 32
E1 = "ev_" + "1" * 32
E2 = "ev_" + "2" * 32


def _catalogue() -> dict:
    return ctrl.build_catalogue(
        provider="NIST",
        catalogue_name="SP 800-53",
        catalogue_version="Rev. 5 supplied snapshot",
        published_at="2026-01-01T00:00:00Z",
        source_locator="snapshot:nist-sp800-53-rev5-reviewed",
        controls=[
            {
                "control_id": "AC-2",
                "title": "Account Management",
                "objective": "Supplied control objective for test fixture.",
                "provenance_record_ids": [P1],
            },
            {
                "control_id": "AU-2",
                "title": "Event Logging",
                "objective": "Supplied control objective for test fixture.",
                "provenance_record_ids": [P2],
            },
        ],
    )


def _mapping(catalogue: dict, *, control: str = "AC-2", kind: str = "attack", ref: str = "T1078", confidence: float = 0.8, provenance: list[str] | None = None) -> dict:
    return ctrl.build_mapping(
        catalogue=catalogue,
        control_id=control,
        target_kind=kind,
        target_ref=ref,
        confidence=confidence,
        provenance_record_ids=provenance or [P3],
        rationale="Reviewed advisory mapping for validation coverage.",
    )


def test_catalogue_mapping_and_projection_validate_against_strict_schemas() -> None:
    catalogue_schema = json.loads(CATALOGUE_SCHEMA.read_text(encoding="utf-8"))
    mapping_schema = json.loads(MAPPING_SCHEMA.read_text(encoding="utf-8"))
    projection_schema = json.loads(PROJECTION_SCHEMA.read_text(encoding="utf-8"))
    catalogue = _catalogue()
    mapping = _mapping(catalogue)
    projection = ctrl.project_control(
        catalogue=catalogue,
        control_id="AC-2",
        mappings=[mapping],
        observations=[{"mapping_id": mapping["mapping_id"], "state": "OBSERVED", "evidence_ids": [E1]}],
    )
    jsonschema.validate(catalogue, catalogue_schema)
    jsonschema.validate(mapping, mapping_schema)
    jsonschema.validate(projection, projection_schema)


def test_catalogue_identity_is_deterministic_independent_of_control_order() -> None:
    catalogue = _catalogue()
    reverse = ctrl.build_catalogue(
        provider="NIST",
        catalogue_name=catalogue["catalogue_name"],
        catalogue_version=catalogue["catalogue_version"],
        published_at=catalogue["published_at"],
        source_locator=catalogue["source_locator"],
        controls=list(reversed(catalogue["controls"])),
    )
    assert catalogue == reverse


def test_catalogue_is_supplied_snapshot_only() -> None:
    catalogue = _catalogue()
    assert catalogue["source_origin"] == "SUPPLIED_SNAPSHOT"
    assert catalogue["external_fetch"] == "NOT_PERFORMED"
    forged = deepcopy(catalogue)
    forged["external_fetch"] = "PERFORMED"
    with pytest.raises(ctrl.ControlKnowledgeError, match="external control fetch"):
        ctrl.validate_catalogue(forged)


def test_mapping_requires_control_present_in_catalogue() -> None:
    with pytest.raises(ctrl.ControlKnowledgeError, match="not present"):
        _mapping(_catalogue(), control="IA-5")


def test_mapping_target_kind_and_format_are_fail_closed() -> None:
    catalogue = _catalogue()
    with pytest.raises(ctrl.ControlKnowledgeError, match="canonical ATT&CK"):
        _mapping(catalogue, kind="attack", ref="1078")
    with pytest.raises(ctrl.ControlKnowledgeError, match="runbook:"):
        _mapping(catalogue, kind="runbook", ref="RB-1")
    with pytest.raises(ctrl.ControlKnowledgeError, match="evidence:"):
        _mapping(catalogue, kind="evidence_requirement", ref="log-review")


def test_boolean_confidence_and_duplicate_provenance_are_rejected() -> None:
    catalogue = _catalogue()
    with pytest.raises(ctrl.ControlKnowledgeError, match="confidence"):
        _mapping(catalogue, confidence=True)
    with pytest.raises(ctrl.ControlKnowledgeError, match="provenance"):
        _mapping(catalogue, provenance=[P3, P3])


def test_unmapped_control_never_becomes_pass() -> None:
    projection = ctrl.project_control(
        catalogue=_catalogue(),
        control_id="AC-2",
        mappings=[],
        observations=[],
    )
    assert projection["projection_state"] == "UNMAPPED"
    assert projection["mapping_count"] == 0
    assert projection["compliance_verdict"] == "NOT_EVALUATED"
    assert projection["certification_claim"] == "NONE"
    assert "PASS" not in json.dumps(projection)


def test_mapped_without_observation_is_not_evidence_or_pass() -> None:
    catalogue = _catalogue()
    mapping = _mapping(catalogue)
    projection = ctrl.project_control(
        catalogue=catalogue,
        control_id="AC-2",
        mappings=[mapping],
        observations=[],
    )
    assert projection["projection_state"] == "MAPPED_NO_OBSERVATION"
    assert projection["evidence_ids"] == []
    assert projection["compliance_verdict"] == "NOT_EVALUATED"


def test_observed_mapping_projects_evidence_but_not_control_effectiveness() -> None:
    catalogue = _catalogue()
    mapping = _mapping(catalogue)
    projection = ctrl.project_control(
        catalogue=catalogue,
        control_id="AC-2",
        mappings=[mapping],
        observations=[{"mapping_id": mapping["mapping_id"], "state": "OBSERVED", "evidence_ids": [E2, E1]}],
    )
    assert projection["projection_state"] == "MAPPED_EVIDENCE_PRESENT"
    assert projection["evidence_ids"] == [E1, E2]
    assert projection["coverage_semantics"] == "MAPPED_VALIDATION_COVERAGE_ONLY"
    assert projection["compliance_verdict"] == "NOT_EVALUATED"
    assert projection["certification_claim"] == "NONE"
    assert "EVIDENCE_DOES_NOT_ESTABLISH_CONTROL_EFFECTIVENESS_BY_ITSELF" in projection["limitations"]


def test_low_mapping_confidence_requires_review() -> None:
    catalogue = _catalogue()
    mapping = _mapping(catalogue, confidence=0.4)
    projection = ctrl.project_control(
        catalogue=catalogue,
        control_id="AC-2",
        mappings=[mapping],
        observations=[],
        minimum_confidence=0.5,
    )
    assert projection["projection_state"] == "REVIEW_REQUIRED"
    assert projection["mapping_confidence"] == 0.4


def test_inconclusive_or_not_observed_requires_review() -> None:
    catalogue = _catalogue()
    mapping = _mapping(catalogue)
    for state in ("INCONCLUSIVE", "NOT_OBSERVED"):
        projection = ctrl.project_control(
            catalogue=catalogue,
            control_id="AC-2",
            mappings=[mapping],
            observations=[{"mapping_id": mapping["mapping_id"], "state": state, "evidence_ids": []}],
        )
        assert projection["projection_state"] == "REVIEW_REQUIRED"
        assert projection["compliance_verdict"] == "NOT_EVALUATED"


def test_not_run_is_mapped_no_observation_not_pass() -> None:
    catalogue = _catalogue()
    mapping = _mapping(catalogue)
    projection = ctrl.project_control(
        catalogue=catalogue,
        control_id="AC-2",
        mappings=[mapping],
        observations=[{"mapping_id": mapping["mapping_id"], "state": "NOT_RUN", "evidence_ids": []}],
    )
    assert projection["projection_state"] == "MAPPED_NO_OBSERVATION"
    assert projection["compliance_verdict"] == "NOT_EVALUATED"


def test_only_observed_may_carry_evidence() -> None:
    catalogue = _catalogue()
    mapping = _mapping(catalogue)
    with pytest.raises(ctrl.ControlKnowledgeError, match="only OBSERVED"):
        ctrl.project_control(
            catalogue=catalogue,
            control_id="AC-2",
            mappings=[mapping],
            observations=[{"mapping_id": mapping["mapping_id"], "state": "NOT_RUN", "evidence_ids": [E1]}],
        )
    with pytest.raises(ctrl.ControlKnowledgeError, match="OBSERVED requires"):
        ctrl.project_control(
            catalogue=catalogue,
            control_id="AC-2",
            mappings=[mapping],
            observations=[{"mapping_id": mapping["mapping_id"], "state": "OBSERVED", "evidence_ids": []}],
        )


def test_observation_cannot_reference_mapping_for_another_control() -> None:
    catalogue = _catalogue()
    ac_mapping = _mapping(catalogue, control="AC-2")
    au_mapping = _mapping(catalogue, control="AU-2", kind="evidence_requirement", ref="evidence:audit-log")
    with pytest.raises(ctrl.ControlKnowledgeError, match="outside projected control"):
        ctrl.project_control(
            catalogue=catalogue,
            control_id="AC-2",
            mappings=[ac_mapping, au_mapping],
            observations=[{"mapping_id": au_mapping["mapping_id"], "state": "OBSERVED", "evidence_ids": [E1]}],
        )


def test_mapping_from_other_catalogue_fails_closed() -> None:
    catalogue = _catalogue()
    other = ctrl.build_catalogue(
        provider="NIST",
        catalogue_name="SP 800-53",
        catalogue_version="Different supplied snapshot",
        published_at="2026-02-01T00:00:00Z",
        source_locator="snapshot:nist-other",
        controls=catalogue["controls"],
    )
    mapping = _mapping(other)
    with pytest.raises(ctrl.ControlKnowledgeError, match="supplied catalogue"):
        ctrl.project_control(
            catalogue=catalogue,
            control_id="AC-2",
            mappings=[mapping],
            observations=[],
        )


def test_duplicate_mapping_and_observation_ids_fail_closed() -> None:
    catalogue = _catalogue()
    mapping = _mapping(catalogue)
    with pytest.raises(ctrl.ControlKnowledgeError, match="mapping ids must be unique"):
        ctrl.project_control(
            catalogue=catalogue,
            control_id="AC-2",
            mappings=[mapping, deepcopy(mapping)],
            observations=[],
        )
    observation = {"mapping_id": mapping["mapping_id"], "state": "NOT_RUN", "evidence_ids": []}
    with pytest.raises(ctrl.ControlKnowledgeError, match="one observation"):
        ctrl.project_control(
            catalogue=catalogue,
            control_id="AC-2",
            mappings=[mapping],
            observations=[observation, deepcopy(observation)],
        )


def test_authority_secret_or_compliance_fields_fail_closed() -> None:
    catalogue = _catalogue()
    forged = deepcopy(catalogue)
    forged["compliance_status"] = "pass"
    with pytest.raises(ctrl.ControlKnowledgeError, match="compliance"):
        ctrl.validate_catalogue(forged)

    mapping = _mapping(catalogue)
    forged_mapping = deepcopy(mapping)
    forged_mapping["authorization_ref"] = "forbidden"
    with pytest.raises(ctrl.ControlKnowledgeError, match="authority"):
        ctrl.validate_mapping(forged_mapping)


def test_projection_never_grants_authority_or_compliance_claim() -> None:
    catalogue = _catalogue()
    mapping = _mapping(catalogue)
    projection = ctrl.project_control(
        catalogue=catalogue,
        control_id="AC-2",
        mappings=[mapping],
        observations=[{"mapping_id": mapping["mapping_id"], "state": "OBSERVED", "evidence_ids": [E1]}],
    )
    assert projection["planning_effect"] == "ADVISORY_ONLY"
    assert projection["execution_authority"] == "NONE"
    assert projection["compliance_verdict"] == "NOT_EVALUATED"
    assert projection["certification_claim"] == "NONE"
