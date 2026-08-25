from __future__ import annotations

from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
CHANGE = ROOT / "changes" / "CHG-HSL-097.yaml"
CAMPAIGN = ROOT / "validation" / "VAL-HSL-AIMCP-CANCELLATION-RUNTIME.yaml"
EVIDENCE = (
    ROOT
    / "deployment"
    / "ai-mcp-live"
    / "evidence"
    / "cancellation-observation-CHG-HSL-097.yaml"
)
COMPATIBILITY = ROOT / "platform" / "runner-protocol" / "compatibility.yaml"
FUNCTIONAL_SHA = "76ecc4aac3cb25e1697613a27304c6ca0dc082bd"


def _load(path: Path) -> dict:
    value = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value


def _controlled() -> dict:
    document = _load(COMPATIBILITY)
    family = next(item for item in document["runner_families"] if item["id"] == "ai-mcp")
    return family["controlled_runtime_integration"]

def test_chg097_exact_sha_cancellation_evidence_is_sanitized_and_bounded() -> None:
    evidence = _load(EVIDENCE)
    assert evidence["change_record"] == "CHG-HSL-097"
    assert evidence["functional_commit"] == FUNCTIONAL_SHA
    assert evidence["runtime_status"] == "OBSERVED_LAB_CONTROLLED_RDC_CANCELLATION"
    live = evidence["live_worker"]
    assert live["selection"] == "fixed_trusted"
    assert live["cancellation_ack"] == "accepted"
    assert live["terminal_status"] == "CANCELLED"
    assert live["supervision_status"] == "CANCELLED"
    assert live["first_process_count"] == 1
    assert live["replay_second_process"] == "none"
    assert live["cleanup_failed"] is False
    assert evidence["force_after_grace"]["force_killed"] is True
    assert evidence["zero_residue"] == "PASS"
    assert evidence["raw_evidence"]["durable_raw_custody_claimed"] is False


def test_chg097_change_and_campaign_bind_the_same_observation() -> None:
    change = _load(CHANGE)
    campaign = _load(CAMPAIGN)
    observation = campaign["observations"][0]
    assert change["source"]["campaign"] == campaign["id"]
    assert change["source"]["observation"] == observation["id"]
    assert observation["changeRecord"] == "CHG-HSL-097"
    assert campaign["candidate"]["commit"] == FUNCTIONAL_SHA
    assert observation["result"] == "PASS"
    assert change["validation"]["runtime"] == "PASS"
    assert change["validation"]["regression"] == "PASS"
    assert change["promotion"]["commit"] is None

def test_current_compatibility_records_controlled_cancellation_without_promotion() -> None:
    controlled = _controlled()
    assert controlled["cancellation_timeout_integration"] == (
        "HARD_TIMEOUT_PASS_CANCELLATION_PASS_CONTROLLED"
    )
    supervised = controlled["supervised_process"]
    assert supervised["cancellation_request"] == "PASS_LAB_CONTROLLED_RDC"
    cancellation = supervised["cancellation_live_observation"]
    assert cancellation["functional_commit"] == FUNCTIONAL_SHA
    assert cancellation["acknowledgement"] == "accepted"
    assert cancellation["terminal_status"] == "CANCELLED"
    assert cancellation["replay_second_process"] == "none"
    assert cancellation["force_after_grace"] == "PASS_CONTROLLED_PROCESS"
    assert cancellation["zero_residue"] == "PASS"
    assert controlled["sandbox_status"] == "NOT_IMPLEMENTED"
    assert controlled["production_execution"] == "NOT_RUN"
    assert controlled["production_effect_claim"] == "none"
