#!/usr/bin/env python3
"""Minimal, deterministic backend abstraction for Hermes Security Labs (Lane H).

Why this exists
---------------
Every executable environment manifest already declares a ``backend`` field
(``docker-compose``, ``kind``, ...), but nothing in the repository turned that
field into a *typed, fail-closed* contract. The lifecycle dispatcher
(``platform/scripts/lab_lifecycle.py``) resolves shipped scripts and knows
nothing about backend classes; the readiness contract
(``platform/scripts/lab_readiness.py``) knows nothing about them either.

This module adds the missing seam and nothing else:

* a **contract**: five backend types (``DOCKER``, ``VM``, ``KUBERNETES``,
  ``CLOUD``, ``REMOTE_ISOLATED``) with a bounded operation vocabulary
  (``provision``, ``status``, ``reset``, ``destroy``);
* a **registry**: ``platform/backends/backend-registry.yaml``, declarative, which
  states per backend the support state (``SUPPORTED`` / ``DEFINED`` /
  ``UNSUPPORTED``), the readiness (``READY`` / ``NOT_READY``) and the capability
  requirements that are *not* met when it is not ready;
* an **interface**: :class:`BackendAdapter` with ``plan(operation)`` only. A plan
  is a description, never an execution. This module never runs anything.
* a **resolver**: manifest ``backend`` string -> backend type, fail closed on an
  unknown or missing value.

Hard design constraints honoured here
-------------------------------------
- only the Docker Compose backend is implemented, and it is implemented by
  *delegating* to the lifecycle actions the environment already ships. It adds
  no provisioning logic of its own;
- no arbitrary shell: the adapter emits an allowlisted lifecycle *action name*
  plus, when the shipped script exists, the argv vector that
  ``lab_lifecycle.resolve`` already validated. There is no command field, no
  ``shell=True``, no string interpolation into a command anywhere;
- backends other than Docker are modelled explicitly as ``DEFINED`` /
  ``NOT_READY`` with their missing capabilities. Planning against them raises
  :class:`BackendError`. They never silently degrade into "works";
- read-only: this module does not write, start, stop or destroy anything, and it
  does not modify the target registry, the scenario/tool registry, the evidence
  core or CI.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping

try:
    import yaml
except ImportError as exc:  # pragma: no cover - dependency declared in docs
    raise SystemExit("PyYAML is required to use platform/scripts/lab_backends.py") from exc

PLATFORM_DIR = Path(__file__).resolve().parents[1]
REGISTRY_PATH = PLATFORM_DIR / "backends" / "backend-registry.yaml"

SCHEMA_VERSION = 1

#: The complete backend vocabulary. Anything outside this set is unknown and
#: fails closed at resolution time.
BACKEND_TYPES: tuple[str, ...] = ("DOCKER", "VM", "KUBERNETES", "CLOUD", "REMOTE_ISOLATED")

#: The complete, bounded operation vocabulary of the backend API.
OPERATIONS: tuple[str, ...] = ("provision", "status", "reset", "destroy")

#: Operations that irrecoverably change or remove state.
DESTRUCTIVE_OPERATIONS: frozenset[str] = frozenset({"reset", "destroy"})

SUPPORT_STATES: frozenset[str] = frozenset({"SUPPORTED", "DEFINED", "UNSUPPORTED"})
READINESS_STATES: frozenset[str] = frozenset({"READY", "NOT_READY"})

#: Lifecycle actions the Docker Compose adapter is allowed to name. This mirrors
#: the dispatcher allowlist; it is duplicated deliberately so the backend layer
#: fails closed even if it is used without the dispatcher.
DOCKER_ACTION_ALLOWLIST: frozenset[str] = frozenset({"start", "status", "reset", "destroy"})

# Stable reason codes (consumed by tests, CI and operators).
REASON_BACKEND_MISSING = "BACKEND_FIELD_MISSING"
REASON_BACKEND_UNKNOWN = "BACKEND_UNKNOWN"
REASON_BACKEND_NOT_SUPPORTED = "BACKEND_NOT_SUPPORTED"
REASON_BACKEND_NOT_READY = "BACKEND_NOT_READY"
REASON_OPERATION_UNKNOWN = "OPERATION_UNKNOWN"
REASON_OPERATION_UNSUPPORTED = "OPERATION_UNSUPPORTED_BY_BACKEND"
REASON_REGISTRY_INVALID = "BACKEND_REGISTRY_INVALID"

EXIT_OK = 0
EXIT_NOT_READY = 1
EXIT_FAIL_CLOSED = 2


class BackendError(Exception):
    """A backend cannot be resolved, is not ready, or cannot plan the operation."""


# --------------------------------------------------------------------------- #
# Registry model
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class BackendSpec:
    """One declarative backend entry, as loaded from the registry."""

    backend_type: str
    support_state: str
    readiness: str
    aliases: tuple[str, ...]
    adapter: str | None
    description: str
    operations: Mapping[str, str] = field(default_factory=dict)
    required_capabilities: tuple[str, ...] = ()
    missing_capabilities: tuple[str, ...] = ()

    @property
    def is_supported(self) -> bool:
        return self.support_state == "SUPPORTED"

    @property
    def is_ready(self) -> bool:
        return self.readiness == "READY"

    def as_dict(self) -> dict[str, Any]:
        return {
            "backend_type": self.backend_type,
            "support_state": self.support_state,
            "readiness": self.readiness,
            "aliases": list(self.aliases),
            "adapter": self.adapter,
            "description": self.description.strip(),
            "operations": dict(self.operations),
            "required_capabilities": list(self.required_capabilities),
            "missing_capabilities": list(self.missing_capabilities),
        }


@dataclass(frozen=True)
class BackendRegistry:
    """The immutable, validated set of backend specifications."""

    source: Path
    specs: Mapping[str, BackendSpec]

    def get(self, backend_type: str) -> BackendSpec:
        try:
            return self.specs[backend_type]
        except KeyError as exc:
            raise BackendError(f"{REASON_BACKEND_UNKNOWN}: {backend_type!r}") from exc

    def resolve_alias(self, value: str) -> BackendSpec:
        """Map a manifest ``backend`` string onto a backend specification."""
        needle = str(value).strip().lower()
        if not needle:
            raise BackendError(f"{REASON_BACKEND_MISSING}: manifest declares no backend")
        for spec in self.specs.values():
            if needle == spec.backend_type.lower() or needle in spec.aliases:
                return spec
        raise BackendError(
            f"{REASON_BACKEND_UNKNOWN}: {value!r} is not a known backend "
            f"(known: {', '.join(sorted(self.specs))})"
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema_version": SCHEMA_VERSION,
            "source": self.source.relative_to(PLATFORM_DIR).as_posix(),
            "operations": list(OPERATIONS),
            "backends": {name: spec.as_dict() for name, spec in sorted(self.specs.items())},
        }


def _require_mapping(value: Any, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise BackendError(f"{REASON_REGISTRY_INVALID}: {label} must be a mapping")
    return value


def load_registry(path: Path | None = None) -> BackendRegistry:
    """Load and validate the declarative backend registry. Fails closed."""
    source = path or REGISTRY_PATH
    try:
        raw = yaml.safe_load(source.read_text(encoding="utf-8"))
    except OSError as exc:
        raise BackendError(f"{REASON_REGISTRY_INVALID}: cannot read {source}: {exc}") from exc
    except yaml.YAMLError as exc:
        raise BackendError(f"{REASON_REGISTRY_INVALID}: invalid YAML in {source}: {exc}") from exc

    data = _require_mapping(raw, "registry")
    if data.get("schema_version") != SCHEMA_VERSION:
        raise BackendError(
            f"{REASON_REGISTRY_INVALID}: schema_version must be {SCHEMA_VERSION}, "
            f"got {data.get('schema_version')!r}"
        )
    declared_ops = tuple(data.get("operations") or ())
    if tuple(declared_ops) != OPERATIONS:
        raise BackendError(
            f"{REASON_REGISTRY_INVALID}: operations must be exactly {list(OPERATIONS)}"
        )

    entries = _require_mapping(data.get("backends"), "backends")
    if set(entries) != set(BACKEND_TYPES):
        missing = sorted(set(BACKEND_TYPES) - set(entries))
        extra = sorted(set(entries) - set(BACKEND_TYPES))
        raise BackendError(
            f"{REASON_REGISTRY_INVALID}: backends must cover exactly {list(BACKEND_TYPES)} "
            f"(missing={missing}, unexpected={extra})"
        )

    specs: dict[str, BackendSpec] = {}
    seen_aliases: dict[str, str] = {}
    for name in BACKEND_TYPES:
        entry = _require_mapping(entries[name], f"backends.{name}")
        support_state = str(entry.get("support_state", "")).strip()
        readiness = str(entry.get("readiness", "")).strip()
        if support_state not in SUPPORT_STATES:
            raise BackendError(f"{REASON_REGISTRY_INVALID}: {name}.support_state={support_state!r}")
        if readiness not in READINESS_STATES:
            raise BackendError(f"{REASON_REGISTRY_INVALID}: {name}.readiness={readiness!r}")
        if readiness == "READY" and support_state != "SUPPORTED":
            raise BackendError(
                f"{REASON_REGISTRY_INVALID}: {name} is READY but support_state={support_state!r}"
            )

        aliases = tuple(str(a).strip().lower() for a in (entry.get("manifest_aliases") or ()))
        for alias in aliases:
            if alias in seen_aliases:
                raise BackendError(
                    f"{REASON_REGISTRY_INVALID}: alias {alias!r} claimed by both "
                    f"{seen_aliases[alias]} and {name}"
                )
            seen_aliases[alias] = name

        operations = _require_mapping(entry.get("operations") or {}, f"backends.{name}.operations")
        for op in operations:
            if op not in OPERATIONS:
                raise BackendError(f"{REASON_REGISTRY_INVALID}: {name} maps unknown operation {op!r}")
        if support_state == "SUPPORTED" and set(operations) != set(OPERATIONS):
            raise BackendError(
                f"{REASON_REGISTRY_INVALID}: SUPPORTED backend {name} must map every operation"
            )
        if support_state != "SUPPORTED" and operations:
            raise BackendError(
                f"{REASON_REGISTRY_INVALID}: {name} is {support_state} and must not map operations"
            )

        required = tuple(str(c) for c in (entry.get("required_capabilities") or ()))
        missing = tuple(str(c) for c in (entry.get("missing_capabilities") or ()))
        unknown_missing = sorted(set(missing) - set(required))
        if unknown_missing:
            raise BackendError(
                f"{REASON_REGISTRY_INVALID}: {name} lists missing capabilities that are not "
                f"required: {unknown_missing}"
            )
        if readiness == "NOT_READY" and not missing:
            raise BackendError(
                f"{REASON_REGISTRY_INVALID}: {name} is NOT_READY but declares no missing capability"
            )
        if readiness == "READY" and missing:
            raise BackendError(f"{REASON_REGISTRY_INVALID}: {name} is READY but declares {missing}")

        adapter = entry.get("adapter")
        adapter_name = None if adapter in (None, "", "null") else str(adapter)
        if support_state == "SUPPORTED" and not adapter_name:
            raise BackendError(f"{REASON_REGISTRY_INVALID}: SUPPORTED backend {name} has no adapter")
        if support_state != "SUPPORTED" and adapter_name:
            raise BackendError(
                f"{REASON_REGISTRY_INVALID}: {name} is {support_state} but names adapter "
                f"{adapter_name!r}"
            )

        specs[name] = BackendSpec(
            backend_type=name,
            support_state=support_state,
            readiness=readiness,
            aliases=aliases,
            adapter=adapter_name,
            description=str(entry.get("description", "")),
            operations={str(k): str(v) for k, v in operations.items()},
            required_capabilities=required,
            missing_capabilities=missing,
        )

    return BackendRegistry(source=source, specs=specs)


# --------------------------------------------------------------------------- #
# Backend API: plans and adapters
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class BackendPlan:
    """A bounded, inert description of one backend operation.

    A plan is never executed by this module. ``argv`` is populated only when the
    environment ships a concrete script that the lifecycle dispatcher already
    validated; otherwise it is empty and ``executable`` is False.
    """

    env_id: str
    backend_type: str
    operation: str
    action: str
    destructive: bool
    executable: bool
    argv: tuple[str, ...] = ()
    notes: tuple[str, ...] = ()

    def as_dict(self) -> dict[str, Any]:
        return {
            "env_id": self.env_id,
            "backend_type": self.backend_type,
            "operation": self.operation,
            "action": self.action,
            "destructive": self.destructive,
            "executable": self.executable,
            "argv": list(self.argv),
            "notes": list(self.notes),
        }


class BackendAdapter:
    """Interface every backend adapter implements. Planning only, no execution."""

    backend_type: str = ""

    def __init__(self, spec: BackendSpec) -> None:
        self.spec = spec

    def capability_report(self) -> dict[str, Any]:
        return {
            "backend_type": self.spec.backend_type,
            "support_state": self.spec.support_state,
            "readiness": self.spec.readiness,
            "required_capabilities": list(self.spec.required_capabilities),
            "missing_capabilities": list(self.spec.missing_capabilities),
        }

    def plan(self, env_id: str, operation: str) -> BackendPlan:  # pragma: no cover - interface
        raise NotImplementedError


class UnavailableBackendAdapter(BackendAdapter):
    """Adapter for every backend that is modelled but not implemented.

    It exists so callers get one uniform, explicit failure instead of a missing
    attribute or an accidental fallback to Docker.
    """

    def plan(self, env_id: str, operation: str) -> BackendPlan:
        _require_operation(operation)
        reason = (
            REASON_BACKEND_NOT_SUPPORTED
            if self.spec.support_state != "SUPPORTED"
            else REASON_BACKEND_NOT_READY
        )
        missing = ", ".join(self.spec.missing_capabilities) or "none declared"
        raise BackendError(
            f"{reason}: backend {self.spec.backend_type} is "
            f"{self.spec.support_state}/{self.spec.readiness} for {env_id!r} "
            f"(missing capabilities: {missing})"
        )


class DockerComposeBackendAdapter(BackendAdapter):
    """The only implemented backend: Docker Compose, via the shipped lifecycle.

    It contributes no provisioning of its own. ``plan`` maps a backend operation
    onto the allowlisted lifecycle action for the environment and, when the
    dispatcher can resolve a shipped script, records the already-validated argv.
    """

    backend_type = "DOCKER"

    def __init__(self, spec: BackendSpec, resolver: Any | None = None) -> None:
        super().__init__(spec)
        self._resolver = resolver

    def _resolve_argv(self, env_id: str, action: str) -> tuple[tuple[str, ...], tuple[str, ...]]:
        resolver = self._resolver if self._resolver is not None else _default_lifecycle_resolver()
        if resolver is None:
            return (), ("lifecycle dispatcher unavailable: plan is descriptive only",)
        try:
            resolution = resolver(env_id, action)
        except Exception as exc:  # noqa: BLE001 - dispatcher raises its own error type
            return (), (f"no shipped script for action {action!r}: {exc}",)
        argv = tuple(str(part) for part in getattr(resolution, "argv", ()))
        return argv, ()

    def plan(self, env_id: str, operation: str) -> BackendPlan:
        _require_operation(operation)
        action = self.spec.operations.get(operation, "")
        if action not in DOCKER_ACTION_ALLOWLIST:
            raise BackendError(
                f"{REASON_OPERATION_UNSUPPORTED}: DOCKER cannot map {operation!r} onto an "
                f"allowlisted lifecycle action (got {action!r})"
            )
        argv, notes = self._resolve_argv(env_id, action)
        return BackendPlan(
            env_id=env_id,
            backend_type=self.spec.backend_type,
            operation=operation,
            action=action,
            destructive=operation in DESTRUCTIVE_OPERATIONS,
            executable=bool(argv),
            argv=argv,
            notes=notes,
        )


ADAPTERS: dict[str, type[BackendAdapter]] = {"docker_compose": DockerComposeBackendAdapter}


def _require_operation(operation: str) -> None:
    if operation not in OPERATIONS:
        raise BackendError(
            f"{REASON_OPERATION_UNKNOWN}: {operation!r} (known: {', '.join(OPERATIONS)})"
        )


def _default_lifecycle_resolver() -> Any | None:
    """Best-effort, non-invasive seam onto the existing lifecycle dispatcher.

    Import failures are tolerated: the backend layer degrades to a descriptive
    plan instead of breaking. It never patches or replaces dispatcher behaviour.
    """
    try:
        import importlib.util

        spec = importlib.util.spec_from_file_location(
            "lab_lifecycle_for_backends", Path(__file__).resolve().parent / "lab_lifecycle.py"
        )
        if spec is None or spec.loader is None:
            return None
        module = importlib.util.module_from_spec(spec)
        # dataclasses resolve ``cls.__module__`` through ``sys.modules`` during class
        # creation, so the module must be registered before it is executed.
        sys.modules.setdefault(spec.name, module)
        spec.loader.exec_module(module)
    except Exception:  # noqa: BLE001 - the seam must never break the caller
        return None
    return getattr(module, "resolve", None)


def adapter_for(spec: BackendSpec, resolver: Any | None = None) -> BackendAdapter:
    """Return the adapter for a spec. Unimplemented backends get the fail-closed one."""
    if not spec.is_supported or not spec.is_ready or spec.adapter is None:
        return UnavailableBackendAdapter(spec)
    adapter_cls = ADAPTERS.get(spec.adapter)
    if adapter_cls is None:
        raise BackendError(
            f"{REASON_BACKEND_NOT_SUPPORTED}: registry names adapter {spec.adapter!r} "
            f"for {spec.backend_type} but no implementation is registered"
        )
    if adapter_cls is DockerComposeBackendAdapter:
        return DockerComposeBackendAdapter(spec, resolver=resolver)
    return adapter_cls(spec)  # pragma: no cover - single adapter today


# --------------------------------------------------------------------------- #
# Resolver: manifest -> backend
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class BackendBinding:
    """The resolved binding between an environment and its backend."""

    env_id: str
    declared: str
    spec: BackendSpec
    adapter: BackendAdapter

    def as_dict(self) -> dict[str, Any]:
        return {
            "env_id": self.env_id,
            "declared_backend": self.declared,
            "backend_type": self.spec.backend_type,
            "support_state": self.spec.support_state,
            "readiness": self.spec.readiness,
            "missing_capabilities": list(self.spec.missing_capabilities),
        }


def resolve_backend(
    manifest: Mapping[str, Any],
    *,
    registry: BackendRegistry | None = None,
    resolver: Any | None = None,
) -> BackendBinding:
    """Resolve the backend of an *executable* manifest. Fails closed.

    Rules:
      - only ``execution_class: executable`` manifests bind a backend; catalog-only
        entries make no runtime claim and are rejected here;
      - a missing/empty ``backend`` field is a hard failure;
      - an unknown ``backend`` value is a hard failure (no default, no guess).
    """
    reg = registry or load_registry()
    env_id = str(manifest.get("id", "")).strip() or "<unknown>"
    execution_class = str(manifest.get("execution_class", "")).strip()
    if execution_class != "executable":
        raise BackendError(
            f"{REASON_BACKEND_MISSING}: {env_id} is not executable "
            f"(execution_class={execution_class or 'absent'!r}); catalog-only entries have no backend"
        )
    declared_raw = manifest.get("backend")
    declared = "" if declared_raw is None else str(declared_raw).strip()
    if not declared:
        raise BackendError(f"{REASON_BACKEND_MISSING}: {env_id} declares no backend")
    spec = reg.resolve_alias(declared)
    return BackendBinding(
        env_id=env_id,
        declared=declared,
        spec=spec,
        adapter=adapter_for(spec, resolver=resolver),
    )


def load_manifest(path: Path) -> dict[str, Any]:
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise BackendError(f"cannot read {path}: {exc}") from exc
    except yaml.YAMLError as exc:
        raise BackendError(f"invalid YAML in {path}: {exc}") from exc
    if not isinstance(data, dict):
        raise BackendError(f"manifest is not a mapping: {path}")
    return data


def executable_manifests() -> dict[str, tuple[Path, dict[str, Any]]]:
    """Directory-based executable manifests, keyed by environment id."""
    found: dict[str, tuple[Path, dict[str, Any]]] = {}
    root = PLATFORM_DIR / "environments"
    if not root.is_dir():
        return found
    for path in sorted(root.rglob("manifest.yaml")):
        try:
            data = load_manifest(path)
        except BackendError:
            continue
        if str(data.get("execution_class", "")).strip() != "executable":
            continue
        env_id = str(data.get("id", "")).strip()
        if env_id and env_id not in found:
            found[env_id] = (path, data)
    return found


def backend_matrix(registry: BackendRegistry | None = None) -> list[dict[str, Any]]:
    """Per-environment binding report. Read-only, deterministic ordering."""
    reg = registry or load_registry()
    rows: list[dict[str, Any]] = []
    for env_id, (path, data) in sorted(executable_manifests().items()):
        row: dict[str, Any] = {
            "env_id": env_id,
            "manifest": path.relative_to(PLATFORM_DIR).as_posix(),
            "declared_backend": str(data.get("backend", "")),
        }
        try:
            binding = resolve_backend(data, registry=reg)
        except BackendError as exc:
            row.update({"backend_type": None, "resolution": "FAIL_CLOSED", "reason": str(exc)})
        else:
            row.update(
                {
                    "backend_type": binding.spec.backend_type,
                    "support_state": binding.spec.support_state,
                    "readiness": binding.spec.readiness,
                    "resolution": "RESOLVED",
                    "missing_capabilities": list(binding.spec.missing_capabilities),
                }
            )
        rows.append(row)
    return rows


# --------------------------------------------------------------------------- #
# CLI (read-only)
# --------------------------------------------------------------------------- #


def cmd_list(args: argparse.Namespace) -> int:
    try:
        registry = load_registry()
    except BackendError as exc:
        print(f"FAIL-CLOSED\t{exc}", file=sys.stderr)
        return EXIT_FAIL_CLOSED
    if args.json:
        print(json.dumps(registry.as_dict(), indent=2, sort_keys=True))
        return EXIT_OK
    print("backend_type\tsupport_state\treadiness\tadapter")
    for name, spec in sorted(registry.specs.items()):
        print(f"{name}\t{spec.support_state}\t{spec.readiness}\t{spec.adapter or '-'}")
    return EXIT_OK


def cmd_matrix(args: argparse.Namespace) -> int:
    try:
        rows = backend_matrix()
    except BackendError as exc:
        print(f"FAIL-CLOSED\t{exc}", file=sys.stderr)
        return EXIT_FAIL_CLOSED
    if args.json:
        print(json.dumps(rows, indent=2, sort_keys=True))
        return EXIT_OK
    print("env_id\tdeclared_backend\tbackend_type\tresolution\treadiness")
    for row in rows:
        print(
            f"{row['env_id']}\t{row['declared_backend']}\t{row.get('backend_type') or '-'}"
            f"\t{row['resolution']}\t{row.get('readiness', '-')}"
        )
    return EXIT_OK


def cmd_plan(args: argparse.Namespace) -> int:
    try:
        registry = load_registry()
        entry = executable_manifests().get(args.env_id)
        if entry is None:
            raise BackendError(f"{REASON_BACKEND_MISSING}: no executable manifest for {args.env_id!r}")
        binding = resolve_backend(entry[1], registry=registry)
        plan = binding.adapter.plan(args.env_id, args.operation)
    except BackendError as exc:
        print(f"FAIL-CLOSED\t{exc}", file=sys.stderr)
        return EXIT_FAIL_CLOSED
    if args.json:
        print(json.dumps(plan.as_dict(), indent=2, sort_keys=True))
    else:
        argv = " ".join(plan.argv) or "-"
        print(
            f"PLAN\t{plan.env_id}\t{plan.backend_type}\t{plan.operation}\taction={plan.action}"
            f"\tdestructive={plan.destructive}\texecutable={plan.executable}\t{argv}"
        )
    return EXIT_OK if plan.executable else EXIT_NOT_READY


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Read-only backend contract, registry and planner for Hermes Security Labs."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    listing = subparsers.add_parser("list", help="list backend types with support/readiness state")
    listing.add_argument("--json", action="store_true")
    listing.set_defaults(func=cmd_list)

    matrix = subparsers.add_parser("matrix", help="per-environment backend binding report")
    matrix.add_argument("--json", action="store_true")
    matrix.set_defaults(func=cmd_matrix)

    plan = subparsers.add_parser("plan", help="describe (never execute) one backend operation")
    plan.add_argument("env_id")
    plan.add_argument("operation", choices=list(OPERATIONS))
    plan.add_argument("--json", action="store_true")
    plan.set_defaults(func=cmd_plan)

    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
