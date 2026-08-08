from __future__ import annotations

import importlib.util
from copy import deepcopy
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "knowledge-fabric" / "knowledge_quality.py"

spec = importlib.util.spec_from_file_location("knowledge_quality_hardening", MODULE_PATH)
assert spec and spec.loader
kq = importlib.util.module_from_spec(spec)
spec.loader.exec_module(kq)

SNAPSHOT = "ks_" + "a" * 32
R1 = "kr_" + "1" * 32
R2 = "kr_" + "2" * 32


def _case() -> dict:
    return kq.build_curation_case(
        knowledge_snapshot_id=SNAPSHOT,
        finding_type="CONFLICT",
        subject_ref="cve:CVE-2026-0001:severity",
        candidate_source_record_ids=[R1, R2],
        rationale="Conflicting source assertions require accountable curation.",
    )


def test_case_id_is_bound_to_exact_case_content() -> None:
    for field, value in (
        ("subject_ref", "cve:CVE-2026-0002:severity"),
        ("rationale", "Changed rationale after case creation."),
        ("finding_type", "LOW_CONFIDENCE"),
    ):
        forged = deepcopy(_case())
        forged[field] = value
        with pytest.raises(kq.KnowledgeQualityError, match="canonical content"):
            kq.record_curator_decision(
                case=forged,
                curator_id="curator.pedro",
                decision="DEFER",
                selected_source_record_id=None,
                rationale="Do not accept a tampered curation case.",
                decided_at="2026-08-08T00:30:00Z",
            )


def test_case_candidate_tampering_invalidates_content_address() -> None:
    forged = deepcopy(_case())
    forged["candidate_source_record_ids"] = [R1]
    with pytest.raises(kq.KnowledgeQualityError, match="canonical content"):
        kq.record_policy_decision(
            case=forged,
            precedence_policy_id="policy:source-precedence:v1",
            selected_source_record_id=R1,
            rationale="Do not accept modified candidates.",
            decided_at="2026-08-08T00:30:00Z",
        )


def test_quality_and_curation_outputs_never_gain_execution_authority() -> None:
    case = _case()
    curator = kq.record_curator_decision(
        case=case,
        curator_id="curator.pedro",
        decision="DEFER",
        selected_source_record_id=None,
        rationale="Additional source review is required.",
        decided_at="2026-08-08T00:30:00Z",
    )
    policy = kq.record_policy_decision(
        case=case,
        precedence_policy_id="policy:source-precedence:v1",
        selected_source_record_id=R1,
        rationale="Applied explicit precedence policy for the fixture.",
        decided_at="2026-08-08T00:30:00Z",
    )
    assert case["execution_authority"] == "NONE"
    assert curator["execution_authority"] == "NONE"
    assert policy["execution_authority"] == "NONE"
    assert curator["historical_rewrite"] is False
    assert policy["historical_rewrite"] is False
