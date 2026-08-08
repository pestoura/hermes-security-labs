from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
EPIC = ROOT / "docs/roadmap/epics/EPIC-06-kali-image-factory.md"
README = ROOT / "platform/runtime-base/README.md"
CATALOGUE = ROOT / "roadmap/epics/security-validation-platform-v2-concepts.yaml"


def test_epic06_is_implementing_but_not_final() -> None:
    text = EPIC.read_text(encoding="utf-8")

    assert "**IMPLEMENTING**" in text
    assert "| IMPLEMENTING | yes |" in text
    assert "| AS_BUILT | no |" in text
    assert "| FINAL | no |" in text
    assert "PR #142" in text
    assert "PR #215" in text
    assert "Reserved" in text


def test_epic06_records_controlled_ci_runtime_without_production_overclaim() -> None:
    text = EPIC.read_text(encoding="utf-8")

    for marker in (
        "image build: `PASS_CONTROLLED_CI`",
        "container start: `PASS_CONTROLLED_CI`",
        "non-root observation: `PASS_CONTROLLED_CI`",
        "read-only root observation: `PASS_CONTROLLED_CI`",
        "capability-drop observation: `PASS_CONTROLLED_CI`",
        "image publication: `NOT_RUN`",
        "SBOM/signing/provenance promotion: `NOT_RUN`",
        "Hermes deployment: `NOT_RUN`",
        "deployed runtime changes: `NO_DEPLOYED_RUNTIME_CHANGE`",
    ):
        assert marker in text


def test_runtime_base_readme_scopes_controlled_candidate_claims() -> None:
    text = README.read_text(encoding="utf-8")

    assert "core runtime policy requires execution as a non-root UID" in text
    assert "root filesystem is read-only for the controlled candidate" in text
    assert "`NET_RAW` exists only in an explicit, justified `raw-network` profile" in text
    assert "PR #215" in text
    assert "Image publication, SBOM generation, signing, provenance attestation" in text
    assert "`NO_DEPLOYED_RUNTIME_CHANGE`" in text


def test_epic06_catalogue_remains_implementing_until_broader_factory_evidence() -> None:
    data = yaml.safe_load(CATALOGUE.read_text(encoding="utf-8"))
    epics = data["concept_epics"]
    epic = next(item for item in epics if item["concept_id"] == "EPIC-06")

    assert epic["status"] == "implementing"
    assert "PR #142" in epic["current_state"]
    assert "NOT_RUN" in epic["current_state"]
