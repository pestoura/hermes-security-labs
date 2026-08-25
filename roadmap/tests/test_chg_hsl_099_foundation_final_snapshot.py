from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
SNAPSHOT = ROOT / "roadmap" / "reconciliation" / "foundation-final-snapshot-CHG-HSL-099.yaml"
CHANGE = ROOT / "changes" / "CHG-HSL-099.yaml"
STATUS_DOC = ROOT / "docs" / "roadmap" / "current-walking-skeleton-status.md"
EPIC05 = ROOT / "docs" / "roadmap" / "epics" / "EPIC-05-runner-protocol-v2.md"
CONCEPTS = ROOT / "roadmap" / "epics" / "security-validation-platform-v2-concepts.yaml"
POSTMERGE = ROOT / "roadmap" / "reconciliation" / "chg097-postmerge-runtime-CHG-HSL-099.yaml"
BASELINE = "7711ddf2920c87259b6c0c4a4119d5441dba4181"


def _load(path: Path) -> dict:
    document = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert isinstance(document, dict)
    return document


def test_foundation_snapshot_completes_after_chg097_postmerge_runtime_pass() -> None:
    snapshot = _load(SNAPSHOT)
    assert snapshot["functional_baseline"] == BASELINE
    assert snapshot["status"] == "COMPLETE"
    assert snapshot["foundation_complete"] is True
    criteria = snapshot["criteria"]
    assert criteria["change_record_ids_unique"] == "PASS"
    assert criteria["foundation_milestone_accounting"] == "PASS"
    assert criteria["juice_shop_current_main_reconciliation"] == "PASS"
    assert criteria["promptme_cancellation_merge"] == "PASS"
    assert criteria["final_main_ci"] == "PASS"
    assert criteria["chg097_post_merge_runtime"] == "PASS"


def test_snapshot_preserves_non_foundation_boundaries() -> None:
    snapshot = _load(SNAPSHOT)
    boundaries = snapshot["boundaries"]
    assert boundaries["production_ready"] is False
    assert boundaries["core_operational_v1_complete"] is False
    assert boundaries["full_target_architecture_complete"] is False
    assert boundaries["secret_zero"] == "NOT_RUN"
    assert boundaries["runner_live_promotion"] is False
    assert boundaries["customer_target_execution"] is False


def test_chg099_records_runtime_pass_without_production_promotion() -> None:
    change = _load(CHANGE)
    assert change["id"] == "CHG-HSL-099"
    assert change["classification"] == "DOC_ONLY"
    assert change["validation"]["targeted"] == "PASS"
    assert change["validation"]["regression"] == "PASS"
    assert change["validation"]["runtime"] == "PASS"
    assert change["promotion"]["commit"] is None


def test_current_docs_distinguish_controlled_cancellation_from_operational_dispatch() -> None:
    status = STATUS_DOC.read_text(encoding="utf-8")
    epic = EPIC05.read_text(encoding="utf-8")
    concepts = _load(CONCEPTS)
    epic05 = next(item for item in concepts["concept_epics"] if item["concept_id"] == "EPIC-05")
    assert BASELINE in status
    assert "Foundation / Walking Skeleton (Level A): `COMPLETE`" in status
    assert "CHG-HSL-097" in epic
    assert "PASS_LAB_CONTROLLED_RDC" in epic
    assert "Cancellation requests remain `NOT_RUN`" not in epic
    current_state = epic05["current_state"]
    assert "CHG-HSL-097" in current_state
    assert "PASS_LAB_CONTROLLED_RDC" in current_state
    assert "Cancellation requests remain NOT_RUN" not in current_state
    assert "Operational Control Plane" in current_state


def test_postmerge_runtime_evidence_is_exact_main_sanitized_and_zero_residue() -> None:
    evidence = _load(POSTMERGE)
    assert evidence["change_record"] == "CHG-HSL-099"
    assert evidence["subject_change"] == "CHG-HSL-097"
    assert evidence["observed_main"] == BASELINE
    assert evidence["result"] == "PASS"
    live = evidence["live_cancellation"]
    assert live["acknowledgement"] == "accepted"
    assert live["terminal_status"] == "CANCELLED"
    assert live["first_process_count"] == 1
    assert live["replay_terminal"] == "CANCELLED"
    assert live["replay_second_process"] == "none"
    assert evidence["force_after_grace"]["force_killed"] is True
    assert evidence["zero_residue"] == "PASS"
    assert evidence["boundaries"]["production_execution"] == "NOT_RUN"
    assert evidence["boundaries"]["promotion_allowed"] is False
