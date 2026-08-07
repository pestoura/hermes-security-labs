from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import jsonschema
import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
THREAT_DIR = ROOT / "platform" / "threat-validation"

spec = importlib.util.spec_from_file_location("threat_validation", THREAT_DIR / "threat_validation.py")
assert spec and spec.loader
module = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = module
spec.loader.exec_module(module)

ThreatValidationError = module.ThreatValidationError
build_emulation_plan = module.build_emulation_plan
build_threat_profile = module.build_threat_profile
degree_centrality = module.degree_centrality
find_paths = module.find_paths
validate_graph = module.validate_graph

SNAPSHOT = "ks_" + "a" * 32
EVIDENCE = "ev_" + "b" * 32


def _profile():
    return build_threat_profile(
        critical_function="synthetic customer portal",
        knowledge_snapshot_id=SNAPSHOT,
        actor_refs=["atlas.synthetic.actor"],
        objectives=["synthetic access validation"],
    )


def _graph():
    nodes = [
        {"id": "asset:web", "type": "asset"},
        {"id": "vuln:synthetic", "type": "vulnerability"},
        {"id": "control:waf", "type": "control"},
    ]
    edges = [
        {"from": "asset:web", "to": "vuln:synthetic", "state": "evidenced", "evidence_ids": [EVIDENCE]},
        {"from": "vuln:synthetic", "to": "control:waf", "state": "hypothetical", "evidence_ids": []},
    ]
    return nodes, edges


def test_threat_profile_is_bound_to_critical_function_and_snapshot() -> None:
    profile = _profile()
    assert profile["critical_function"] == "synthetic customer portal"
    assert profile["knowledge_snapshot_id"] == SNAPSHOT
    assert profile["executable"] is False
    schema = json.loads((THREAT_DIR / "threat-profile.schema.json").read_text())
    jsonschema.Draft202012Validator(schema).validate(profile)


def test_emulation_plan_is_non_executable_and_intrusiveness_bounded() -> None:
    profile = _profile()
    plan = build_emulation_plan(
        profile_id=profile["profile_id"],
        critical_function=profile["critical_function"],
        steps=[{"objective": "synthetic", "technique": "T1190", "intrusiveness": 1}],
    )
    assert plan["state"] == "PLAN_ONLY"
    assert plan["executable"] is False
    assert plan["authorization_source"] == "CONTROL_PLANE_ONLY"
    with pytest.raises(ThreatValidationError):
        build_emulation_plan(
            profile_id=profile["profile_id"],
            critical_function=profile["critical_function"],
            steps=[{"objective": "synthetic", "technique": "T1190", "intrusiveness": 5}],
        )


@pytest.mark.parametrize("forbidden", ["command", "argv", "shell", "credential_value", "secret", "token"])
def test_emulation_plan_rejects_execution_or_secret_material(forbidden: str) -> None:
    profile = _profile()
    step = {"objective": "synthetic", "technique": "T1190", "intrusiveness": 1}
    step[forbidden] = "synthetic-placeholder"
    with pytest.raises(ThreatValidationError):
        build_emulation_plan(profile_id=profile["profile_id"], critical_function=profile["critical_function"], steps=[step])


def test_attack_graph_distinguishes_hypothetical_and_evidenced_paths() -> None:
    nodes, edges = _graph()
    validate_graph(nodes, edges)
    assert find_paths(nodes, edges, start="asset:web", end="control:waf") == [["asset:web", "vuln:synthetic", "control:waf"]]
    assert find_paths(nodes, edges, start="asset:web", end="control:waf", evidenced_only=True) == []


def test_evidenced_edges_require_evidence_and_hypothetical_edges_cannot_claim_it() -> None:
    nodes, edges = _graph()
    broken = [dict(item) for item in edges]
    broken[0]["evidence_ids"] = []
    with pytest.raises(ThreatValidationError):
        validate_graph(nodes, broken)
    broken = [dict(item) for item in edges]
    broken[1]["evidence_ids"] = [EVIDENCE]
    with pytest.raises(ThreatValidationError):
        validate_graph(nodes, broken)


def test_degree_centrality_is_deterministic_and_non_executing() -> None:
    nodes, edges = _graph()
    assert degree_centrality(nodes, edges) == {"asset:web": 1, "vuln:synthetic": 2, "control:waf": 1}


def test_runtime_nonclaims_are_preserved() -> None:
    policy = yaml.safe_load((THREAT_DIR / "threat-validation-policy.yaml").read_text())
    assert policy["emulation_plans"]["executable"] is False
    assert policy["runtime_status"] == {
        "adversary_emulation": "NOT_RUN",
        "attack_flow_transport": "NOT_IMPLEMENTED",
        "graph_store": "NOT_IMPLEMENTED",
        "credential_use": "NOT_RUN",
        "lateral_movement": "NOT_RUN",
        "production_path_finding": "NOT_RUN",
    }
