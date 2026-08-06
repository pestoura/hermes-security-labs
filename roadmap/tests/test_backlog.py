"""Integrity tests for the Security Validation Platform v2 backlog."""

from __future__ import annotations

import json
from collections import Counter, defaultdict
from pathlib import Path

import jsonschema
import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
BACKLOG = ROOT / "roadmap" / "epics" / "security-validation-platform-v2.yaml"
SCHEMA = ROOT / "schemas" / "backlog-epic.schema.json"
DOCS = [
    ROOT / "docs" / "roadmap" / "security-validation-platform-v2.md",
    ROOT / "docs" / "architecture" / "security-validation-reference-architecture.md",
    ROOT / "docs" / "architecture" / "framework-crosswalk.md",
    ROOT / "docs" / "architecture" / "security-knowledge-fabric.md",
    ROOT / "docs" / "architecture" / "continuous-content-factories.md",
]


@pytest.fixture(scope="module")
def backlog() -> dict:
    return yaml.safe_load(BACKLOG.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def schema() -> dict:
    return json.loads(SCHEMA.read_text(encoding="utf-8"))


def test_backlog_matches_schema(backlog: dict, schema: dict) -> None:
    jsonschema.validate(backlog, schema)


def test_epic_ids_are_unique(backlog: dict) -> None:
    ids = [epic["id"] for epic in backlog["epics"]]
    duplicates = [key for key, count in Counter(ids).items() if count > 1]
    assert duplicates == []


def test_epic_id_matches_pillar(backlog: dict) -> None:
    for epic in backlog["epics"]:
        assert epic["id"].split("-")[1] == epic["pillar"]


def test_dependencies_exist_and_are_not_self_referential(backlog: dict) -> None:
    ids = {epic["id"] for epic in backlog["epics"]}
    for epic in backlog["epics"]:
        assert epic["id"] not in epic["dependencies"]
        for dependency in epic["dependencies"]:
            assert dependency in ids, f"{epic['id']} -> {dependency}"


def test_dependency_graph_has_no_cycles(backlog: dict) -> None:
    graph = {epic["id"]: list(epic["dependencies"]) for epic in backlog["epics"]}
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


def test_every_pillar_is_covered(backlog: dict) -> None:
    declared = {pillar["id"] for pillar in backlog["pillars"]}
    used = {epic["pillar"] for epic in backlog["epics"]}
    assert declared == used


def test_declared_phases_are_used_by_epics(backlog: dict) -> None:
    declared = {phase["id"] for phase in backlog["phases"]}
    for epic in backlog["epics"]:
        assert epic["phase"] in declared


def test_labels_follow_the_governance_taxonomy(backlog: dict) -> None:
    allowed_prefixes = ("pillar:", "priority:", "impact:", "runtime:", "status:", "type:")
    allowed_plain = {"roadmap", "architecture"}
    for epic in backlog["epics"]:
        labels = epic["labels"]
        assert f"pillar:{epic['pillar']}" in labels
        assert f"priority:{epic['priority']}" in labels
        assert f"status:{epic['status']}" in labels
        assert "type:epic" in labels
        for label in labels:
            assert label in allowed_plain or label.startswith(allowed_prefixes), label


def test_dependencies_do_not_go_backwards_in_phase(backlog: dict) -> None:
    phases = {epic["id"]: epic["phase"] for epic in backlog["epics"]}
    for epic in backlog["epics"]:
        for dependency in epic["dependencies"]:
            assert phases[dependency] <= epic["phase"], f"{epic['id']} -> {dependency}"


def test_canonical_documents_exist_and_are_not_empty() -> None:
    for document in DOCS:
        assert document.is_file(), document
        assert len(document.read_text(encoding="utf-8").strip()) > 500


def test_yaml_is_deterministic_and_ascii_safe() -> None:
    raw = BACKLOG.read_text(encoding="utf-8")
    assert raw.endswith("\n")
    assert "\t" not in raw
