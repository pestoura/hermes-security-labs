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
    assert "Reserved" in text


def test_epic06_preserves_non_runtime_boundary() -> None:
    text = EPIC.read_text(encoding="utf-8")

    for marker in (
        "image build/publication: `NOT_RUN`",
        "container start: `NOT_RUN`",
        "real non-root observation: `NOT_RUN`",
        "real read-only-root observation: `NOT_RUN`",
        "real capability-drop observation: `NOT_RUN`",
        "Hermes deployment: `NOT_RUN`",
        "runtime changes: `NO_RUNTIME_CHANGE`",
    ):
        assert marker in text


def test_runtime_base_readme_keeps_candidate_only_claims() -> None:
    text = README.read_text(encoding="utf-8")

    assert "core runtime must execute as a non-root UID" in text
    assert "root filesystem is declared read-only" in text
    assert "`NET_RAW` exists only in an explicit, justified `raw-network` profile" in text
    assert "No image is built or promoted by this block" in text
    assert "`NO_RUNTIME_CHANGE`" in text


def test_epic06_catalogue_matches_implementing_state() -> None:
    data = yaml.safe_load(CATALOGUE.read_text(encoding="utf-8"))
    epics = data["concept_epics"]
    epic = next(item for item in epics if item["concept_id"] == "EPIC-06")

    assert epic["status"] == "implementing"
    assert "PR #142" in epic["current_state"]
    assert "NOT_RUN" in epic["current_state"]
