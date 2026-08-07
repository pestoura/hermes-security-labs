from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[2]
EPIC_26 = ROOT / "docs/roadmap/epics/EPIC-26-interoperable-playbooks-and-results.md"
CATALOGUE = ROOT / "roadmap/epics/security-validation-platform-v2-concepts.yaml"


def _epic26() -> dict:
    data = yaml.safe_load(CATALOGUE.read_text(encoding="utf-8"))
    return next(item for item in data["concept_epics"] if item["concept_id"] == "EPIC-26")


def test_epic26_is_implementing_not_as_built_or_final() -> None:
    text = EPIC_26.read_text(encoding="utf-8")
    assert "**IMPLEMENTING**" in text
    assert "| IMPLEMENTING | yes |" in text
    assert "| AS_BUILT | no |" in text
    assert "| FINAL | no |" in text
    assert "PR #157" in text
    assert "Reserved" in text
    assert "NO_RUNTIME_CHANGE" in text


def test_interchange_never_grants_execution_authorization() -> None:
    text = EPIC_26.read_text(encoding="utf-8")
    assert "imported content never grants authorization" in text.lower()
    assert "sole execution-authorization authority" in text
    assert "External import/export and round-trip compatibility remain `NOT_RUN`" in text
    assert "OSCAL" in text
    assert "CACAO" in text
    assert "Attack Flow" in text


def test_interoperability_preserves_operational_nonclaims() -> None:
    text = EPIC_26.read_text(encoding="utf-8")
    assert "authoritative schema fetch/lifecycle: `NOT_IMPLEMENTED` / `NOT_RUN`" in text
    assert "cryptographic signing: `NOT_RUN`" in text
    assert "external transport/delivery: `NOT_RUN`" in text
    assert "external consumers: `NOT_RUN`" in text
    assert "certified conformance: **not claimed**" in text


def test_machine_readable_catalogue_matches_j02_lifecycle() -> None:
    item = _epic26()
    assert item["status"] == "implementing"
    assert "PR #157" in item["current_state"]
    assert "NOT_RUN" in item["current_state"]
