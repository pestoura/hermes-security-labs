"""Fail-closed authorization at the semantic / offensive execution boundary.

Design contract
---------------

* ``target_id`` is the only execution authority. Callers MUST provide a
  canonical ``target_id``; a URL, hostname, IP address or container name is
  never, on its own, an authority to execute anything.
* Before any typed offensive operation (or offensive runbook step) is
  dispatched, the target is resolved through the canonical registry
  (:mod:`platform.targets.target_registry`) and the operation is authorized:

  - ``authorization_state`` must be ``LAB_ONLY`` or ``AUTHORIZED_TEST_TARGET``;
  - ``lifecycle`` must be execution-ready (``PROVISIONED`` or ``ACTIVE``);
  - ``health`` must be compatible (``UNKNOWN`` or ``HEALTHY``);
  - the operation must be inside the target's declared scope.

  ``UNVERIFIED``, ``BLOCKED``, ``EXTERNAL``, missing, ambiguous, retired and
  out-of-scope inputs deny **deterministically, before a handler/tool is
  invoked**.
* Safety operations (cleanup / stop / reset / destroy) that perform no
  offensive interaction remain available for targets whose offensive execution
  is denied. Being ``BLOCKED`` must never prevent safe destruction.
* Generic execution stays forbidden: an operation id that looks like a
  command/exec/shell/terminal escape is denied here as well, independently of
  the typed operation registry (which keeps its own guard).
* The decision object is audit friendly: identifiers, boolean and a stable
  reason code only. Raw URLs / network locators are never emitted as labels.

This module is deterministic and side-effect free. It never touches the
network, never starts a container and never mutates runtime state.
"""

from __future__ import annotations

import argparse
import ipaddress
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence, TypeVar

if __package__ in (None, ""):  # pragma: no cover - direct-file import support
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from target_registry import (  # type: ignore[no-redef]
        OFFENSIVE_EXECUTION_STATES,
        AUTHORIZATION_STATES,
        TargetRegistryError,
        index_by_id,
        load_registry,
    )
else:  # pragma: no cover - package import support
    from .target_registry import (
        OFFENSIVE_EXECUTION_STATES,
        AUTHORIZATION_STATES,
        TargetRegistryError,
        index_by_id,
        load_registry,
    )

__all__ = [
    "AuthorizationDecision",
    "AuthorizationError",
    "OPERATION_CLASSES",
    "REASON_CODES",
    "SAFETY_OPERATION_IDS",
    "authorize_operation",
    "guarded_dispatch",
    "is_safety_operation",
]

T = TypeVar("T")

OPERATION_CLASSES = ("OFFENSIVE", "SAFETY")

#: Lifecycle states in which an offensive interaction may be dispatched.
EXECUTION_READY_LIFECYCLE = frozenset({"PROVISIONED", "ACTIVE"})
#: Health states compatible with offensive interaction. The canonical registry
#: is static and reports ``UNKNOWN`` by design, which stays compatible.
EXECUTION_COMPATIBLE_HEALTH = frozenset({"UNKNOWN", "HEALTHY"})

#: Non-offensive safety operations. These never interact with the target's
#: attack surface; they tear the laboratory down.
SAFETY_OPERATION_IDS = frozenset(
    {
        "lab.lifecycle.stop",
        "lab.lifecycle.reset",
        "lab.lifecycle.destroy",
        "lab.lifecycle.cleanup",
        "lifecycle.stop",
        "lifecycle.reset",
        "lifecycle.destroy",
        "lifecycle.cleanup",
    }
)

#: Tokens that indicate a generic-execution escape hatch.
FORBIDDEN_OPERATION_TOKENS = ("command", "exec", "shell", "terminal")

#: Characters that reveal a raw network locator rather than a canonical id.
LOCATOR_CHARACTERS = ("/", ":", "@", " ", "?", "#", "\\")

REASON_CODES = (
    "ALLOW_OFFENSIVE_OPERATION",
    "ALLOW_SAFETY_OPERATION",
    "TARGET_ID_MISSING",
    "TARGET_ID_NOT_CANONICAL",
    "TARGET_UNKNOWN",
    "TARGET_REGISTRY_AMBIGUOUS",
    "OPERATION_ID_MISSING",
    "OPERATION_CLASS_INVALID",
    "GENERIC_EXECUTION_FORBIDDEN",
    "AUTHORIZATION_STATE_INVALID",
    "AUTHORIZATION_STATE_DENIED",
    "TARGET_LIFECYCLE_RETIRED",
    "TARGET_LIFECYCLE_NOT_READY",
    "TARGET_HEALTH_INCOMPATIBLE",
    "TARGET_SCOPE_EMPTY",
    "OPERATION_OUT_OF_SCOPE",
    "OPERATION_EXPLICITLY_DENIED",
)


class AuthorizationError(RuntimeError):
    """Raised when a denied operation is dispatched through the guard."""

    def __init__(self, decision: "AuthorizationDecision") -> None:
        super().__init__(f"{decision.reason_code}: operation denied")
        self.decision = decision


@dataclass(frozen=True)
class AuthorizationDecision:
    """Audit-friendly, deterministic authorization outcome.

    Only canonical identifiers, enumerated states and a stable ``reason_code``
    are carried. No raw URL, hostname, IP address or free-form target label is
    ever emitted, so the object is safe for evidence and metrics pipelines.
    """

    target_id: str | None
    operation_id: str | None
    allowed: bool
    reason_code: str
    operation_class: str = "OFFENSIVE"
    authorization_state: str | None = None
    lifecycle: str | None = None
    health: str | None = None
    environment_id: str | None = None
    allowed_operations: tuple[str, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        if self.reason_code not in REASON_CODES:
            raise ValueError(f"unknown reason code: {self.reason_code}")
        for value in (self.target_id, self.operation_id, self.environment_id):
            if isinstance(value, str) and ("://" in value or value.startswith("//")):
                raise ValueError("decision fields must not carry network locators")

    def as_dict(self) -> dict[str, Any]:
        return {
            "target_id": self.target_id,
            "operation_id": self.operation_id,
            "operation_class": self.operation_class,
            "allowed": self.allowed,
            "reason_code": self.reason_code,
            "authorization_state": self.authorization_state,
            "lifecycle": self.lifecycle,
            "health": self.health,
            "environment_id": self.environment_id,
            "allowed_operations": list(self.allowed_operations),
        }


def is_safety_operation(operation_id: Any) -> bool:
    """True when the operation is a non-offensive lifecycle safety action."""

    if not isinstance(operation_id, str):
        return False
    return operation_id.strip() in SAFETY_OPERATION_IDS


def _is_generic_execution(operation_id: str) -> bool:
    lowered = operation_id.lower()
    parts = [part for chunk in lowered.split(".") for part in chunk.split("_")]
    return any(token in parts for token in FORBIDDEN_OPERATION_TOKENS)


def _deny(
    reason_code: str,
    *,
    target_id: str | None = None,
    operation_id: str | None = None,
    operation_class: str = "OFFENSIVE",
    **extra: Any,
) -> AuthorizationDecision:
    return AuthorizationDecision(
        target_id=target_id,
        operation_id=operation_id,
        allowed=False,
        reason_code=reason_code,
        operation_class=operation_class,
        **extra,
    )


def _canonical_operation_id(operation_id: Any) -> str | None:
    if not isinstance(operation_id, str) or not operation_id.strip():
        return None
    return operation_id.strip()


def _canonical_target_id(target_id: Any) -> tuple[str | None, str | None]:
    """Return ``(canonical_id, deny_reason)``."""

    if not isinstance(target_id, str) or not target_id.strip():
        return None, "TARGET_ID_MISSING"
    candidate = target_id.strip()
    if candidate != target_id:
        return None, "TARGET_ID_NOT_CANONICAL"
    if any(character in candidate for character in LOCATOR_CHARACTERS):
        return None, "TARGET_ID_NOT_CANONICAL"
    if any(character.isspace() for character in candidate):
        return None, "TARGET_ID_NOT_CANONICAL"
    try:
        ipaddress.ip_address(candidate)
    except ValueError:
        pass
    else:
        return None, "TARGET_ID_NOT_CANONICAL"
    return candidate, None


def authorize_operation(
    target_id: Any,
    operation_id: Any,
    *,
    document: Mapping[str, Any] | None = None,
    operation_class: str = "OFFENSIVE",
) -> AuthorizationDecision:
    """Decide whether ``operation_id`` may be dispatched against ``target_id``.

    Fails closed for every missing, malformed, unknown, ambiguous, retired,
    unauthorized or out-of-scope input. The caller MUST NOT invoke any tool or
    handler when ``allowed`` is ``False``.
    """

    if operation_class not in OPERATION_CLASSES:
        return _deny("OPERATION_CLASS_INVALID", operation_class="OFFENSIVE")

    canonical_operation = _canonical_operation_id(operation_id)
    if canonical_operation is None:
        return _deny("OPERATION_ID_MISSING", operation_class=operation_class)

    safety = is_safety_operation(canonical_operation)
    if operation_class == "SAFETY" and not safety:
        # A caller may not self-declare an arbitrary operation as safety: the
        # allow-list of non-offensive lifecycle operations is the only source.
        return _deny(
            "OPERATION_CLASS_INVALID",
            operation_id=canonical_operation,
            operation_class="OFFENSIVE",
        )
    effective_class = "SAFETY" if safety else "OFFENSIVE"

    if _is_generic_execution(canonical_operation):
        return _deny(
            "GENERIC_EXECUTION_FORBIDDEN",
            operation_id=canonical_operation,
            operation_class=effective_class,
        )

    canonical_target, reason = _canonical_target_id(target_id)
    if canonical_target is None:
        assert reason is not None
        return _deny(
            reason,
            operation_id=canonical_operation,
            operation_class=effective_class,
        )

    registry = document if document is not None else load_registry()
    try:
        entry = index_by_id(registry).get(canonical_target)
    except TargetRegistryError:
        return _deny(
            "TARGET_REGISTRY_AMBIGUOUS",
            target_id=canonical_target,
            operation_id=canonical_operation,
            operation_class=effective_class,
        )
    if entry is None:
        return _deny(
            "TARGET_UNKNOWN",
            target_id=canonical_target,
            operation_id=canonical_operation,
            operation_class=effective_class,
        )

    state = entry.get("authorization_state")
    lifecycle = entry.get("lifecycle") if isinstance(entry.get("lifecycle"), str) else None
    health = entry.get("health") if isinstance(entry.get("health"), str) else None
    environment_id = (
        entry.get("environment_id") if isinstance(entry.get("environment_id"), str) else None
    )
    raw_scope = entry.get("scope")
    scope: Mapping[str, Any] = raw_scope if isinstance(raw_scope, Mapping) else {}
    raw_allowed = scope.get("allowed_operations")
    allowed_operations = (
        tuple(op for op in raw_allowed if isinstance(op, str))
        if isinstance(raw_allowed, list)
        else ()
    )
    raw_denied = scope.get("denied_operations")
    denied_operations = (
        tuple(op for op in raw_denied if isinstance(op, str)) if isinstance(raw_denied, list) else ()
    )
    context: dict[str, Any] = {
        "authorization_state": state if isinstance(state, str) else None,
        "lifecycle": lifecycle,
        "health": health,
        "environment_id": environment_id,
        "allowed_operations": allowed_operations,
    }

    if effective_class == "SAFETY":
        # Cleanup / stop / reset / destroy perform no offensive interaction and
        # stay available for a resolved target regardless of its authorization
        # state, lifecycle or health. Being BLOCKED or UNVERIFIED must never
        # prevent safe destruction of a laboratory target.
        return AuthorizationDecision(
            target_id=canonical_target,
            operation_id=canonical_operation,
            allowed=True,
            reason_code="ALLOW_SAFETY_OPERATION",
            operation_class="SAFETY",
            **context,
        )

    if not isinstance(state, str) or state not in AUTHORIZATION_STATES:
        return _deny(
            "AUTHORIZATION_STATE_INVALID",
            target_id=canonical_target,
            operation_id=canonical_operation,
            operation_class=effective_class,
            **context,
        )
    if state not in OFFENSIVE_EXECUTION_STATES:
        return _deny(
            "AUTHORIZATION_STATE_DENIED",
            target_id=canonical_target,
            operation_id=canonical_operation,
            operation_class=effective_class,
            **context,
        )
    if lifecycle == "RETIRED":
        return _deny(
            "TARGET_LIFECYCLE_RETIRED",
            target_id=canonical_target,
            operation_id=canonical_operation,
            operation_class=effective_class,
            **context,
        )
    if lifecycle not in EXECUTION_READY_LIFECYCLE:
        return _deny(
            "TARGET_LIFECYCLE_NOT_READY",
            target_id=canonical_target,
            operation_id=canonical_operation,
            operation_class=effective_class,
            **context,
        )
    if health not in EXECUTION_COMPATIBLE_HEALTH:
        return _deny(
            "TARGET_HEALTH_INCOMPATIBLE",
            target_id=canonical_target,
            operation_id=canonical_operation,
            operation_class=effective_class,
            **context,
        )
    if not allowed_operations:
        return _deny(
            "TARGET_SCOPE_EMPTY",
            target_id=canonical_target,
            operation_id=canonical_operation,
            operation_class=effective_class,
            **context,
        )
    if canonical_operation in denied_operations:
        return _deny(
            "OPERATION_EXPLICITLY_DENIED",
            target_id=canonical_target,
            operation_id=canonical_operation,
            operation_class=effective_class,
            **context,
        )
    if canonical_operation not in allowed_operations:
        return _deny(
            "OPERATION_OUT_OF_SCOPE",
            target_id=canonical_target,
            operation_id=canonical_operation,
            operation_class=effective_class,
            **context,
        )

    return AuthorizationDecision(
        target_id=canonical_target,
        operation_id=canonical_operation,
        allowed=True,
        reason_code="ALLOW_OFFENSIVE_OPERATION",
        operation_class=effective_class,
        **context,
    )


def guarded_dispatch(
    target_id: Any,
    operation_id: Any,
    handler: Callable[..., T],
    *args: Any,
    document: Mapping[str, Any] | None = None,
    operation_class: str = "OFFENSIVE",
    **kwargs: Any,
) -> tuple[AuthorizationDecision, T]:
    """Authorize first; invoke ``handler`` only on an allowed decision.

    Raises :class:`AuthorizationError` carrying the decision when denied. The
    handler is guaranteed not to be called in that case.
    """

    decision = authorize_operation(
        target_id,
        operation_id,
        document=document,
        operation_class=operation_class,
    )
    if not decision.allowed:
        raise AuthorizationError(decision)
    return decision, handler(*args, **kwargs)


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Fail-closed target authorization for offensive execution."
    )
    sub = parser.add_subparsers(dest="command", required=True)
    authorize = sub.add_parser("authorize", help="authorize an operation against a target_id")
    authorize.add_argument("target_id")
    authorize.add_argument("operation_id")
    authorize.add_argument(
        "--class",
        dest="operation_class",
        choices=list(OPERATION_CLASSES),
        default="OFFENSIVE",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    decision = authorize_operation(
        args.target_id,
        args.operation_id,
        operation_class=args.operation_class,
    )
    print(json.dumps(decision.as_dict(), indent=2, sort_keys=True))
    return 0 if decision.allowed else 2


if __name__ == "__main__":  # pragma: no cover - CLI entry point
    raise SystemExit(main())
