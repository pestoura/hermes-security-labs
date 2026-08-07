from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[2]
EPIC_24 = ROOT / "docs/roadmap/epics/EPIC-24-purple-team-and-detection-validation.md"
EPIC_32 = ROOT / "docs/roadmap/epics/EPIC-32-resilience-validation-and-tlpt.md"
CATALOGUE = ROOT / "roadmap/epics/security-validation-platform-v2-concepts.yaml"


def _epic(concept_id: str) -> dict:
    data = yaml.safe_load(CATALOGUE.read_text(encoding="utf-8"))
    return next(item for item in data["concept_epics"] if item["concept_id"] == concept_id)


def test_f02_concepts_are_implementing_not_final() -> None:
    for path in (EPIC_24, EPIC_32):
        text = path.read_text(encoding="utf-8")
        assert "**IMPLEMENTING**" in text
        assert "| IMPLEMENTING | yes |" in text
        assert "| AS_BUILT | no |" in text
        assert "| FINAL | no |" in text
        assert "PR #153" in text
        assert "NO_RUNTIME_CHANGE" in text


def test_purple_team_absence_never_becomes_prevention() -> None:
    text = EPIC_24.read_text(encoding="utf-8")
    assert "NOT_OBSERVED" in text
    assert "never converted into prevention/detection" in text
    assert "SIEM/EDR" in text
    assert "NOT_IMPLEMENTED" in text
    assert "NOT_RUN" in text


def test_resilience_plan_does_not_claim_tlpt_completion() -> None:
    text = EPIC_32.read_text(encoding="utf-8")
    assert "EXERCISE_PLAN_ONLY" in text
    assert "executable=false" in text
    assert "CONTROL_PLANE_ONLY" in text
    assert "white-team" in text
    assert "escalation" in text
    assert "does not yet satisfy" in text
    assert "NOT_RUN" in text


def test_machine_readable_catalogue_matches_f02_lifecycle() -> None:
    for concept_id in ("EPIC-24", "EPIC-32"):
        item = _epic(concept_id)
        assert item["status"] == "implementing"
        assert "PR #153" in item["current_state"]
        assert "NOT_RUN" in item["current_state"] or "NOT_IMPLEMENTED" in item["current_state"]
