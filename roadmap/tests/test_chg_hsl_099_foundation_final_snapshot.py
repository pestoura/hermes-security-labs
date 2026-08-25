from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
SNAPSHOT = ROOT / "roadmap" / "reconciliation" / "foundation-final-snapshot-CHG-HSL-099.yaml"
CHANGE = ROOT / "changes" / "CHG-HSL-099.yaml"
STATUS_DOC = ROOT / "docs" / "roadmap" / "current-walking-skeleton-status.md"
EPIC05 = ROOT / "docs" / "roadmap" / "epics" / "EPIC-05-runner-protocol-v2.md"
CONCEPTS = ROOT / "roadmap" / "epics" / "security-validation-platform-v2-concepts.yaml"
BASELINE = "7711ddf2920c87259b6c0c4a4119d5441dba4181"


def _load(path: Path) -> dict:
    document = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert isinstance(document, dict)
    return document


def test_foundation_snapshot_holds_fail_closed_until_chg097_postmerge_runtime() -> None:
    snapshot = _load(SNAPSHOT)
    assert snapshot["functional_baseline"] == BASELINE
    assert snapshot["status"] == "HOLD_POST_MERGE_RUNTIME_CHG097"
    assert snapshot["foundation_complete"] is False
    criteria = snapshot["criteria"]
    assert criteria["change_record_ids_unique"] == "PASS"
    assert criteria["foundation_milestone_accounting"] == "PASS"
    assert criteria["juice_shop_current_main_reconciliation"] == "PASS"
    assert criteria["promptme_cancellation_merge"] == "PASS"
    assert criteria["final_main_ci"] == "PASS"
    assert criteria["chg097_post_merge_runtime"] == "NOT_RUN_HERMES_OFFLINE"


def test_snapshot_preserves_non_foundation_boundaries() -> None:
    snapshot = _load(SNAPSHOT)
    boundaries = snapshot["boundaries"]
    assert boundaries["production_ready"] is False
    assert boundaries["core_operational_v1_complete"] is False
    assert boundaries["full_target_architecture_complete"] is False
    assert boundaries["secret_zero"] == "NOT_RUN"
    assert boundaries["runner_live_promotion"] is False
    assert boundaries["customer_target_execution"] is False


def test_chg099_records_hold_without_claiming_runtime_pass() -> None:
    change = _load(CHANGE)
    assert change["id"] == "CHG-HSL-099"
    assert change["classification"] == "DOC_ONLY"
    assert change["validation"]["targeted"] == "PASS"
    assert change["validation"]["regression"] == "NOT_RUN"
    assert change["validation"]["runtime"] == "NOT_RUN"
    assert change["promotion"]["commit"] is None


def test_current_docs_distinguish_controlled_cancellation_from_operational_dispatch() -> None:
    status = STATUS_DOC.read_text(encoding="utf-8")
    epic = EPIC05.read_text(encoding="utf-8")
    concepts = _load(CONCEPTS)
    epic05 = next(item for item in concepts["concept_epics"] if item["concept_id"] == "EPIC-05")
    assert BASELINE in status
    assert "Foundation / Walking Skeleton (Level A): `HOLD`" in status
    assert "CHG-HSL-097" in epic
    assert "PASS_LAB_CONTROLLED_RDC" in epic
    assert "Cancellation requests remain `NOT_RUN`" not in epic
    current_state = epic05["current_state"]
    assert "CHG-HSL-097" in current_state
    assert "PASS_LAB_CONTROLLED_RDC" in current_state
    assert "Cancellation requests remain NOT_RUN" not in current_state
    assert "Operational Control Plane" in current_state
