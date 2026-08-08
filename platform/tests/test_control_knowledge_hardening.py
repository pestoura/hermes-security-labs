from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "knowledge-fabric" / "control_knowledge.py"

spec = importlib.util.spec_from_file_location("control_knowledge_hardening", MODULE_PATH)
assert spec and spec.loader
ctrl = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ctrl)

P1 = "kr_" + "1" * 32
P2 = "kr_" + "2" * 32
P3 = "kr_" + "3" * 32
P4 = "kr_" + "4" * 32
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


def _mapping(catalogue: dict, *, kind: str, ref: str, provenance: str) -> dict:
    return ctrl.build_mapping(
        catalogue=catalogue,
        control_id="AC-2",
        target_kind=kind,
        target_ref=ref,
        confidence=0.8,
        provenance_record_ids=[provenance],
        rationale="Reviewed mapping for control-oriented validation coverage.",
    )


def test_canonical_mapping_for_unknown_control_fails_closed() -> None:
    catalogue = _catalogue()
    seed = {
        "control_catalogue_id": catalogue["catalogue_id"],
        "control_id": "IA-5",
        "target_kind": "attack",
        "target_ref": "T1078",
        "confidence": 0.8,
        "provenance_record_ids": [P3],
        "rationale": "Structurally valid but the control is absent from the supplied catalogue.",
    }
    mapping = {
        "schema_version": "1.0",
        "mapping_id": f"ctrlmap_{ctrl._digest(seed)[:32]}",
        **seed,
    }
    assert ctrl.validate_mapping(mapping)["control_id"] == "IA-5"

    with pytest.raises(ctrl.ControlKnowledgeError, match="not present in supplied catalogue"):
        ctrl.project_control(
            catalogue=catalogue,
            control_id="AC-2",
            mappings=[mapping],
            observations=[],
        )


def test_partial_observation_requires_review_instead_of_positive_evidence_state() -> None:
    catalogue = _catalogue()
    attack_mapping = _mapping(
        catalogue,
        kind="attack",
        ref="T1078",
        provenance=P3,
    )
    evidence_mapping = _mapping(
        catalogue,
        kind="evidence_requirement",
        ref="evidence:account-lifecycle",
        provenance=P4,
    )

    projection = ctrl.project_control(
        catalogue=catalogue,
        control_id="AC-2",
        mappings=[attack_mapping, evidence_mapping],
        observations=[
            {
                "mapping_id": attack_mapping["mapping_id"],
                "state": "OBSERVED",
                "evidence_ids": [E1],
            }
        ],
    )

    assert projection["projection_state"] == "REVIEW_REQUIRED"
    assert projection["evidence_ids"] == [E1]
    assert projection["compliance_verdict"] == "NOT_EVALUATED"
    assert projection["certification_claim"] == "NONE"


def test_all_mappings_observed_may_report_mapped_evidence_only() -> None:
    catalogue = _catalogue()
    attack_mapping = _mapping(
        catalogue,
        kind="attack",
        ref="T1078",
        provenance=P3,
    )
    evidence_mapping = _mapping(
        catalogue,
        kind="evidence_requirement",
        ref="evidence:account-lifecycle",
        provenance=P4,
    )

    projection = ctrl.project_control(
        catalogue=catalogue,
        control_id="AC-2",
        mappings=[attack_mapping, evidence_mapping],
        observations=[
            {
                "mapping_id": attack_mapping["mapping_id"],
                "state": "OBSERVED",
                "evidence_ids": [E1],
            },
            {
                "mapping_id": evidence_mapping["mapping_id"],
                "state": "OBSERVED",
                "evidence_ids": [E2],
            },
        ],
    )

    assert projection["projection_state"] == "MAPPED_EVIDENCE_PRESENT"
    assert projection["evidence_ids"] == [E1, E2]
    assert projection["coverage_semantics"] == "MAPPED_VALIDATION_COVERAGE_ONLY"
    assert projection["compliance_verdict"] == "NOT_EVALUATED"
    assert projection["execution_authority"] == "NONE"


def test_observation_input_must_be_a_bounded_sequence_not_text() -> None:
    catalogue = _catalogue()
    mapping = _mapping(
        catalogue,
        kind="attack",
        ref="T1078",
        provenance=P3,
    )
    with pytest.raises(ctrl.ControlKnowledgeError, match="bounded contract"):
        ctrl.project_control(
            catalogue=catalogue,
            control_id="AC-2",
            mappings=[mapping],
            observations="not-a-list",
        )
