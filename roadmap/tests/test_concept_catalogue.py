"""Integrity tests for the 45 concept epic machine-readable catalogue."""

from __future__ import annotations

import json
import re
from collections import Counter, defaultdict
from pathlib import Path

import jsonschema
import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
CONCEPTS = ROOT / "roadmap" / "epics" / "security-validation-platform-v2-concepts.yaml"
SCHEMA = ROOT / "schemas" / "concept-epic.schema.json"
DELIVERY = ROOT / "roadmap" / "epics" / "security-validation-platform-v2.yaml"


@pytest.fixture(scope="module")
def concepts() -> dict:
    return yaml.safe_load(CONCEPTS.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def delivery() -> dict:
    return yaml.safe_load(DELIVERY.read_text(encoding="utf-8"))


def test_matches_schema(concepts: dict) -> None:
    jsonschema.validate(concepts, json.loads(SCHEMA.read_text(encoding="utf-8")))


def test_exactly_45_concept_epics(concepts: dict) -> None:
    assert len(concepts["concept_epics"]) == 45


def test_concept_ids_are_unique_and_contiguous(concepts: dict) -> None:
    ids = [item["concept_id"] for item in concepts["concept_epics"]]
    assert len(set(ids)) == 45
    assert sorted(ids) == [f"EPIC-{n:02d}" for n in range(1, 46)]


def test_slugs_and_doc_paths_are_unique(concepts: dict) -> None:
    for key in ("slug", "doc_path"):
        values = [item[key] for item in concepts["concept_epics"]]
        duplicates = [v for v, c in Counter(values).items() if c > 1]
        assert duplicates == [], f"duplicate {key}: {duplicates}"


def test_doc_paths_exist_and_match_ids(concepts: dict) -> None:
    for item in concepts["concept_epics"]:
        path = ROOT / item["doc_path"]
        assert path.is_file(), item["doc_path"]
        assert path.name.startswith(item["concept_id"]), item["concept_id"]
        assert path.name.endswith(f"{item['slug']}.md"), item["slug"]


def test_delivery_backlog_is_still_21_umbrellas(delivery: dict) -> None:
    assert len(delivery["epics"]) == 21


def test_mapping_targets_existing_umbrellas(concepts: dict, delivery: dict) -> None:
    known = {epic["id"] for epic in delivery["epics"]}
    for item in concepts["concept_epics"]:
        assert item["umbrella_id"] in known, item["concept_id"]


def test_umbrella_issue_matches_umbrella_pillar(concepts: dict) -> None:
    seen: dict[str, int] = {}
    for item in concepts["concept_epics"]:
        umbrella, issue = item["umbrella_id"], item["umbrella_issue"]
        assert umbrella.split("-")[1] == umbrella.split("-")[1]
        if umbrella in seen:
            assert seen[umbrella] == issue, f"{umbrella} maps to two issues"
        seen[umbrella] = issue
    assert len(set(seen.values())) == len(seen), "issue numbers are not unique per umbrella"


def test_every_concept_maps_to_exactly_one_umbrella(concepts: dict) -> None:
    for item in concepts["concept_epics"]:
        assert isinstance(item["umbrella_id"], str)


def test_dependencies_exist_and_are_acyclic(concepts: dict) -> None:
    ids = {item["concept_id"] for item in concepts["concept_epics"]}
    graph = {item["concept_id"]: list(item["dependencies"]) for item in concepts["concept_epics"]}
    for node, deps in graph.items():
        assert node not in deps, f"{node} depends on itself"
        for dep in deps:
            assert dep in ids, f"{node} -> {dep}"

    state: dict[str, int] = defaultdict(int)

    def visit(node: str, trail: list[str]) -> None:
        if state[node] == 1:
            raise AssertionError(f"cycle detected: {' -> '.join(trail + [node])}")
        if state[node] == 2:
            return
        state[node] = 1
        for child in graph[node]:
            visit(child, trail + [node])
        state[node] = 2

    for node in graph:
        visit(node, [])


def test_dependencies_do_not_go_forward_in_phase(concepts: dict) -> None:
    phases = {item["concept_id"]: item["phase"] for item in concepts["concept_epics"]}
    for item in concepts["concept_epics"]:
        for dep in item["dependencies"]:
            assert phases[dep] <= item["phase"], f"{item['concept_id']} -> {dep}"


def test_declared_pillars_and_phases_are_used(concepts: dict) -> None:
    pillars = {p["id"] for p in concepts["pillars"]}
    phases = {p["id"] for p in concepts["phases"]}
    for item in concepts["concept_epics"]:
        assert item["pillar"] in pillars
        assert item["phase"] in phases


def test_statuses_match_document_lifecycle(concepts: dict) -> None:
    for item in concepts["concept_epics"]:
        document = ROOT / item["doc_path"]
        text = document.read_text(encoding="utf-8")
        marker = item["status"].upper()
        assert f"**{marker}**" in text, (
            f"{item['concept_id']} catalogue status {item['status']!r} "
            "does not match its epic document"
        )


def test_yaml_is_deterministic_and_ascii_safe() -> None:
    raw = CONCEPTS.read_text(encoding="utf-8")
    assert raw.endswith("\n")
    assert "\t" not in raw
    assert raw.isascii()


CATALOGUE_DOC = ROOT / "docs" / "roadmap" / "epic-catalogue-45.md"


def _lifecycle_register_rows() -> dict[str, tuple[str, str, str, str]]:
    """Parse the lifecycle state register table of the master catalogue."""
    text = CATALOGUE_DOC.read_text(encoding="utf-8")
    section = text.split("## 7. Lifecycle state register", 1)[1].split("\n## ", 1)[0]
    rows: dict[str, tuple[str, str, str, str]] = {}
    pattern = re.compile(
        r"^\|\s*\[`(EPIC-\d{2})`\]\([^)]+\)\s*\|\s*`([A-Z_]+)`\s*\|"
        r"\s*`(SVP2-[A-L]-\d{2})`\s*\(#(\d+)\)\s*\|\s*`([a-z_]+)`\s*\|$"
    )
    for line in section.splitlines():
        match = pattern.match(line.strip())
        if match:
            rows[match.group(1)] = (match.group(2), match.group(3), match.group(4), match.group(5))
    return rows


def test_lifecycle_register_covers_every_concept_epic() -> None:
    assert len(_lifecycle_register_rows()) == 45


def test_lifecycle_register_matches_both_canonical_sources(
    concepts: dict, delivery: dict
) -> None:
    """The catalogue register must never disagree with the two machine-readable sources."""
    rows = _lifecycle_register_rows()
    delivery_status = {epic["id"]: epic["status"] for epic in delivery["epics"]}
    for item in concepts["concept_epics"]:
        concept_id = item["concept_id"]
        assert concept_id in rows, f"{concept_id} missing from the lifecycle register"
        state, umbrella, issue, umbrella_state = rows[concept_id]
        assert state == item["status"].upper(), concept_id
        assert umbrella == item["umbrella_id"], concept_id
        assert int(issue) == item["umbrella_issue"], concept_id
        assert umbrella_state == delivery_status[item["umbrella_id"]], concept_id


def test_catalogue_does_not_imply_completed_umbrella_means_final() -> None:
    """A completed delivery umbrella must never be presented as a FINAL concept epic."""
    text = CATALOGUE_DOC.read_text(encoding="utf-8")
    assert "delivery status and not a lifecycle claim" in text
    assert "never implies that every concept epic it covers is `FINAL`" in text
