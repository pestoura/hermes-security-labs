from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[2]
EPIC_35 = ROOT / "docs/roadmap/epics/EPIC-35-sdk-plugins-and-runtime-certification.md"
CATALOGUE = ROOT / "roadmap/epics/security-validation-platform-v2-concepts.yaml"


def _epic35() -> dict:
    data = yaml.safe_load(CATALOGUE.read_text(encoding="utf-8"))
    return next(item for item in data["concept_epics"] if item["concept_id"] == "EPIC-35")


def test_epic35_is_implementing_not_as_built_or_final() -> None:
    text = EPIC_35.read_text(encoding="utf-8")
    assert "**IMPLEMENTING**" in text
    assert "| IMPLEMENTING | yes |" in text
    assert "| AS_BUILT | no |" in text
    assert "| FINAL | no |" in text
    assert "PR #147" in text
    assert "Reserved" in text
    assert "NO_RUNTIME_CHANGE" in text


def test_extension_contract_preserves_authority_and_runtime_nonclaims() -> None:
    text = EPIC_35.read_text(encoding="utf-8")
    normalized = text.lower()
    assert "sole execution-authorization authority" in text
    assert "never creates, grants or expands an `authorization_ref`" in text
    assert "not a production cryptographic signature-verification implementation" in normalized
    assert "production cryptographic signature verification: `not_run`" in normalized
    assert "extension loading/import: `not_run`" in normalized
    assert "runtime isolation/sandbox enforcement: `not_run`" in normalized
    assert "production effective permission-intersection enforcement: `not_implemented` / `not_run`" in normalized
    assert "third-party extension execution: `not_run`" in normalized


def test_machine_readable_catalogue_matches_k01_lifecycle() -> None:
    item = _epic35()
    assert item["status"] == "implementing"
    assert "PR #147" in item["current_state"]
    assert "NOT_RUN" in item["current_state"]
    assert "sole authority" in item["current_state"]
