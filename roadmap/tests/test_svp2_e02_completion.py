from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
BACKLOG = ROOT / "roadmap" / "epics" / "security-validation-platform-v2.yaml"
POLICY = ROOT / "platform" / "knowledge-api" / "knowledge-api-policy.yaml"
EPIC_43 = ROOT / "docs" / "roadmap" / "epics" / "EPIC-43-knowledge-driven-campaign-planner.md"
EPIC_44 = ROOT / "docs" / "roadmap" / "epics" / "EPIC-44-knowledge-quality-and-conflict-resolution.md"
EPIC_45 = ROOT / "docs" / "roadmap" / "epics" / "EPIC-45-operational-query-and-discovery.md"
COMPLETION = ROOT / "docs" / "roadmap" / "SVP2-E-02-completion-as-built.md"


def _epic():
    data = yaml.safe_load(BACKLOG.read_text(encoding="utf-8"))
    return next(epic for epic in data["epics"] if epic["id"] == "SVP2-E-02")


def test_e02_completed_without_promoting_dependent_concepts_or_runtime() -> None:
    epic = _epic()
    policy = yaml.safe_load(POLICY.read_text(encoding="utf-8"))
    completion = COMPLETION.read_text(encoding="utf-8")

    assert epic["status"] == "completed"
    assert "status:completed" in epic["labels"]
    assert "docs/roadmap/SVP2-E-02-completion-as-built.md" in epic["references"]

    for path in (EPIC_43, EPIC_44, EPIC_45):
        text = path.read_text(encoding="utf-8")
        assert "**IMPLEMENTING**" in text
        assert "| AS_BUILT | no |" in text
        assert "| FINAL | no |" in text

    controlled = policy["controlled_local_persistence"]
    assert controlled == {
        "status": "PASS_CONTROLLED_CI",
        "technical_pr": 228,
        "merge_sha": "79ad05837b6bbe7c26787be31c2ff2229aa97438",
        "backend": "local_create_only_filesystem",
        "snapshot_persistence": "PASS_CONTROLLED_CI",
        "snapshot_provenance_gate": "PASS_CONTROLLED_CI",
        "campaign_snapshot_pinning": "PASS_CONTROLLED_CI",
        "campaign_rebind": "FORBIDDEN",
        "temporal_append_only": "PASS_CONTROLLED_CI",
        "proposal_persistence": "PASS_CONTROLLED_CI",
        "proposal_execution_authority": "NONE",
        "proposal_dispatch_available": False,
        "operational_query_snapshot_filter": "PASS_CONTROLLED_CI",
        "operational_query_minimum_confidence": "PASS_CONTROLLED_CI",
        "production_service_claim": "NONE",
    }
    assert policy["campaigns"]["proposals_executable"] is False
    assert policy["campaigns"]["authorization_source"] == "CONTROL_PLANE_ONLY"
    assert policy["runtime_status"] == {
        "http_api": "NOT_IMPLEMENTED",
        "database": "NOT_IMPLEMENTED",
        "graph_query_engine": "NOT_IMPLEMENTED",
        "external_sync": "NOT_RUN",
        "production_planner": "NOT_RUN",
        "production_temporal_ingestion": "NOT_RUN",
        "production_snapshot_store": "NOT_RUN",
        "production_campaign_binding_store": "NOT_RUN",
        "control_plane_runtime_integration": "NOT_RUN",
    }

    assert "SVP2-E-02`: **candidate for `completed`**" in completion
    assert "EPIC-43`: **`IMPLEMENTING` / `AS_BUILT=no` / `FINAL=no`**" in completion
    assert "EPIC-44`: **`IMPLEMENTING` / `AS_BUILT=no` / `FINAL=no`**" in completion
    assert "EPIC-45`: **`IMPLEMENTING` / `AS_BUILT=no` / `FINAL=no`**" in completion
    assert "proposal execution authority: **`NONE`**" in completion
    assert "Control Plane runtime integration: **`NOT_RUN`**" in completion
    assert "DOD-10" in completion
