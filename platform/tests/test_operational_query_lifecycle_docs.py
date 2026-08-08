from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[2]
DOC = ROOT / "docs/roadmap/epics/EPIC-45-operational-query-and-discovery.md"
CATALOGUE = ROOT / "roadmap/epics/security-validation-platform-v2-concepts.yaml"


def _epic45() -> dict:
    data = yaml.safe_load(CATALOGUE.read_text(encoding="utf-8"))
    return next(item for item in data["concept_epics"] if item["concept_id"] == "EPIC-45")


def test_epic45_remains_implementing_with_pr196_evidence() -> None:
    text = DOC.read_text(encoding="utf-8")
    assert "**IMPLEMENTING**" in text
    assert "| IMPLEMENTING | yes |" in text
    assert "| AS_BUILT | no |" in text
    assert "| FINAL | no |" in text
    assert "PR #196" in text
    assert "54da73138b3de098e7911852616ffdc5f26d0005" in text
    assert "31233734226" in text
    assert "31233734241" in text
    assert "NO_RUNTIME_CHANGE" in text


def test_epic45_preserves_query_safety_boundaries() -> None:
    text = DOC.read_text(encoding="utf-8")
    assert "SANITIZED_METADATA_ONLY" in text
    assert "raw_evidence_exposed=false" in text
    assert "assurance_effect=NONE" in text
    assert "compliance_effect=NONE" in text
    assert "execution_authority=NONE" in text
    assert "absence of results never produces a `PASS` verdict" in text
    assert "required index kinds" in text


def test_epic45_machine_readable_lifecycle_remains_implementing() -> None:
    epic = _epic45()
    assert epic["status"] == "implementing"
    assert "NOT_RUN" in epic["current_state"] or "NOT_IMPLEMENTED" in epic["current_state"]
