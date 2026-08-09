#!/usr/bin/env python3
"""Deterministic inventory of remote branches for repository hygiene.

Read-only Git accounting. This tool NEVER deletes, pushes, or otherwise
mutates any reference: it only classifies branches so that a human decision
about pruning can be taken from evidence instead of from a misleading
`git branch --no-merged` count.

Why `--merged` is not enough
----------------------------
Squash-merged branches keep commits that are not reachable from `main`, so
they appear as "not merged" even though their content is fully integrated.
The reliable signal is `git cherry <base> <branch>`: a branch whose every
commit has an equivalent patch already in the base carries no unique work.

Classification
--------------
MERGED_REACHABLE       branch tip is an ancestor of the base ref
NO_UNIQUE_COMMITS      not reachable, but every commit has an equivalent in base
UNIQUE_COMMITS         carries at least one patch absent from the base
UNKNOWN                the branch could not be evaluated

Only MERGED_REACHABLE and NO_UNIQUE_COMMITS are reported as prune candidates,
and even then the tool merely lists them.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

TOOL_VERSION = "1.0.0"
REPORT_SCHEMA_VERSION = "1.0.0"

EXIT_OK = 0
EXIT_CANDIDATES = 1
EXIT_UNKNOWN = 2
EXIT_USAGE = 3

PROTECTED_BRANCHES = ("main", "master", "HEAD")


class InventoryError(Exception):
    """Recoverable error with a stable exit code."""

    def __init__(self, message: str, code: int = EXIT_UNKNOWN) -> None:
        super().__init__(message)
        self.code = code


def git(repo: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(repo), *args],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise InventoryError(f"git {' '.join(args)} failed: {result.stderr.strip()[:200]}")
    return result.stdout.strip()


def list_remote_branches(repo: Path, remote: str) -> list[str]:
    """Remote-tracking branches, excluding protected refs and symbolic refs.

    `refs/remotes/<remote>/HEAD` renders as the bare remote name in
    `%(refname:short)`, so it must be filtered explicitly or the remote HEAD is
    reported as a prune candidate.
    """
    raw = git(
        repo,
        "for-each-ref",
        "--format=%(refname:short)%09%(symref)",
        f"refs/remotes/{remote}",
    )
    branches = []
    for line in raw.splitlines():
        name, _, symref = line.partition("\t")
        name = name.strip()
        if not name or symref.strip():
            continue
        if name == remote:
            continue
        short = name[len(remote) + 1 :] if name.startswith(remote + "/") else name
        if short in PROTECTED_BRANCHES:
            continue
        branches.append(name)
    return sorted(set(branches))


def unique_commits(repo: Path, base: str, branch: str) -> list[str]:
    """Commits of branch whose patch has no equivalent in base."""
    raw = git(repo, "cherry", base, branch)
    return [line[2:] for line in raw.splitlines() if line.startswith("+ ")]


def is_ancestor(repo: Path, ancestor: str, descendant: str) -> bool:
    result = subprocess.run(
        ["git", "-C", str(repo), "merge-base", "--is-ancestor", ancestor, descendant],
        capture_output=True,
        check=False,
    )
    return result.returncode == 0


def classify_branch(repo: Path, base: str, branch: str) -> dict[str, Any]:
    entry: dict[str, Any] = {"branch": branch}
    try:
        entry["tip"] = git(repo, "rev-parse", branch)
        entry["last_commit_utc"] = git(repo, "log", "-1", "--format=%cI", branch)
        if is_ancestor(repo, branch, base):
            entry["classification"] = "MERGED_REACHABLE"
            entry["unique_commits"] = 0
        else:
            unique = unique_commits(repo, base, branch)
            entry["unique_commits"] = len(unique)
            entry["classification"] = "NO_UNIQUE_COMMITS" if not unique else "UNIQUE_COMMITS"
    except InventoryError as exc:
        entry["classification"] = "UNKNOWN"
        entry["reason"] = str(exc)
    entry["prune_candidate"] = entry["classification"] in ("MERGED_REACHABLE", "NO_UNIQUE_COMMITS")
    return entry


def build_report(repo: Path, base: str, remote: str) -> dict[str, Any]:
    if not (repo / ".git").exists():
        raise InventoryError(f"not a git checkout: {repo}", EXIT_USAGE)
    try:
        base_commit = git(repo, "rev-parse", base)
    except InventoryError as exc:
        raise InventoryError(f"base ref unusable: {exc}", EXIT_UNKNOWN) from exc

    branches = [classify_branch(repo, base, name) for name in list_remote_branches(repo, remote)]
    branches.sort(key=lambda item: item["branch"])
    counts: dict[str, int] = {}
    for entry in branches:
        counts[entry["classification"]] = counts.get(entry["classification"], 0) + 1

    return {
        "schema_version": REPORT_SCHEMA_VERSION,
        "tool_version": TOOL_VERSION,
        "base_ref": base,
        "base_commit": base_commit,
        "remote": remote,
        "counts": {key: counts[key] for key in sorted(counts)},
        "total_branches": len(branches),
        "prune_candidates": sorted(e["branch"] for e in branches if e["prune_candidate"]),
        "branches": branches,
        "notes": [
            "Read-only inventory: this tool never deletes or pushes references.",
            "NO_UNIQUE_COMMITS covers squash-merged branches that `git branch --no-merged` still lists.",
            "UNKNOWN never counts as a prune candidate.",
        ],
    }


def cmd_report(args: argparse.Namespace) -> int:
    repo = Path(args.repo).resolve()
    report = build_report(repo, args.base, args.remote)
    payload = json.dumps(report, indent=2, sort_keys=True)
    if args.output:
        Path(args.output).write_text(payload + "\n", encoding="utf-8")
    print(payload)
    if report["counts"].get("UNKNOWN"):
        return EXIT_UNKNOWN
    return EXIT_CANDIDATES if report["prune_candidates"] else EXIT_OK


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    sub = parser.add_subparsers(dest="command", required=True)
    rep = sub.add_parser("report", help="deterministic JSON inventory of remote branches")
    rep.add_argument("--repo", default=str(Path(__file__).resolve().parents[1]))
    rep.add_argument("--base", default="origin/main")
    rep.add_argument("--remote", default="origin")
    rep.add_argument("--output", default=None)
    rep.set_defaults(func=cmd_report)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return int(args.func(args))
    except InventoryError as exc:
        print(json.dumps({"status": "ERROR", "reason": str(exc)}), file=sys.stderr)
        return exc.code


if __name__ == "__main__":
    raise SystemExit(main())
