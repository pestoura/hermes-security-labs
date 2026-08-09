"""Fail-closed tests for the dry-run cleanup planner.

Mirrors the loader pattern of the other deployment/tests modules: the
deployment package is injected on sys.path and the module is imported
directly, so no dependency install is required. Every case drives
``evaluate_path``/``plan_cleanup`` against a synthetic ``tmp_path`` repo and a
fixed ``now``, so results are identical on any runner and nothing on the real
host is ever touched.
"""

from __future__ import annotations

import json
from pathlib import Path
import sys

import pytest

DEPLOYMENT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(DEPLOYMENT_DIR))

import cleanup_planner as cp  # noqa: E402

#: Fixed evaluation clock so age math is deterministic across runners.
NOW = 1_700_000_000.0
DAY = 86400.0


def _policy():
    """Default policy (controls the allowlist roots and max ages)."""
    return cp.parse_policy(cp.DEFAULT_POLICY)


def _make_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / ".tmp-hsl").mkdir()
    (repo / "artifacts").mkdir()
    (repo / "evidence").mkdir()
    (repo / "src").mkdir()
    return repo


def _touch(path: Path, age_days: float) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("{}", encoding="utf-8")
    mtime = NOW - age_days * DAY
    import os

    os.utime(path, (mtime, mtime))


# --- parse_policy fail-closed ---------------------------------------------


@pytest.mark.parametrize(
    "bad",
    [
        "not a mapping",
        {},
        {"cleanup": None},
        {"cleanup": {"allowlist_roots": []}},
        {"cleanup": {"allowlist_roots": {}}},
        {"cleanup": {"allowlist_roots": [{"category": "x"}]}},
        {"cleanup": {"allowlist_roots": [{"root": "..", "max_age_days": 1}]}},
        {
            "cleanup": {
                "allowlist_roots": [{"root": "a", "max_age_days": 1}],
                "forbidden_operations": ["rm -rf"],
            },
            "refuse_rules": list(cp.REFUSE_RULES),
        },
        {
            "cleanup": {
                "allowlist_roots": [{"root": "a", "max_age_days": 1}],
                "forbidden_operations": ["docker system prune"],
            },
            "refuse_rules": ["unknown_path"],
        },
    ],
)
def test_parse_policy_malformed_fails_closed(bad):
    with pytest.raises(cp.CleanupError):
        cp.parse_policy(bad)


def test_parse_policy_default_is_valid():
    policy = _policy()
    assert policy.forbidden_operations == ("docker system prune",)
    assert set(policy.refuse_rules) == set(cp.REFUSE_RULES)
    assert any(r.root == ".tmp-hsl" for r in policy.allowlist_roots)


# --- candidate: allowlisted stale ------------------------------------------


def test_allowlisted_stale_path_is_report_only_candidate(tmp_path: Path):
    repo = _make_repo(tmp_path)
    target = repo / ".tmp-hsl" / "old-run"
    _touch(target, age_days=30.0)  # well past the 7d max_age
    result = cp.evaluate_path(
        Path(".tmp-hsl/old-run"), repo, _policy(), now=NOW
    )
    assert isinstance(result, cp.Candidate)
    assert result.action == "report-only"
    assert result.root == ".tmp-hsl"
    assert result.category == "artifact"
    assert result.max_age_days == 7


# --- refusal: fresh path ---------------------------------------------------


def test_fresh_allowlisted_path_is_insufficient_proof(tmp_path: Path):
    repo = _make_repo(tmp_path)
    target = repo / ".tmp-hsl" / "fresh"
    _touch(target, age_days=0.0)  # today -> age 0 < 7d
    result = cp.evaluate_path(Path(".tmp-hsl/fresh"), repo, _policy(), now=NOW)
    assert isinstance(result, cp.Refusal)
    assert result.reason == cp.REFUSE_INSUFFICIENT_PROOF


def test_nonexistent_allowlisted_path_is_insufficient_proof(tmp_path: Path):
    repo = _make_repo(tmp_path)
    result = cp.evaluate_path(Path(".tmp-hsl/ghost"), repo, _policy(), now=NOW)
    assert isinstance(result, cp.Refusal)
    assert result.reason == cp.REFUSE_INSUFFICIENT_PROOF


# --- refusal: outside allowlist --------------------------------------------


def test_path_outside_allowlist_is_unknown_path(tmp_path: Path):
    repo = _make_repo(tmp_path)
    src = repo / "src" / "app.py"
    _touch(src, age_days=0.0)
    result = cp.evaluate_path(Path("src/app.py"), repo, _policy(), now=NOW)
    assert isinstance(result, cp.Refusal)
    assert result.reason == cp.REFUSE_UNKNOWN_PATH


def test_path_outside_repo_root_is_unknown_path(tmp_path: Path):
    repo = _make_repo(tmp_path)
    # absolute path outside the repo root -> lexical containment fails
    outside = tmp_path / "not-in-repo"
    outside.mkdir()
    result = cp.evaluate_path(outside, repo, _policy(), now=NOW)
    assert isinstance(result, cp.Refusal)
    assert result.reason == cp.REFUSE_UNKNOWN_PATH


# --- refusal: symlink escape -----------------------------------------------


def test_symlink_is_symlink_escape(tmp_path: Path):
    repo = _make_repo(tmp_path)
    real = repo / ".tmp-hsl" / "real.txt"
    _touch(real, age_days=30.0)
    link = repo / ".tmp-hsl" / "escape"

    link.symlink_to(real)
    result = cp.evaluate_path(Path(".tmp-hsl/escape"), repo, _policy(), now=NOW)
    assert isinstance(result, cp.Refusal)
    assert result.reason == cp.REFUSE_SYMLINK_ESCAPE


# --- refusal: active worktree ----------------------------------------------


def test_path_inside_active_worktree_is_active_worktree(tmp_path: Path):
    repo = _make_repo(tmp_path)
    wt = repo / ".tmp-hsl" / "active-wt"
    wt.mkdir(parents=True)
    target = wt / "old-run"
    _touch(target, age_days=30.0)
    result = cp.evaluate_path(
        Path(".tmp-hsl/active-wt/old-run"),
        repo,
        _policy(),
        now=NOW,
        active_worktrees=[wt],
    )
    assert isinstance(result, cp.Refusal)
    assert result.reason == cp.REFUSE_ACTIVE_WORKTREE


# --- refusal: current evidence ---------------------------------------------


def test_referenced_evidence_is_current_evidence(tmp_path: Path):
    repo = _make_repo(tmp_path)
    target = repo / "evidence" / "old"
    _touch(target, age_days=30.0)  # stale -> would be a candidate if unreferenced
    result = cp.evaluate_path(
        Path("evidence/old"),
        repo,
        _policy(),
        now=NOW,
        referenced_evidence=[repo / "evidence" / "old"],
    )
    assert isinstance(result, cp.Refusal)
    assert result.reason == cp.REFUSE_CURRENT_EVIDENCE


def test_unreferenced_stale_evidence_is_candidate(tmp_path: Path):
    repo = _make_repo(tmp_path)
    target = repo / "evidence" / "old"
    _touch(target, age_days=30.0)
    result = cp.evaluate_path(Path("evidence/old"), repo, _policy(), now=NOW)
    assert isinstance(result, cp.Candidate)
    assert result.action == "report-only"


# --- plan_cleanup determinism / serialisation ------------------------------


def test_plan_cleanup_is_deterministic_json_serialisable_dry_run(tmp_path: Path):
    repo = _make_repo(tmp_path)
    a = repo / ".tmp-hsl" / "aaaa"
    b = repo / ".tmp-hsl" / "bbbb"
    _touch(a, age_days=20.0)
    _touch(b, age_days=20.0)

    plan1 = cp.plan_cleanup(
        repo,
        _policy(),
        now=NOW,
        paths=[Path(".tmp-hsl/bbbb"), Path(".tmp-hsl/aaaa")],
    )
    plan2 = cp.plan_cleanup(
        repo,
        _policy(),
        now=NOW,
        paths=[Path(".tmp-hsl/bbbb"), Path(".tmp-hsl/aaaa")],
    )

    assert plan1.mode == "dry-run"
    payload1 = json.loads(json.dumps(plan1.as_dict()))
    payload2 = json.loads(json.dumps(plan2.as_dict()))
    assert payload1 == payload2
    assert payload1["mode"] == "dry-run"
    assert payload1["summary"]["candidates"] == 2
    assert [c["path"] for c in payload1["candidates"]] == [
        ".tmp-hsl/aaaa",
        ".tmp-hsl/bbbb",
    ]


def test_forbidden_operations_never_appear_as_candidate_action(tmp_path: Path):
    repo = _make_repo(tmp_path)
    a = repo / ".tmp-hsl" / "aaaa"
    _touch(a, age_days=20.0)
    plan = cp.plan_cleanup(
        repo, _policy(), now=NOW, paths=[Path(".tmp-hsl/aaaa")]
    )
    assert all(c.action not in cp.FORBIDDEN_OPERATIONS for c in plan.candidates)
    assert plan.forbidden_operations == ("docker system prune",)


# --- assert_operation_allowed ----------------------------------------------


def test_assert_operation_allowed_blocks_docker_system_prune():
    with pytest.raises(cp.ForbiddenOperationError):
        cp.assert_operation_allowed("docker system prune")


def test_assert_operation_allowed_blocks_prune_with_args():
    with pytest.raises(cp.ForbiddenOperationError):
        cp.assert_operation_allowed("docker system prune -a --force --volumes")


def test_assert_operation_allowed_blocks_normalised_whitespace():
    with pytest.raises(cp.ForbiddenOperationError):
        cp.assert_operation_allowed("  docker   system   prune  ")


def test_assert_operation_allowed_allows_non_forbidden():
    # must not raise
    cp.assert_operation_allowed("docker images")
    cp.assert_operation_allowed("git status")


# --- CLI -------------------------------------------------------------------


def test_cli_check_operation_forbidden_returns_exit_forbidden():
    code = cp.main(["check-operation", "docker system prune"])
    assert code == cp.EXIT_FORBIDDEN


def test_cli_check_operation_allowed_returns_ok():
    code = cp.main(["check-operation", "docker images"])
    assert code == cp.EXIT_OK
