from __future__ import annotations

from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
CAMPAIGN_PATH = ROOT / "validation" / "VAL-HSL-RUNNER-L1-LIVE-PROMOTION.yaml"
STATUS_PATH = ROOT / "docs" / "roadmap" / "current-walking-skeleton-status.md"
BASELINE = "6dbd34cabb5766837803c6c9083254902fefa1dc"


def _campaign() -> dict:
    document = yaml.safe_load(CAMPAIGN_PATH.read_text(encoding="utf-8"))
    assert isinstance(document, dict)
    return document


def test_campaign_reconciles_repository_candidate_without_promoting_live_state() -> None:
    campaign = _campaign()
    assert campaign["state"] == "BLOCKED"
    assert campaign["promotionRecommendation"] == "HOLD"
    assert campaign["candidate"]["commit"] == BASELINE

    observations = {item["id"]: item for item in campaign["observations"]}
    assert observations["OBS-RUNNER-REPO-CHAIN"]["result"] == "PASS"
    assert observations["OBS-RUNNER-REPO-CHAIN"]["status"] == "RESOLVED"

    for observation_id in (
        "OBS-TB1-LIVE-DELIVERY",
        "OBS-RUNNER-POLICY-PROMOTION",
        "OBS-EVIDENCE-CUSTODY",
        "OBS-LIVE-EFFECT-RESET",
    ):
        assert observations[observation_id]["required"] is True
        assert observations[observation_id]["result"] == "BLOCKED"
        assert observations[observation_id]["status"] == "OPEN"


def test_campaign_records_new_repo_capabilities_as_non_live_evidence() -> None:
    campaign = _campaign()
    observations = {item["id"]: item for item in campaign["observations"]}

    repo_evidence = observations["OBS-RUNNER-REPO-CHAIN"]["evidence"]
    for pr in ("335", "336", "337", "338"):
        assert pr in repo_evidence

    policy_text = observations["OBS-RUNNER-POLICY-PROMOTION"]["summary"]
    assert "host-evidence" in policy_text
    assert "Evidence Plane audit custody" in policy_text
    assert "service composition" in policy_text
    assert "DISABLED/NOT_RUN" in policy_text

    evidence_text = observations["OBS-EVIDENCE-CUSTODY"]["summary"]
    assert "production durable/WORM backend" in evidence_text
    assert "DISABLED/NOT_RUN" in evidence_text


def test_walking_skeleton_status_uses_same_baseline_and_hold_state() -> None:
    text = STATUS_PATH.read_text(encoding="utf-8")
    assert f"**Current Labs baseline:** `{BASELINE}`" in text
    assert "GREEN-REPO is not live acceptance" in text
    assert "Promotion bundle reconciliation | #338" in text
    assert "Runner service composition | #337" in text
    assert "Read-only Runner host evidence | #336" in text
    assert "Dispatch audit Evidence Plane custody | #335" in text
    assert "promotion_allowed=false" in text
    assert "HOLD / BLOCKED-ON-LIVE-PROMOTION-EVIDENCE-AND-CONNECTOR" in text


def test_unknown_webgoat_rerun_is_not_promoted_to_pass_or_fail() -> None:
    campaign = _campaign()
    observation = next(
        item for item in campaign["observations"] if item["id"] == "OBS-LIVE-EFFECT-RESET"
    )
    assert "result=UNKNOWN" in observation["evidence"]
    assert "live-runner-effect:NOT_RUN" in observation["evidence"]
