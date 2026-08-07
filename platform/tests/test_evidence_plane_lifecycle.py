from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[2]
EPIC_10 = ROOT / "docs/roadmap/epics/EPIC-10-evidence-plane.md"
EPIC_12 = ROOT / "docs/roadmap/epics/EPIC-12-redaction-and-data-classification.md"
CATALOGUE = ROOT / "roadmap/epics/security-validation-platform-v2-concepts.yaml"


def _epic(concept_id: str) -> dict:
    data = yaml.safe_load(CATALOGUE.read_text(encoding="utf-8"))
    return next(item for item in data["concept_epics"] if item["concept_id"] == concept_id)


def test_evidence_plane_concepts_are_implementing_not_final() -> None:
    for path in (EPIC_10, EPIC_12):
        text = path.read_text(encoding="utf-8")
        assert "**IMPLEMENTING**" in text
        assert "| IMPLEMENTING | yes |" in text
        assert "| AS_BUILT | no |" in text
        assert "| FINAL | no |" in text
        assert "NO_RUNTIME_CHANGE" in text


def test_epic_10_preserves_operational_non_claims() -> None:
    text = EPIC_10.read_text(encoding="utf-8")
    for marker in (
        "WORM",
        "retention",
        "production redaction/replay",
        "NOT_IMPLEMENTED",
        "NOT_RUN",
    ):
        assert marker in text


def test_epic_12_preserves_redaction_non_claims() -> None:
    text = EPIC_12.read_text(encoding="utf-8")
    for marker in (
        "Production redaction",
        "publication",
        "NOT_IMPLEMENTED",
        "NOT_RUN",
    ):
        assert marker in text


def test_machine_readable_catalogue_matches_document_lifecycle() -> None:
    epic_10 = _epic("EPIC-10")
    epic_12 = _epic("EPIC-12")

    assert epic_10["status"] == "implementing"
    assert epic_12["status"] == "implementing"
    assert "PR #141" in epic_10["current_state"]
    assert "PR #141" in epic_12["current_state"]
    assert "NOT_RUN" in epic_10["current_state"]
    assert "NOT_RUN" in epic_12["current_state"]
