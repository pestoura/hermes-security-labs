from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
STATUS = ROOT / "docs" / "roadmap" / "current-walking-skeleton-status.md"
CAMPAIGN = ROOT / "validation" / "VAL-HSL-RUNNER-L1-LIVE-PROMOTION.yaml"


def test_shared_vault_live_observation_is_reconciled_without_authority() -> None:
    status = STATUS.read_text(encoding="utf-8")
    assert "CHG-HSL-086" in status
    assert "OBSERVED_PRE_SECRET_ZERO" in status
    assert "172.25.0.3/32" in status
    assert "SECRETID_ISSUANCE=NOT_RUN" in status
    assert "Hermes Vault v1" in status
    assert "OPERATIONAL BASELINE" in status
    assert "campaign remains `BLOCKED / HOLD`" in status

    campaign = yaml.safe_load(CAMPAIGN.read_text(encoding="utf-8"))
    assert campaign["state"] == "BLOCKED"
    assert campaign["promotionRecommendation"] == "HOLD"
    serialized = CAMPAIGN.read_text(encoding="utf-8")
    assert "OBSERVED_PRE_SECRET_ZERO" in serialized
    assert "SECRETID_ISSUANCE=NOT_RUN" in serialized
    assert "shared-vault-pre-secret-zero:PASS" in serialized
    assert "trust-store:ABSENT" in serialized
    assert "signer-provider:NOT_RUN" in serialized
    assert "signer:NOT_OBSERVED" in serialized
