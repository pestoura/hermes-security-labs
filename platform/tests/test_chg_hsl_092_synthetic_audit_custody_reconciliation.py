from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
CAMPAIGN = ROOT / "validation" / "VAL-HSL-RUNNER-L1-LIVE-PROMOTION.yaml"
STATUS = ROOT / "docs" / "roadmap" / "current-walking-skeleton-status.md"
EVIDENCE = (
    ROOT
    / "deployment"
    / "authorization-audit-live"
    / "evidence"
    / "live-observation-CHG-HSL-090.yaml"
)
CHANGE = ROOT / "changes" / "CHG-HSL-092.yaml"
MERGED_MAIN = "eada361cb5fd3f612b7b5911146cd4b448241e04"


def _campaign() -> dict:
    document = yaml.safe_load(CAMPAIGN.read_text(encoding="utf-8"))
    assert isinstance(document, dict)
    return document


def _observations() -> dict[str, dict]:
    return {item["id"]: item for item in _campaign()["observations"]}


def test_sanitized_live_observation_is_preserved_without_sensitive_fields() -> None:
    assert EVIDENCE.exists(), "CHG-HSL-090 live observation is not reconciled yet"
    evidence = yaml.safe_load(EVIDENCE.read_text(encoding="utf-8"))
    assert evidence["schema_version"] == "hsl.authorization-audit-live-observation/v1"
    assert evidence["change_record"] == "CHG-HSL-090"
    assert evidence["observed_main"] == MERGED_MAIN
    assert evidence["runtime_status"] == "OBSERVED_SYNTHETIC_CUSTODY"
    assert evidence["proof"] == {
        "custody_persisted": True,
        "reopen_verified": True,
        "audit_chain_verified": True,
        "classification": "restricted",
        "record_count": 1,
        "cleanup_verified": True,
    }
    assert evidence["invariants"]["policy_source_state"] == "DISABLED"
    assert evidence["invariants"]["policy_runtime_status"] == "NOT_RUN"
    assert evidence["invariants"]["execution_authority"] == "NONE"
    assert evidence["invariants"]["promotion_allowed"] is False
    assert evidence["invariants"]["target_effect"] == "none"
    serialized = EVIDENCE.read_text(encoding="utf-8")
    for forbidden in ("evidence_id", "evidence_ref", "authorization_ref", "/tmp/"):
        assert forbidden not in serialized


def test_campaign_records_synthetic_pass_but_keeps_operational_hold() -> None:
    campaign = _campaign()
    assert campaign["state"] == "BLOCKED"
    assert campaign["promotionRecommendation"] == "HOLD"

    observations = _observations()
    custody = observations["OBS-EVIDENCE-CUSTODY"]
    assert custody["result"] == "BLOCKED"
    assert custody["status"] == "OPEN"
    assert custody["changeRecord"] == "CHG-HSL-092"
    assert "synthetic-live-audit-custody:PASS(CHG-HSL-090" in custody["evidence"]
    assert f"main={MERGED_MAIN}" in custody["evidence"]
    assert "runtime=OBSERVED_SYNTHETIC_CUSTODY" in custody["evidence"]
    assert "operational-live-audit-custody:NOT_RUN" in custody["evidence"]
    assert "custody-policy:DISABLED/NOT_RUN" in custody["evidence"]

    tb1 = observations["OBS-TB1-LIVE-DELIVERY"]
    assert tb1["result"] == "BLOCKED"
    assert "synthetic-live-auth-audit:PASS(CHG-HSL-090)" in tb1["evidence"]
    assert "operational-live-auth-audit:NOT_RUN" in tb1["evidence"]
    assert "receipt-delivery:DISABLED/NOT_RUN" in tb1["evidence"]
    assert "trust-store:ABSENT" in tb1["evidence"]


def test_status_and_change_record_preserve_non_authority_semantics() -> None:
    text = STATUS.read_text(encoding="utf-8")
    assert f"**CHG-HSL-090 accepted merge:** `{MERGED_MAIN}`" in text
    assert "Authorization-audit synthetic custody proof" in text
    assert "PASS / OBSERVED_SYNTHETIC_CUSTODY" in text
    assert "operational policy remains `DISABLED / NOT_RUN`" in text
    assert "HOLD / BLOCKED-ON-LIVE-PROMOTION-EVIDENCE" in text

    record = yaml.safe_load(CHANGE.read_text(encoding="utf-8"))
    assert record["id"] == "CHG-HSL-092"
    assert record["source"]["observation"] == "OBS-EVIDENCE-CUSTODY"
    assert record["validation"]["targeted"] == "PASS"
    assert record["validation"]["runtime"] == "PASS"
    assert record["promotion"]["commit"] is None
    assert record["promotion"]["artifactDigest"] is None
