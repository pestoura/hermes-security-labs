from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[2]
EPIC_15 = ROOT / "docs/roadmap/epics/EPIC-15-backlog-and-documentation-quality.md"
CATALOGUE = ROOT / "roadmap/epics/security-validation-platform-v2-concepts.yaml"


def _epic15() -> dict:
    data = yaml.safe_load(CATALOGUE.read_text(encoding="utf-8"))
    return next(item for item in data["concept_epics"] if item["concept_id"] == "EPIC-15")


def test_epic15_is_final_with_full_lifecycle() -> None:
    text = EPIC_15.read_text(encoding="utf-8")
    assert "**FINAL**" in text
    assert "| INTENT | yes |" in text
    assert "| IMPLEMENTING | yes |" in text
    assert "| AS_BUILT | yes |" in text
    assert "| FINAL | yes |" in text
    assert "Reserved" in text
    assert "NO_RUNTIME_CHANGE" in text


def test_epic15_final_evidence_is_recorded() -> None:
    text = EPIC_15.read_text(encoding="utf-8")
    for token in ("PR #99", "PR #135", "PR #138", "umbrella #78"):
        assert token in text
    assert "45 concept epic documents" in text
    assert "21 delivery umbrellas" in text
    assert "Exactly 45 concept epic documents exist and validate" in text
    assert "Every concept epic maps to an existing umbrella" in text


def test_epic15_records_historical_lifecycle_divergence() -> None:
    text = EPIC_15.read_text(encoding="utf-8")
    normalized = text.lower()
    assert "historical lifecycle inconsistency" in normalized
    assert "section 15" in normalized
    assert "issue #78 was nevertheless closed" in normalized
    assert "does **not** retroactively claim" in text
    assert "_Not started._" not in text


def test_machine_readable_catalogue_matches_epic15_final() -> None:
    item = _epic15()
    assert item["status"] == "final"
    assert "PR #99" in item["current_state"]
    assert "PR #135" in item["current_state"]
    assert "PR #138" in item["current_state"]
    assert "#78" in item["current_state"]
    assert "NO_RUNTIME_CHANGE" in item["current_state"]
