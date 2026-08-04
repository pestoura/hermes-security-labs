"""Typed request/result/evidence contracts for DevSecOps handler execution.

The contracts are deliberately explicit and machine readable. Every adapter
must return an :class:`ExecutionResult`; the runner serialises it to a stable
JSON document.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

SCHEMA_VERSION = 1


class Status(str, Enum):
    """Execution status of a handler invocation."""

    OK = "ok"
    DRY_RUN = "dry-run"
    SKIPPED = "skipped"
    NOT_IMPLEMENTED = "not-implemented"
    ERROR = "error"


class Decision(str, Enum):
    """Security decision derived from collected signals."""

    VULNERABLE = "vulnerable"
    SECURE = "secure"
    INCONCLUSIVE = "inconclusive"
    NOT_APPLICABLE = "not-applicable"


@dataclass(frozen=True)
class Evidence:
    """A single sanitised evidence item.

    ``value`` never carries raw secret material: adapters store counts, rule
    identifiers, status codes and booleans, never the matched challenge value.
    """

    ref: str
    kind: str
    value: Any
    redacted: bool = True

    def to_dict(self) -> dict[str, Any]:
        return {
            "ref": self.ref,
            "kind": self.kind,
            "value": self.value,
            "redacted": self.redacted,
        }


@dataclass(frozen=True)
class ExecutionRequest:
    """Validated handler invocation request."""

    provider: str
    action: str
    profile: str
    target_ref: str
    scope: str
    arguments: dict[str, Any] = field(default_factory=dict)
    control_id: str | None = None
    schema_version: int = SCHEMA_VERSION

    @property
    def handler(self) -> tuple[str, str]:
        return (self.provider, self.action)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "provider": self.provider,
            "action": self.action,
            "profile": self.profile,
            "target_ref": self.target_ref,
            "scope": self.scope,
            "control_id": self.control_id,
            "arguments": dict(self.arguments),
        }

    @classmethod
    def from_payload(cls, payload: Any) -> ExecutionRequest:
        """Build a request from an untrusted JSON payload.

        Raises :class:`ValueError` with an explicit message when the payload
        does not satisfy the contract.
        """

        if not isinstance(payload, dict):
            raise ValueError("payload must be a JSON object")

        version = payload.get("schema_version", SCHEMA_VERSION)
        if version != SCHEMA_VERSION:
            raise ValueError(f"unsupported schema_version {version!r}")

        arguments = payload.get("arguments", {})
        if arguments is None:
            arguments = {}
        if not isinstance(arguments, dict):
            raise ValueError("arguments must be an object")

        def _required_str(key: str, fallback: Any = None) -> str:
            value = payload.get(key, fallback)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"field {key!r} must be a non-empty string")
            return value.strip()

        target_ref = payload.get("target_ref") or arguments.get("target_ref")
        if not isinstance(target_ref, str) or not target_ref.strip():
            raise ValueError("field 'target_ref' must be a non-empty string")

        scope = payload.get("scope") or arguments.get("scope")
        if not isinstance(scope, str) or not scope.strip():
            raise ValueError("field 'scope' must be a non-empty string")

        control_id = payload.get("control_id") or arguments.get("control_id")
        if control_id is not None and not isinstance(control_id, str):
            raise ValueError("field 'control_id' must be a string when present")

        return cls(
            provider=_required_str("provider"),
            action=_required_str("action"),
            profile=_required_str("profile"),
            target_ref=target_ref.strip(),
            scope=scope.strip(),
            arguments=dict(arguments),
            control_id=control_id,
            schema_version=SCHEMA_VERSION,
        )


@dataclass(frozen=True)
class ExecutionResult:
    """Deterministic, machine-readable handler result."""

    status: Status
    decision: Decision
    provider: str
    action: str
    profile: str
    target_ref: str
    scope: str
    reason: str
    control_id: str | None = None
    vulnerable_signals: tuple[str, ...] = ()
    secure_signals: tuple[str, ...] = ()
    inconclusive_signals: tuple[str, ...] = ()
    evidence: tuple[Evidence, ...] = ()
    meta: dict[str, Any] = field(default_factory=dict)
    schema_version: int = SCHEMA_VERSION

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "status": self.status.value,
            "decision": self.decision.value,
            "provider": self.provider,
            "action": self.action,
            "profile": self.profile,
            "target_ref": self.target_ref,
            "scope": self.scope,
            "control_id": self.control_id,
            "reason": self.reason,
            "vulnerable_signals": list(self.vulnerable_signals),
            "secure_signals": list(self.secure_signals),
            "inconclusive_signals": list(self.inconclusive_signals),
            "evidence": [item.to_dict() for item in self.evidence],
            "meta": dict(self.meta),
        }

    @classmethod
    def error(cls, message: str, request: ExecutionRequest | None = None) -> ExecutionResult:
        return cls(
            status=Status.ERROR,
            decision=Decision.INCONCLUSIVE,
            provider=request.provider if request else "unknown",
            action=request.action if request else "unknown",
            profile=request.profile if request else "unknown",
            target_ref=request.target_ref if request else "unknown",
            scope=request.scope if request else "unknown",
            control_id=request.control_id if request else None,
            reason=message,
            inconclusive_signals=("handler.error",),
        )
