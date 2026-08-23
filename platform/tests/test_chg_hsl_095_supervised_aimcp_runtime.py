from __future__ import annotations

from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
COMPATIBILITY = ROOT / "platform" / "runner-protocol" / "compatibility.yaml"
CHANGE = ROOT / "changes" / "CHG-HSL-095.yaml"
CAMPAIGN = ROOT / "validation" / "VAL-HSL-AIMCP-SUPERVISED-RUNTIME.yaml"
EVIDENCE = ROOT / "deployment" / "ai-mcp-live" / "evidence" / "controlled-supervision-CHG-HSL-095.yaml"
LIVE_EVIDENCE = ROOT / "deployment" / "ai-mcp-live" / "evidence" / "live-supervised-observation-CHG-HSL-095.yaml"


def _load(path: Path) -> dict:
    document = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert isinstance(document, dict)
    return document


def _controlled() -> dict:
    document = _load(COMPATIBILITY)
    family = next(item for item in document["runner_families"] if item["id"] == "ai-mcp")
    return family["controlled_runtime_integration"]


def test_controlled_runtime_records_supervised_process_without_live_promotion() -> None:
    controlled = _controlled()
    assert controlled["process_supervision"] == "PASS_CONTROLLED_PROCESS"
    assert controlled["cancellation_timeout_integration"] == "HARD_TIMEOUT_PASS_CANCELLATION_NOT_RUN"
    supervised = controlled["supervised_process"]
    assert supervised["status"] == "PASS_CONTROLLED_PROCESS"
    assert supervised["worker_selection"] == "fixed_trusted"
    assert supervised["request_controlled_command_surface"] == "none"
    assert supervised["hard_timeout"] == "PASS_CONTROLLED_PROCESS"
    assert supervised["cancellation_request"] == "NOT_RUN"
    assert supervised["live_lab_execution"] == "PASS_LAB_CONTROLLED_RDC_SUPERVISED"
    live = supervised["live_lab_observation"]
    assert live["status"] == "OBSERVED_LAB_CONTROLLED_RDC_SUPERVISED"
    assert live["runner_outcome"] == "PASS"
    assert live["supervision_status"] == "EXITED"
    assert live["runtime_status"] == "ok"
    assert live["runtime_decision"] == "vulnerable"
    assert live["replay_second_process"] == "none"
    assert live["zero_residue"] == "PASS"
    assert controlled["sandbox_status"] == "NOT_IMPLEMENTED"
    assert controlled["production_execution"] == "NOT_RUN"


def test_chg095_governance_artifacts_exist_and_preserve_authority_boundary() -> None:
    assert CHANGE.is_file()
    assert CAMPAIGN.is_file()
    assert EVIDENCE.is_file()
    assert LIVE_EVIDENCE.is_file()
    change = _load(CHANGE)
    evidence = _load(EVIDENCE)
    live_evidence = _load(LIVE_EVIDENCE)
    campaign = _load(CAMPAIGN)
    assert change["id"] == "CHG-HSL-095"
    assert change["source"]["observation"] == "OBS-AIMCP-SUPERVISED-LIVE-RDC"
    assert evidence["runtime_status"] == "PASS_CONTROLLED_PROCESS"
    assert evidence["live_lab_execution"] == "NOT_RUN_TOOL_BLOCK"
    assert live_evidence["runtime_status"] == "OBSERVED_LAB_CONTROLLED_RDC_SUPERVISED"
    assert live_evidence["runner_outcome"] == "PASS"
    assert live_evidence["supervision_status"] == "EXITED"
    assert live_evidence["replay_second_process"] == "none"
    assert live_evidence["zero_residue"] == "PASS"
    invariants = live_evidence["invariants"]
    assert invariants["control_plane_authority"] == "NONE"
    assert invariants["operational_authorization_receipt"] == "NOT_USED"
    assert invariants["production_execution"] == "NOT_RUN"
    assert invariants["promotion_allowed"] is False
    observations = {item["id"]: item for item in campaign["observations"]}
    assert observations["OBS-AIMCP-SUPERVISED-CONTROLLED"]["result"] == "PASS"
    assert observations["OBS-AIMCP-SUPERVISED-LIVE-RDC"]["result"] == "PASS"
    assert campaign["promotionRecommendation"] == "ACCEPT"


def test_docs_state_hard_timeout_pass_but_cancellation_and_live_remain_not_run() -> None:
    projection = (
        ROOT / "security" / "packs" / "ai-mcp" / "docs" / "runner-protocol-runtime-projection.md"
    ).read_text(encoding="utf-8")
    completion = (ROOT / "docs" / "roadmap" / "SVP2-B-02-completion-as-built.md").read_text(
        encoding="utf-8"
    )
    for document in (projection, completion):
        assert "PASS_CONTROLLED_PROCESS" in document
        normalized = document.lower()
        assert "cancellation request: **`not_run`**" in normalized
        assert "supervised live lab execution: **`pass_lab_controlled_rdc_supervised`**" in normalized
        assert "production execution" in normalized and "not_run" in normalized
