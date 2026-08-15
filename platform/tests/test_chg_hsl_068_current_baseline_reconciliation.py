from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
STATUS_PATH = ROOT / "docs" / "roadmap" / "current-walking-skeleton-status.md"
EXPECTED_RECONCILIATION_BASE = "8c654379afb2114e34d6e748bb558b3ad5b8fb4b"


def test_current_walking_skeleton_records_latest_reconciliation_base() -> None:
    text = STATUS_PATH.read_text(encoding="utf-8")

    assert f"**Current Labs baseline:** `{EXPECTED_RECONCILIATION_BASE}`" in text
    assert (
        "current reconciliation provenance is **CHG-HSL-068 "
        f"(`{EXPECTED_RECONCILIATION_BASE}`)**"
    ) in text


def test_stale_chg_hsl_060_current_provenance_is_not_retained() -> None:
    text = STATUS_PATH.read_text(encoding="utf-8")

    assert "current reconciliation provenance is **CHG-HSL-060" not in text
