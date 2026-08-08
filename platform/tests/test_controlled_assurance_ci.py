from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ASSURANCE = ROOT / "platform/assurance"


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


controlled = _load("controlled_assurance_ci", ASSURANCE / "controlled_assurance_ci.py")
evidence = _load("failure_evidence_ci", ASSURANCE / "failure_evidence.py")


def test_controlled_assurance_exercises_all_canonical_cases_and_is_evidence_valid() -> None:
    results = controlled.run_controlled_assurance(observed_at="2026-08-08T22:30:00Z")
    assert set(results) == set(controlled.CASES) == set(evidence.FAILURE_CASES)
    assert all(record["boundary"] == "CONTROLLED_CI" for record in results.values())
    digest = evidence.validate_failure_evidence(results)
    assert len(digest) == 64


def test_controlled_evidence_ids_are_unique_per_failure_semantic() -> None:
    results = controlled.run_controlled_assurance(observed_at="2026-08-08T22:31:00Z")
    ids = [record["evidence_id"] for record in results.values()]
    assert len(ids) == len(set(ids))
