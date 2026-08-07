from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[2]
EPIC_21 = ROOT / "docs/roadmap/epics/EPIC-21-framework-crosswalk-and-canonical-methodology.md"
CATALOGUE = ROOT / "roadmap/epics/security-validation-platform-v2-concepts.yaml"


def _epic21() -> dict:
    data = yaml.safe_load(CATALOGUE.read_text(encoding="utf-8"))
    return next(item for item in data["concept_epics"] if item["concept_id"] == "EPIC-21")


def test_epic21_is_repository_as_built_not_final() -> None:
    text = EPIC_21.read_text(encoding="utf-8")
    assert "**AS_BUILT**" in text
    assert "| INTENT | yes |" in text
    assert "| IMPLEMENTING | yes |" in text
    assert "| AS_BUILT | yes |" in text
    assert "| FINAL | no |" in text
    assert "PR #182" in text
    assert "Reserved" in text
    assert "NO_RUNTIME_CHANGE" in text


def test_epic21_preserves_mapping_and_runtime_nonclaims() -> None:
    text = EPIC_21.read_text(encoding="utf-8")
    normalized = text.lower()
    assert "authoritative external framework synchronization: `not_run`" in normalized
    assert "automatic framework updates/version adoption: `not_implemented`" in normalized
    assert "planner consumer integration: `not_implemented`" in normalized
    assert "reporting consumer integration: `not_implemented`" in normalized
    assert "graph/database production consumer integration: `not_implemented` / `not_run`" in normalized
    assert "external certification or compliance assessment: **not claimed**" in normalized
    assert "execution effect of crosswalk data: `none`" in normalized


def test_epic21_preserves_execution_authority_boundary() -> None:
    text = EPIC_21.read_text(encoding="utf-8")
    assert "sole execution-authorization authority" in text
    assert "never create, grant or expand an `authorization_ref`" in text
    assert "caller-controlled `roe_decision`" in text


def test_machine_readable_catalogue_matches_epic21_as_built() -> None:
    item = _epic21()
    assert item["status"] == "as_built"
    assert "PR #182" in item["current_state"]
    assert "NOT_RUN" in item["current_state"]
    assert "NOT_IMPLEMENTED" in item["current_state"]
    assert "sole execution-authorization authority" in item["current_state"]
