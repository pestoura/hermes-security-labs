from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[2]
DOC = ROOT / "docs/roadmap/epics/EPIC-44-knowledge-quality-and-conflict-resolution.md"
CATALOGUE = ROOT / "roadmap/epics/security-validation-platform-v2-concepts.yaml"


def _epic44() -> dict:
    data = yaml.safe_load(CATALOGUE.read_text(encoding="utf-8"))
    return next(item for item in data["concept_epics"] if item["concept_id"] == "EPIC-44")


def test_epic44_remains_implementing_with_pr192_evidence() -> None:
    text = DOC.read_text(encoding="utf-8")
    assert "**IMPLEMENTING**" in text
    assert "| IMPLEMENTING | yes |" in text
    assert "| AS_BUILT | no |" in text
    assert "| FINAL | no |" in text
    assert "PR #192" in text
    assert "58fc929be589c3f5dbaaf0779a12c1060f7ad30e" in text
    assert "31232309584" in text
    assert "31232309593" in text
    assert "NO_RUNTIME_CHANGE" in text


def test_epic44_preserves_quality_and_authority_boundaries() -> None:
    text = DOC.read_text(encoding="utf-8")
    assert "QUALITY_POLICY_MET" in text
    assert "assurance_effect = NONE" in text
    assert "execution_authority = NONE" in text
    assert "Automatic resolution" in text or "automatic resolution" in text
    assert "historical snapshot rewrite" in text or "historical snapshots remain unchanged" in text
    assert "sole execution-authorization authority" in text


def test_epic44_machine_readable_lifecycle_remains_implementing() -> None:
    epic = _epic44()
    assert epic["status"] == "implementing"
    assert "NOT_IMPLEMENTED" in epic["current_state"] or "NOT_RUN" in epic["current_state"]
