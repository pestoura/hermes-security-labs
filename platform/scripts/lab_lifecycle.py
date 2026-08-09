#!/usr/bin/env python3
"""Canonical, fail-closed lifecycle dispatcher for Hermes Security Labs.

Scope and non-goals
-------------------
This dispatcher does **not** invent provisioning. It resolves, for an explicitly
supported environment, the lifecycle script that the environment already ships,
and executes it with an argument vector (never through a shell).

An environment is SUPPORTED for an action only when *all* of the following hold:

1. the catalog entry is a directory-based ``manifest.yaml``
   (flat ``<id>.yaml`` entries are catalog-only metadata and are never dispatched);
2. the requested action is in the manifest ``lifecycle`` list, or is one of the
   connectivity actions the shipped script explicitly dispatches;
3. a concrete executable exists next to the manifest, either
   ``scripts/lifecycle.sh`` (unified dispatcher) or ``scripts/<action>.sh``
   (discrete script);
4. the resolved path stays inside the environment directory.

Anything else is UNSUPPORTED and exits non-zero without touching runtime state.

Safety properties
-----------------
- action allowlist, no free-form command input, no ``shell=True``, no ``eval``;
- resolved paths are confined to the environment directory (traversal rejected);
- per-action timeouts, always bounded, killing the child on expiry;
- destructive actions (``reset``, ``destroy``) require explicit ``--yes``;
- ``--dry-run`` prints the exact argv and changes nothing;
- idempotency is a property of the shipped scripts; the dispatcher never
  retries, never loops and never chains actions on its own.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

try:
    import yaml
except ImportError as exc:  # pragma: no cover - dependency declared in docs
    raise SystemExit("PyYAML is required to use platform/scripts/lab_lifecycle.py") from exc

PLATFORM_DIR = Path(__file__).resolve().parents[1]
ENVIRONMENTS_DIRNAME = "environments"

#: The only actions this dispatcher will ever run.
ACTIONS: tuple[str, ...] = (
    "start",
    "status",
    "smoke",
    "connect-kali",
    "disconnect-kali",
    "stop",
    "reset",
    "destroy",
)

#: Actions that change or remove state irrecoverably and need explicit consent.
DESTRUCTIVE_ACTIONS: frozenset[str] = frozenset({"reset", "destroy"})

#: Actions that are about attacker connectivity rather than the lab itself.
#: They are not part of the manifest ``lifecycle`` vocabulary (the schema does
#: not define them), so support is decided purely by the shipped script.
CONNECTIVITY_ACTIONS: frozenset[str] = frozenset({"connect-kali", "disconnect-kali"})

#: Bounded per-action timeouts in seconds. Deliberately generous for image pulls
#: and health waits, deliberately finite for everything.
DEFAULT_TIMEOUTS: dict[str, int] = {
    "start": 900,
    "status": 120,
    "smoke": 300,
    "connect-kali": 120,
    "disconnect-kali": 120,
    "stop": 300,
    "reset": 1200,
    "destroy": 600,
}

EXIT_OK = 0
EXIT_FAILED = 1
EXIT_UNSUPPORTED = 2
EXIT_REFUSED = 3
EXIT_TIMEOUT = 4


class ResolutionError(Exception):
    """The requested environment/action pair cannot be dispatched."""


@dataclass(frozen=True)
class Resolution:
    """A concrete, validated dispatch target."""

    env_id: str
    action: str
    env_dir: Path
    script: Path
    argv: tuple[str, ...]
    mode: str  # "unified" or "discrete"

    def as_dict(self) -> dict[str, Any]:
        return {
            "env_id": self.env_id,
            "action": self.action,
            "mode": self.mode,
            "script": self.script.relative_to(PLATFORM_DIR).as_posix(),
            "argv": list(self.argv),
        }


def environments_dir() -> Path:
    return PLATFORM_DIR / ENVIRONMENTS_DIRNAME


def load_manifest(path: Path) -> dict[str, Any]:
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise ResolutionError(f"cannot read {path}: {exc}") from exc
    except yaml.YAMLError as exc:
        raise ResolutionError(f"invalid YAML in {path}: {exc}") from exc
    if not isinstance(data, dict):
        raise ResolutionError(f"manifest is not a mapping: {path}")
    return data


def dispatchable_manifests() -> dict[str, tuple[Path, dict[str, Any]]]:
    """Directory-based manifests only: those are the ones that can ship scripts."""
    found: dict[str, tuple[Path, dict[str, Any]]] = {}
    root = environments_dir()
    if not root.is_dir():
        return found
    for path in sorted(root.rglob("manifest.yaml")):
        try:
            data = load_manifest(path)
        except ResolutionError:
            continue
        env_id = str(data.get("id", "")).strip()
        if not env_id or env_id in found:
            continue
        found[env_id] = (path, data)
    return found


def _script_dispatches(script: Path, action: str) -> bool:
    """True when a unified ``lifecycle.sh`` declares a case branch for ``action``."""
    try:
        text = script.read_text(encoding="utf-8")
    except OSError:
        return False
    return f"{action})" in text


def _confined(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
    except ValueError:
        return False
    return True


def resolve(env_id: str, action: str) -> Resolution:
    if action not in ACTIONS:
        raise ResolutionError(f"unsupported action '{action}' (allowed: {', '.join(ACTIONS)})")

    manifests = dispatchable_manifests()
    entry = manifests.get(env_id)
    if entry is None:
        raise ResolutionError(
            f"environment '{env_id}' has no dispatchable manifest.yaml "
            "(catalog-only entries are metadata and are never dispatched)"
        )

    manifest_path, data = entry
    env_dir = manifest_path.parent

    declared = data.get("lifecycle")
    if not isinstance(declared, list):
        raise ResolutionError(f"{env_id}: manifest lifecycle is not a list")
    if action not in CONNECTIVITY_ACTIONS and action not in {str(item) for item in declared}:
        raise ResolutionError(f"{env_id}: manifest does not declare lifecycle action '{action}'")

    scripts_dir = env_dir / "scripts"
    unified = scripts_dir / "lifecycle.sh"
    discrete = scripts_dir / f"{action}.sh"

    if unified.is_file() and _script_dispatches(unified, action):
        script, argv_tail, mode = unified, (action,), "unified"
    elif discrete.is_file():
        script, argv_tail, mode = discrete, (), "discrete"
    else:
        raise ResolutionError(
            f"{env_id}: no shipped script implements '{action}' "
            f"(looked for {unified.name} dispatch and {discrete.name})"
        )

    if not _confined(script, env_dir):
        raise ResolutionError(f"{env_id}: resolved script escapes the environment directory")
    if not os.access(script, os.X_OK):
        raise ResolutionError(f"{env_id}: {script.name} is not executable")

    argv = ("bash", str(script), *argv_tail)
    return Resolution(env_id=env_id, action=action, env_dir=env_dir, script=script, argv=argv, mode=mode)


def support_matrix() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for env_id, (manifest_path, data) in sorted(dispatchable_manifests().items()):
        actions: dict[str, str] = {}
        for action in ACTIONS:
            try:
                resolve(env_id, action)
            except ResolutionError:
                actions[action] = "UNSUPPORTED"
            else:
                actions[action] = "SUPPORTED"
        rows.append(
            {
                "env_id": env_id,
                "status": str(data.get("status", "")),
                "runtime": str(data.get("runtime", "")),
                "manifest": manifest_path.relative_to(PLATFORM_DIR).as_posix(),
                "actions": actions,
                "supported": sorted(a for a, state in actions.items() if state == "SUPPORTED"),
            }
        )
    return rows


def timeout_for(action: str, override: int | None) -> int:
    if override is not None:
        if override <= 0:
            raise ResolutionError("timeout must be a positive number of seconds")
        return override
    env_override = os.environ.get("LAB_LIFECYCLE_TIMEOUT")
    if env_override:
        try:
            value = int(env_override)
        except ValueError as exc:
            raise ResolutionError("LAB_LIFECYCLE_TIMEOUT must be an integer") from exc
        if value <= 0:
            raise ResolutionError("LAB_LIFECYCLE_TIMEOUT must be positive")
        return value
    return DEFAULT_TIMEOUTS[action]


def cmd_support(args: argparse.Namespace) -> int:
    rows = support_matrix()
    if args.env_id:
        rows = [row for row in rows if row["env_id"] == args.env_id]
        if not rows:
            print(f"UNSUPPORTED\t{args.env_id}\tno dispatchable manifest", file=sys.stderr)
            return EXIT_UNSUPPORTED
    if args.json:
        print(json.dumps(rows, indent=2, sort_keys=True))
        return EXIT_OK
    print("env_id\tstatus\truntime\tsupported_actions")
    for row in rows:
        supported = ",".join(row["supported"]) or "-"
        print(f"{row['env_id']}\t{row['status']}\t{row['runtime']}\t{supported}")
    return EXIT_OK


def cmd_run(args: argparse.Namespace) -> int:
    try:
        resolution = resolve(args.env_id, args.action)
        timeout = timeout_for(args.action, args.timeout)
    except ResolutionError as exc:
        print(f"UNSUPPORTED\t{exc}", file=sys.stderr)
        return EXIT_UNSUPPORTED

    printable = " ".join(resolution.argv)
    if args.dry_run:
        # A dry run changes nothing, so it is never gated on --yes.
        print(f"DRY-RUN\t{resolution.env_id}\t{resolution.action}\t{printable}")
        return EXIT_OK

    if args.action in DESTRUCTIVE_ACTIONS and not args.yes:
        print(
            f"REFUSED\t'{args.action}' is destructive; re-run with --yes to confirm",
            file=sys.stderr,
        )
        return EXIT_REFUSED

    print(f"DISPATCH\t{resolution.env_id}\t{resolution.action}\ttimeout={timeout}s\t{printable}")
    try:
        completed = subprocess.run(  # noqa: S603 - argv vector, no shell, allowlisted action
            list(resolution.argv),
            cwd=str(resolution.env_dir),
            timeout=timeout,
            check=False,
        )
    except subprocess.TimeoutExpired:
        print(
            f"TIMEOUT\t{resolution.env_id}\t{resolution.action}\tafter {timeout}s",
            file=sys.stderr,
        )
        return EXIT_TIMEOUT
    except OSError as exc:
        print(f"FAILED\t{resolution.env_id}\t{resolution.action}\t{exc}", file=sys.stderr)
        return EXIT_FAILED

    if completed.returncode != 0:
        print(
            f"FAILED\t{resolution.env_id}\t{resolution.action}\texit={completed.returncode}",
            file=sys.stderr,
        )
        return EXIT_FAILED
    print(f"OK\t{resolution.env_id}\t{resolution.action}")
    return EXIT_OK


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Fail-closed lifecycle dispatcher for supported labs.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    support = subparsers.add_parser(
        "support", help="readiness gate: SUPPORTED/UNSUPPORTED per environment and action"
    )
    support.add_argument("env_id", nargs="?")
    support.add_argument("--json", action="store_true")
    support.set_defaults(func=cmd_support)

    run = subparsers.add_parser("run", help="dispatch one allowlisted lifecycle action")
    run.add_argument("env_id")
    run.add_argument("action", choices=ACTIONS)
    run.add_argument("--dry-run", action="store_true", help="print the argv and change nothing")
    run.add_argument("--yes", action="store_true", help="confirm a destructive action")
    run.add_argument("--timeout", type=int, help="override the per-action timeout, in seconds")
    run.set_defaults(func=cmd_run)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
