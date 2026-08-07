from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
EPIC07 = ROOT / "docs/roadmap/epics/EPIC-07-capability-registry.md"
EPIC30 = ROOT / "docs/roadmap/epics/EPIC-30-supply-chain-attestations.md"
README = ROOT / "platform/capability-registry/README.md"
CATALOGUE = ROOT / "roadmap/epics/security-validation-platform-v2-concepts.yaml"


def _assert_implementing_not_final(path: Path) -> str:
    text = path.read_text(encoding="utf-8")
    assert "**IMPLEMENTING**" in text
    assert "| IMPLEMENTING | yes |" in text
    assert "| AS_BUILT | no |" in text
    assert "| FINAL | no |" in text
    assert "PR #143" in text
    assert "Reserved" in text
    assert "NO_RUNTIME_CHANGE" in text
    return text


def test_epic07_is_implementing_without_runtime_claims() -> None:
    text = _assert_implementing_not_final(EPIC07)
    for marker in (
        "live gateway registry consumption: `NOT_RUN`",
        "campaign registry snapshot pinning: `NOT_RUN`",
        "production capability routing/use: `NOT_RUN`",
        "production revocation exercise: `NOT_RUN`",
    ):
        assert marker in text


def test_epic30_is_implementing_without_supply_chain_execution_claims() -> None:
    text = _assert_implementing_not_final(EPIC30)
    for marker in (
        "SBOM generation: `NOT_RUN`",
        "artefact signing/signature verification: `NOT_RUN`",
        "provenance generation/verification: `NOT_RUN`",
        "image scanning: `NOT_RUN`",
        "image publication/promotion: `NOT_RUN`",
        "production revocation: `NOT_RUN`",
    ):
        assert marker in text


def test_registry_readme_preserves_fail_closed_stable_promotion() -> None:
    text = README.read_text(encoding="utf-8")
    for marker in (
        "SBOM reference present",
        "signature reference present",
        "provenance reference present",
        "zero blocking scan findings",
        "Revocation makes a capability immediately unusable",
        "does not generate SBOMs",
        "`NO_RUNTIME_CHANGE`",
    ):
        assert marker in text


def test_c02_catalogue_moves_both_concepts_together() -> None:
    data = yaml.safe_load(CATALOGUE.read_text(encoding="utf-8"))
    epics = {item["concept_id"]: item for item in data["concept_epics"]}

    for concept_id in ("EPIC-07", "EPIC-30"):
        epic = epics[concept_id]
        assert epic["status"] == "implementing"
        assert "PR #143" in epic["current_state"]
        assert "NOT_RUN" in epic["current_state"]
