#!/usr/bin/env python3
"""Validate the repository-owned runtime source-of-truth contract.

This tool is read-only. It validates declarative Git artefacts and never inspects,
changes or reconciles a live runtime.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import yaml
from jsonschema import Draft7Validator

PLATFORM_DIR = Path(__file__).resolve().parents[1]
REPOSITORY_ROOT = PLATFORM_DIR.parent
REGISTRY_PATH = PLATFORM_DIR / "registry.yaml"
ROLLOUT_PATH = PLATFORM_DIR / "rollout.yaml"
RUNTIME_DIR = PLATFORM_DIR / "runtimes"
RUNTIME_SCHEMA_PATH = PLATFORM_DIR / "schemas" / "runtime-profile.schema.json"
ENVIRONMENT_DIR = PLATFORM_DIR / "environments"
IGNORED_ENVIRONMENT_YAML = {"compose.yaml", "compose-effective.yaml"}
REQUIRED_DRIFT_STATES = {"IN_SYNC", "DRIFT_DETECTED", "UNKNOWN"}
REQUIRED_NON_AUTHORITATIVE_CLASSES = {
    "applied-deployment-state",
    "host-runtime-state",
    "issue-tracking",
    "generated-output",
}


def load_yaml(path: Path) -> Any:
    try:
        return yaml.safe_load(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise ValueError(f"cannot read {path}: {exc}") from exc
    except yaml.YAMLError as exc:
        raise ValueError(f"invalid YAML in {path}: {exc}") from exc


def load_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise ValueError(f"cannot read {path}: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid JSON in {path}: {exc}") from exc


def repository_path(value: object) -> Path | None:
    if not isinstance(value, str) or not value.strip():
        return None
    candidate = Path(value)
    if candidate.is_absolute() or ".." in candidate.parts:
        return None
    return REPOSITORY_ROOT / candidate


def validate_runtime_profile(
    path: Path,
    schema: dict[str, Any],
    expected_id: str,
    statuses: set[str],
) -> list[str]:
    errors: list[str] = []
    try:
        data = load_yaml(path)
    except ValueError as exc:
        return [str(exc)]
    if not isinstance(data, dict):
        return [f"{path.relative_to(REPOSITORY_ROOT)}: profile must be an object"]

    validator = Draft7Validator(schema)
    for error in sorted(validator.iter_errors(data), key=lambda item: list(item.path)):
        location = ".".join(str(part) for part in error.path) or "$"
        errors.append(
            f"{path.relative_to(REPOSITORY_ROOT)}: schema {location}: {error.message}"
        )

    actual_id = str(data.get("id", ""))
    if actual_id != expected_id:
        errors.append(
            f"{path.relative_to(REPOSITORY_ROOT)}: id '{actual_id}' does not match registry id '{expected_id}'"
        )
    status = str(data.get("status", ""))
    if status not in statuses:
        errors.append(
            f"{path.relative_to(REPOSITORY_ROOT)}: status '{status}' is not registered"
        )
    return errors


def discover_environment_runtimes() -> tuple[dict[str, str], list[str]]:
    runtimes: dict[str, str] = {}
    errors: list[str] = []
    if not ENVIRONMENT_DIR.is_dir():
        return runtimes, ["missing platform/environments directory"]

    for path in sorted(ENVIRONMENT_DIR.rglob("*.yaml")):
        if path.name in IGNORED_ENVIRONMENT_YAML:
            continue
        try:
            data = load_yaml(path)
        except ValueError as exc:
            errors.append(str(exc))
            continue
        if not isinstance(data, dict):
            continue
        if path.name != "manifest.yaml" and not {"id", "runtime", "status"}.issubset(data):
            continue
        env_id = str(data.get("id", "")).strip()
        runtime = str(data.get("runtime", "")).strip()
        if not env_id or not runtime:
            continue
        previous = runtimes.get(env_id)
        if previous is not None:
            errors.append(f"duplicate environment id in source-of-truth scan: {env_id}")
        else:
            runtimes[env_id] = runtime
    return runtimes, errors


def validate_repository() -> list[str]:
    errors: list[str] = []
    try:
        registry = load_yaml(REGISTRY_PATH)
        schema = load_json(RUNTIME_SCHEMA_PATH)
    except ValueError as exc:
        return [str(exc)]
    if not isinstance(registry, dict):
        return ["platform/registry.yaml must be an object"]
    if not isinstance(schema, dict):
        return ["runtime profile schema must be an object"]

    source = registry.get("source_of_truth")
    if not isinstance(source, dict):
        return ["platform/registry.yaml: source_of_truth must be an object"]
    if source.get("canonical_root") != "platform/registry.yaml":
        errors.append("source_of_truth.canonical_root must be platform/registry.yaml")

    authoritative = source.get("authoritative")
    if not isinstance(authoritative, dict):
        errors.append("source_of_truth.authoritative must be an object")
    else:
        required_authorities = {
            "rollout_plan",
            "runtime_profiles",
            "environment_manifests",
            "runtime_templates",
        }
        missing = sorted(required_authorities - set(authoritative))
        if missing:
            errors.append(f"missing authoritative artefact classes: {', '.join(missing)}")
        for name, declaration in authoritative.items():
            if not isinstance(declaration, dict):
                errors.append(f"authoritative.{name} must be an object")
                continue
            for key in ("path", "root", "schema"):
                if key not in declaration:
                    continue
                resolved = repository_path(declaration[key])
                if resolved is None:
                    errors.append(f"authoritative.{name}.{key} is not a safe repository path")
                elif not resolved.exists():
                    errors.append(
                        f"authoritative.{name}.{key} does not exist: {declaration[key]}"
                    )

    non_authoritative = source.get("non_authoritative")
    classes = {
        str(item.get("class"))
        for item in non_authoritative or []
        if isinstance(item, dict) and item.get("class")
    }
    missing_classes = sorted(REQUIRED_NON_AUTHORITATIVE_CLASSES - classes)
    if missing_classes:
        errors.append(
            "missing non-authoritative classes: " + ", ".join(missing_classes)
        )

    drift = source.get("drift")
    if not isinstance(drift, dict):
        errors.append("source_of_truth.drift must be an object")
    else:
        states = {str(item) for item in drift.get("states", [])}
        if states != REQUIRED_DRIFT_STATES:
            errors.append("drift states must be exactly IN_SYNC, DRIFT_DETECTED and UNKNOWN")
        for field in (
            "missing_observation",
            "unparsable_observation",
            "unverifiable_observation",
        ):
            if drift.get(field) != "UNKNOWN":
                errors.append(f"drift.{field} must be UNKNOWN")
        if drift.get("automatic_reconciliation") != "forbidden":
            errors.append("automatic drift reconciliation must be forbidden")
        comparator = repository_path(drift.get("comparator"))
        if comparator is None or not comparator.is_file():
            errors.append("drift comparator must reference an existing repository file")

    release_identity = source.get("release_identity")
    if not isinstance(release_identity, dict):
        errors.append("source_of_truth.release_identity must be an object")
    else:
        if release_identity.get("image_digest_scope") != "runtime-release":
            errors.append("image digests must be scoped to a runtime release")
        if release_identity.get("environment_digest_override") != "forbidden":
            errors.append("environment image digest overrides must be forbidden")
        if release_identity.get("missing_required_digest") != "UNKNOWN":
            errors.append("a missing required image digest must map to UNKNOWN")

    statuses = {str(item) for item in registry.get("statuses", []) if item}
    runtime_entries = registry.get("runtimes")
    if not isinstance(runtime_entries, list):
        return errors + ["platform/registry.yaml: runtimes must be an array"]

    runtime_ids: set[str] = set()
    runtime_paths: set[Path] = set()
    for item in runtime_entries:
        if not isinstance(item, dict):
            errors.append("runtime registry entry must be an object")
            continue
        runtime_id = str(item.get("id", "")).strip()
        manifest_value = item.get("manifest")
        if not runtime_id:
            errors.append("runtime registry entry has an empty id")
            continue
        if runtime_id in runtime_ids:
            errors.append(f"duplicate runtime id: {runtime_id}")
        runtime_ids.add(runtime_id)
        manifest = repository_path(
            f"platform/{manifest_value}" if isinstance(manifest_value, str) else manifest_value
        )
        if manifest is None:
            errors.append(f"runtime {runtime_id}: manifest is not a safe relative path")
            continue
        if manifest in runtime_paths:
            errors.append(f"runtime manifest referenced more than once: {manifest_value}")
        runtime_paths.add(manifest)
        if not manifest.is_file():
            errors.append(f"runtime {runtime_id}: missing manifest {manifest_value}")
            continue
        errors.extend(validate_runtime_profile(manifest, schema, runtime_id, statuses))

    declared_files = set(RUNTIME_DIR.glob("*.yaml"))
    for orphan in sorted(declared_files - runtime_paths):
        errors.append(
            f"orphan runtime profile not referenced by registry: {orphan.relative_to(REPOSITORY_ROOT)}"
        )

    environment_runtimes, environment_errors = discover_environment_runtimes()
    errors.extend(environment_errors)
    for env_id, runtime_id in sorted(environment_runtimes.items()):
        if runtime_id not in runtime_ids:
            errors.append(
                f"environment {env_id}: runtime '{runtime_id}' has no authoritative profile"
            )

    try:
        rollout = load_yaml(ROLLOUT_PATH)
    except ValueError as exc:
        errors.append(str(exc))
    else:
        if not isinstance(rollout, dict) or not isinstance(rollout.get("phases"), list):
            errors.append("platform/rollout.yaml: phases must be an array")
        else:
            phase_ids: set[str] = set()
            for phase in rollout["phases"]:
                if not isinstance(phase, dict):
                    errors.append("rollout phase must be an object")
                    continue
                phase_id = str(phase.get("id", ""))
                if not phase_id:
                    errors.append("rollout phase has an empty id")
                elif phase_id in phase_ids:
                    errors.append(f"duplicate rollout phase id: {phase_id}")
                phase_ids.add(phase_id)
                environments = phase.get("environments", [])
                if not isinstance(environments, list):
                    errors.append(f"rollout phase {phase_id}: environments must be an array")
                elif len(environments) != len(set(map(str, environments))):
                    errors.append(f"rollout phase {phase_id}: duplicate environment reference")

    return errors


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "command",
        nargs="?",
        choices=("validate",),
        default="validate",
        help="validation operation (default: validate)",
    )
    return parser


def main() -> int:
    build_parser().parse_args()
    errors = validate_repository()
    if errors:
        for error in errors:
            print(f"FAIL\t{error}")
        return 1
    environments, _ = discover_environment_runtimes()
    registry = load_yaml(REGISTRY_PATH)
    print(
        "SOURCE_OF_TRUTH_OK\t"
        f"runtimes={len(registry['runtimes'])}\t"
        f"environments={len(environments)}\t"
        "drift=IN_SYNC|DRIFT_DETECTED|UNKNOWN"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
