from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
PATH = ROOT / "platform/threat-validation/attack_graph_binding.py"
spec = importlib.util.spec_from_file_location("attack_graph_binding", PATH)
assert spec and spec.loader
binding = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = binding
spec.loader.exec_module(binding)


def test_plan_is_bound_to_same_profile_and_critical_function() -> None:
    profile = {"profile_id": "tp_1", "critical_function": "care-delivery", "executable": False}
    plan = {
        "profile_id": "tp_1",
        "critical_function": "care-delivery",
        "state": "PLAN_ONLY",
        "executable": False,
        "authorization_source": "CONTROL_PLANE_ONLY",
    }
    binding.validate_plan_binding(profile=profile, plan=plan)
    with pytest.raises(binding.ThreatGraphBindingError, match="PLAN_CRITICAL_FUNCTION_MISMATCH"):
        binding.validate_plan_binding(profile=profile, plan={**plan, "critical_function": "other"})


def test_path_distinguishes_evidenced_from_hypothetical_segments() -> None:
    evidenced = binding.classify_path(
        path=["asset-a", "identity-b", "asset-c"],
        edges=[
            {"from": "asset-a", "to": "identity-b", "state": "evidenced", "evidence_ids": ["ev-1"]},
            {"from": "identity-b", "to": "asset-c", "state": "evidenced", "evidence_ids": ["ev-2"]},
        ],
    )
    assert evidenced["classification"] == "evidenced"
    assert evidenced["evidence_ids"] == ["ev-1", "ev-2"]

    mixed = binding.classify_path(
        path=["asset-a", "identity-b", "asset-c"],
        edges=[
            {"from": "asset-a", "to": "identity-b", "state": "evidenced", "evidence_ids": ["ev-1"]},
            {"from": "identity-b", "to": "asset-c", "state": "hypothetical", "evidence_ids": []},
        ],
    )
    assert mixed["classification"] == "hypothetical"
    assert mixed["hypothetical_segments"] == [["identity-b", "asset-c"]]
