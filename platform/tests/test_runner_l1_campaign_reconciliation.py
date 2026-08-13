from __future__ import annotations

from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
CAMPAIGN_PATH = ROOT / "validation" / "VAL-HSL-RUNNER-L1-LIVE-PROMOTION.yaml"
STATUS_PATH = ROOT / "docs" / "roadmap" / "current-walking-skeleton-status.md"
EPIC_PATH = ROOT / "docs" / "roadmap" / "epics" / "EPIC-10-evidence-plane.md"
BASELINE = "6a77921ec2079aa6689d11e2d7118f948ccb3a60"


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


def test_campaign_records_current_repo_capabilities_as_non_live_evidence() -> None:
    campaign = _campaign()
    observations = {item["id"]: item for item in campaign["observations"]}

    repo_evidence = observations["OBS-RUNNER-REPO-CHAIN"]["evidence"]
    for pr in (
        "335",
        "336",
        "337",
        "338",
        "340",
        "341",
        "342",
        "343",
        "345",
        "346",
        "348",
        "349",
        "350",
        "351",
        "352",
    ):
        assert pr in repo_evidence

    tb1 = observations["OBS-TB1-LIVE-DELIVERY"]
    assert "signer-observation verification" in tb1["summary"]
    assert "signer-provider-observation:NOT_RUN" in tb1["evidence"]
    assert "signer-source-evidence:NOT_RUN" in tb1["evidence"]

    policy = observations["OBS-RUNNER-POLICY-PROMOTION"]
    assert "tenant-isolation verification" in policy["summary"]
    assert "phased live-evidence package verification" in policy["summary"]
    assert "userns:NOT_RUN" in policy["evidence"]
    assert "production-backend:NOT_IMPLEMENTED/NOT_RUN" in policy["evidence"]
    assert "tenant-isolation:NOT_RUN" in policy["evidence"]
    assert "live-evidence-package-verifier:GREEN-REPO" in policy["evidence"]
    assert "pre-promotion-package:NOT_RUN" in policy["evidence"]
    assert "post-effect-package:NOT_RUN" in policy["evidence"]
    assert "DISABLED/NOT_RUN" in policy["summary"]

    evidence = observations["OBS-EVIDENCE-CUSTODY"]
    assert "phased live-evidence package verifiers are also GREEN-REPO" in evidence["summary"]
    assert "durable-backend-verifier:GREEN-REPO" in evidence["evidence"]
    assert "tenant-isolation-verifier:GREEN-REPO" in evidence["evidence"]
    assert "live-evidence-package-verifier:GREEN-REPO" in evidence["evidence"]
    assert "production-WORM-backend:NOT_IMPLEMENTED/NOT_RUN" in evidence["evidence"]
    assert "backend-tenant-config:NOT_RUN" in evidence["evidence"]
    assert "cross-tenant-negatives:NOT_RUN" in evidence["evidence"]
    assert "pre-promotion-package:NOT_RUN" in evidence["evidence"]
    assert "post-effect-package:NOT_RUN" in evidence["evidence"]


def test_walking_skeleton_status_uses_same_baseline_and_hold_state() -> None:
    text = STATUS_PATH.read_text(encoding="utf-8")
    assert f"**Current Labs baseline:** `{BASELINE}`" in text
    assert "GREEN-REPO is not live acceptance" in text
    assert "Evidence Plane backend tenant-isolation verifier" in text
    assert "Tenant-isolation promotion reconciliation" in text
    assert "Phased live-promotion evidence package" in text
    assert "Live-package promotion reconciliation" in text
    assert "real tenant config/evidence and cross-tenant negatives `NOT_RUN`" in text
    assert "production backend `NOT_IMPLEMENTED / NOT_RUN`" in text
    assert "PRE_PROMOTION and POST_EFFECT packages `NOT_RUN`" in text
    assert "promotion_allowed=false" in text
    assert "HOLD / BLOCKED-ON-LIVE-PROMOTION-EVIDENCE-AND-CONNECTOR" in text


def test_epic10_records_tenant_verifier_without_claiming_live_isolation() -> None:
    text = EPIC_PATH.read_text(encoding="utf-8")
    assert "Document version | 1.5.0" in text
    assert "backend tenant-isolation attestation verifier: `GREEN_REPO`" in text
    assert "production backend selection/deployment: `NOT_IMPLEMENTED` / `NOT_RUN`" in text
    assert "production tenant configuration: `NOT_RUN`" in text
    assert "cross-tenant list/read/write negative acceptance: `NOT_RUN`" in text
    assert "A GREEN tenant-isolation verifier does not mean tenant isolation has run live" in text
    assert "Evidence Record v2 is not modified" in text
    assert "`AS_BUILT` for the complete concept remains false" in text
    assert "`FINAL` remains false" in text
    assert "NO_RUNTIME_CHANGE" in text


def test_unknown_webgoat_rerun_is_not_promoted_to_pass_or_fail() -> None:
    campaign = _campaign()
    observation = next(
        item for item in campaign["observations"] if item["id"] == "OBS-LIVE-EFFECT-RESET"
    )
    assert "result=UNKNOWN" in observation["evidence"]
    assert "live-runner-effect:NOT_RUN" in observation["evidence"]
    assert "post-effect-package:NOT_RUN" in observation["evidence"]
