"""Canonical target registry for Hermes Security Labs.

Design contract (fail closed):

* ``target_id`` is the only execution authority. A URL, hostname or IP address
  is never, on its own, an authority to execute anything.
* Offensive execution eligibility resolves ``True`` only when the target's
  ``authorization_state`` is ``LAB_ONLY`` or ``AUTHORIZED_TEST_TARGET``.
  Unknown, missing, malformed or ambiguous states resolve ``False`` with an
  explicit reason.
* The resolver is deterministic and side-effect free: it never touches the
  network, never starts a container and never mutates runtime state.

This module is deliberately standalone. It is NOT wired into
``platform/lab-lifecycle/lifecycle_protocol.py`` or into ``lab_lifecycle`` in
this lane; consumers import :func:`resolve_target` /
:func:`resolve_execution_eligibility` explicitly.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping, Sequence

try:  # pragma: no cover - exercised indirectly by both import styles
    import yaml
except ImportError as exc:  # pragma: no cover - dependency is present in CI
    raise RuntimeError("PyYAML is required to load the target registry") from exc

ROOT = Path(__file__).resolve().parents[2]
REGISTRY_PATH = Path(__file__).resolve().parent / "target-registry.yaml"
SCHEMA_PATH = Path(__file__).resolve().parent / "target-registry.schema.json"
ENVIRONMENTS_DIR = ROOT / "platform" / "environments"

IGNORED_ENVIRONMENT_YAML = {"compose.yaml", "compose-effective.yaml"}

AUTHORIZATION_STATES = (
    "LAB_ONLY",
    "AUTHORIZED_TEST_TARGET",
    "UNVERIFIED",
    "BLOCKED",
    "EXTERNAL",
)
OFFENSIVE_EXECUTION_STATES = frozenset({"LAB_ONLY", "AUTHORIZED_TEST_TARGET"})
LIFECYCLE_STATES = ("PLANNED", "PROVISIONED", "ACTIVE", "SUSPENDED", "RETIRED")
HEALTH_STATES = ("UNKNOWN", "HEALTHY", "DEGRADED", "UNHEALTHY")
ALLOWED_REACHABILITY = frozenset({"lab-internal", "loopback"})


class TargetRegistryError(ValueError):
    """Fail-closed target registry contract violation."""


@dataclass(frozen=True)
class ExecutionDecision:
    """Deterministic outcome of an offensive-execution eligibility question."""

    target_id: str | None
    eligible: bool
    reason: str
    authorization_state: str | None = None
    environment_id: str | None = None
    allowed_operations: tuple[str, ...] = field(default_factory=tuple)

    def as_dict(self) -> dict[str, Any]:
        return {
            "target_id": self.target_id,
            "eligible": self.eligible,
            "reason": self.reason,
            "authorization_state": self.authorization_state,
            "environment_id": self.environment_id,
            "allowed_operations": list(self.allowed_operations),
        }


# --------------------------------------------------------------------------
# loading
# --------------------------------------------------------------------------


def load_registry(path: Path | str | None = None) -> dict[str, Any]:
    """Load and structurally validate the registry document."""

    registry_path = Path(path) if path is not None else REGISTRY_PATH
    if not registry_path.is_file():
        raise TargetRegistryError(f"target registry not found: {registry_path}")
    try:
        document = yaml.safe_load(registry_path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise TargetRegistryError(f"target registry is not valid YAML: {exc}") from exc
    errors = validate_registry(document)
    if errors:
        raise TargetRegistryError("; ".join(errors))
    assert isinstance(document, dict)
    return document


def targets(document: Mapping[str, Any]) -> list[dict[str, Any]]:
    entries = document.get("targets")
    if not isinstance(entries, list):
        raise TargetRegistryError("registry targets must be an array")
    return [dict(entry) for entry in entries if isinstance(entry, Mapping)]


def index_by_id(document: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    index: dict[str, dict[str, Any]] = {}
    for entry in targets(document):
        target_id = entry.get("target_id")
        if not isinstance(target_id, str):
            raise TargetRegistryError("every target requires a string target_id")
        if target_id in index:
            raise TargetRegistryError(f"duplicate target_id: {target_id}")
        index[target_id] = entry
    return index


# --------------------------------------------------------------------------
# validation
# --------------------------------------------------------------------------


def _validate_identity(label: str, identity: Any) -> list[str]:
    errors: list[str] = []
    if not isinstance(identity, Mapping):
        return [f"{label}: identity must be an object"]
    hostname = identity.get("hostname")
    if not isinstance(hostname, str) or not hostname.strip():
        errors.append(f"{label}: identity.hostname is required")
    network = identity.get("network")
    if not isinstance(network, str) or not network.strip():
        errors.append(f"{label}: identity.network is required")
    reachability = identity.get("reachability")
    if reachability not in ALLOWED_REACHABILITY:
        errors.append(
            f"{label}: identity.reachability must be one of {sorted(ALLOWED_REACHABILITY)}"
        )
    port = identity.get("port")
    if port is not None:
        if isinstance(port, bool) or not isinstance(port, int) or not 1 <= port <= 65535:
            errors.append(f"{label}: identity.port must be a TCP/UDP port number")
    return errors


def _validate_scope(label: str, scope: Any) -> list[str]:
    if not isinstance(scope, Mapping):
        return [f"{label}: scope must be an object"]
    allowed = scope.get("allowed_operations")
    if not isinstance(allowed, list) or not allowed:
        return [f"{label}: scope.allowed_operations must be a non-empty array"]
    errors: list[str] = []
    if len(set(allowed)) != len(allowed):
        errors.append(f"{label}: scope.allowed_operations contains duplicates")
    for operation in allowed:
        if not isinstance(operation, str) or not operation.strip():
            errors.append(f"{label}: scope.allowed_operations entries must be non-empty strings")
    return errors


def validate_registry(document: Any) -> list[str]:
    """Return a list of contract violations. Empty list means valid."""

    if not isinstance(document, Mapping):
        return ["target registry must be a mapping"]

    errors: list[str] = []
    if document.get("schema_version") != "1.0":
        errors.append("schema_version must be '1.0'")

    contract = document.get("contract")
    if not isinstance(contract, Mapping):
        errors.append("contract must be an object")
    else:
        if contract.get("canonical_authority") != "target_id":
            errors.append("contract.canonical_authority must be 'target_id'")
        if contract.get("fail_closed") is not True:
            errors.append("contract.fail_closed must be true")
        states = contract.get("offensive_execution_states")
        if not isinstance(states, list) or set(states) != set(OFFENSIVE_EXECUTION_STATES):
            errors.append(
                "contract.offensive_execution_states must be exactly "
                f"{sorted(OFFENSIVE_EXECUTION_STATES)}"
            )

    entries = document.get("targets")
    if not isinstance(entries, list) or not entries:
        return errors + ["targets must be a non-empty array"]

    seen: set[str] = set()
    for position, entry in enumerate(entries):
        label = f"targets[{position}]"
        if not isinstance(entry, Mapping):
            errors.append(f"{label}: must be an object")
            continue
        target_id = entry.get("target_id")
        if not isinstance(target_id, str) or not target_id.strip():
            errors.append(f"{label}: target_id is required")
        else:
            label = f"target '{target_id}'"
            if target_id in seen:
                errors.append(f"{label}: duplicate target_id")
            seen.add(target_id)
        environment_id = entry.get("environment_id")
        if not isinstance(environment_id, str) or not environment_id.strip():
            errors.append(f"{label}: environment_id is required")
        if entry.get("kind") not in {"network_service", "application"}:
            errors.append(f"{label}: kind must be network_service or application")
        if entry.get("authorization_state") not in AUTHORIZATION_STATES:
            errors.append(f"{label}: authorization_state must be one of {list(AUTHORIZATION_STATES)}")
        if entry.get("lifecycle") not in LIFECYCLE_STATES:
            errors.append(f"{label}: lifecycle must be one of {list(LIFECYCLE_STATES)}")
        if entry.get("health") not in HEALTH_STATES:
            errors.append(f"{label}: health must be one of {list(HEALTH_STATES)}")
        errors.extend(_validate_identity(label, entry.get("identity")))
        errors.extend(_validate_scope(label, entry.get("scope")))
        if entry.get("authorization_state") == "EXTERNAL":
            errors.append(f"{label}: EXTERNAL targets must not be committed to this registry")
    return errors


# --------------------------------------------------------------------------
# orphan checks
# --------------------------------------------------------------------------


def known_environment_ids(environments_dir: Path | str | None = None) -> set[str]:
    """Discover environment ids from the committed environment manifests."""

    directory = Path(environments_dir) if environments_dir is not None else ENVIRONMENTS_DIR
    known: set[str] = set()
    if not directory.is_dir():
        return known
    for path in sorted(directory.rglob("*.yaml")):
        if path.name in IGNORED_ENVIRONMENT_YAML:
            continue
        try:
            data = yaml.safe_load(path.read_text(encoding="utf-8"))
        except yaml.YAMLError:
            continue
        if not isinstance(data, Mapping):
            continue
        env_id = data.get("id")
        if isinstance(env_id, str) and env_id.strip():
            known.add(env_id.strip())
    return known


def orphan_targets(
    document: Mapping[str, Any],
    environments_dir: Path | str | None = None,
) -> list[str]:
    """Return violations for targets pointing at unknown environment ids."""

    known = known_environment_ids(environments_dir)
    violations: list[str] = []
    for entry in targets(document):
        environment_id = entry.get("environment_id")
        target_id = entry.get("target_id", "<unnamed>")
        if not isinstance(environment_id, str) or environment_id not in known:
            violations.append(
                f"target '{target_id}': environment_id '{environment_id}' is not a known environment"
            )
    return violations


# --------------------------------------------------------------------------
# resolver API
# --------------------------------------------------------------------------


def resolve_target(
    target_id: Any,
    document: Mapping[str, Any] | None = None,
) -> dict[str, Any] | None:
    """Resolve a canonical target_id to its registry entry, or ``None``."""

    if not isinstance(target_id, str) or not target_id.strip():
        return None
    registry = document if document is not None else load_registry()
    return index_by_id(registry).get(target_id.strip())


def resolve_execution_eligibility(
    target_id: Any,
    document: Mapping[str, Any] | None = None,
    *,
    operation: str | None = None,
) -> ExecutionDecision:
    """Deterministically decide whether offensive execution is allowed.

    Fails closed for every unknown, missing, malformed or ambiguous input.
    """

    if not isinstance(target_id, str) or not target_id.strip():
        return ExecutionDecision(
            target_id=None,
            eligible=False,
            reason="missing or non-canonical target_id; execution authority requires a target_id",
        )
    canonical = target_id.strip()
    if canonical != target_id or any(ch in canonical for ch in "/:@ "):
        return ExecutionDecision(
            target_id=None,
            eligible=False,
            reason="target_id looks like a URL, address or unnormalized value; "
            "raw network locators are never an execution authority",
        )
    registry = document if document is not None else load_registry()
    entry = index_by_id(registry).get(canonical)
    if entry is None:
        return ExecutionDecision(
            target_id=canonical,
            eligible=False,
            reason="target_id is not present in the canonical registry",
        )

    state = entry.get("authorization_state")
    environment_id = entry.get("environment_id") if isinstance(entry.get("environment_id"), str) else None
    raw_scope = entry.get("scope")
    scope: Mapping[str, Any] = raw_scope if isinstance(raw_scope, Mapping) else {}
    allowed_raw = scope.get("allowed_operations")
    allowed = tuple(op for op in allowed_raw if isinstance(op, str)) if isinstance(allowed_raw, list) else ()

    if not isinstance(state, str) or state not in AUTHORIZATION_STATES:
        return ExecutionDecision(
            target_id=canonical,
            eligible=False,
            reason="authorization_state is missing or not a recognized value",
            environment_id=environment_id,
        )
    if state not in OFFENSIVE_EXECUTION_STATES:
        return ExecutionDecision(
            target_id=canonical,
            eligible=False,
            reason=f"authorization_state '{state}' does not authorize offensive execution",
            authorization_state=state,
            environment_id=environment_id,
            allowed_operations=allowed,
        )
    if entry.get("lifecycle") == "RETIRED":
        return ExecutionDecision(
            target_id=canonical,
            eligible=False,
            reason="target lifecycle is RETIRED",
            authorization_state=state,
            environment_id=environment_id,
            allowed_operations=allowed,
        )
    if not allowed:
        return ExecutionDecision(
            target_id=canonical,
            eligible=False,
            reason="target declares no allowed operations",
            authorization_state=state,
            environment_id=environment_id,
        )
    if operation is not None and operation not in allowed:
        return ExecutionDecision(
            target_id=canonical,
            eligible=False,
            reason=f"operation '{operation}' is outside the declared scope of this target",
            authorization_state=state,
            environment_id=environment_id,
            allowed_operations=allowed,
        )
    return ExecutionDecision(
        target_id=canonical,
        eligible=True,
        reason="authorized laboratory target within declared scope",
        authorization_state=state,
        environment_id=environment_id,
        allowed_operations=allowed,
    )


def eligible_target_ids(document: Mapping[str, Any] | None = None) -> list[str]:
    registry = document if document is not None else load_registry()
    return sorted(
        target_id
        for target_id in index_by_id(registry)
        if resolve_execution_eligibility(target_id, registry).eligible
    )


def targets_for_environment(
    environment_id: str,
    document: Mapping[str, Any] | None = None,
) -> list[dict[str, Any]]:
    registry = document if document is not None else load_registry()
    return [entry for entry in targets(registry) if entry.get("environment_id") == environment_id]


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------


def _print(payload: Any) -> None:
    print(json.dumps(payload, indent=2, sort_keys=True))


def _cmd_validate(args: argparse.Namespace) -> int:
    registry_path = Path(args.registry) if args.registry else REGISTRY_PATH
    try:
        document = yaml.safe_load(registry_path.read_text(encoding="utf-8"))
    except OSError as exc:
        print(f"FAIL target registry unreadable: {exc}", file=sys.stderr)
        return 1
    except yaml.YAMLError as exc:
        print(f"FAIL target registry is not valid YAML: {exc}", file=sys.stderr)
        return 1

    problems: list[str] = list(validate_registry(document))
    if not problems:
        problems.extend(orphan_targets(document, args.environments))
    if problems:
        for problem in problems:
            print(f"FAIL {problem}", file=sys.stderr)
        return 1
    total = len(targets(document))
    eligible = len(eligible_target_ids(document))
    print(f"OK targets={total} offensive_eligible={eligible} orphans=0")
    return 0


def _cmd_list(args: argparse.Namespace) -> int:
    document = load_registry(args.registry)
    rows = []
    for entry in targets(document):
        decision = resolve_execution_eligibility(entry.get("target_id"), document)
        rows.append(
            {
                "target_id": entry.get("target_id"),
                "environment_id": entry.get("environment_id"),
                "authorization_state": entry.get("authorization_state"),
                "lifecycle": entry.get("lifecycle"),
                "health": entry.get("health"),
                "offensive_execution_eligible": decision.eligible,
            }
        )
    _print(rows)
    return 0


def _cmd_resolve(args: argparse.Namespace) -> int:
    document = load_registry(args.registry)
    decision = resolve_execution_eligibility(args.target_id, document, operation=args.operation)
    _print(decision.as_dict())
    return 0 if decision.eligible else 2


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="target_registry.py",
        description="Validate and query the canonical Hermes Security Labs target registry.",
    )
    parser.add_argument("--registry", help="path to an alternative registry file")
    sub = parser.add_subparsers(dest="command", required=True)

    validate = sub.add_parser("validate", help="validate schema, contract and orphan environment ids")
    validate.add_argument("--environments", help="path to an alternative environments directory")
    validate.set_defaults(func=_cmd_validate)

    listing = sub.add_parser("list", help="list registered targets with their resolved eligibility")
    listing.set_defaults(func=_cmd_list)

    resolve = sub.add_parser("resolve", help="resolve offensive execution eligibility for a target_id")
    resolve.add_argument("target_id")
    resolve.add_argument("--operation", help="optional operation to check against the declared scope")
    resolve.set_defaults(func=_cmd_resolve)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(list(argv) if argv is not None else None)
    return int(args.func(args))


__all__ = [
    "AUTHORIZATION_STATES",
    "OFFENSIVE_EXECUTION_STATES",
    "ExecutionDecision",
    "TargetRegistryError",
    "eligible_target_ids",
    "index_by_id",
    "known_environment_ids",
    "load_registry",
    "main",
    "orphan_targets",
    "resolve_execution_eligibility",
    "resolve_target",
    "targets",
    "targets_for_environment",
    "validate_registry",
]


if __name__ == "__main__":  # pragma: no cover - CLI entry point
    raise SystemExit(main())
