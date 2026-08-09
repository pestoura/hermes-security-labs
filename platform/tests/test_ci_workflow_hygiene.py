"""CI hygiene contract for GitHub Actions workflows.

Locks the Lane C assurance invariants so CI acceleration work cannot silently
weaken determinism or supply-chain posture:

* every third-party / first-party action reference is pinned to a full 40-hex
  commit SHA (mutable tags such as ``@v4`` are rejected);
* every job declares an explicit ``timeout-minutes`` bound;
* every workflow triggered by repository events declares a ``concurrency``
  group so superseded runs cannot pile up;
* ``cancel-in-progress`` is never unconditionally true, so ``push`` runs on
  ``main`` (post-merge exact-SHA evidence) are never cancelled.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
WORKFLOW_DIR = ROOT / ".github/workflows"

SHA_PIN = re.compile(r"^[^@]+@[0-9a-f]{40}$")
EVENT_TRIGGERS = {"push", "pull_request", "pull_request_target", "schedule"}


def _workflows() -> list[Path]:
    paths = sorted(
        p for p in WORKFLOW_DIR.iterdir() if p.suffix in {".yml", ".yaml"}
    )
    assert paths, "no workflow files discovered"
    return paths


def _load(path: Path) -> dict:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert isinstance(data, dict), f"{path.name} is not a mapping"
    return data


def _triggers(document: dict) -> set[str]:
    # PyYAML resolves the bare ``on:`` key to boolean True.
    raw = document.get("on", document.get(True))
    if isinstance(raw, dict):
        return set(raw)
    if isinstance(raw, list):
        return set(raw)
    if isinstance(raw, str):
        return {raw}
    return set()


@pytest.mark.parametrize("path", _workflows(), ids=lambda p: p.name)
def test_every_action_reference_is_pinned_to_a_commit_sha(path: Path) -> None:
    document = _load(path)
    unpinned: list[str] = []
    for job in document.get("jobs", {}).values():
        for step in job.get("steps", []) or []:
            uses = step.get("uses")
            if uses and not SHA_PIN.match(uses):
                unpinned.append(uses)
    assert not unpinned, f"{path.name} uses mutable action refs: {unpinned}"


@pytest.mark.parametrize("path", _workflows(), ids=lambda p: p.name)
def test_every_job_declares_a_timeout(path: Path) -> None:
    document = _load(path)
    unbounded = [
        name
        for name, job in document.get("jobs", {}).items()
        if not isinstance(job.get("timeout-minutes"), int)
    ]
    assert not unbounded, f"{path.name} has jobs without timeout-minutes: {unbounded}"


@pytest.mark.parametrize("path", _workflows(), ids=lambda p: p.name)
def test_event_triggered_workflows_declare_concurrency(path: Path) -> None:
    document = _load(path)
    if not (_triggers(document) & EVENT_TRIGGERS):
        pytest.skip("manually dispatched workflow")
    concurrency = document.get("concurrency")
    assert isinstance(concurrency, dict), f"{path.name} lacks a concurrency group"
    assert concurrency.get("group"), f"{path.name} concurrency group is empty"


@pytest.mark.parametrize("path", _workflows(), ids=lambda p: p.name)
def test_push_runs_are_never_unconditionally_cancelled(path: Path) -> None:
    concurrency = _load(path).get("concurrency")
    if not isinstance(concurrency, dict):
        pytest.skip("no concurrency block")
    cancel = concurrency.get("cancel-in-progress", False)
    assert cancel is not True, (
        f"{path.name} cancels in-progress runs unconditionally, which can drop "
        "post-merge exact-SHA evidence runs"
    )


@pytest.mark.parametrize("path", _workflows(), ids=lambda p: p.name)
def test_workflow_declares_least_privilege_permissions(path: Path) -> None:
    document = _load(path)
    jobs = document.get("jobs", {})
    top_level = "permissions" in document
    missing = [name for name, job in jobs.items() if "permissions" not in job]
    assert top_level or not missing, (
        f"{path.name} declares no permissions at workflow level and jobs "
        f"{missing} inherit the default token scope"
    )


def test_validate_workflow_aggregates_every_gate_into_exact_sha_evidence() -> None:
    document = _load(WORKFLOW_DIR / "validate.yaml")
    jobs = document["jobs"]
    assert "evidence" in jobs, "validate.yaml lost its aggregation evidence job"
    evidence = jobs["evidence"]
    needs = set(evidence["needs"])
    gates = set(jobs) - {"evidence"}
    assert needs == gates, (
        "the evidence job must depend on every validate gate; "
        f"missing={sorted(gates - needs)} extra={sorted(needs - gates)}"
    )
    # The aggregation job must run even when a gate fails, and must fail closed.
    assert "always()" in str(evidence.get("if", ""))
    body = "\n".join(step.get("run", "") for step in evidence["steps"])
    assert "exit 1" in body, "the evidence job must fail closed on a non-success gate"
    assert "GITHUB_SHA" in body, "the evidence job must record the exact commit SHA"

