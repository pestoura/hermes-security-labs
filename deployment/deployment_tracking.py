#!/usr/bin/env python3
"""Deployment tracking and drift detection for hermes-security-labs.

Pure configuration/integrity engineering: this module never executes
laboratories, scanners or any offensive tooling. It only copies approved
configuration files, hashes them and compares the applied state with a known
Git commit.

Commands
--------
deploy       apply approved files to a target directory and write state
verify       validate an existing state file against the target directory
drift-check  report IN_SYNC / DRIFT_DETECTED / UNKNOWN
rollback     restore the snapshot referenced by the current state
"""

from __future__ import annotations

import argparse
import fnmatch
import hashlib
import json
import os
import shutil
import stat
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

TOOL_VERSION = "1.0.0"
STATE_SCHEMA_VERSION = "1.0.0"
STATE_FILENAME = ".deployment.json"
SNAPSHOT_DIRNAME = ".deployment-snapshots"
STATE_MODE = 0o600

EXIT_OK = 0
EXIT_DRIFT = 1
EXIT_UNKNOWN = 2
EXIT_USAGE = 3
EXIT_PRECONDITION = 4

# Approved deployment scope: directories and files that describe configuration.
SCOPE_DIRS = (
    "config",
    "deployment",
    "kali-mcp",
    "platform",
    "security",
)
SCOPE_FILES = (
    "compose.yaml",
    "Makefile",
    "Dockerfile",
    ".env.example",
    ".gitignore",
)

EXCLUDE_DIR_NAMES = {
    ".git",
    "__pycache__",
    ".pytest_cache",
    ".ruff_cache",
    ".venv",
    "node_modules",
    "evidence",
    "runtime",
    "state",
    "tmp",
    "cache",
    SNAPSHOT_DIRNAME,
}
EXCLUDE_FILE_GLOBS = (
    ".env",
    ".env.*",
    "*.key",
    "*.pem",
    "*.crt",
    "*.p12",
    "*.pfx",
    "*.token",
    "*.secret",
    "*.log",
    "*.sqlite",
    "*.db",
    "*.bak",
    "*.bak-*",
    "*.tar",
    "*.tar.gz",
    "*.zip",
    "*.pyc",
    "*.swp",
    "*~",
    STATE_FILENAME,
    "compose-effective.yaml",
    "container-inspect*.json",
    "deployment.local.json",
)
KEEP_EXCLUDE_EXCEPTIONS = (".env.example",)

RUNNER_PATHS = (
    "security/packs/api/runner/kali_runner.py",
    "security/packs/devsecops/runner/devsecops_runner.py",
    "security/packs/ai-mcp/runner/ai_mcp_runner.py",
)
BINDINGS_PATH = "security/bindings/labs.yaml"
CONFIG_REFERENCES = (
    "compose.yaml",
    "kali-mcp/compose.yaml",
    "security/catalog/manifest.yaml",
    "platform/registry.yaml",
    "platform/rollout.yaml",
)

SECRET_KEY_HINTS = (
    "password",
    "passwd",
    "secret",
    "token",
    "apikey",
    "api_key",
    "private_key",
    "authorization",
    "cookie",
    "credential",
)


class TrackingError(Exception):
    """Recoverable error with a stable exit code."""

    def __init__(self, message: str, code: int = EXIT_UNKNOWN) -> None:
        super().__init__(message)
        self.code = code


# --------------------------------------------------------------------------
# helpers
# --------------------------------------------------------------------------


def utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def git(repo: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(repo), *args],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise TrackingError(
            f"git {' '.join(args)} failed: {result.stderr.strip()[:200]}",
            EXIT_PRECONDITION,
        )
    return result.stdout.strip()


def git_optional(repo: Path, *args: str) -> str | None:
    try:
        return git(repo, *args)
    except TrackingError:
        return None


def is_excluded_file(name: str) -> bool:
    if name in KEEP_EXCLUDE_EXCEPTIONS:
        return False
    return any(fnmatch.fnmatch(name, pattern) for pattern in EXCLUDE_FILE_GLOBS)


def iter_scope(root: Path) -> list[str]:
    """Return sorted relative paths of approved files present under root."""
    found: list[str] = []
    for name in SCOPE_FILES:
        candidate = root / name
        if candidate.is_file() and not is_excluded_file(name):
            found.append(name)
    for dirname in SCOPE_DIRS:
        base = root / dirname
        if not base.is_dir():
            continue
        for current, dirs, files in os.walk(base):
            dirs[:] = sorted(d for d in dirs if d not in EXCLUDE_DIR_NAMES)
            for filename in sorted(files):
                if is_excluded_file(filename):
                    continue
                rel = Path(current, filename).relative_to(root).as_posix()
                found.append(rel)
    return sorted(set(found))


def build_inventory(root: Path, paths: list[str]) -> dict[str, dict[str, Any]]:
    inventory: dict[str, dict[str, Any]] = {}
    for rel in paths:
        path = root / rel
        inventory[rel] = {
            "sha256": sha256_file(path),
            "size": path.stat().st_size,
            "mode": oct(stat.S_IMODE(path.stat().st_mode)),
        }
    return inventory


def contains_secret_like(obj: Any) -> bool:
    if isinstance(obj, dict):
        for key, value in obj.items():
            if any(hint in str(key).lower() for hint in SECRET_KEY_HINTS):
                return True
            if contains_secret_like(value):
                return True
        return False
    if isinstance(obj, list):
        return any(contains_secret_like(item) for item in obj)
    return False


def atomic_write_json(path: Path, payload: dict[str, Any], mode: int = STATE_MODE) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(dir=str(path.parent), prefix=".deployment-", suffix=".tmp")
    tmp = Path(tmp_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(tmp, mode)
        os.replace(tmp, path)
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise


def load_state(state_file: Path) -> dict[str, Any]:
    if not state_file.exists():
        raise TrackingError(f"state file missing: {state_file}", EXIT_UNKNOWN)
    try:
        data = json.loads(state_file.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise TrackingError(f"state file is not valid JSON: {exc.msg}", EXIT_UNKNOWN) from exc
    if not isinstance(data, dict):
        raise TrackingError("state file root must be an object", EXIT_UNKNOWN)
    return data


REQUIRED_STATE_KEYS = (
    "schema_version",
    "tool_version",
    "deployment_id",
    "applied_at_utc",
    "repository",
    "git",
    "target_dir",
    "inventory",
    "runners",
    "bindings",
    "config_references",
    "previous_state",
)


def validate_schema(state: dict[str, Any]) -> list[str]:
    problems = [f"missing key: {key}" for key in REQUIRED_STATE_KEYS if key not in state]
    if state.get("schema_version") not in (None, STATE_SCHEMA_VERSION):
        problems.append(f"unsupported schema_version: {state.get('schema_version')}")
    git_block = state.get("git")
    if not isinstance(git_block, dict):
        problems.append("git block must be an object")
    else:
        for key in ("commit", "ref"):
            if not git_block.get(key):
                problems.append(f"git.{key} missing")
        commit = str(git_block.get("commit", ""))
        if commit and (len(commit) != 40 or not all(c in "0123456789abcdef" for c in commit)):
            problems.append("git.commit is not a full sha1")
    if not isinstance(state.get("inventory"), dict) or not state.get("inventory"):
        problems.append("inventory must be a non-empty object")
    if contains_secret_like(state):
        problems.append("state contains secret-like keys")
    return problems


# --------------------------------------------------------------------------
# deploy
# --------------------------------------------------------------------------


def snapshot_previous(target: Path, state_file: Path, deployment_id: str) -> dict[str, Any] | None:
    if not state_file.exists():
        return None
    try:
        previous = load_state(state_file)
    except TrackingError:
        previous = {}
    snap_root = target / SNAPSHOT_DIRNAME / deployment_id
    snap_files = snap_root / "files"
    snap_files.mkdir(parents=True, exist_ok=True)
    inventory = previous.get("inventory") if isinstance(previous.get("inventory"), dict) else {}
    for rel in sorted(inventory or {}):
        src = target / rel
        if not src.is_file():
            continue
        dst = snap_files / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
    shutil.copy2(state_file, snap_root / "state.json")
    os.chmod(snap_root / "state.json", STATE_MODE)
    return {
        "deployment_id": previous.get("deployment_id"),
        "commit": (previous.get("git") or {}).get("commit"),
        "applied_at_utc": previous.get("applied_at_utc"),
        "snapshot_dir": snap_root.relative_to(target).as_posix(),
        "state_sha256": sha256_file(snap_root / "state.json"),
    }


def cmd_deploy(args: argparse.Namespace) -> int:
    repo = Path(args.repo).resolve()
    target = Path(args.target_dir).resolve()
    if not (repo / ".git").exists():
        raise TrackingError(f"not a git checkout: {repo}", EXIT_PRECONDITION)

    dirty = git(repo, "status", "--porcelain")
    if dirty and not args.allow_dirty:
        raise TrackingError("refusing to deploy: working tree is dirty", EXIT_PRECONDITION)

    commit = git(repo, "rev-parse", "HEAD")
    ref = git(repo, "rev-parse", "--abbrev-ref", "HEAD")
    upstream = git_optional(repo, "rev-parse", "--abbrev-ref", "@{upstream}")
    divergence = None
    if upstream:
        counts = git_optional(repo, "rev-list", "--left-right", "--count", f"{upstream}...HEAD")
        if counts:
            behind, ahead = (int(x) for x in counts.split())
            divergence = {"upstream": upstream, "behind": behind, "ahead": ahead}
            if (behind or ahead) and not args.allow_divergence:
                raise TrackingError(
                    f"refusing to deploy: diverged from {upstream} (behind={behind} ahead={ahead})",
                    EXIT_PRECONDITION,
                )

    paths = iter_scope(repo)
    if not paths:
        raise TrackingError("no approved files found in scope", EXIT_PRECONDITION)

    deployment_id = f"{utc_now().replace(':', '').replace('-', '')}-{commit[:12]}"
    state_file = Path(args.state_file).resolve() if args.state_file else target / STATE_FILENAME

    if args.dry_run:
        report = {
            "action": "deploy",
            "mode": "dry-run",
            "repo": str(repo),
            "target_dir": str(target),
            "commit": commit,
            "ref": ref,
            "files_in_scope": len(paths),
            "state_file": str(state_file),
            "divergence": divergence,
        }
        print(json.dumps(report, indent=2, sort_keys=True))
        return EXIT_OK

    target.mkdir(parents=True, exist_ok=True)
    previous = snapshot_previous(target, state_file, deployment_id)

    staged: list[tuple[Path, Path]] = []
    try:
        for rel in paths:
            src = repo / rel
            dst = target / rel
            dst.parent.mkdir(parents=True, exist_ok=True)
            tmp = dst.with_name(dst.name + ".deploytmp")
            shutil.copy2(src, tmp)
            staged.append((tmp, dst))
        for tmp, dst in staged:
            os.replace(tmp, dst)
    except BaseException:
        for tmp, _ in staged:
            tmp.unlink(missing_ok=True)
        raise

    state = build_state(repo, target, paths, commit, ref, deployment_id, previous, divergence)
    if args.fail_after_copy:  # test hook: simulate failure before state write
        raise TrackingError("simulated failure during state write", EXIT_UNKNOWN)
    atomic_write_json(state_file, state)
    print(
        json.dumps(
            {
                "action": "deploy",
                "result": "APPLIED",
                "deployment_id": deployment_id,
                "commit": commit,
                "files": len(paths),
                "state_file": str(state_file),
                "state_sha256": sha256_file(state_file),
            },
            indent=2,
            sort_keys=True,
        )
    )
    return EXIT_OK


def build_state(
    repo: Path,
    target: Path,
    paths: list[str],
    commit: str,
    ref: str,
    deployment_id: str,
    previous: dict[str, Any] | None,
    divergence: dict[str, Any] | None,
) -> dict[str, Any]:
    inventory = build_inventory(target, paths)
    runners = {
        rel: inventory[rel]["sha256"]
        for rel in RUNNER_PATHS
        if rel in inventory
    }
    bindings: dict[str, Any] = {"path": BINDINGS_PATH}
    if BINDINGS_PATH in inventory:
        bindings["sha256"] = inventory[BINDINGS_PATH]["sha256"]
        bindings["laboratories"] = count_bindings(target / BINDINGS_PATH)
    config_refs = {
        rel: inventory[rel]["sha256"] for rel in CONFIG_REFERENCES if rel in inventory
    }
    return {
        "schema_version": STATE_SCHEMA_VERSION,
        "tool_version": TOOL_VERSION,
        "deployment_id": deployment_id,
        "applied_at_utc": utc_now(),
        "repository": "pestoura/hermes-security-labs",
        "git": {
            "commit": commit,
            "ref": ref,
            "source_dir": str(repo),
            "divergence": divergence,
        },
        "target_dir": str(target),
        "scope": {"dirs": list(SCOPE_DIRS), "files": list(SCOPE_FILES)},
        "inventory": inventory,
        "runners": runners,
        "bindings": bindings,
        "config_references": config_refs,
        "previous_state": previous,
    }


def count_bindings(path: Path) -> int:
    """Count laboratories declared in the bindings catalog without extra deps."""
    total = 0
    try:
        import yaml  # type: ignore

        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        for domain in (data.get("domains") or {}).values():
            total += len(domain.get("laboratories") or [])
        return total
    except Exception:
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.strip().startswith("- id:"):
                total += 1
        return total


# --------------------------------------------------------------------------
# verify / drift
# --------------------------------------------------------------------------


def evaluate(target: Path, state_file: Path, repo: Path | None) -> dict[str, Any]:
    findings: list[dict[str, Any]] = []
    result: dict[str, Any] = {
        "action": "verify",
        "state_file": str(state_file),
        "target_dir": str(target),
        "findings": findings,
    }

    state = load_state(state_file)
    mode = stat.S_IMODE(state_file.stat().st_mode)
    result["state_mode"] = oct(mode)
    if mode != STATE_MODE:
        findings.append({"type": "state_permissions", "expected": "0o600", "actual": oct(mode)})

    schema_problems = validate_schema(state)
    if schema_problems:
        result["schema_problems"] = schema_problems
        raise TrackingError("state schema invalid: " + "; ".join(schema_problems), EXIT_UNKNOWN)

    result["deployment_id"] = state["deployment_id"]
    result["commit"] = state["git"]["commit"]

    inventory: dict[str, Any] = state["inventory"]
    for rel, meta in sorted(inventory.items()):
        path = target / rel
        if not path.is_file():
            findings.append({"type": "missing_file", "path": rel})
            continue
        actual = sha256_file(path)
        if actual != meta.get("sha256"):
            findings.append({"type": "modified_file", "path": rel})
        expected_mode = meta.get("mode")
        actual_mode = oct(stat.S_IMODE(path.stat().st_mode))
        if expected_mode and expected_mode != actual_mode:
            findings.append(
                {"type": "mode_changed", "path": rel, "expected": expected_mode, "actual": actual_mode}
            )

    for rel in iter_scope(target):
        if rel not in inventory:
            findings.append({"type": "extra_file", "path": rel})

    for rel, expected in (state.get("runners") or {}).items():
        path = target / rel
        if not path.is_file():
            findings.append({"type": "runner_missing", "path": rel})
        elif sha256_file(path) != expected:
            findings.append({"type": "runner_outdated", "path": rel})
    result["runners_tracked"] = len(state.get("runners") or {})

    bindings = state.get("bindings") or {}
    result["bindings_laboratories"] = bindings.get("laboratories")
    bpath = target / bindings.get("path", BINDINGS_PATH)
    if not bpath.is_file():
        findings.append({"type": "bindings_missing", "path": bindings.get("path")})
    else:
        if bindings.get("sha256") and sha256_file(bpath) != bindings["sha256"]:
            findings.append({"type": "bindings_changed", "path": bindings.get("path")})
        current = count_bindings(bpath)
        if bindings.get("laboratories") is not None and current != bindings["laboratories"]:
            findings.append(
                {
                    "type": "bindings_count_changed",
                    "expected": bindings["laboratories"],
                    "actual": current,
                }
            )

    if repo is not None and (repo / ".git").exists():
        head = git(repo, "rev-parse", "HEAD")
        result["repo_head"] = head
        if head != state["git"]["commit"]:
            findings.append(
                {"type": "commit_mismatch", "expected": state["git"]["commit"], "actual": head}
            )
        known = subprocess.run(
            ["git", "-C", str(repo), "cat-file", "-e", state["git"]["commit"] + "^{commit}"],
            capture_output=True,
            check=False,
        )
        if known.returncode != 0:
            raise TrackingError("recorded commit is unknown to the repository", EXIT_UNKNOWN)

    result["status"] = "IN_SYNC" if not findings else "DRIFT_DETECTED"
    return result


def cmd_verify(args: argparse.Namespace) -> int:
    target = Path(args.target_dir).resolve()
    state_file = Path(args.state_file).resolve() if args.state_file else target / STATE_FILENAME
    repo = Path(args.repo).resolve() if args.repo else None
    report = evaluate(target, state_file, repo)
    print(json.dumps(report, indent=2, sort_keys=True))
    return EXIT_OK if report["status"] == "IN_SYNC" else EXIT_DRIFT


def cmd_drift(args: argparse.Namespace) -> int:
    target = Path(args.target_dir).resolve()
    state_file = Path(args.state_file).resolve() if args.state_file else target / STATE_FILENAME
    repo = Path(args.repo).resolve() if args.repo else None
    try:
        report = evaluate(target, state_file, repo)
    except TrackingError as exc:
        print(json.dumps({"status": "UNKNOWN", "reason": str(exc)}, indent=2, sort_keys=True))
        return EXIT_UNKNOWN
    except Exception as exc:  # never fail open
        print(
            json.dumps(
                {"status": "UNKNOWN", "reason": f"unexpected error: {type(exc).__name__}"},
                indent=2,
                sort_keys=True,
            )
        )
        return EXIT_UNKNOWN
    payload = {
        "status": report["status"],
        "commit": report.get("commit"),
        "findings": report["findings"],
    }
    print(json.dumps(payload, indent=2, sort_keys=True))
    return EXIT_OK if report["status"] == "IN_SYNC" else EXIT_DRIFT


# --------------------------------------------------------------------------
# rollback
# --------------------------------------------------------------------------


def cmd_rollback(args: argparse.Namespace) -> int:
    target = Path(args.target_dir).resolve()
    state_file = Path(args.state_file).resolve() if args.state_file else target / STATE_FILENAME
    if args.repo:
        repo = Path(args.repo).resolve()
        if (repo / ".git").exists() and git(repo, "status", "--porcelain") and not args.allow_dirty:
            raise TrackingError("refusing to rollback: source working tree is dirty", EXIT_PRECONDITION)

    state = load_state(state_file)
    previous = state.get("previous_state")
    if not previous or not previous.get("snapshot_dir"):
        raise TrackingError("no previous snapshot recorded", EXIT_PRECONDITION)
    snap_root = target / previous["snapshot_dir"]
    snap_state = snap_root / "state.json"
    if not snap_state.is_file():
        raise TrackingError(f"snapshot state missing: {snap_state}", EXIT_PRECONDITION)
    if previous.get("state_sha256") and sha256_file(snap_state) != previous["state_sha256"]:
        raise TrackingError("snapshot state hash mismatch", EXIT_PRECONDITION)

    restored = json.loads(snap_state.read_text(encoding="utf-8"))
    problems = validate_schema(restored)
    if problems:
        raise TrackingError("snapshot state invalid: " + "; ".join(problems), EXIT_PRECONDITION)

    files = sorted((restored.get("inventory") or {}).keys())
    if args.dry_run:
        print(
            json.dumps(
                {
                    "action": "rollback",
                    "mode": "dry-run",
                    "to_deployment_id": restored.get("deployment_id"),
                    "to_commit": (restored.get("git") or {}).get("commit"),
                    "files": len(files),
                },
                indent=2,
                sort_keys=True,
            )
        )
        return EXIT_OK

    staged: list[tuple[Path, Path]] = []
    try:
        for rel in files:
            src = snap_root / "files" / rel
            if not src.is_file():
                continue
            dst = target / rel
            dst.parent.mkdir(parents=True, exist_ok=True)
            tmp = dst.with_name(dst.name + ".rollbacktmp")
            shutil.copy2(src, tmp)
            staged.append((tmp, dst))
        for tmp, dst in staged:
            os.replace(tmp, dst)
    except BaseException:
        for tmp, _ in staged:
            tmp.unlink(missing_ok=True)
        raise

    current_inventory = set(state.get("inventory") or {})
    for rel in sorted(current_inventory - set(files)):
        (target / rel).unlink(missing_ok=True)

    restored["previous_state"] = None
    restored["rolled_back_at_utc"] = utc_now()
    atomic_write_json(state_file, restored)
    print(
        json.dumps(
            {
                "action": "rollback",
                "result": "RESTORED",
                "deployment_id": restored.get("deployment_id"),
                "commit": (restored.get("git") or {}).get("commit"),
                "files": len(files),
            },
            indent=2,
            sort_keys=True,
        )
    )
    return EXIT_OK


# --------------------------------------------------------------------------
# cli
# --------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)

    def common(p: argparse.ArgumentParser) -> None:
        p.add_argument("--target-dir", required=True)
        p.add_argument("--state-file", default=None)
        p.add_argument("--repo", default=None)

    dep = sub.add_parser("deploy")
    common(dep)
    dep.add_argument("--dry-run", action="store_true")
    dep.add_argument("--allow-dirty", action="store_true")
    dep.add_argument("--allow-divergence", action="store_true")
    dep.add_argument("--fail-after-copy", action="store_true", help=argparse.SUPPRESS)
    dep.set_defaults(func=cmd_deploy)

    ver = sub.add_parser("verify")
    common(ver)
    ver.set_defaults(func=cmd_verify)

    dri = sub.add_parser("drift-check")
    common(dri)
    dri.set_defaults(func=cmd_drift)

    rol = sub.add_parser("rollback")
    common(rol)
    rol.add_argument("--dry-run", action="store_true")
    rol.add_argument("--allow-dirty", action="store_true")
    rol.set_defaults(func=cmd_rollback)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "deploy" and not args.repo:
        args.repo = str(Path(__file__).resolve().parents[1])
    try:
        return int(args.func(args))
    except TrackingError as exc:
        print(json.dumps({"status": "ERROR", "reason": str(exc)}), file=sys.stderr)
        return exc.code


if __name__ == "__main__":
    raise SystemExit(main())
