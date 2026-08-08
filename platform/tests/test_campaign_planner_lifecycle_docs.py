from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[2]
DOC = ROOT / "docs/roadmap/epics/EPIC-43-knowledge-driven-campaign-planner.md"
CATALOGUE = ROOT / "roadmap/epics/security-validation-platform-v2-concepts.yaml"


def _epic43() -> dict:
    data = yaml.safe_load(CATALOGUE.read_text(encoding="utf-8"))
    return next(item for item in data["concept_epics"] if item["concept_id"] == "EPIC-43")


def test_epic43_remains_implementing_with_pr194_evidence() -> None:
    text = DOC.read_text(encoding="utf-8")
    assert "**IMPLEMENTING**" in text
    assert "| IMPLEMENTING | yes |" in text
    assert "| AS_BUILT | no |" in text
    assert "| FINAL | no |" in text
    assert "PR #194" in text
    assert "52b355b61a3d273b8d6d934ab270157dc0a34c48" in text
    assert "31233069181" in text
    assert "31233069182" in text
    assert "NO_RUNTIME_CHANGE" in text


def test_epic43_preserves_proposal_and_authority_boundary() -> None:
    text = DOC.read_text(encoding="utf-8")
    assert "PROPOSAL_ONLY" in text
    assert "executable=false" in text
    assert "authorization_effect=NONE" in text
    assert "requires_fresh_authorization=true" in text
    assert "CONTROL_PLANE_ONLY" in text
    assert "planning constraints never create or expand authorization" in text
    assert "sole execution-authorization authority" in text


def test_epic43_machine_readable_lifecycle_remains_implementing() -> None:
    epic = _epic43()
    assert epic["status"] == "implementing"
    assert "NOT_RUN" in epic["current_state"] or "NOT_IMPLEMENTED" in epic["current_state"]
