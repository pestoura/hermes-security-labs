from __future__ import annotations

from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
EVIDENCE = ROOT / "deployment" / "ai-mcp-live" / "evidence" / "live-observation-CHG-HSL-094.yaml"
COMPATIBILITY = ROOT / "platform" / "runner-protocol" / "compatibility.yaml"
CHANGE = ROOT / "changes" / "CHG-HSL-094.yaml"
COMPLETION = ROOT / "docs" / "roadmap" / "SVP2-B-02-completion-as-built.md"
PROJECTION_DOC = ROOT / "security" / "packs" / "ai-mcp" / "docs" / "runner-protocol-runtime-projection.md"


def _ai_mcp() -> dict:
    data = yaml.safe_load(COMPATIBILITY.read_text(encoding="utf-8"))
    return next(item for item in data["runner_families"] if item["id"] == "ai-mcp")


def test_live_observation_records_only_sanitized_lab_evidence() -> None:
    assert EVIDENCE.is_file(), "CHG-HSL-094 live observation is missing"
    evidence = yaml.safe_load(EVIDENCE.read_text(encoding="utf-8"))
    assert evidence["schema_version"] == "hsl.ai-mcp-live-lab-observation/v1"
    assert evidence["change_record"] == "CHG-HSL-094"
    assert evidence["observed_main"] == "b4ada2ed220b788c775158a701ac220437d8716a"
    assert evidence["runtime_status"] == "OBSERVED_LAB_CONTROLLED_RDC"
    proof = evidence["proof"]
    assert proof["post_start_health_observation"] == "PASS"
    assert proof["smoke"] == "PASS"
    assert proof["runner_outcome"] == "PASS"
    assert proof["runtime_status"] == "ok"
    assert proof["runtime_decision"] == "vulnerable"
    assert proof["replay_second_effect"] == "none"
    assert proof["ledger_entries"] == 1
    assert proof["destroy"] == "PASS"
    assert proof["zero_residue"] == "PASS"

    lifecycle = evidence["lifecycle"]
    assert lifecycle["start_command_transport"] == "UNKNOWN"
    assert lifecycle["kali_connected"] is False
    assert lifecycle["target_egress"] == "denied"

    invariants = evidence["invariants"]
    assert invariants["control_plane_authority"] == "NONE"
    assert invariants["operational_authorization_receipt"] == "NOT_USED"
    assert invariants["process_supervision"] == "NOT_COMPOSED"
    assert invariants["production_execution"] == "NOT_RUN"
    assert invariants["promotion_allowed"] is False
    sanitization = evidence["sanitization"]
    assert sanitization == {
        "raw_prompt_exposed": False,
        "raw_response_exposed": False,
        "authorization_ref_exposed": False,
        "local_paths_exposed": False,
    }


def test_compatibility_promotes_only_the_controlled_lab_observation() -> None:
    controlled = _ai_mcp()["controlled_runtime_integration"]
    assert controlled["status"] == "PASS_CONTROLLED_IN_PROCESS"
    assert controlled["live_network_execution"] == "PASS_LAB_CONTROLLED_RDC"
    live = controlled["live_lab_observation"]
    assert live["status"] == "OBSERVED_LAB_CONTROLLED_RDC"
    assert live["lab_id"] == "promptme"
    assert live["observed_main"] == "b4ada2ed220b788c775158a701ac220437d8716a"
    assert live["authorization_semantics"] == "TEST_ONLY_NOT_OPERATIONAL_AUTHORITY"
    assert live["replay_second_effect"] == "none"
    assert live["zero_residue"] == "PASS"
    assert controlled["process_supervision"] == "NOT_COMPOSED"
    assert controlled["cancellation_timeout_integration"] == "NOT_RUN"
    assert controlled["sandbox_status"] == "NOT_IMPLEMENTED"
    assert controlled["production_execution"] == "NOT_RUN"
    assert controlled["production_effect_claim"] == "none"
    assert _ai_mcp()["promotion_status"] == "blocked"


def test_change_and_docs_reconcile_without_production_claim() -> None:
    assert CHANGE.is_file(), "CHG-HSL-094 change record is missing"
    change = yaml.safe_load(CHANGE.read_text(encoding="utf-8"))
    assert change["id"] == "CHG-HSL-094"
    assert change["validation"]["targeted"] == "PASS"
    assert change["validation"]["runtime"] == "PASS"
    assert change["promotion"]["commit"] is None

    completion = COMPLETION.read_text(encoding="utf-8")
    projection = PROJECTION_DOC.read_text(encoding="utf-8")
    marker = "PASS_LAB_CONTROLLED_RDC"
    assert marker in completion
    assert marker in projection
    assert "production execution integration: **`NOT_RUN`**" in completion
    assert "production execution remains `NOT_RUN`" in projection
