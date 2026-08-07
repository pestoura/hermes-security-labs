from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[2]
CATALOGUE = ROOT / "roadmap/epics/security-validation-platform-v2-concepts.yaml"
DOCS = {
    "EPIC-21": ROOT / "docs/roadmap/epics/EPIC-21-framework-crosswalk-and-canonical-methodology.md",
    "EPIC-36": ROOT / "docs/roadmap/epics/EPIC-36-security-knowledge-fabric.md",
    "EPIC-37": ROOT / "docs/roadmap/epics/EPIC-37-vulnerability-intelligence-synchronization.md",
    "EPIC-38": ROOT / "docs/roadmap/epics/EPIC-38-cwe-capec-attack-semantic-chain.md",
    "EPIC-39": ROOT / "docs/roadmap/epics/EPIC-39-attack-synchronization-service.md",
}
INTENT_ONLY = {"EPIC-38", "EPIC-39"}


def _catalogue() -> dict[str, dict]:
    data = yaml.safe_load(CATALOGUE.read_text(encoding="utf-8"))
    return {item["concept_id"]: item for item in data["concept_epics"]}


def test_epic36_is_implementing_but_not_final() -> None:
    text = DOCS["EPIC-36"].read_text(encoding="utf-8")
    assert "**IMPLEMENTING**" in text
    assert "| IMPLEMENTING | yes |" in text
    assert "| AS_BUILT | no |" in text
    assert "| FINAL | no |" in text
    assert "PR #146" in text
    assert "NOT_RUN" in text
    assert "NOT_IMPLEMENTED" in text
    assert "NO_RUNTIME_CHANGE" in text


def test_epic37_is_implementing_without_runtime_claims() -> None:
    text = DOCS["EPIC-37"].read_text(encoding="utf-8")
    assert "**IMPLEMENTING**" in text
    assert "| IMPLEMENTING | yes |" in text
    assert "| AS_BUILT | no |" in text
    assert "| FINAL | no |" in text
    assert "PR #184" in text
    assert "external NVD/CISA/FIRST network fetch: `NOT_RUN`" in text
    assert "automatic source updates: `NOT_IMPLEMENTED`" in text
    assert "production ingestion pipeline: `NOT_IMPLEMENTED`" in text
    assert "Hermes / Control Plane remains the sole execution-authorization authority" in text
    assert "NO_RUNTIME_CHANGE" in text


def test_generic_fabric_does_not_promote_unimplemented_specific_services() -> None:
    for concept_id in INTENT_ONLY:
        text = DOCS[concept_id].read_text(encoding="utf-8")
        assert "**INTENT**" in text
        assert "| IMPLEMENTING | no |" in text
        assert "| AS_BUILT | no |" in text
        assert "| FINAL | no |" in text
        assert "PR #146" in text
        assert "remains INTENT" in text
        assert "NO_RUNTIME_CHANGE" in text


def test_machine_readable_catalogue_matches_e01_boundary() -> None:
    catalogue = _catalogue()

    epic36 = catalogue["EPIC-36"]
    assert epic36["status"] == "implementing"
    assert "PR #146" in epic36["current_state"]
    assert "NOT_RUN" in epic36["current_state"]

    epic21 = catalogue["EPIC-21"]
    assert epic21["status"] == "as_built"
    assert "PR #182" in epic21["current_state"]

    epic37 = catalogue["EPIC-37"]
    assert epic37["status"] == "implementing"
    assert "PR #184" in epic37["current_state"]
    assert "NOT_RUN" in epic37["current_state"]
    assert "NOT_IMPLEMENTED" in epic37["current_state"]
    assert "NO_RUNTIME_CHANGE" in epic37["current_state"]

    for concept_id in INTENT_ONLY:
        item = catalogue[concept_id]
        assert item["status"] == "intent"
        assert "PR #146" in item["current_state"]
        assert "remains INTENT" in item["current_state"]
