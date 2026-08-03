from __future__ import annotations

import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

from validate_pack import load_runbooks, validate


def test_pack_is_valid():
    assert validate() == []


def test_each_runbook_is_a_separate_file():
    entries = load_runbooks()
    assert len(entries) == len({path for path, _ in entries})
    assert all(path.suffix == ".yaml" for path, _ in entries)


def test_ids_and_profiles_are_unique():
    entries = load_runbooks()
    ids = [item["metadata"]["id"] for _, item in entries]
    profiles = [(item["metadata"]["category"], item["steps"][1]["profile"]) for _, item in entries]
    assert len(ids) == len(set(ids))
    assert len(profiles) == len(set(profiles))


def test_runbooks_have_specific_evidence_and_decisions():
    for _, item in load_runbooks():
        assert len(item["steps"]) == 3
        assert len(item["evaluation"]["vulnerable_when"]) >= 2
        assert len(item["evaluation"]["secure_when"]) >= 2
        assert len(item["evaluation"]["inconclusive_when"]) >= 2
        assert any("evidence" in key for step in item["steps"] for key in step["arguments"])


def test_category_counts_match_documented_pack():
    counts = Counter(item["metadata"]["category"] for _, item in load_runbooks())
    assert sum(counts.values()) == 100
    assert counts == Counter({'agent-discovery': 6, 'direct-prompt-injection': 14, 'indirect-prompt-injection': 12, 'tool-poisoning': 12, 'excessive-agency': 10, 'mcp-authorization': 12, 'rag-poisoning': 10, 'memory-security': 8, 'exfiltration': 10, 'output-integrity': 6})
