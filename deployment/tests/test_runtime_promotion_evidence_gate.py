"""Repository-only tests for the aggregate WebGoat L1 promotion evidence gate.

The gate may prove repository prerequisites but must never turn evidence into
execution authority or policy promotion.
"""

from __future__ import annotations

import ast
import copy
import importlib.util
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
GATE_PATH = (
    ROOT
    / "deployment"
    / "runtime-promotion"
    / "runtime_promotion_evidence_gate.py"
)
BUNDLE_PATH = (
    ROOT
    / "deployment"
    / "runtime-promotion"
    / "runtime-promotion-evidence-bundle.yaml"
)


def _load(name: str, path: Path) -> Any:
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


gate = _load("runtime_promotion_evidence_gate_test", GATE_PATH)


def _bundle() -> dict[str, Any]:
    return copy.deepcopy(yaml.safe_load(BUNDLE_PATH.read_text(encoding="utf-8")))


def test_canonical_bundle_is_repository_ready_but_live_hold() -> None:
    bundle = gate.load_bundle(BUNDLE_PATH)
    result = gate.run_gate(bundle)

    assert result.repository_ready is True
    assert result.live_evidence_complete is False
    assert result.promotion_allowed is False
    assert result.recommendation == "HOLD"
    assert "OBS-TB1-LIVE-DELIVERY" in result.blockers
    assert "OBS-RUNNER-POLICY-PROMOTION" in result.blockers
    assert "OBS-EVIDENCE-CUSTODY" in result.blockers
    assert "OBS-LIVE-EFFECT-RESET" in result.blockers
    assert result.checked_components == len(bundle["required_components"])
    assert result.checked_change_records == len(bundle["required_change_records"])
    assert result.checked_policies == len(bundle["fail_closed_policies"])


def test_cli_reports_hold_without_claiming_promotion() -> None:
    completed = subprocess.run(
        [sys.executable, str(GATE_PATH), "--json", "check"],
        capture_output=True,
        text=True,
        check=True,
    )
    report = json.loads(completed.stdout)
    assert report["repository_ready"] is True
    assert report["live_evidence_complete"] is False
    assert report["promotion_allowed"] is False
    assert report["recommendation"] == "HOLD"


@pytest.mark.parametrize(
    "path,value",
    [
        (("runtime_status",), "READY"),
        (("execution_authority",), "hermes"),
        (("promotion_mode",), "PROMOTE"),
        (("candidate", "environment_id"), "dvwa"),
        (("candidate", "adapter_id"), "other-adapter"),
        (("candidate", "capability_id"), "web.discovery.tls"),
        (("candidate", "intrusiveness_level"), "L2"),
    ],
)
def test_in_memory_call_cannot_bypass_fixed_candidate_or_non_operational_state(
    path: tuple[str, ...], value: str
) -> None:
    bundle = _bundle()
    target: dict[str, Any] = bundle
    for key in path[:-1]:
        target = target[key]
    target[path[-1]] = value
    with pytest.raises(gate.PromotionGateError) as exc:
        gate.run_gate(bundle)
    assert exc.value.code == "BUNDLE_INVALID"


def test_duplicate_or_non_string_evidence_lists_fail_closed() -> None:
    bundle = _bundle()
    bundle["required_components"].append(bundle["required_components"][0])
    with pytest.raises(gate.PromotionGateError):
        gate.run_gate(bundle)

    bundle = _bundle()
    bundle["required_change_records"][0] = 42
    with pytest.raises(gate.PromotionGateError):
        gate.run_gate(bundle)


def test_bundle_paths_cannot_escape_repository_root() -> None:
    bundle = _bundle()
    bundle["campaign"] = "../../outside.yaml"
    with pytest.raises(gate.PromotionGateError) as exc:
        gate.run_gate(bundle)
    assert exc.value.code == "BUNDLE_PATH_INVALID"


def test_policy_gate_requires_canonical_fail_closed_posture() -> None:
    path = ROOT / "platform" / "runner-dispatch" / "routing-policy.yaml"
    policy = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert gate._policy_findings(path, policy) == []

    for key, bad_value in (
        ("state", "ENABLED"),
        ("default", "allow"),
        ("runtime_status", "READY"),
        ("execution_authority", "runner"),
    ):
        mutated = dict(policy)
        mutated[key] = bad_value
        findings = gate._policy_findings(path, mutated)
        assert findings
        assert key in findings[0]


def test_required_change_records_are_accepted_repository_evidence() -> None:
    for change_id in _bundle()["required_change_records"]:
        assert gate._change_record_findings(change_id) == []


def test_complete_live_observations_still_require_separate_human_promotion(monkeypatch) -> None:
    monkeypatch.setattr(gate, "_campaign_state", lambda _path: (True, "HOLD", []))
    result = gate.run_gate(_bundle())
    assert result.repository_ready is True
    assert result.live_evidence_complete is True
    assert result.promotion_allowed is False
    assert result.recommendation == "HOLD"
    assert result.blockers == ("HUMAN_PROMOTION_APPROVAL_REQUIRED",)


def test_non_hold_campaign_is_a_repository_gate_failure(monkeypatch) -> None:
    monkeypatch.setattr(
        gate,
        "_campaign_state",
        lambda _path: (False, "PROMOTE", ["OBS-LIVE-EFFECT-RESET"]),
    )
    result = gate.run_gate(_bundle())
    assert result.repository_ready is False
    assert result.promotion_allowed is False
    assert result.recommendation == "HOLD"
    assert any("campaign must remain HOLD" in item for item in result.blockers)


def test_missing_component_and_unaccepted_change_fail_repository_readiness(monkeypatch) -> None:
    bundle = _bundle()
    bundle["required_components"][0] = "platform/does-not-exist.py"
    result = gate.run_gate(bundle)
    assert result.repository_ready is False
    assert any("missing required component" in item for item in result.blockers)

    monkeypatch.setattr(
        gate,
        "_change_record_findings",
        lambda change_id: [f"change record {change_id} is not ACCEPTED"]
        if change_id == "CHG-HSL-009"
        else [],
    )
    result = gate.run_gate(_bundle())
    assert result.repository_ready is False
    assert any("CHG-HSL-009" in item for item in result.blockers)


def test_campaign_parser_treats_every_required_non_resolved_observation_as_blocker(
    tmp_path: Path,
) -> None:
    campaign = {
        "promotionRecommendation": "HOLD",
        "observations": [
            {"id": "PASS-ONE", "required": True, "result": "PASS", "status": "RESOLVED"},
            {"id": "BLOCKED-ONE", "required": True, "result": "BLOCKED", "status": "OPEN"},
            {"id": "OPTIONAL", "required": False, "result": "BLOCKED", "status": "OPEN"},
        ],
    }
    path = tmp_path / "campaign.yaml"
    path.write_text(yaml.safe_dump(campaign), encoding="utf-8")
    complete, recommendation, blockers = gate._campaign_state(path)
    assert complete is False
    assert recommendation == "HOLD"
    assert blockers == ["BLOCKED-ONE"]


def test_gate_source_has_no_runtime_mutation_or_external_execution_imports() -> None:
    source = GATE_PATH.read_text(encoding="utf-8")
    tree = ast.parse(source)
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module.split(".")[0])
    assert not imported & {"subprocess", "socket", "requests", "urllib", "os", "shutil"}
    for forbidden in (
        "chmod(",
        "chown(",
        "write_text(",
        "write_bytes(",
        "unlink(",
        "rename(",
        "replace(",
        "docker",
        "execute_command",
        "execute_runbook",
    ):
        assert forbidden not in source
