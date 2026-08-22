from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
STATUS = ROOT / "docs" / "roadmap" / "current-walking-skeleton-status.md"
CAMPAIGN = ROOT / "validation" / "VAL-HSL-RUNNER-L1-LIVE-PROMOTION.yaml"


def test_receipt_delivery_live_boundary_is_reconciled_without_authority() -> None:
    status = STATUS.read_text(encoding="utf-8")
    assert "CHG-HSL-088 accepted merge" in status
    assert "PASS / AUTHENTICATED_HOLD" in status
    assert "/run/hexor/runner-authz.sock" in status
    assert "4101:4110" in status
    assert "0660" in status
    assert "receipt-delivery and resolver policies remain `DISABLED / NOT_RUN`" in status

    campaign = yaml.safe_load(CAMPAIGN.read_text(encoding="utf-8"))
    assert campaign["state"] == "BLOCKED"
    assert campaign["promotionRecommendation"] == "HOLD"
    serialized = CAMPAIGN.read_text(encoding="utf-8")
    assert "receipt-boundary:PASS(CHG-HSL-088" in serialized
    assert "AUTHENTICATED_HOLD" in serialized
    assert "receipt-delivery-policy:DISABLED/NOT_RUN" in serialized
    assert "resolver:DISABLED/NOT_RUN" in serialized
