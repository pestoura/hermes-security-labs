from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
STATUS = ROOT / "docs" / "roadmap" / "current-walking-skeleton-status.md"
CHANGE = ROOT / "changes" / "CHG-HSL-101.yaml"
FOUNDATION = "7711ddf2920c87259b6c0c4a4119d5441dba4181"
CHG099_MAIN = "d418c0ad30054c464c2bc2316bf6b81d03082e83"
CHG100_MAIN = "0349cea6eb60f0719464e8735bfc1d0bdf2f227f"


def _load(path: Path) -> dict:
    value = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value


def test_status_separates_foundation_baseline_from_latest_reconciled_milestone() -> None:
    text = STATUS.read_text(encoding="utf-8")
    assert "**Reconciled:** 2026-08-28 UTC" in text
    assert f"**Foundation functional baseline:** `{FOUNDATION}`" in text
    assert f"CHG-HSL-100 / PR #448 / `{CHG100_MAIN}`" in text
    assert "Current repository main / Foundation functional baseline" not in text


def test_status_records_core_operational_v1_exact_hold_boundary() -> None:
    text = STATUS.read_text(encoding="utf-8")
    assert "Foundation / Walking Skeleton (Level A): `COMPLETE`" in text
    assert "**Core Operational v1 / LAB_L1 promotion:** `IN_PROGRESS / BLOCKED_AT_SECRET_ZERO_HITL`" in text
    assert "**Secret Zero:** `NOT_RUN`" in text
    assert "**signer human decision:** `NO_DECISION`" in text
    assert "**supplier selection:** `NO_SELECTION`" in text
    assert "promotion_allowed=false" in text
    assert "execution_authority=none" in text


def test_status_reconciles_chg099_and_chg100_without_claiming_authority() -> None:
    text = STATUS.read_text(encoding="utf-8")
    assert f"**CHG-HSL-099 accepted merge:** `{CHG099_MAIN}` (PR #447" in text
    assert f"**CHG-HSL-100 accepted merge:** `{CHG100_MAIN}` (PR #448" in text
    assert "sanitized Secret Zero reconciliation contract" in text
    assert "operator-only HITL" in text
    assert "does not grant trust, Runner or target authority" in text


def test_chg101_is_doc_only_and_runtime_not_run() -> None:
    change = _load(CHANGE)
    assert change["id"] == "CHG-HSL-101"
    assert change["classification"] == "DOC_ONLY"
    assert change["state"] == "ACCEPTED"
    assert change["validation"]["runtime"] == "NOT_RUN"
    assert change["promotion"]["commit"] is None
    text = CHANGE.read_text(encoding="utf-8")
    assert "Secret Zero remains NOT_RUN" in text
    assert "NO_DECISION" in text
    assert "NO_SELECTION" in text
    assert "no execution authority" in text
