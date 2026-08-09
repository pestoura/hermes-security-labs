#!/usr/bin/env python3
"""Read-only catalog and rollout CLI for Hermes Security Labs.

The CLI deliberately does not start or destroy environments. It provides one
catalog implementation for flat YAML manifests and directory-based
``manifest.yaml`` files while the repository migrates to a single convention.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

try:
    import yaml
except ImportError as exc:  # pragma: no cover
    raise SystemExit("PyYAML is required to use platform/scripts/labctl.py") from exc

PLATFORM_DIR = Path(__file__).resolve().parents[1]
ENVIRONMENTS_DIR = PLATFORM_DIR / "environments"
REGISTRY_PATH = PLATFORM_DIR / "registry.yaml"
ROLLOUT_PATH = PLATFORM_DIR / "rollout.yaml"
SCHEMA_PATH = PLATFORM_DIR / "schemas" / "lab-manifest.schema.json"
REQUIRED_FIELDS = {"id", "name", "runtime", "status"}
MANIFEST_HINT_FIELDS = REQUIRED_FIELDS | {"category", "resources", "lifecycle"}
IGNORED_YAML_NAMES = {"compose.yaml", "compose-effective.yaml"}
DEFAULT_RUNTIMES = {"docker", "kubernetes", "virtual-machine", "cloud", "emulator"}
DEFAULT_STATUSES = {
    "CURRENT",
    "CURRENT-LIMITED",
    "FUTURE-VM",
    "FUTURE-HARDWARE",
    "CLOUD-SANDBOX",
    "EXTERNAL-HARDWARE",
    "PLANNED",
}


@dataclass(frozen=True)
class Manifest:
    env_id: str
    path: Path
    data: dict[str, Any]

    @property
    def relative_path(self) -> str:
        return self.path.relative_to(PLATFORM_DIR).as_posix()


def load_yaml(path: Path) -> Any:
    try:
        return yaml.safe_load(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise ValueError(f"cannot read {path}: {exc}") from exc
    except yaml.YAMLError as exc:
        raise ValueError(f"invalid YAML in {path}: {exc}") from exc


def candidate_yaml_files() -> Iterable[Path]:
    if not ENVIRONMENTS_DIR.is_dir():
        raise ValueError(f"missing environments directory: {ENVIRONMENTS_DIR}")
    for path in sorted(ENVIRONMENTS_DIR.rglob("*.yaml")):
        if path.name in IGNORED_YAML_NAMES:
            continue
        yield path


def discover_manifests() -> tuple[list[Manifest], list[str]]:
    manifests: list[Manifest] = []
    errors: list[str] = []

    try:
        candidates = list(candidate_yaml_files())
    except ValueError as exc:
        return manifests, [str(exc)]

    for path in candidates:
        try:
            data = load_yaml(path)
        except ValueError as exc:
            errors.append(str(exc))
            continue

        if not isinstance(data, dict):
            continue

        looks_like_manifest = path.name == "manifest.yaml" or bool(
            MANIFEST_HINT_FIELDS.intersection(data)
        )
        if not looks_like_manifest:
            continue

        missing = REQUIRED_FIELDS - set(data)
        if missing:
            errors.append(
                f"{path.relative_to(PLATFORM_DIR)}: missing fields "
                f"{', '.join(sorted(missing))}"
            )
            continue

        env_id = str(data["id"]).strip()
        if not env_id:
            errors.append(f"empty id in {path.relative_to(PLATFORM_DIR)}")
            continue
        manifests.append(Manifest(env_id=env_id, path=path, data=data))

    seen: dict[str, Path] = {}
    for manifest in manifests:
        previous = seen.get(manifest.env_id)
        if previous:
            errors.append(
                f"duplicate id '{manifest.env_id}': "
                f"{previous.relative_to(PLATFORM_DIR)} and {manifest.relative_path}"
            )
        else:
            seen[manifest.env_id] = manifest.path

    return manifests, errors


def registry_constraints() -> tuple[set[str], set[str]]:
    runtimes = set(DEFAULT_RUNTIMES)
    statuses = set(DEFAULT_STATUSES)
    if not REGISTRY_PATH.exists():
        return runtimes, statuses

    data = load_yaml(REGISTRY_PATH)
    if not isinstance(data, dict):
        return runtimes, statuses

    runtime_entries = data.get("runtimes", [])
    if isinstance(runtime_entries, list):
        configured = {
            str(item.get("id"))
            for item in runtime_entries
            if isinstance(item, dict) and item.get("id")
        }
        if configured:
            runtimes = configured

    status_entries = data.get("statuses", [])
    if isinstance(status_entries, list):
        configured_statuses = {str(item) for item in status_entries if item}
        if configured_statuses:
            statuses = configured_statuses

    return runtimes, statuses


def manifest_index() -> tuple[dict[str, Manifest], list[str]]:
    manifests, errors = discover_manifests()
    return {manifest.env_id: manifest for manifest in manifests}, errors


def schema_errors(manifest: Manifest) -> list[str]:
    if not SCHEMA_PATH.exists():
        return [f"missing schema: {SCHEMA_PATH.relative_to(PLATFORM_DIR)}"]

    try:
        schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return [f"invalid schema {SCHEMA_PATH.relative_to(PLATFORM_DIR)}: {exc}"]

    try:
        from jsonschema import Draft7Validator
    except ImportError:
        return []

    validator = Draft7Validator(schema)
    errors: list[str] = []
    for error in sorted(validator.iter_errors(manifest.data), key=lambda item: list(item.path)):
        location = ".".join(str(part) for part in error.path) or "$"
        errors.append(f"{manifest.relative_path}: schema {location}: {error.message}")
    return errors


def cmd_list(args: argparse.Namespace) -> int:
    index, errors = manifest_index()
    if errors:
        for error in errors:
            print(f"ERROR\t{error}", file=sys.stderr)
        return 1

    print("id\tcategory\truntime\tstatus\tpath")
    for env_id in sorted(index):
        manifest = index[env_id]
        data = manifest.data
        category = str(data.get("category", "uncategorized"))
        runtime = str(data.get("runtime", "unknown"))
        status = str(data.get("status", "unknown"))
        if args.category and category != args.category:
            continue
        if args.runtime and runtime != args.runtime:
            continue
        if args.status and status != args.status:
            continue
        print(f"{env_id}\t{category}\t{runtime}\t{status}\t{manifest.relative_path}")
    return 0


def cmd_status(args: argparse.Namespace) -> int:
    index, errors = manifest_index()
    if errors:
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
        return 1
    manifest = index.get(args.env_id)
    if not manifest:
        print(f"unknown environment: {args.env_id}", file=sys.stderr)
        return 2
    data = manifest.data
    print(f"id={manifest.env_id}")
    print(f"name={data.get('name', '')}")
    print(f"category={data.get('category', 'uncategorized')}")
    print(f"runtime={data.get('runtime', '')}")
    print(f"driver={data.get('driver', '')}")
    print(f"status={data.get('status', '')}")
    print(f"path={manifest.relative_path}")
    return 0


def cmd_validate(_: argparse.Namespace) -> int:
    manifests, errors = discover_manifests()
    runtimes, statuses = registry_constraints()

    for manifest in manifests:
        data = manifest.data
        runtime = str(data.get("runtime", ""))
        status = str(data.get("status", ""))
        if runtime not in runtimes:
            errors.append(f"{manifest.relative_path}: unsupported runtime '{runtime}'")
        if status not in statuses:
            errors.append(f"{manifest.relative_path}: unsupported status '{status}'")
        if "category" not in data:
            errors.append(f"{manifest.relative_path}: missing category")
        if "resources" not in data or not isinstance(data.get("resources"), dict):
            errors.append(f"{manifest.relative_path}: resources must be an object")
        if "lifecycle" not in data or not isinstance(data.get("lifecycle"), list):
            errors.append(f"{manifest.relative_path}: lifecycle must be an array")
        errors.extend(schema_errors(manifest))

    if errors:
        for error in errors:
            print(f"FAIL\t{error}")
        return 1

    print(f"OK\t{len(manifests)} manifests validated")
    return 0


def cmd_plan(args: argparse.Namespace) -> int:
    if not ROLLOUT_PATH.exists():
        print(f"missing rollout file: {ROLLOUT_PATH}", file=sys.stderr)
        return 1
    rollout = load_yaml(ROLLOUT_PATH)
    if not isinstance(rollout, dict) or not isinstance(rollout.get("phases"), list):
        print("invalid rollout.yaml: phases must be an array", file=sys.stderr)
        return 1

    index, errors = manifest_index()
    if errors:
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
        return 1

    selected = 0
    print("phase\tpriority\tissue\tenvironment\tcatalog_state")
    for phase in rollout["phases"]:
        if not isinstance(phase, dict):
            continue
        phase_id = str(phase.get("id", ""))
        if args.phase and phase_id != args.phase:
            continue
        selected += 1
        priority = phase.get("priority", "")
        issue = phase.get("issue", "")
        environments = phase.get("environments", [])
        if not isinstance(environments, list):
            print(f"invalid environments list for phase {phase_id}", file=sys.stderr)
            return 1
        for env_id in environments:
            env_name = str(env_id)
            state = "CATALOGUED" if env_name in index else "PLANNED"
            print(f"{phase_id}\t{priority}\t{issue}\t{env_name}\t{state}")

    if args.phase and not selected:
        print(f"unknown rollout phase: {args.phase}", file=sys.stderr)
        return 2
    return 0


def _load_lifecycle_module():
    """Import the fail-closed lifecycle dispatcher without importing it at module load."""
    import importlib.util

    path = PLATFORM_DIR / "scripts" / "lab_lifecycle.py"
    spec = importlib.util.spec_from_file_location("lab_lifecycle", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def cmd_support(args: argparse.Namespace) -> int:
    """Readiness gate: SUPPORTED/UNSUPPORTED per environment and action (no runtime)."""
    lifecycle = _load_lifecycle_module()
    argv = ["support"]
    if args.env_id:
        argv.append(args.env_id)
    if args.json:
        argv.append("--json")
    return int(lifecycle.main(argv))


def cmd_lifecycle(args: argparse.Namespace) -> int:
    """Dispatch one allowlisted lifecycle action through the fail-closed dispatcher."""
    lifecycle = _load_lifecycle_module()
    argv = ["run", args.env_id, args.action]
    if args.dry_run:
        argv.append("--dry-run")
    if args.yes:
        argv.append("--yes")
    if args.timeout is not None:
        argv.extend(["--timeout", str(args.timeout)])
    return int(lifecycle.main(argv))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    list_parser = subparsers.add_parser("list", help="list discovered environments")
    list_parser.add_argument("--category")
    list_parser.add_argument("--runtime")
    list_parser.add_argument("--status")
    list_parser.set_defaults(func=cmd_list)

    status_parser = subparsers.add_parser("status", help="show catalog status")
    status_parser.add_argument("env_id")
    status_parser.set_defaults(func=cmd_status)

    validate_parser = subparsers.add_parser("validate", help="validate catalog")
    validate_parser.set_defaults(func=cmd_validate)

    plan_parser = subparsers.add_parser("plan", help="show phased rollout plan")
    plan_parser.add_argument("--phase")
    plan_parser.set_defaults(func=cmd_plan)

    support_parser = subparsers.add_parser(
        "support",
        help="readiness gate: SUPPORTED/UNSUPPORTED per environment and action",
    )
    support_parser.add_argument("env_id", nargs="?")
    support_parser.add_argument("--json", action="store_true")
    support_parser.set_defaults(func=cmd_support)

    lifecycle_parser = subparsers.add_parser(
        "lifecycle",
        help="dispatch one allowlisted lifecycle action via the fail-closed dispatcher",
    )
    lifecycle_parser.add_argument("env_id")
    lifecycle_parser.add_argument(
        "action",
        choices=("start", "status", "smoke", "connect-kali", "disconnect-kali", "stop", "reset", "destroy"),
    )
    lifecycle_parser.add_argument("--dry-run", action="store_true")
    lifecycle_parser.add_argument("--yes", action="store_true")
    lifecycle_parser.add_argument("--timeout", type=int)
    lifecycle_parser.set_defaults(func=cmd_lifecycle)

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
