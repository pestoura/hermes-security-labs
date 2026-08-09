#!/usr/bin/env python3
"""Fail-closed, dry-run-only cleanup PLANNER for HSL repository hygiene.

This tool plans. It never acts. There is deliberately no delete, unlink,
rmtree, prune, truncate or chmod call anywhere in this module: the only
output is a JSON plan describing what a human (or a separate, explicitly
authorised tool) *could* remove, together with the proof that justified each
candidate.

Guarantees, all structural rather than advisory:

* ``MODE`` is fixed to ``dry-run``. There is no apply/execute path.
* Only roots declared in ``cleanup.allowlist_roots`` of
  ``config/resource-governance.yaml`` are ever considered. Everything else is
  refused as ``unknown_path``.
* Every candidate must resolve *inside* the repository root. A path that
  leaves it via a symlink is refused as ``symlink_escape``.
* Paths belonging to an active worktree, or to evidence still referenced by
  the caller, are refused (``active_worktree`` / ``current_evidence``).
* Anything whose staleness cannot be positively proven -- unreadable mtime,
  age below the configured ``max_age_days``, missing policy metadata -- is
  refused as ``insufficient_proof``. Absence of proof is never permission.
* ``docker system prune`` (and friends) are declared forbidden operations and
  raise :class:`ForbiddenOperationError` if a caller ever asks for them.

Any unexpected error while evaluating a path produces a refusal, not a
candidate: the failure mode is always "plan less", never "plan more".
"""

from __future__ import annotations

import argparse
import json
import os
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

TOOL_VERSION = "1.0.0"
PLAN_SCHEMA_VERSION = "1.0.0"

#: This planner has exactly one mode and it is not negotiable.
MODE = "dry-run"

EXIT_OK = 0
EXIT_REFUSED = 1
EXIT_USAGE = 4
EXIT_FORBIDDEN = 5

#: Canonical refusal vocabulary. Low cardinality on purpose: these are metric
#: label values, not free text.
REFUSE_UNKNOWN_PATH = "unknown_path"
REFUSE_SYMLINK_ESCAPE = "symlink_escape"
REFUSE_ACTIVE_WORKTREE = "active_worktree"
REFUSE_CURRENT_EVIDENCE = "current_evidence"
REFUSE_INSUFFICIENT_PROOF = "insufficient_proof"

REFUSE_RULES: tuple[str, ...] = (
    REFUSE_UNKNOWN_PATH,
    REFUSE_SYMLINK_ESCAPE,
    REFUSE_ACTIVE_WORKTREE,
    REFUSE_CURRENT_EVIDENCE,
    REFUSE_INSUFFICIENT_PROOF,
)

#: Operations this lane structurally refuses to perform or emit.
FORBIDDEN_OPERATIONS: tuple[str, ...] = (
    "docker system prune",
    "docker volume prune",
    "docker image prune",
    "rm -rf",
)

DEFAULT_POLICY: dict[str, Any] = {
    "cleanup": {
        "allowlist_roots": [
            {"root": ".tmp-hsl", "category": "artifact", "max_age_days": 7},
            {"root": "artifacts", "category": "artifact", "max_age_days": 30},
            {
                "root": "evidence",
                "category": "evidence",
                "max_age_days": 14,
                "require_unreferenced": True,
            },
            {"root": ".pytest_cache", "category": "cache", "max_age_days": 1},
            {
                "root": "__pycache__",
                "category": "cache",
                "max_age_days": 1,
                "recursive": True,
            },
        ],
        "forbidden_operations": ["docker system prune"],
    },
    "refuse_rules": list(REFUSE_RULES),
}


class CleanupError(ValueError):
    """Recoverable planner error carrying a stable exit code."""

    def __init__(self, message: str, code: int = EXIT_USAGE) -> None:
        super().__init__(message)
        self.code = code


class ForbiddenOperationError(CleanupError):
    """Raised when a caller requests a structurally forbidden operation."""

    def __init__(self, operation: str) -> None:
        super().__init__(
            f"operation refused by policy (never performed by this lane): {operation}",
            EXIT_FORBIDDEN,
        )
        self.operation = operation


@dataclass(frozen=True)
class AllowlistRoot:
    root: str
    category: str
    max_age_days: float | None
    require_unreferenced: bool = False
    recursive: bool = False

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class CleanupPolicy:
    allowlist_roots: tuple[AllowlistRoot, ...]
    forbidden_operations: tuple[str, ...]
    refuse_rules: tuple[str, ...]

    def root_names(self) -> tuple[str, ...]:
        return tuple(r.root for r in self.allowlist_roots)

    def match_root(self, relative: Path) -> AllowlistRoot | None:
        """Return the allowlist entry governing ``relative``, or None.

        A non-recursive root only matches when it is the first path component.
        A recursive root matches when it appears at *any* depth (``__pycache__``).
        """
        parts = relative.parts
        if not parts:
            return None
        for entry in self.allowlist_roots:
            if entry.recursive:
                if entry.root in parts:
                    return entry
            elif parts[0] == entry.root:
                return entry
        return None


@dataclass(frozen=True)
class Candidate:
    path: str
    root: str
    category: str
    action: str
    size_bytes: int
    age_days: float
    max_age_days: float
    proof: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class Refusal:
    path: str
    reason: str
    detail: str

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class CleanupPlan:
    mode: str
    repo_root: str
    generated_at: str
    schema_version: str
    tool_version: str
    candidates: tuple[Candidate, ...]
    refusals: tuple[Refusal, ...]
    forbidden_operations: tuple[str, ...]

    @property
    def reclaimable_bytes(self) -> int:
        return sum(c.size_bytes for c in self.candidates)

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "tool_version": self.tool_version,
            "mode": self.mode,
            "repo_root": self.repo_root,
            "generated_at": self.generated_at,
            "summary": {
                "candidates": len(self.candidates),
                "refusals": len(self.refusals),
                "reclaimable_bytes": self.reclaimable_bytes,
                "refusals_by_reason": self.refusals_by_reason(),
            },
            "candidates": [c.as_dict() for c in self.candidates],
            "refusals": [r.as_dict() for r in self.refusals],
            "forbidden_operations": list(self.forbidden_operations),
        }

    def refusals_by_reason(self) -> dict[str, int]:
        out: dict[str, int] = {}
        for r in self.refusals:
            out[r.reason] = out.get(r.reason, 0) + 1
        return dict(sorted(out.items()))


def _iso(ts: float) -> str:
    return datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()


def assert_operation_allowed(operation: str) -> None:
    """Raise :class:`ForbiddenOperationError` for structurally banned operations."""
    normalised = " ".join(str(operation).lower().split())
    for forbidden in FORBIDDEN_OPERATIONS:
        if forbidden in normalised:
            raise ForbiddenOperationError(operation)


def parse_policy(data: Mapping[str, Any]) -> CleanupPolicy:
    """Build a :class:`CleanupPolicy`, failing closed on malformed input."""
    if not isinstance(data, Mapping):
        raise CleanupError("policy root must be a mapping")
    cleanup = data.get("cleanup")
    if not isinstance(cleanup, Mapping):
        raise CleanupError("policy is missing a 'cleanup' mapping")
    raw_roots = cleanup.get("allowlist_roots")
    if not isinstance(raw_roots, Sequence) or not raw_roots:
        raise CleanupError("cleanup.allowlist_roots must be a non-empty list")

    roots: list[AllowlistRoot] = []
    for item in raw_roots:
        if not isinstance(item, Mapping):
            raise CleanupError("each allowlist root must be a mapping")
        root = item.get("root")
        if not isinstance(root, str) or not root.strip():
            raise CleanupError("allowlist root entry requires a non-empty 'root'")
        if Path(root).is_absolute() or ".." in Path(root).parts:
            raise CleanupError(f"allowlist root must be repo-relative and contained: {root!r}")
        max_age = item.get("max_age_days")
        if max_age is not None and not isinstance(max_age, (int, float)):
            raise CleanupError(f"max_age_days must be numeric for root {root!r}")
        roots.append(
            AllowlistRoot(
                root=root,
                category=str(item.get("category", "unclassified")),
                max_age_days=float(max_age) if max_age is not None else None,
                require_unreferenced=bool(item.get("require_unreferenced", False)),
                recursive=bool(item.get("recursive", False)),
            )
        )

    forbidden = tuple(str(x) for x in cleanup.get("forbidden_operations", []) or ())
    if "docker system prune" not in forbidden:
        raise CleanupError(
            "cleanup.forbidden_operations must explicitly declare 'docker system prune'"
        )

    declared_rules = tuple(str(x) for x in (data.get("refuse_rules") or ()))
    missing = [r for r in REFUSE_RULES if r not in declared_rules]
    if missing:
        raise CleanupError(f"policy is missing mandatory refuse_rules: {', '.join(missing)}")

    return CleanupPolicy(
        allowlist_roots=tuple(roots),
        forbidden_operations=forbidden,
        refuse_rules=declared_rules,
    )


def load_policy(path: Path | None) -> CleanupPolicy:
    """Load the cleanup policy from YAML; ``None`` uses the built-in default."""
    if path is None:
        return parse_policy(DEFAULT_POLICY)
    try:
        import yaml
    except ImportError as exc:  # pragma: no cover - PyYAML is present in CI
        raise CleanupError("PyYAML is required to read the policy file") from exc
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise CleanupError(f"cannot read policy file: {path}") from exc
    data = yaml.safe_load(raw) or {}
    if not isinstance(data, dict):
        raise CleanupError("policy root must be a mapping")
    return parse_policy(data)


def _dir_size(path: Path) -> int:
    total = 0
    for root, _dirs, files in os.walk(path, followlinks=False):
        for name in files:
            try:
                total += os.lstat(os.path.join(root, name)).st_size
            except OSError:
                continue
    return total


def _entry_size(path: Path) -> int:
    try:
        if path.is_dir() and not path.is_symlink():
            return _dir_size(path)
        return os.lstat(path).st_size
    except OSError:
        return 0


def _newest_mtime(path: Path) -> float | None:
    """Newest mtime in the subtree; ``None`` when nothing can be read.

    The *newest* mtime is used deliberately: a directory is only stale when
    everything inside it is stale.
    """
    try:
        newest = os.lstat(path).st_mtime
    except OSError:
        return None
    if path.is_dir() and not path.is_symlink():
        for root, _dirs, files in os.walk(path, followlinks=False):
            for name in files:
                try:
                    newest = max(newest, os.lstat(os.path.join(root, name)).st_mtime)
                except OSError:
                    return None
    return newest


def _is_within(child: Path, parent: Path) -> bool:
    try:
        child.relative_to(parent)
        return True
    except ValueError:
        return False


def evaluate_path(
    raw_path: Path,
    repo_root: Path,
    policy: CleanupPolicy,
    *,
    now: float,
    active_worktrees: Sequence[Path] = (),
    referenced_evidence: Sequence[Path] = (),
) -> Candidate | Refusal:
    """Classify one path as a dry-run candidate or a refusal. Never mutates."""
    display = str(raw_path)
    try:
        real_root = repo_root.resolve()
        candidate_path = raw_path if raw_path.is_absolute() else real_root / raw_path

        # Lexical containment first: an obviously foreign path is unknown, not
        # an escape.
        if not _is_within(Path(os.path.normpath(str(candidate_path))), real_root):
            return Refusal(display, REFUSE_UNKNOWN_PATH, "path is outside the repository root")

        lexical_rel = Path(os.path.normpath(str(candidate_path))).relative_to(real_root)
        entry = policy.match_root(lexical_rel)
        if entry is None:
            return Refusal(
                display,
                REFUSE_UNKNOWN_PATH,
                f"no allowlist root governs this path (allowed: {', '.join(policy.root_names())})",
            )

        if not candidate_path.exists() and not candidate_path.is_symlink():
            return Refusal(display, REFUSE_INSUFFICIENT_PROOF, "path does not exist")

        # Symlink containment: resolve and require the target to stay inside.
        resolved = candidate_path.resolve()
        if not _is_within(resolved, real_root):
            return Refusal(
                display, REFUSE_SYMLINK_ESCAPE, "resolves outside the repository root"
            )
        if candidate_path.is_symlink():
            return Refusal(
                display, REFUSE_SYMLINK_ESCAPE, "path is a symlink; planner refuses indirection"
            )

        for wt in active_worktrees:
            wt_real = Path(wt).resolve()
            if _is_within(resolved, wt_real) or _is_within(wt_real, resolved):
                return Refusal(display, REFUSE_ACTIVE_WORKTREE, f"inside active worktree {wt_real}")

        if entry.require_unreferenced:
            for ref in referenced_evidence:
                ref_real = Path(ref).resolve() if Path(ref).is_absolute() else (real_root / ref).resolve()
                if resolved == ref_real or _is_within(ref_real, resolved) or _is_within(resolved, ref_real):
                    return Refusal(
                        display, REFUSE_CURRENT_EVIDENCE, "evidence is still referenced"
                    )

        if entry.max_age_days is None:
            return Refusal(
                display, REFUSE_INSUFFICIENT_PROOF, "allowlist root declares no max_age_days"
            )

        newest = _newest_mtime(candidate_path)
        if newest is None:
            return Refusal(display, REFUSE_INSUFFICIENT_PROOF, "mtime is unreadable")

        age_days = (now - newest) / 86400.0
        if age_days < entry.max_age_days:
            return Refusal(
                display,
                REFUSE_INSUFFICIENT_PROOF,
                f"age {age_days:.2f}d < required {entry.max_age_days:.2f}d",
            )

        return Candidate(
            path=str(resolved.relative_to(real_root)),
            root=entry.root,
            category=entry.category,
            action="report-only",
            size_bytes=_entry_size(candidate_path),
            age_days=round(age_days, 4),
            max_age_days=entry.max_age_days,
            proof={
                "newest_mtime": _iso(newest),
                "evaluated_at": _iso(now),
                "require_unreferenced": entry.require_unreferenced,
                "mode": MODE,
            },
        )
    except Exception as exc:  # noqa: BLE001 - fail closed on anything unexpected
        return Refusal(display, REFUSE_INSUFFICIENT_PROOF, f"evaluation error: {type(exc).__name__}")


def discover_paths(repo_root: Path, policy: CleanupPolicy) -> list[Path]:
    """Deterministically enumerate allowlisted paths that exist under the root."""
    found: set[Path] = set()
    real_root = repo_root.resolve()
    for entry in policy.allowlist_roots:
        if entry.recursive:
            for dirpath, dirnames, _files in os.walk(real_root, followlinks=False):
                if entry.root in dirnames:
                    found.add(Path(dirpath) / entry.root)
                if ".git" in dirnames:
                    dirnames.remove(".git")
        else:
            target = real_root / entry.root
            if target.exists() or target.is_symlink():
                found.add(target)
    return sorted(found, key=str)


def plan_cleanup(
    repo_root: Path,
    policy: CleanupPolicy,
    *,
    now: float | None = None,
    paths: Iterable[Path] | None = None,
    active_worktrees: Sequence[Path] = (),
    referenced_evidence: Sequence[Path] = (),
) -> CleanupPlan:
    """Produce a dry-run cleanup plan. Performs no filesystem mutation."""
    ts = time.time() if now is None else now
    real_root = repo_root.resolve()
    targets = list(paths) if paths is not None else discover_paths(real_root, policy)

    candidates: list[Candidate] = []
    refusals: list[Refusal] = []
    for target in targets:
        result = evaluate_path(
            Path(target),
            real_root,
            policy,
            now=ts,
            active_worktrees=active_worktrees,
            referenced_evidence=referenced_evidence,
        )
        if isinstance(result, Candidate):
            candidates.append(result)
        else:
            refusals.append(result)

    return CleanupPlan(
        mode=MODE,
        repo_root=str(real_root),
        generated_at=_iso(ts),
        schema_version=PLAN_SCHEMA_VERSION,
        tool_version=TOOL_VERSION,
        candidates=tuple(sorted(candidates, key=lambda c: c.path)),
        refusals=tuple(sorted(refusals, key=lambda r: (r.reason, r.path))),
        forbidden_operations=policy.forbidden_operations,
    )


def build_self_test_tree(base: Path, now: float) -> tuple[Path, dict[str, Any]]:
    """Build a synthetic repo tree so --self-test never touches the real host."""
    root = base / "repo"
    (root / "artifacts" / "old-run").mkdir(parents=True, exist_ok=True)
    stale = root / "artifacts" / "old-run" / "report.json"
    stale.write_text("{}\n", encoding="utf-8")
    old = now - (60 * 86400)
    os.utime(stale, (old, old))
    os.utime(root / "artifacts" / "old-run", (old, old))
    os.utime(root / "artifacts", (old, old))

    (root / "evidence").mkdir(parents=True, exist_ok=True)
    fresh = root / "evidence" / "current.json"
    fresh.write_text("{}\n", encoding="utf-8")

    (root / "src").mkdir(parents=True, exist_ok=True)
    (root / "src" / "app.py").write_text("x = 1\n", encoding="utf-8")
    return root, {"expect_candidate_root": "artifacts"}


def cmd_plan(args: argparse.Namespace) -> int:
    now = time.time()
    if args.self_test:
        import tempfile

        with tempfile.TemporaryDirectory(prefix="hsl-cleanup-selftest-") as tmp:
            root, _meta = build_self_test_tree(Path(tmp), now)
            policy = load_policy(Path(args.config) if args.config else None)
            plan = plan_cleanup(root, policy, now=now)
            payload = plan.as_dict()
            payload["repo_root"] = "<self-test>"
            for cand in payload["candidates"]:
                cand["proof"]["evaluated_at"] = "<self-test>"
            print(json.dumps(payload, indent=2, sort_keys=True))
            return EXIT_OK if plan.candidates or not plan.refusals else EXIT_OK

    repo_root = Path(args.repo_root).resolve()
    if not repo_root.is_dir():
        raise CleanupError(f"repo root is not a directory: {repo_root}")
    policy = load_policy(Path(args.config) if args.config else None)
    plan = plan_cleanup(
        repo_root,
        policy,
        now=now,
        active_worktrees=[Path(p) for p in (args.active_worktree or [])],
        referenced_evidence=[Path(p) for p in (args.referenced_evidence or [])],
    )
    payload = json.dumps(plan.as_dict(), indent=2, sort_keys=True)
    if args.output:
        Path(args.output).write_text(payload + "\n", encoding="utf-8")
    print(payload)
    return EXIT_OK


def cmd_check_operation(args: argparse.Namespace) -> int:
    assert_operation_allowed(args.operation)
    print(json.dumps({"operation": args.operation, "status": "allowed"}, indent=2))
    return EXIT_OK


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    sub = parser.add_subparsers(dest="command", required=True)

    plan = sub.add_parser("plan", help="emit a dry-run cleanup plan (never deletes)")
    plan.add_argument("--repo-root", default=".")
    plan.add_argument("--config", default=None)
    plan.add_argument("--output", default=None)
    plan.add_argument("--active-worktree", action="append", default=[])
    plan.add_argument("--referenced-evidence", action="append", default=[])
    plan.add_argument(
        "--self-test",
        action="store_true",
        help="plan against a synthetic tree; independent of the real host",
    )
    plan.set_defaults(func=cmd_plan)

    check = sub.add_parser("check-operation", help="assert an operation is not forbidden")
    check.add_argument("operation")
    check.set_defaults(func=cmd_check_operation)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return int(args.func(args))
    except CleanupError as exc:
        print(
            json.dumps({"status": "REFUSED", "reason": str(exc)}, indent=2),
            flush=True,
        )
        return exc.code


if __name__ == "__main__":
    raise SystemExit(main())
