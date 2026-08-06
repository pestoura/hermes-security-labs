"""Integrity tests for EPIC-01 architecture decisions and contracts.

Pure standard library plus pytest. The tests validate structure and traceability only;
they do not claim runtime enforcement of roadmap contracts.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
ARCH = ROOT / "docs" / "architecture"
ADR_DIR = ARCH / "adr"
ADR_INDEX = ADR_DIR / "README.md"
CONTRACTS = ARCH / "contracts" / "README.md"
REFERENCE = ARCH / "security-validation-reference-architecture.md"
DOC_INDEX = ROOT / "docs" / "README.md"

ADR_NAME_RE = re.compile(r"^ADR-(\d{4})-[a-z0-9]+(?:-[a-z0-9]+)*\.md$")
REQUIRED_ADR_SECTIONS = (
    "## Context",
    "## Decision",
    "## Consequences",
    "### Positive",
    "### Negative",
    "## Security implications",
    "## Alternatives considered",
    "## Evidence and validation",
    "## Review triggers",
)


def _adr_files() -> list[Path]:
    return sorted(path for path in ADR_DIR.glob("ADR-*.md") if path.name != "README.md")


def test_architecture_contract_paths_exist() -> None:
    for path in (ADR_INDEX, CONTRACTS, REFERENCE):
        assert path.is_file(), f"missing EPIC-01 architecture artefact: {path.relative_to(ROOT)}"


def test_initial_adr_set_is_numbered_and_contiguous() -> None:
    files = _adr_files()
    assert len(files) >= 8, "EPIC-01 requires the initial structural ADR set"
    numbers: list[int] = []
    for path in files:
        match = ADR_NAME_RE.match(path.name)
        assert match, f"invalid ADR filename: {path.name}"
        numbers.append(int(match.group(1)))
    assert len(numbers) == len(set(numbers)), "duplicate ADR numbers"
    assert numbers == list(range(1, len(numbers) + 1)), "ADR numbers must be contiguous"


@pytest.mark.parametrize("path", _adr_files(), ids=lambda path: path.name)
def test_adrs_have_required_contract(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    assert "- **Status:**" in text, f"{path.name} has no status"
    assert "- **Decision owners:**" in text, f"{path.name} has no decision owner"
    missing = [heading for heading in REQUIRED_ADR_SECTIONS if heading not in text]
    assert not missing, f"{path.name} is missing sections: {missing}"


def test_adr_index_links_every_decision() -> None:
    index = ADR_INDEX.read_text(encoding="utf-8")
    missing = [path.name for path in _adr_files() if path.name not in index]
    assert not missing, f"ADR index does not reference: {missing}"


def test_roadmap_structural_decisions_have_adr_coverage() -> None:
    index = ADR_INDEX.read_text(encoding="utf-8").lower()
    required = (
        "knowledge proposes",
        "tb0–tb4",
        "typed execution",
        "fail-safe evaluation",
        "isolation and least privilege",
        "source of truth and provenance",
        "raw and sanitized evidence",
        "generated content never auto-merges",
        "reproducibility before acceptance",
        "explicit authorization",
    )
    missing = [decision for decision in required if decision not in index]
    assert not missing, f"structural decisions without ADR coverage: {missing}"


def test_reference_architecture_defines_all_trust_boundaries() -> None:
    text = REFERENCE.read_text(encoding="utf-8")
    for number in range(5):
        assert f"| `TB{number}` |" in text, f"TB{number} is missing from the canonical table"
    for heading in ("Responsabilidades", "Proibições", "Contrato de travessia", "Falha segura"):
        assert heading in text, f"trust-boundary table is missing {heading!r}"


def test_contract_inventory_covers_cross_plane_contracts() -> None:
    text = CONTRACTS.read_text(encoding="utf-8")
    required = (
        "Operator decision and authorization request",
        "Active authorization reference",
        "Typed execution request",
        "Runner dispatch and result",
        "Laboratory target and network attachment",
        "Evidence write envelope",
        "Evidence derivative and publication request",
        "Knowledge proposal",
        "Knowledge snapshot reference",
    )
    missing = [contract for contract in required if contract not in text]
    assert not missing, f"canonical contract inventory is incomplete: {missing}"


def test_contract_inventory_does_not_claim_runtime_enforcement() -> None:
    text = CONTRACTS.read_text(encoding="utf-8")
    assert "does **not** claim" in text
    assert "`INTENT`" in text
    assert "fail closed" in text


def test_documentation_navigation_publishes_epic_01_artefacts() -> None:
    index = DOC_INDEX.read_text(encoding="utf-8")
    for target in ("architecture/adr/README.md", "architecture/contracts/README.md"):
        assert target in index, f"docs/README.md does not publish {target}"


def test_architecture_documents_contain_no_executable_offensive_examples() -> None:
    paths = [REFERENCE, CONTRACTS, ADR_INDEX, *_adr_files()]
    forbidden = (
        "msfconsole -x",
        "sqlmap -u",
        "hydra -l",
        "curl http://",
        "curl https://",
        "docker run --privileged",
    )
    for path in paths:
        lowered = path.read_text(encoding="utf-8").lower()
        found = [pattern for pattern in forbidden if pattern in lowered]
        assert not found, f"{path.relative_to(ROOT)} contains executable offensive examples: {found}"
