"""Fail-closed target authorization port for the semantic execution boundary.

The engine never trusts a free-form locator. Every offensive runbook step is
dispatched only after an injected :class:`TargetAuthorizer` returns an allowing
:class:`TargetAuthorizationDecision` for the pair ``(target_id, operation_id)``.

The default authorizer denies everything, so an integrator that forgets to wire
a real authority cannot accidentally execute against an unauthorized target.
The canonical authority lives in ``platform/targets`` (registry + resolver);
this module is only the deterministic port so the core package keeps no
dependency on the platform tree.
"""

from __future__ import annotations

import ipaddress
from dataclasses import dataclass, field
from typing import Any, Callable, Mapping, Protocol, Sequence

__all__ = [
    "AuthorizationRequired",
    "CallableAuthorizer",
    "DenyAllAuthorizer",
    "TargetAuthorizationDecision",
    "TargetAuthorizer",
    "canonical_target_id",
    "step_operation_id",
]

SAFETY_OPERATION_PREFIXES = ("lab.lifecycle.", "lifecycle.")
SAFETY_OPERATION_SUFFIXES = ("stop", "reset", "destroy", "cleanup")
LOCATOR_CHARACTERS = ("/", ":", "@", " ", "?", "#", "\\")


class AuthorizationRequired(RuntimeError):
    """Raised when a step is not authorized for the resolved target."""

    def __init__(self, decision: "TargetAuthorizationDecision") -> None:
        super().__init__(f"{decision.reason_code}: step denied at the execution boundary")
        self.decision = decision


@dataclass(frozen=True)
class TargetAuthorizationDecision:
    """Audit-friendly decision. Carries identifiers and a reason code only."""

    target_id: str | None
    operation_id: str | None
    allowed: bool
    reason_code: str
    operation_class: str = "OFFENSIVE"
    extra: Mapping[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "target_id": self.target_id,
            "operation_id": self.operation_id,
            "operation_class": self.operation_class,
            "allowed": self.allowed,
            "reason_code": self.reason_code,
        }
        payload.update(dict(self.extra))
        return payload


class TargetAuthorizer(Protocol):
    """Deterministic authority for the offensive execution boundary."""

    def authorize(
        self,
        target_id: Any,
        operation_id: Any,
        *,
        operation_class: str = "OFFENSIVE",
    ) -> TargetAuthorizationDecision: ...


@dataclass(frozen=True)
class DenyAllAuthorizer:
    """Default authority: denies every operation deterministically."""

    reason_code: str = "AUTHORIZER_NOT_CONFIGURED"

    def authorize(
        self,
        target_id: Any,
        operation_id: Any,
        *,
        operation_class: str = "OFFENSIVE",
    ) -> TargetAuthorizationDecision:
        return TargetAuthorizationDecision(
            target_id=target_id if isinstance(target_id, str) else None,
            operation_id=operation_id if isinstance(operation_id, str) else None,
            allowed=False,
            reason_code=self.reason_code,
            operation_class=operation_class,
        )


@dataclass(frozen=True)
class CallableAuthorizer:
    """Adapt a plain callable (e.g. the platform resolver) to the protocol.

    The callable must return an object exposing ``target_id``, ``operation_id``,
    ``allowed`` and ``reason_code`` (the platform ``AuthorizationDecision``
    satisfies this), or a mapping with the same keys.
    """

    resolver: Callable[..., Any]

    def authorize(
        self,
        target_id: Any,
        operation_id: Any,
        *,
        operation_class: str = "OFFENSIVE",
    ) -> TargetAuthorizationDecision:
        raw = self.resolver(target_id, operation_id, operation_class=operation_class)
        if isinstance(raw, TargetAuthorizationDecision):
            return raw
        if isinstance(raw, Mapping):
            source: Mapping[str, Any] = raw
            get = source.get
        else:
            get = lambda key, default=None: getattr(raw, key, default)  # noqa: E731
        allowed = get("allowed", False)
        reason_code = get("reason_code", "AUTHORIZER_RESPONSE_INVALID")
        if allowed is not True or not isinstance(reason_code, str):
            return TargetAuthorizationDecision(
                target_id=target_id if isinstance(target_id, str) else None,
                operation_id=operation_id if isinstance(operation_id, str) else None,
                allowed=False,
                reason_code=reason_code if isinstance(reason_code, str) else "AUTHORIZER_RESPONSE_INVALID",
                operation_class=operation_class,
            )
        return TargetAuthorizationDecision(
            target_id=get("target_id"),
            operation_id=get("operation_id"),
            allowed=True,
            reason_code=reason_code,
            operation_class=str(get("operation_class", operation_class)),
        )


def _is_ip_literal(candidate: str) -> bool:
    try:
        ipaddress.ip_address(candidate)
    except ValueError:
        return False
    return True


def canonical_target_id(target: Any) -> str | None:
    """Extract the canonical ``target_id`` authority, or ``None``.

    A URL, hostname or address is never accepted as an authority.
    """

    if isinstance(target, Mapping):
        candidate = target.get("target_id")
    else:
        candidate = target
    if not isinstance(candidate, str) or not candidate.strip():
        return None
    if candidate.strip() != candidate:
        return None
    if any(character in candidate for character in LOCATOR_CHARACTERS):
        return None
    if _is_ip_literal(candidate):
        return None
    return candidate


def step_operation_id(step: Mapping[str, Any]) -> str | None:
    """Typed operation identity of a runbook step.

    Prefers an explicit ``operation_id``; otherwise falls back to the declared
    typed ``action`` (never to a free-form command).
    """

    for key in ("operation_id", "action", "handler"):
        value = step.get(key)
        if isinstance(value, str) and value.strip() and value.strip() == value:
            return value
    return None


def is_safety_operation(operation_id: Any) -> bool:
    if not isinstance(operation_id, str):
        return False
    candidate = operation_id.strip()
    if not any(candidate.startswith(prefix) for prefix in SAFETY_OPERATION_PREFIXES):
        return False
    return candidate.rsplit(".", 1)[-1] in SAFETY_OPERATION_SUFFIXES


def _constant(value: Any) -> Callable[..., Any]:
    def _resolver(*_args: Any, **_kwargs: Any) -> Any:
        return value

    return _resolver


def authorize_steps(
    steps: Sequence[Mapping[str, Any]],
    target: Any,
    authorizer: TargetAuthorizer | None,
) -> list[TargetAuthorizationDecision]:
    """Authorize every step up front; raise on the first denial.

    No adapter/handler is invoked by this function: it exists so a caller can
    prove the boundary is evaluated *before* dispatch.
    """

    authority = authorizer if authorizer is not None else DenyAllAuthorizer()
    target_id = canonical_target_id(target)
    decisions: list[TargetAuthorizationDecision] = []
    for step in steps:
        operation_id = step_operation_id(step)
        if operation_id is None:
            raise AuthorizationRequired(
                TargetAuthorizationDecision(
                    target_id=target_id,
                    operation_id=None,
                    allowed=False,
                    reason_code="OPERATION_ID_MISSING",
                )
            )
        if target_id is None:
            raise AuthorizationRequired(
                TargetAuthorizationDecision(
                    target_id=None,
                    operation_id=operation_id,
                    allowed=False,
                    reason_code="TARGET_ID_MISSING",
                )
            )
        operation_class = "SAFETY" if is_safety_operation(operation_id) else "OFFENSIVE"
        raw = authority.authorize(
            target_id,
            operation_id,
            operation_class=operation_class,
        )
        decision = (
            raw
            if isinstance(raw, TargetAuthorizationDecision)
            else CallableAuthorizer(_constant(raw)).authorize(
                target_id, operation_id, operation_class=operation_class
            )
        )
        if not decision.allowed:
            raise AuthorizationRequired(decision)
        decisions.append(decision)
    return decisions
