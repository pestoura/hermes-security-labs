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


def _catalogue() -> dict[str, dict]:
    data = yaml.safe_load(CATALOGUE.read_text(encoding="utf-8"))
    return {item["concept_id"]: item for item in data["concept_epics"]}


def test_epic21_is_as_built_but_not_final() -> None:
    text = DOCS["EPIC-21"].read_text(encoding="utf-8")
    assert "**AS_BUILT**" in text
    assert "| AS_BUILT | yes |" in text
    assert "| FINAL | no |" in text
    assert "PR #182" in text
    assert "NO_RUNTIME_CHANGE" in text


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


def test_epic38_is_implementing_without_external_mapping_or_planner_claims() -> None:
    text = DOCS["EPIC-38"].read_text(encoding="utf-8")
    assert "**IMPLEMENTING**" in text
    assert "| IMPLEMENTING | yes |" in text
    assert "| AS_BUILT | no |" in text
    assert "| FINAL | no |" in text
    assert "PR #186" in text
    assert "authoritative external CWE/CAPEC/ATT&CK mapping acquisition: `NOT_RUN`" in text
    assert "mapping curation/approval workflow: `NOT_IMPLEMENTED`" in text
    assert "production campaign-planner consumption" in text
    assert "`NOT_IMPLEMENTED` / `NOT_RUN`" in text
    assert "Hermes / Control Plane remains the sole execution-authorization authority" in text
    assert "NO_RUNTIME_CHANGE" in text


def test_epic39_is_implementing_without_external_sync_or_auto_adoption() -> None:
    text = DOCS["EPIC-39"].read_text(encoding="utf-8")
    assert "**IMPLEMENTING**" in text
    assert "| IMPLEMENTING | yes |" in text
    assert "| AS_BUILT | no |" in text
    assert "| FINAL | no |" in text
    assert "PR #188" in text
    assert "TAXII or equivalent external ATT&CK synchronization: `NOT_RUN`" in text
    assert "automatic ATT&CK version adoption: `NOT_IMPLEMENTED`" in text
    assert "production migration/adoption workflow: `NOT_IMPLEMENTED` / `NOT_RUN`" in text
    assert "authoritative/current-source claim for supplied snapshots: not claimed" in text
    assert "Hermes / Control Plane remains the sole execution-authorization authority" in text
    assert "NO_RUNTIME_CHANGE" in text


def test_machine_readable_catalogue_matches_e01_boundary() -> None:
    catalogue = _catalogue()

    epic21 = catalogue["EPIC-21"]
    assert epic21["status"] == "as_built"
    assert "PR #182" in epic21["current_state"]

    for concept_id, pr in (
        ("EPIC-36", "PR #146"),
        ("EPIC-37", "PR #184"),
        ("EPIC-38", "PR #186"),
        ("EPIC-39", "PR #188"),
    ):
        item = catalogue[concept_id]
        assert item["status"] == "implementing"
        assert pr in item["current_state"]
        assert "NO_RUNTIME_CHANGE" in item["current_state"] or concept_id == "EPIC-36"

    epic39 = catalogue["EPIC-39"]
    assert "NOT_RUN" in epic39["current_state"]
    assert "NOT_IMPLEMENTED" in epic39["current_state"]
    assert "automatic" in epic39["current_state"].lower()
