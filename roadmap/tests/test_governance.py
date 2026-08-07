from __future__ import annotations

import json
import re
from collections import Counter
from pathlib import Path

import jsonschema
import yaml

ROOT = Path(__file__).resolve().parents[2]
GOVERNANCE = ROOT / "roadmap/governance.yaml"
GOVERNANCE_SCHEMA = ROOT / "schemas/roadmap-governance.schema.json"
BACKLOG = ROOT / "roadmap/epics/security-validation-platform-v2.yaml"
ROADMAP_DOC = ROOT / "docs/roadmap/security-validation-platform-v2.md"


def _load(path: Path) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def test_governance_matches_schema() -> None:
    governance = _load(GOVERNANCE)
    schema = json.loads(GOVERNANCE_SCHEMA.read_text(encoding="utf-8"))

    jsonschema.validate(governance, schema)


def test_every_backlog_epic_uses_exactly_the_declared_label_dimensions() -> None:
    governance = _load(GOVERNANCE)
    backlog = _load(BACKLOG)
    taxonomy = governance["label_taxonomy"]
    required_plain = set(taxonomy["required_plain"])
    scoped = taxonomy["scoped"]

    for epic in backlog["epics"]:
        labels = epic["labels"]
        counts = Counter(labels)
        assert all(count == 1 for count in counts.values()), epic["id"]
        assert required_plain <= set(labels), epic["id"]
        assert f"pillar:{epic['pillar']}" in labels
        assert f"priority:{epic['priority']}" in labels
        assert f"status:{epic['status']}" in labels
        assert "type:epic" in labels

        for dimension in ("pillar", "priority", "status", "type"):
            assert sum(label.startswith(f"{dimension}:") for label in labels) == 1
        for dimension in ("impact", "runtime"):
            assert sum(label.startswith(f"{dimension}:") for label in labels) <= 1

        allowed_plain = required_plain
        for label in labels:
            if ":" not in label:
                assert label in allowed_plain
                continue
            dimension = label.split(":", 1)[0]
            assert dimension in scoped
            rule = scoped[dimension]
            if "values" in rule:
                assert label in rule["values"]
            else:
                assert re.fullmatch(rule["pattern"], label)


def test_ready_and_done_criteria_are_unique_and_machine_identifiable() -> None:
    governance = _load(GOVERNANCE)

    for key, prefix in (("Definition_of_Ready", "DOR-"), ("Definition_of_Done", "DOD-")):
        criteria = governance[key]
        ids = [item["id"] for item in criteria]
        assert len(ids) == len(set(ids))
        assert all(item.startswith(prefix) for item in ids)
        assert all(item["verification"] for item in criteria)


def test_every_critical_function_has_one_resilience_objective() -> None:
    governance = _load(GOVERNANCE)
    functions = {item["id"] for item in governance["critical_functions"]}
    objectives = [item["function"] for item in governance["resilience_objectives"]]

    assert set(objectives) == functions
    assert all(count == 1 for count in Counter(objectives).values())


def test_release_map_covers_every_delivery_epic_exactly_once() -> None:
    governance = _load(GOVERNANCE)
    backlog = _load(BACKLOG)
    expected = {epic["id"] for epic in backlog["epics"]}
    assigned = [epic for release in governance["releases"] for epic in release["epics"]]

    assert set(assigned) == expected
    assert all(count == 1 for count in Counter(assigned).values())


def test_roadmap_keeps_governance_sections_and_release_names() -> None:
    governance = _load(GOVERNANCE)
    text = ROADMAP_DOC.read_text(encoding="utf-8")

    for heading in (
        "## 10. Definition of Ready",
        "## 11. Definition of Done",
        "## 12. Roadmap por releases",
    ):
        assert heading in text
    for release in governance["releases"]:
        assert release["id"] in text
        assert release["milestone"] in text


def test_finality_rule_explicitly_blocks_unproven_completion() -> None:
    governance = _load(GOVERNANCE)

    assert "no_final_claim_with_NOT_RUN_or_NOT_IMPLEMENTED_acceptance_criteria" in governance["release_rules"]
