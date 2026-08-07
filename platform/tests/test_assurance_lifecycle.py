from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[2]
CATALOGUE = ROOT / "roadmap/epics/security-validation-platform-v2-concepts.yaml"
DOCS = {
    "EPIC-11": ROOT / "docs/roadmap/epics/EPIC-11-technical-observability.md",
    "EPIC-13": ROOT / "docs/roadmap/epics/EPIC-13-reliability-and-chaos-testing.md",
    "EPIC-14": ROOT / "docs/roadmap/epics/EPIC-14-real-operations-and-maintenance.md",
    "EPIC-31": ROOT / "docs/roadmap/epics/EPIC-31-opentelemetry-end-to-end.md",
    "EPIC-34": ROOT / "docs/roadmap/epics/EPIC-34-maturity-benchmarking-and-scientific-quality.md",
}
IMPLEMENTING = {"EPIC-11", "EPIC-13", "EPIC-31", "EPIC-34"}


def _catalogue() -> dict[str, dict]:
    data = yaml.safe_load(CATALOGUE.read_text(encoding="utf-8"))
    return {item["concept_id"]: item for item in data["concept_epics"]}


def test_only_pr144_supported_concepts_are_promoted() -> None:
    for concept_id in IMPLEMENTING:
        text = DOCS[concept_id].read_text(encoding="utf-8")
        assert "**IMPLEMENTING**" in text
        assert "| IMPLEMENTING | yes |" in text
        assert "| AS_BUILT | no |" in text
        assert "| FINAL | no |" in text
        assert "PR #144" in text
        assert "NOT_RUN" in text
        assert "NO_RUNTIME_CHANGE" in text


def test_epic14_remains_intent_until_operating_model_exists() -> None:
    text = DOCS["EPIC-14"].read_text(encoding="utf-8")
    assert "**INTENT**" in text
    assert "| IMPLEMENTING | no |" in text
    assert "| AS_BUILT | no |" in text
    assert "| FINAL | no |" in text
    assert "remains intentionally unpromoted" in text
    assert "routine maintenance procedures" in text
    assert "incident handling" in text
    assert "NOT_IMPLEMENTED" in text
    assert "NO_RUNTIME_CHANGE" in text


def test_machine_readable_catalogue_matches_assurance_boundary() -> None:
    catalogue = _catalogue()
    for concept_id in IMPLEMENTING:
        item = catalogue[concept_id]
        assert item["status"] == "implementing"
        assert "PR #144" in item["current_state"]
        assert "NOT_RUN" in item["current_state"]

    epic14 = catalogue["EPIC-14"]
    assert epic14["status"] == "intent"
    assert "PR #144" in epic14["current_state"]
    assert "remains INTENT" in epic14["current_state"]
