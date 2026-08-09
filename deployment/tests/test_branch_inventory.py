"""Tests for the read-only branch inventory tooling.

Everything runs on throwaway Git repositories created by pytest; no network,
no remote mutation.
"""

from __future__ import annotations

import io
import contextlib
import json
import subprocess
import sys
from pathlib import Path

import pytest

DEPLOYMENT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(DEPLOYMENT_DIR))

import branch_inventory as bi  # noqa: E402


def run_git(repo: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(repo), *args], check=True, capture_output=True, text=True
    )
    return result.stdout.strip()


def commit(repo: Path, name: str, content: str) -> None:
    (repo / name).write_text(content, encoding="utf-8")
    run_git(repo, "add", "-A")
    run_git(repo, "commit", "-qm", f"add {name}")


@pytest.fixture()
def remote_repo(tmp_path: Path) -> Path:
    """A clone whose `origin/*` refs cover every classification."""
    upstream = tmp_path / "upstream"
    upstream.mkdir()
    run_git(upstream, "init", "-q", "-b", "main")
    run_git(upstream, "config", "user.email", "test@example.invalid")
    run_git(upstream, "config", "user.name", "test")
    commit(upstream, "base.txt", "base\n")

    # merged-reachable: fast-forwarded into main
    run_git(upstream, "checkout", "-q", "-b", "merged-ff")
    commit(upstream, "ff.txt", "ff\n")
    run_git(upstream, "checkout", "-q", "main")
    run_git(upstream, "merge", "-q", "--ff-only", "merged-ff")

    # squash-merged: same patch content, different commit
    run_git(upstream, "checkout", "-q", "-b", "squashed", "HEAD~1")
    commit(upstream, "squash.txt", "squash\n")
    run_git(upstream, "checkout", "-q", "main")
    (upstream / "squash.txt").write_text("squash\n", encoding="utf-8")
    run_git(upstream, "add", "-A")
    run_git(upstream, "commit", "-qm", "add squash.txt")

    # genuinely unique work
    run_git(upstream, "checkout", "-q", "-b", "active")
    commit(upstream, "active.txt", "active\n")
    run_git(upstream, "checkout", "-q", "main")

    clone = tmp_path / "clone"
    subprocess.run(
        ["git", "clone", "-q", str(upstream), str(clone)], check=True, capture_output=True
    )
    return clone


def report(repo: Path) -> dict:
    return bi.build_report(repo, "origin/main", "origin")


def by_branch(data: dict) -> dict[str, dict]:
    return {entry["branch"]: entry for entry in data["branches"]}


def test_report_has_stable_schema_fields(remote_repo: Path) -> None:
    data = report(remote_repo)
    for key in ("schema_version", "tool_version", "base_ref", "base_commit", "counts", "branches"):
        assert key in data
    assert data["base_ref"] == "origin/main"


def test_fast_forward_merged_branch_is_reachable(remote_repo: Path) -> None:
    entry = by_branch(report(remote_repo))["origin/merged-ff"]
    assert entry["classification"] == "MERGED_REACHABLE"
    assert entry["unique_commits"] == 0
    assert entry["prune_candidate"] is True


def test_squash_merged_branch_has_no_unique_commits(remote_repo: Path) -> None:
    """The case `git branch --no-merged` reports misleadingly."""
    entry = by_branch(report(remote_repo))["origin/squashed"]
    assert entry["classification"] == "NO_UNIQUE_COMMITS"
    assert entry["unique_commits"] == 0
    assert entry["prune_candidate"] is True


def test_active_branch_is_never_a_prune_candidate(remote_repo: Path) -> None:
    entry = by_branch(report(remote_repo))["origin/active"]
    assert entry["classification"] == "UNIQUE_COMMITS"
    assert entry["unique_commits"] >= 1
    assert entry["prune_candidate"] is False


def test_base_branch_is_excluded_from_the_inventory(remote_repo: Path) -> None:
    branches = by_branch(report(remote_repo))
    assert "origin/main" not in branches
    assert "origin/HEAD" not in branches
    # `refs/remotes/origin/HEAD` short-renders as the bare remote name.
    assert "origin" not in branches


def test_report_is_deterministic(remote_repo: Path) -> None:
    first = json.dumps(report(remote_repo), sort_keys=True)
    second = json.dumps(report(remote_repo), sort_keys=True)
    assert first == second


def test_prune_candidates_are_sorted_and_consistent(remote_repo: Path) -> None:
    data = report(remote_repo)
    assert data["prune_candidates"] == sorted(data["prune_candidates"])
    expected = {e["branch"] for e in data["branches"] if e["prune_candidate"]}
    assert set(data["prune_candidates"]) == expected


def test_unknown_base_ref_is_reported_not_assumed(tmp_path: Path) -> None:
    repo = tmp_path / "empty"
    repo.mkdir()
    run_git(repo, "init", "-q", "-b", "main")
    with pytest.raises(bi.InventoryError):
        bi.build_report(repo, "origin/does-not-exist", "origin")


def test_non_git_directory_is_a_usage_error(tmp_path: Path) -> None:
    with pytest.raises(bi.InventoryError) as excinfo:
        bi.build_report(tmp_path, "origin/main", "origin")
    assert excinfo.value.code == bi.EXIT_USAGE


def test_cli_writes_report_and_exits_with_candidate_code(remote_repo: Path, tmp_path: Path) -> None:
    output = tmp_path / "inventory.json"
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = bi.main(["report", "--repo", str(remote_repo), "--output", str(output)])
    assert rc == bi.EXIT_CANDIDATES
    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["total_branches"] == len(payload["branches"])
    assert json.loads(buf.getvalue())["base_ref"] == "origin/main"


def test_cli_reports_ok_when_no_candidates(tmp_path: Path) -> None:
    upstream = tmp_path / "up2"
    upstream.mkdir()
    run_git(upstream, "init", "-q", "-b", "main")
    run_git(upstream, "config", "user.email", "test@example.invalid")
    run_git(upstream, "config", "user.name", "test")
    commit(upstream, "a.txt", "a\n")
    run_git(upstream, "checkout", "-q", "-b", "work")
    commit(upstream, "b.txt", "b\n")
    run_git(upstream, "checkout", "-q", "main")
    clone = tmp_path / "clone2"
    subprocess.run(
        ["git", "clone", "-q", str(upstream), str(clone)], check=True, capture_output=True
    )
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = bi.main(["report", "--repo", str(clone)])
    assert rc == bi.EXIT_OK


def test_tool_never_deletes_references(remote_repo: Path) -> None:
    before = run_git(remote_repo, "for-each-ref", "--format=%(refname)")
    bi.build_report(remote_repo, "origin/main", "origin")
    after = run_git(remote_repo, "for-each-ref", "--format=%(refname)")
    assert before == after
