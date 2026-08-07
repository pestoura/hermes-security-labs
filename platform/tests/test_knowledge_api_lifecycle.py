from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[2]
CATALOGUE = ROOT / "roadmap/epics/security-validation-platform-v2-concepts.yaml"
DOCS = {
    "EPIC-40": ROOT / "docs/roadmap/epics/EPIC-40-nist-control-knowledge-layer.md",
    "EPIC-43": ROOT / "docs/roadmap/epics/EPIC-43-knowledge-driven-campaign-planner.md",
    "EPIC-44": ROOT / "docs/roadmap/epics/EPIC-44-knowledge-quality-and-conflict-resolution.md",
    "EPIC-45": ROOT / "docs/roadmap/epics/EPIC-45-operational-query-and-discovery.md",
}
IMPLEMENTING = {"EPIC-43", "EPIC-44", "EPIC-45"}


def _catalogue() -> dict[str, dict]:
    data = yaml.safe_load(CATALOGUE.read_text(encoding="utf-8"))
    return {item["concept_id"]: item for item in data["concept_epics"]}


def test_supported_e02_concepts_are_implementing_not_final() -> None:
    for concept_id in IMPLEMENTING:
        text = DOCS[concept_id].read_text(encoding="utf-8")
        assert "**IMPLEMENTING**" in text
        assert "| IMPLEMENTING | yes |" in text
        assert "| AS_BUILT | no |" in text
        assert "| FINAL | no |" in text
        assert "NO_RUNTIME_CHANGE" in text


def test_epic40_remains_intent_without_control_layer() -> None:
    text = DOCS["EPIC-40"].read_text(encoding="utf-8")
    assert "**INTENT**" in text
    assert "| IMPLEMENTING | no |" in text
    assert "| AS_BUILT | no |" in text
    assert "| FINAL | no |" in text
    assert "PR #148" in text
    assert "remains INTENT" in text
    assert "NO_RUNTIME_CHANGE" in text


def test_campaign_proposal_never_claims_execution_authority() -> None:
    text = DOCS["EPIC-43"].read_text(encoding="utf-8")
    assert "PROPOSAL_ONLY" in text
    assert "executable=false" in text
    assert "CONTROL_PLANE_ONLY" in text
    assert "production_planner" in text
    assert "NOT_RUN" in text


def test_machine_readable_catalogue_matches_e02_boundary() -> None:
    catalogue = _catalogue()

    for concept_id in IMPLEMENTING:
        item = catalogue[concept_id]
        assert item["status"] == "implementing"
        assert "NOT_RUN" in item["current_state"] or "NOT_IMPLEMENTED" in item["current_state"]

    epic40 = catalogue["EPIC-40"]
    assert epic40["status"] == "intent"
    assert "PR #148" in epic40["current_state"]
    assert "remains INTENT" in epic40["current_state"]
