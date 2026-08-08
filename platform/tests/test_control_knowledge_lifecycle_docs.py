from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[2]
EPIC_40 = ROOT / "docs/roadmap/epics/EPIC-40-nist-control-knowledge-layer.md"
CATALOGUE = ROOT / "roadmap/epics/security-validation-platform-v2-concepts.yaml"


def _epic40() -> dict:
    data = yaml.safe_load(CATALOGUE.read_text(encoding="utf-8"))
    return next(item for item in data["concept_epics"] if item["concept_id"] == "EPIC-40")


def test_epic40_is_implementing_not_as_built_or_final() -> None:
    text = EPIC_40.read_text(encoding="utf-8")
    assert "**IMPLEMENTING**" in text
    assert "| INTENT | yes |" in text
    assert "| IMPLEMENTING | yes |" in text
    assert "| AS_BUILT | no |" in text
    assert "| FINAL | no |" in text
    assert "PR #190" in text
    assert "NO_RUNTIME_CHANGE" in text


def test_epic40_preserves_assessment_and_source_nonclaims() -> None:
    text = EPIC_40.read_text(encoding="utf-8")
    assert "external NIST catalogue acquisition: `NOT_RUN`" in text
    assert "authoritative/current source verification: `NOT_IMPLEMENTED` / `NOT_RUN`" in text
    assert "formal control-effectiveness assessment workflow: `NOT_IMPLEMENTED` / `NOT_RUN`" in text
    assert "formal compliance/certification conclusion: not implemented and not claimed" in text
    assert "`compliance_verdict = NOT_EVALUATED`" in text
    assert "`certification_claim = NONE`" in text
    assert "Hermes / Control Plane remains the sole execution-authorization authority" in text


def test_machine_readable_catalogue_matches_epic40_implementing_boundary() -> None:
    item = _epic40()
    assert item["status"] == "implementing"
    assert "PR #190" in item["current_state"]
    assert "NOT_RUN" in item["current_state"]
    assert "NOT_IMPLEMENTED" in item["current_state"]
    assert "NOT_EVALUATED" in item["current_state"]
    assert "sole execution-authorization authority" in item["current_state"]
    assert "AS_BUILT" in item["current_state"]
    assert "FINAL" in item["current_state"]
    assert "NO_RUNTIME_CHANGE" in item["current_state"]
