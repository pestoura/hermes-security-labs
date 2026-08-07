from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[2]
EPIC_27 = ROOT / "docs/roadmap/epics/EPIC-27-risk-intelligence-and-contextual-prioritization.md"
EPIC_33 = ROOT / "docs/roadmap/epics/EPIC-33-finding-and-remediation-lifecycle.md"
CATALOGUE = ROOT / "roadmap/epics/security-validation-platform-v2-concepts.yaml"


def _epic(concept_id: str) -> dict:
    data = yaml.safe_load(CATALOGUE.read_text(encoding="utf-8"))
    return next(item for item in data["concept_epics"] if item["concept_id"] == concept_id)


def test_j01_concepts_are_as_built_not_final() -> None:
    for path in (EPIC_27, EPIC_33):
        text = path.read_text(encoding="utf-8")
        assert "**AS_BUILT**" in text
        assert "repository contract" in text
        assert "| IMPLEMENTING | yes |" in text
        assert "| AS_BUILT | yes |" in text
        assert "| FINAL | no |" in text
        assert "PR #155" in text
        assert "NO_RUNTIME_CHANGE" in text


def test_risk_model_preserves_operational_nonclaims() -> None:
    text = EPIC_27.read_text(encoding="utf-8")
    assert "production risk ingestion/scoring: `NOT_RUN`" in text
    assert "automated risk acceptance: `NOT_IMPLEMENTED`" in text
    assert "deterministic and auditable" in text


def test_finding_lifecycle_preserves_operational_nonclaims() -> None:
    text = EPIC_33.read_text(encoding="utf-8")
    assert "production ticketing synchronization: `NOT_RUN`" in text
    assert "customer remediation workflow: `NOT_RUN`" in text
    assert "real retest execution: `NOT_RUN`" in text
    assert "automatic risk acceptance: `NOT_IMPLEMENTED`" in text
    assert "owner/expiry enforcement: `NOT_IMPLEMENTED`" in text


def test_machine_readable_catalogue_matches_j01_as_built() -> None:
    for concept_id in ("EPIC-27", "EPIC-33"):
        item = _epic(concept_id)
        assert item["status"] == "as_built"
        assert "PR #155" in item["current_state"]
        assert "NOT_RUN" in item["current_state"]
