"""Structural tests for the 45 concept epic documents.

Pure standard library. Complements ``roadmap/tests/test_concept_catalogue.py``,
which validates the machine-readable catalogue against its JSON schema.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
EPIC_DIR = ROOT / "docs" / "roadmap" / "epics"
CATALOGUE = ROOT / "docs" / "roadmap" / "epic-catalogue-45.md"
INTENT = ROOT / "docs" / "architecture" / "security-validation-platform-v2-intent.md"
LIFECYCLE = ROOT / "docs" / "architecture" / "architecture-documentation-lifecycle.md"

EXPECTED_COUNT = 45
NAME_RE = re.compile(r"^EPIC-(\d{2})-([a-z0-9]+(?:-[a-z0-9]+)*)\.md$")

REQUIRED_SECTIONS = (
    "## 1. Metadata",
    "## 2. Current status",
    "## 3. Problem and motivation",
    "## 4. Intended outcome",
    "## 5. Scope and non-goals",
    "## 6. Intent architecture",
    "## 7. Contracts, data and capabilities",
    "## 8. Dependencies and sequencing",
    "## 9. Security, risks and failure modes",
    "## 10. Deliverables",
    "## 11. Acceptance criteria",
    "## 12. Evidence and validation plan",
    "## 13. Decisions and open questions",
    "## 14. Implementation notes",
    "## 15. As-built / final architecture",
    "## 16. Document change log",
)

VALID_STATUSES = ("INTENT", "IMPLEMENTING", "AS_BUILT", "FINAL")

FORBIDDEN_CLAIMS = ("certified compliant", "fully compliant", "is compliant with")


def _epic_files() -> list[Path]:
    return sorted(EPIC_DIR.glob("EPIC-*.md"))


def test_epic_directory_exists() -> None:
    assert EPIC_DIR.is_dir(), "docs/roadmap/epics/ is missing"


def test_exactly_45_epic_documents() -> None:
    files = _epic_files()
    assert len(files) == EXPECTED_COUNT, f"expected {EXPECTED_COUNT} documents, found {len(files)}"


def test_epic_numbers_are_complete_and_unique() -> None:
    numbers = []
    for path in _epic_files():
        match = NAME_RE.match(path.name)
        assert match, f"bad epic filename: {path.name}"
        numbers.append(int(match.group(1)))
    assert sorted(numbers) == list(range(1, EXPECTED_COUNT + 1))


def test_slugs_are_unique() -> None:
    slugs = [NAME_RE.match(p.name).group(2) for p in _epic_files()]
    assert len(set(slugs)) == len(slugs), "duplicate epic slugs"


@pytest.mark.parametrize("path", _epic_files(), ids=lambda p: p.name)
def test_required_sections_present(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    missing = [section for section in REQUIRED_SECTIONS if section not in text]
    assert not missing, f"{path.name} is missing sections: {missing}"


@pytest.mark.parametrize("path", _epic_files(), ids=lambda p: p.name)
def test_title_matches_filename(path: Path) -> None:
    number = NAME_RE.match(path.name).group(1)
    first = path.read_text(encoding="utf-8").splitlines()[0]
    assert first.startswith(f"# EPIC-{number} — "), f"{path.name} has a mismatched title"


@pytest.mark.parametrize("path", _epic_files(), ids=lambda p: p.name)
def test_metadata_declares_umbrella_and_status(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    assert re.search(r"\| Delivery umbrella \| `SVP2-[A-L]-\d{2}`", text), path.name
    assert any(f"**{status}**" in text for status in VALID_STATUSES), (
        f"{path.name} does not declare a lifecycle status"
    )


@pytest.mark.parametrize("path", _epic_files(), ids=lambda p: p.name)
def test_reserved_sections_are_marked(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    tail = text.split("## 14. Implementation notes", 1)[1]
    assert "Reserved" in tail, f"{path.name} section 14/15 must be marked reserved"


@pytest.mark.parametrize("path", _epic_files() + [CATALOGUE, INTENT, LIFECYCLE], ids=lambda p: p.name)
def test_documents_have_substantive_content(path: Path) -> None:
    assert len(path.read_text(encoding="utf-8").strip()) > 1500, f"{path.name} is too thin"


@pytest.mark.parametrize("path", _epic_files() + [CATALOGUE, INTENT, LIFECYCLE], ids=lambda p: p.name)
def test_no_formal_compliance_claims(path: Path) -> None:
    lowered = path.read_text(encoding="utf-8").lower()
    found = [claim for claim in FORBIDDEN_CLAIMS if claim in lowered]
    assert not found, f"{path.name} makes a formal compliance claim: {found}"


def test_catalogue_references_every_epic_document() -> None:
    text = CATALOGUE.read_text(encoding="utf-8")
    missing = [p.name for p in _epic_files() if f"epics/{p.name}" not in text]
    assert not missing, f"epic-catalogue-45.md does not reference: {missing}"


def test_catalogue_explains_45_versus_21() -> None:
    text = CATALOGUE.read_text(encoding="utf-8")
    for token in ("45", "21", "Delivery umbrellas", "Concept epics"):
        assert token in text, f"catalogue does not explain {token!r}"


def test_intent_document_marks_state_categories() -> None:
    text = INTENT.read_text(encoding="utf-8")
    for marker in ("CURRENT/IMPLEMENTED", "INTENT/PLANNED", "FUTURE/DEPENDENT"):
        assert marker in text, f"intent document is missing the {marker} marker"


def test_intent_document_has_the_minimum_diagram_set() -> None:
    text = INTENT.read_text(encoding="utf-8")
    assert text.count("```mermaid") >= 9, "intent document needs at least nine Mermaid diagrams"


def test_lifecycle_contract_blocks_closure_without_as_built() -> None:
    text = LIFECYCLE.read_text(encoding="utf-8").lower()
    assert "section 15" in text
    assert "may be closed" in text or "closed while" in text
