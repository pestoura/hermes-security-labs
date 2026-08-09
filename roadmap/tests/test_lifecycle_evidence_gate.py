"""Fail-closed evidence gate for concept-epic lifecycle promotion.

Lane B established the lifecycle register: delivery status and concept lifecycle are two
different axes, and a `completed` umbrella never promotes the concept epics it covers.
This module adds the mechanical half of the promotion rule stated in
``docs/architecture/architecture-documentation-lifecycle.md`` section 6: a concept epic may
only sit at ``AS_BUILT`` or ``FINAL`` when section 15 of its document records *verifiable*
evidence, meaning at least one exact 40-character commit SHA and at least one CI run
identifier.

The gate is fail-closed in both directions:

- an unknown lifecycle status fails;
- a promoted epic without exact evidence fails;
- a non-promoted epic that nevertheless declares ``AS_BUILT`` reached fails.

It intentionally does not judge semantic sufficiency. Whether the cited evidence actually
satisfies the acceptance criteria in section 11 remains a human review responsibility, and
the promotion review register records that judgement per epic.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
CONCEPTS = ROOT / "roadmap" / "epics" / "security-validation-platform-v2-concepts.yaml"

PROMOTED = frozenset({"as_built", "final"})
NOT_PROMOTED = frozenset({"intent", "implementing"})
KNOWN_STATUSES = PROMOTED | NOT_PROMOTED

COMMIT_SHA = re.compile(r"\b[0-9a-f]{40}\b")
CI_RUN_ID = re.compile(r"\b\d{10,12}\b")


def _concept_epics() -> list[dict]:
    data = yaml.safe_load(CONCEPTS.read_text(encoding="utf-8"))
    return sorted(data["concept_epics"], key=lambda item: item["concept_id"])


def _section_15(item: dict) -> str:
    text = (ROOT / item["doc_path"]).read_text(encoding="utf-8")
    assert "## 15. As-built / final architecture" in text, item["concept_id"]
    return text.split("## 15. As-built / final architecture", 1)[1].split("\n## 16", 1)[0]


def _lifecycle_table(item: dict) -> str:
    return (ROOT / item["doc_path"]).read_text(encoding="utf-8")


CONCEPT_EPICS = _concept_epics()
IDS = [item["concept_id"] for item in CONCEPT_EPICS]


@pytest.mark.parametrize("item", CONCEPT_EPICS, ids=IDS)
def test_lifecycle_status_is_known(item: dict) -> None:
    """An unrecognised lifecycle value must never pass silently."""
    assert item["status"] in KNOWN_STATUSES, (
        f"{item['concept_id']} declares unknown lifecycle status {item['status']!r}"
    )


@pytest.mark.parametrize(
    "item",
    [item for item in CONCEPT_EPICS if item["status"] in PROMOTED],
    ids=[item["concept_id"] for item in CONCEPT_EPICS if item["status"] in PROMOTED],
)
def test_promoted_epics_cite_exact_evidence_in_section_15(item: dict) -> None:
    """AS_BUILT and FINAL require an exact commit SHA and a CI run identifier."""
    section = _section_15(item)
    shas = sorted(set(COMMIT_SHA.findall(section)))
    runs = sorted(set(CI_RUN_ID.findall(section)))
    assert shas, (
        f"{item['concept_id']} is {item['status'].upper()} but section 15 cites no exact "
        "40-character commit SHA"
    )
    assert runs, (
        f"{item['concept_id']} is {item['status'].upper()} but section 15 cites no CI run "
        "identifier"
    )


@pytest.mark.parametrize(
    "item",
    [item for item in CONCEPT_EPICS if item["status"] in PROMOTED],
    ids=[item["concept_id"] for item in CONCEPT_EPICS if item["status"] in PROMOTED],
)
def test_promoted_epics_declare_reached_states(item: dict) -> None:
    text = _lifecycle_table(item)
    assert "| AS_BUILT | yes |" in text, f"{item['concept_id']} does not declare AS_BUILT reached"
    expected_final = "yes" if item["status"] == "final" else "no"
    assert f"| FINAL | {expected_final} |" in text, item["concept_id"]


@pytest.mark.parametrize(
    "item",
    [item for item in CONCEPT_EPICS if item["status"] in NOT_PROMOTED],
    ids=[item["concept_id"] for item in CONCEPT_EPICS if item["status"] in NOT_PROMOTED],
)
def test_non_promoted_epics_never_declare_promotion(item: dict) -> None:
    """A non-promoted epic must not claim AS_BUILT or FINAL was reached."""
    text = _lifecycle_table(item)
    assert "| AS_BUILT | yes |" not in text, (
        f"{item['concept_id']} is {item['status'].upper()} but declares AS_BUILT reached"
    )
    assert "| FINAL | yes |" not in text, (
        f"{item['concept_id']} is {item['status'].upper()} but declares FINAL reached"
    )


def test_gate_covers_every_concept_epic() -> None:
    assert len(CONCEPT_EPICS) == 45
    assert len({item["concept_id"] for item in CONCEPT_EPICS}) == 45


def test_evidence_never_contains_credential_shaped_material() -> None:
    """Evidence must cite commits and runs, never secret-shaped values."""
    forbidden = ("ghp_", "github_pat_", "-----BEGIN", "Authorization: Bearer", "AKIA")
    for item in CONCEPT_EPICS:
        section = _section_15(item)
        found = [token for token in forbidden if token in section]
        assert not found, f"{item['concept_id']} section 15 contains {found}"
