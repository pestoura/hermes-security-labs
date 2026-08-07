from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[2]
EPIC_22 = ROOT / "docs/roadmap/epics/EPIC-22-threat-informed-security-validation.md"
EPIC_23 = ROOT / "docs/roadmap/epics/EPIC-23-attack-graph-and-attack-flow.md"
CATALOGUE = ROOT / "roadmap/epics/security-validation-platform-v2-concepts.yaml"


def _epic(concept_id: str) -> dict:
    data = yaml.safe_load(CATALOGUE.read_text(encoding="utf-8"))
    return next(item for item in data["concept_epics"] if item["concept_id"] == concept_id)


def test_f01_concepts_are_implementing_not_final() -> None:
    for path in (EPIC_22, EPIC_23):
        text = path.read_text(encoding="utf-8")
        assert "**IMPLEMENTING**" in text
        assert "| IMPLEMENTING | yes |" in text
        assert "| AS_BUILT | no |" in text
        assert "| FINAL | no |" in text
        assert "PR #150" in text
        assert "NO_RUNTIME_CHANGE" in text


def test_threat_profile_preserves_provenance_and_execution_gaps() -> None:
    text = EPIC_22.read_text(encoding="utf-8")
    assert "source/date" in text
    assert "knowledge snapshot" in text
    assert "CONTROL_PLANE_ONLY" in text
    assert "adversary emulation" in text
    assert "NOT_RUN" in text


def test_attack_graph_preserves_hypothetical_and_runtime_boundaries() -> None:
    text = EPIC_23.read_text(encoding="utf-8")
    assert "hypothetical" in text
    assert "evidenced" in text
    assert "Attack Flow" in text
    assert "NOT_IMPLEMENTED" in text
    assert "production path finding" in text
    assert "NOT_RUN" in text


def test_machine_readable_catalogue_matches_f01_lifecycle() -> None:
    for concept_id in ("EPIC-22", "EPIC-23"):
        item = _epic(concept_id)
        assert item["status"] == "implementing"
        assert "PR #150" in item["current_state"]
        assert "NOT_RUN" in item["current_state"] or "NOT_IMPLEMENTED" in item["current_state"]
