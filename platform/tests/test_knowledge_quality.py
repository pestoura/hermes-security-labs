from __future__ import annotations

import importlib.util
import json
from copy import deepcopy
from pathlib import Path

import jsonschema
import pytest


ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "knowledge-fabric" / "knowledge_quality.py"
REPORT_SCHEMA = ROOT / "knowledge-fabric" / "knowledge-quality-report.schema.json"
CASE_SCHEMA = ROOT / "knowledge-fabric" / "knowledge-curation-case.schema.json"
DECISION_SCHEMA = ROOT / "knowledge-fabric" / "knowledge-curation-decision.schema.json"

spec = importlib.util.spec_from_file_location("knowledge_quality", MODULE_PATH)
assert spec and spec.loader
kq = importlib.util.module_from_spec(spec)
spec.loader.exec_module(kq)

R1 = "kr_" + "1" * 32
R2 = "kr_" + "2" * 32
R3 = "kr_" + "3" * 32
SNAPSHOT = "ks_" + "a" * 32


def _snapshot(record_ids: list[str] | None = None) -> dict:
    return {
        "schema_version": "1.0",
        "snapshot_id": SNAPSHOT,
        "created_at": "2026-08-08T00:00:00Z",
        "source_record_ids": record_ids or [R1, R2],
        "snapshot_sha256": "b" * 64,
        "immutable": True,
    }


def _record(record_id: str, source: str, retrieved_at: str) -> dict:
    return {
        "schema_version": "1.0",
        "record_id": record_id,
        "entity": {"type": "cve", "id": f"CVE-2026-{record_id[-4:]}"},
        "source": {
            "name": source,
            "version": "fixture-v1",
            "retrieved_at": retrieved_at,
            "locator": f"snapshot:{source}",
        },
        "ingested_at": "2026-08-08T00:05:00Z",
        "raw_sha256": "c" * 64,
        "immutable_raw": True,
    }


def _relation(confidence: float = 0.9, provenance: list[str] | None = None) -> dict:
    return {
        "relation": "related_to",
        "from": "CVE-2026-0001",
        "to": "CWE-79",
        "confidence": confidence,
        "provenance_record_ids": provenance or [R1],
        "rationale": "Reviewed fixture relation.",
    }


def _unresolved_conflict() -> dict:
    return {
        "key": "cve:CVE-2026-0001:severity",
        "status": "unresolved",
        "assertions": [
            {"source_record_id": R1, "value": "high"},
            {"source_record_id": R2, "value": "critical"},
        ],
        "selected_assertion": None,
    }


def _quality(**overrides) -> dict:
    args = {
        "snapshot": _snapshot(),
        "records": [
            _record(R1, "nvd", "2026-08-07T23:30:00Z"),
            _record(R2, "kev", "2026-08-07T23:45:00Z"),
        ],
        "relations": [_relation()],
        "conflicts": [],
        "freshness_policy_seconds": {"nvd": 7200, "kev": 7200},
        "minimum_relation_confidence": 0.7,
        "as_of": "2026-08-08T00:30:00Z",
    }
    args.update(overrides)
    return kq.assess_quality(**args)


def test_quality_report_validates_against_strict_schema() -> None:
    schema = json.loads(REPORT_SCHEMA.read_text(encoding="utf-8"))
    report = _quality()
    jsonschema.validate(report, schema)


def test_quality_policy_met_is_not_a_security_verdict() -> None:
    report = _quality()
    assert report["quality_state"] == "QUALITY_POLICY_MET"
    assert report["completeness"]["ratio"] == 1.0
    assert report["freshness"]["stale_record_ids"] == []
    assert report["confidence"]["below_policy_count"] == 0
    assert report["conflicts"]["unresolved"] == 0
    assert report["assurance_effect"] == "NONE"
    assert report["execution_authority"] == "NONE"
    assert "QUALITY_POLICY_MET_IS_NOT_A_SECURITY_VERDICT" in report["limitations"]


def test_missing_snapshot_record_requires_review() -> None:
    report = _quality(records=[_record(R1, "nvd", "2026-08-07T23:30:00Z")])
    assert report["quality_state"] == "REVIEW_REQUIRED"
    assert report["completeness"]["provided_record_count"] == 1
    assert report["completeness"]["missing_record_ids"] == [R2]
    assert report["completeness"]["ratio"] == 0.5


def test_stale_record_requires_review() -> None:
    report = _quality(
        records=[
            _record(R1, "nvd", "2026-08-07T20:00:00Z"),
            _record(R2, "kev", "2026-08-07T23:45:00Z"),
        ],
        freshness_policy_seconds={"nvd": 3600, "kev": 7200},
    )
    assert report["quality_state"] == "REVIEW_REQUIRED"
    assert report["freshness"]["stale_record_ids"] == [R1]


def test_low_confidence_relation_requires_review() -> None:
    report = _quality(relations=[_relation(0.4)])
    assert report["quality_state"] == "REVIEW_REQUIRED"
    assert report["confidence"]["minimum"] == 0.4
    assert report["confidence"]["below_policy_count"] == 1


def test_unresolved_conflict_requires_review() -> None:
    report = _quality(conflicts=[_unresolved_conflict()])
    assert report["quality_state"] == "REVIEW_REQUIRED"
    assert report["conflicts"] == {"total": 1, "unresolved": 1, "resolved": 0}


def test_resolved_conflict_counts_as_resolved_only_with_existing_assertion() -> None:
    conflict = _unresolved_conflict()
    conflict["status"] = "resolved"
    conflict["selected_assertion"] = R1
    report = _quality(conflicts=[conflict])
    assert report["quality_state"] == "QUALITY_POLICY_MET"
    assert report["conflicts"] == {"total": 1, "unresolved": 0, "resolved": 1}

    conflict["selected_assertion"] = R3
    with pytest.raises(kq.KnowledgeQualityError, match="existing assertion"):
        _quality(conflicts=[conflict])


def test_records_relations_and_conflicts_must_belong_to_snapshot() -> None:
    with pytest.raises(kq.KnowledgeQualityError, match="belong to assessed snapshot"):
        _quality(records=[_record(R3, "nvd", "2026-08-07T23:30:00Z")])
    with pytest.raises(kq.KnowledgeQualityError, match="relation provenance"):
        _quality(relations=[_relation(provenance=[R3])])
    conflict = _unresolved_conflict()
    conflict["assertions"][1]["source_record_id"] = R3
    with pytest.raises(kq.KnowledgeQualityError, match="conflict assertions"):
        _quality(conflicts=[conflict])


def test_freshness_policy_must_cover_every_provided_source() -> None:
    with pytest.raises(kq.KnowledgeQualityError, match="cover every"):
        _quality(freshness_policy_seconds={"nvd": 7200})


def test_future_retrieval_time_fails_closed() -> None:
    with pytest.raises(kq.KnowledgeQualityError, match="future"):
        _quality(
            records=[
                _record(R1, "nvd", "2026-08-08T01:00:00Z"),
                _record(R2, "kev", "2026-08-07T23:45:00Z"),
            ]
        )


def test_quality_report_is_deterministic_independent_of_record_order() -> None:
    records = [
        _record(R1, "nvd", "2026-08-07T23:30:00Z"),
        _record(R2, "kev", "2026-08-07T23:45:00Z"),
    ]
    forward = _quality(records=records)
    reverse = _quality(records=list(reversed(records)))
    assert forward == reverse


def test_curation_case_validates_against_schema_and_has_no_automatic_resolution() -> None:
    schema = json.loads(CASE_SCHEMA.read_text(encoding="utf-8"))
    case = kq.build_curation_case(
        knowledge_snapshot_id=SNAPSHOT,
        finding_type="CONFLICT",
        subject_ref="cve:CVE-2026-0001:severity",
        candidate_source_record_ids=[R2, R1],
        rationale="Conflicting source assertions require curation.",
    )
    jsonschema.validate(case, schema)
    assert case["candidate_source_record_ids"] == [R1, R2]
    assert case["state"] == "OPEN"
    assert case["automatic_resolution"] is False
    assert case["execution_authority"] == "NONE"


def test_curator_resolution_records_identity_rationale_and_no_historical_rewrite() -> None:
    decision_schema = json.loads(DECISION_SCHEMA.read_text(encoding="utf-8"))
    case = kq.build_curation_case(
        knowledge_snapshot_id=SNAPSHOT,
        finding_type="CONFLICT",
        subject_ref="cve:CVE-2026-0001:severity",
        candidate_source_record_ids=[R1, R2],
        rationale="Conflict requires an accountable human decision.",
    )
    decision = kq.record_curator_decision(
        case=case,
        curator_id="curator.pedro",
        decision="SELECT_ASSERTION",
        selected_source_record_id=R2,
        rationale="Selected the assertion with the stronger reviewed provenance.",
        decided_at="2026-08-08T00:30:00Z",
    )
    jsonschema.validate(decision, decision_schema)
    assert decision["decision_basis"] == "CURATOR"
    assert decision["curator_id"] == "curator.pedro"
    assert decision["precedence_policy_id"] is None
    assert decision["automatic_resolution"] is False
    assert decision["historical_rewrite"] is False
    assert decision["effect"] == "KNOWLEDGE_CURATION_ONLY"
    assert decision["execution_authority"] == "NONE"


def test_policy_resolution_records_policy_and_requires_candidate() -> None:
    decision_schema = json.loads(DECISION_SCHEMA.read_text(encoding="utf-8"))
    case = kq.build_curation_case(
        knowledge_snapshot_id=SNAPSHOT,
        finding_type="CONFLICT",
        subject_ref="cve:CVE-2026-0001:severity",
        candidate_source_record_ids=[R1, R2],
        rationale="Conflict can use an explicit precedence policy.",
    )
    decision = kq.record_policy_decision(
        case=case,
        precedence_policy_id="policy:source-precedence:v1",
        selected_source_record_id=R1,
        rationale="Applied the declared source precedence policy.",
        decided_at="2026-08-08T00:30:00Z",
    )
    jsonschema.validate(decision, decision_schema)
    assert decision["decision_basis"] == "PRECEDENCE_POLICY"
    assert decision["curator_id"] is None
    assert decision["precedence_policy_id"] == "policy:source-precedence:v1"
    assert decision["historical_rewrite"] is False

    with pytest.raises(kq.KnowledgeQualityError, match="case candidate"):
        kq.record_policy_decision(
            case=case,
            precedence_policy_id="policy:source-precedence:v1",
            selected_source_record_id=R3,
            rationale="Invalid candidate.",
            decided_at="2026-08-08T00:30:00Z",
        )


def test_defer_or_reject_all_cannot_select_assertion() -> None:
    case = kq.build_curation_case(
        knowledge_snapshot_id=SNAPSHOT,
        finding_type="LOW_CONFIDENCE",
        subject_ref="relation:CVE-2026-0001:CWE-79",
        candidate_source_record_ids=[R1],
        rationale="Review confidence before selecting source truth.",
    )
    for decision in ("DEFER", "REJECT_ALL"):
        with pytest.raises(kq.KnowledgeQualityError, match="cannot select"):
            kq.record_curator_decision(
                case=case,
                curator_id="curator.pedro",
                decision=decision,
                selected_source_record_id=R1,
                rationale="Must not select for this decision.",
                decided_at="2026-08-08T00:30:00Z",
            )


def test_authority_or_secret_fields_fail_closed() -> None:
    snapshot = _snapshot()
    snapshot["authorization_ref"] = "forbidden"
    with pytest.raises(kq.KnowledgeQualityError, match="authority"):
        kq.assess_quality(
            snapshot=snapshot,
            records=[],
            relations=[],
            conflicts=[],
            freshness_policy_seconds={"nvd": 1},
            minimum_relation_confidence=0.0,
            as_of="2026-08-08T00:30:00Z",
        )

    case = kq.build_curation_case(
        knowledge_snapshot_id=SNAPSHOT,
        finding_type="CONFLICT",
        subject_ref="subject",
        candidate_source_record_ids=[R1],
        rationale="fixture",
    )
    forged = deepcopy(case)
    forged["token"] = "forbidden"
    with pytest.raises(kq.KnowledgeQualityError, match="authority"):
        kq.record_curator_decision(
            case=forged,
            curator_id="curator.pedro",
            decision="DEFER",
            selected_source_record_id=None,
            rationale="fixture",
            decided_at="2026-08-08T00:30:00Z",
        )
