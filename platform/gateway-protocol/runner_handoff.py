"""Canonical gateway -> Runner Protocol v2 handoff boundary.

This module is the single canonical path that turns an *admitted* typed gateway
operation into a Runner Protocol v2 ``runner.step.request`` message.

Authorization is never accepted from the caller. The handoff calls
``admission.authorize_admission()`` internally; that API derives the Rules of
Engagement decision from the signed contract, the file-backed trust store and
the external kill switch. A caller cannot supply an ``AdmissionDecision``, a
``roe_decision`` or an ``authorization_ref`` as proof of authorization: those
inputs are refused before anything else happens.

Boundary: message construction only. Nothing here dispatches, connects,
executes, schedules, spawns a process, touches a runner, a laboratory, a
network or a target. A positive result means exactly one thing: a valid
``runner.step.request`` message was *built*. It never means the request was
dispatched, sent, accepted or executed. Refusal is fail-closed and total:
either a fully validated ``runner.step.request`` is returned, or
``runner_request`` is ``None``. There is no partial construction and no
partial effect.

The emitted ``authorization_ref`` is a **reference**, not a bearer token, not a
grant, not a capability and not a signature. It is a deterministic,
content-addressed digest over the sanitized admitted authorization context. It
carries no target value, no parameters and no secret material, and possessing
it grants nothing. A future runtime must resolve it against a trusted
authority / control plane before acting on it; that resolution is
``NOT_IMPLEMENTED`` and ``NOT_RUN`` in this repository.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping

ROOT = Path(__file__).resolve().parent
REPOSITORY_ROOT = ROOT.parents[1]
RUNNER_SDK_SRC = REPOSITORY_ROOT / "platform" / "runner-protocol" / "src"

if str(RUNNER_SDK_SRC) not in sys.path:  # pragma: no cover - import wiring
    sys.path.insert(0, str(RUNNER_SDK_SRC))

from runner_protocol_v2 import (  # noqa: E402
    ProtocolValidationError,
    request_fingerprint,
    validate_semantics,
)


def _load_module(module_name: str, path: Path) -> Any:
    existing = sys.modules.get(module_name)
    if existing is not None:
        return existing
    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:  # pragma: no cover - packaging defect
        raise RuntimeError(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


admission = _load_module("gateway_admission_handoff_core", ROOT / "admission.py")
gateway_protocol = admission.gateway_protocol

AUTHORIZATION_REF_PREFIX = "roe-authz:v1:"
IDEMPOTENCY_KEY_PREFIX = "rp2-step-"
PROTOCOL_VERSION = "2.0.0"
CORRELATION_FIELDS = ("campaign_id", "run_id", "step_id", "attempt_id")

#: Fields a caller may never provide: they would attempt to carry, replace or
#: amplify authorization instead of letting it be derived here.
CALLER_SUPPLIED_AUTHORIZATION_FIELDS = (
    "admission_decision",
    "authorization_ref",
    "authorized",
    "cancellation_policy",
    "idempotency_key",
    "progress_mode",
    "retry_policy",
    "roe_decision",
    "roe_decision_ref",
    "runner_request",
    "timeout_budget",
)


class RunnerHandoffConfigError(ValueError):
    """Raised with a stable code when the service configuration is unusable."""


@dataclass(frozen=True)
class RunnerDispatchPolicy:
    """Typed SERVICE-level dispatch policy carried *inside* the built message.

    These are the timeout, retry, cancellation and progress fields a future
    runner would honour. Holding them here does not dispatch anything: this
    module only writes them into the ``runner.step.request`` it builds.

    They are configured by the operating service, never by request-level data.
    Request data can therefore not widen a budget, add retries or change
    cancellation semantics, and can never amplify authorization.
    """

    soft_timeout_ms: int = 30_000
    hard_timeout_ms: int = 120_000
    max_attempts: int = 2
    retryable_error_codes: tuple[str, ...] = ("TRANSIENT_DEPENDENCY", "RUNNER_UNAVAILABLE")
    cancellation_mode: str = "cooperative"
    grace_period_ms: int = 5_000
    progress_mode: str = "optional"

    def validate(self) -> None:
        """Validate against the canonical Runner Protocol bounds and taxonomy."""

        if not 100 <= int(self.soft_timeout_ms) <= 86_400_000:
            raise RunnerHandoffConfigError("DISPATCH_POLICY_TIMEOUT_OUT_OF_BOUNDS")
        if not 100 <= int(self.hard_timeout_ms) <= 86_400_000:
            raise RunnerHandoffConfigError("DISPATCH_POLICY_TIMEOUT_OUT_OF_BOUNDS")
        if int(self.hard_timeout_ms) <= int(self.soft_timeout_ms):
            raise RunnerHandoffConfigError("DISPATCH_POLICY_TIMEOUT_ORDER_INVALID")
        if not 0 <= int(self.grace_period_ms) <= 300_000:
            raise RunnerHandoffConfigError("DISPATCH_POLICY_GRACE_OUT_OF_BOUNDS")
        if int(self.grace_period_ms) > int(self.hard_timeout_ms):
            raise RunnerHandoffConfigError("DISPATCH_POLICY_GRACE_EXCEEDS_HARD_TIMEOUT")
        if not 1 <= int(self.max_attempts) <= 5:
            raise RunnerHandoffConfigError("DISPATCH_POLICY_ATTEMPTS_OUT_OF_BOUNDS")
        codes = tuple(self.retryable_error_codes)
        if len(codes) != len(set(codes)) or len(codes) > 3:
            raise RunnerHandoffConfigError("DISPATCH_POLICY_RETRY_CODES_INVALID")
        allowed = {"TRANSIENT_DEPENDENCY", "RUNNER_UNAVAILABLE", "TIMEOUT_SOFT"}
        if not set(codes) <= allowed:
            raise RunnerHandoffConfigError("DISPATCH_POLICY_RETRY_CODES_INVALID")
        if self.cancellation_mode not in {"cooperative", "cooperative_then_force"}:
            raise RunnerHandoffConfigError("DISPATCH_POLICY_CANCELLATION_MODE_INVALID")
        if self.progress_mode not in {"optional", "required"}:
            raise RunnerHandoffConfigError("DISPATCH_POLICY_PROGRESS_MODE_INVALID")

    def as_message_fragments(self) -> dict[str, Any]:
        return {
            "timeout_budget": {
                "soft_timeout_ms": int(self.soft_timeout_ms),
                "hard_timeout_ms": int(self.hard_timeout_ms),
            },
            "retry_policy": {
                "max_attempts": int(self.max_attempts),
                "retryable_error_codes": list(self.retryable_error_codes),
            },
            "cancellation_policy": {
                "mode": self.cancellation_mode,
                "grace_period_ms": int(self.grace_period_ms),
            },
            "progress_mode": self.progress_mode,
        }


@dataclass(frozen=True)
class RunnerHandoffConfig:
    """Typed SERVICE configuration for the handoff boundary."""

    trust_store_path: Path | None = None
    kill_switch_path: Path | None = None
    policy_path: Path | None = None
    registry_path: Path | None = None
    runtime_registry_path: Path | None = None
    dispatch_policy: RunnerDispatchPolicy = field(default_factory=RunnerDispatchPolicy)


@dataclass(frozen=True)
class RunnerHandoffResult:
    """Outcome of building a ``runner.step.request``.

    ``request_built`` is the only positive state and it is deliberately
    factual: it means a valid ``runner.step.request`` message was constructed.
    It does **not** mean the request was dispatched, sent, accepted, scheduled
    or executed; nothing in this module performs any of those.

    Confidentiality boundary:

    - the result *metadata* (``codes``, ``admission_codes``, the identifiers,
      ``authorization_ref``, ``idempotency_key``, ``request_fingerprint``) is
      sanitized: it carries no target value, no operation parameters, no
      contract signature and no key material, and is safe to log or persist as
      a decision record;
    - ``runner_request``, when present, is **not** sanitized. It deliberately
      carries the raw target and the operation parameters because a future
      runner must consume them. It is RESTRICTED operational payload: it must
      not be logged, printed or persisted as a decision. It is therefore
      excluded from ``repr()``; use :meth:`sanitized_summary` for anything
      log-shaped.
    """

    request_built: bool
    codes: tuple[str, ...]
    admission_codes: tuple[str, ...]
    request_id: str | None
    campaign_id: str | None
    operation_id: str | None
    operation_version: str | None
    authorization_ref: str | None
    idempotency_key: str | None
    request_fingerprint: str | None
    runner_request: dict[str, Any] | None = field(repr=False, default=None)

    def sanitized_summary(self) -> dict[str, Any]:
        """Return the log-safe projection of this outcome.

        Contains stable codes, stable identifiers and content-addressed
        references only. It never contains the target value, operation
        parameters, contract or signature material, key material, trust-store
        paths or the ``runner_request`` payload. ``runner_request_present`` is
        a boolean presence flag, not the payload.
        """

        return {
            "request_built": bool(self.request_built),
            "codes": list(self.codes),
            "admission_codes": list(self.admission_codes),
            "request_id": self.request_id,
            "campaign_id": self.campaign_id,
            "operation_id": self.operation_id,
            "operation_version": self.operation_version,
            "authorization_ref": self.authorization_ref,
            "idempotency_key": self.idempotency_key,
            "request_fingerprint": self.request_fingerprint,
            "runner_request_present": self.runner_request is not None,
        }

    @classmethod
    def refuse(
        cls,
        codes: Iterable[str],
        request: Mapping[str, Any] | None,
        *,
        admission_codes: Iterable[str] = (),
    ) -> "RunnerHandoffResult":
        unique = tuple(dict.fromkeys(codes)) or ("HANDOFF_REFUSED",)
        operation = request.get("operation") if isinstance(request, Mapping) else None
        return cls(
            request_built=False,
            codes=unique,
            admission_codes=tuple(admission_codes),
            request_id=_identifier(request, "request_id"),
            campaign_id=_identifier(request, "campaign_id"),
            operation_id=_identifier(operation, "id"),
            operation_version=_identifier(operation, "version"),
            authorization_ref=None,
            idempotency_key=None,
            request_fingerprint=None,
            runner_request=None,
        )


def build_authorization_ref(context: Mapping[str, Any]) -> str:
    """Return the deterministic, content-addressed authorization reference.

    The digest covers the sanitized admitted authorization context only. The
    raw target value is never part of it: only its canonical SHA-256 digest is.
    The canonical context binds the campaign, the ``run_id``, the gateway
    request/step, the RoE step request, the contract payload hash, the
    operation id/version, the capability and the intrusiveness level.
    ``attempt_id`` is deliberately excluded so retries of the same logical step
    share the same authorization reference.

    The result is a REFERENCE — it is not a bearer token, not a grant, not a
    capability and not a signature, and it authorizes nothing by itself.
    """

    encoded = json.dumps(
        dict(context), sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")
    return AUTHORIZATION_REF_PREFIX + hashlib.sha256(encoded).hexdigest()


def build_step_request(
    request: Mapping[str, Any],
    contract: Mapping[str, Any],
    roe_step_request: Mapping[str, Any],
    config: RunnerHandoffConfig | None = None,
) -> RunnerHandoffResult:
    """Canonical gateway -> Runner Protocol v2 handoff entry point.

    Admission is derived internally through ``authorize_admission()``. A
    ``runner.step.request`` is produced only when admission is positive and the
    resulting message passes canonical Runner Protocol semantic validation.
    Any refusal or integration defect yields ``runner_request=None``.
    """

    config = config or RunnerHandoffConfig()

    if not isinstance(request, Mapping):
        return RunnerHandoffResult.refuse(("HANDOFF_REQUEST_INVALID",), None)

    for name in CALLER_SUPPLIED_AUTHORIZATION_FIELDS:
        if name in request:
            return RunnerHandoffResult.refuse(
                ("HANDOFF_CALLER_SUPPLIED_AUTHORIZATION",), request
            )

    try:
        config.dispatch_policy.validate()
    except RunnerHandoffConfigError as exc:
        return RunnerHandoffResult.refuse((str(exc),), request)
    except Exception:  # noqa: BLE001 - malformed configuration is fail-closed
        return RunnerHandoffResult.refuse(("DISPATCH_POLICY_INVALID",), request)

    try:
        decision = admission.authorize_admission(
            request,
            contract,
            roe_step_request,
            trust_store_path=config.trust_store_path,
            kill_switch_path=config.kill_switch_path,
            policy_path=config.policy_path,
            registry_path=config.registry_path,
            runtime_registry_path=config.runtime_registry_path,
        )
    except Exception:  # noqa: BLE001 - any integration defect is fail-closed
        return RunnerHandoffResult.refuse(("ADMISSION_INTEGRATION_ERROR",), request)

    if not decision.admitted:
        return RunnerHandoffResult.refuse(
            ("ADMISSION_REFUSED", *decision.codes),
            request,
            admission_codes=decision.codes,
        )

    correlation_codes = _correlation_codes(request)
    if correlation_codes:
        return RunnerHandoffResult.refuse(
            correlation_codes, request, admission_codes=decision.codes
        )

    try:
        message = _assemble_message(request, roe_step_request, decision, config)
    except ProtocolValidationError:
        return RunnerHandoffResult.refuse(
            ("RUNNER_REQUEST_INVALID",), request, admission_codes=decision.codes
        )
    except gateway_protocol.GatewayValidationError:
        return RunnerHandoffResult.refuse(
            ("RUNNER_INPUT_FORBIDDEN_FIELD",), request, admission_codes=decision.codes
        )
    except Exception:  # noqa: BLE001 - fail closed, never emit a partial message
        return RunnerHandoffResult.refuse(
            ("HANDOFF_INTEGRATION_ERROR",), request, admission_codes=decision.codes
        )

    return RunnerHandoffResult(
        request_built=True,
        codes=("HANDOFF_STEP_REQUEST_BUILT",),
        admission_codes=decision.codes,
        request_id=decision.request_id,
        campaign_id=decision.campaign_id,
        operation_id=decision.operation_id,
        operation_version=decision.operation_version,
        authorization_ref=message["authorization_ref"],
        idempotency_key=message["idempotency_key"],
        request_fingerprint=request_fingerprint(message),
        runner_request=message,
    )


def _assemble_message(
    request: Mapping[str, Any],
    roe_step_request: Mapping[str, Any],
    decision: Any,
    config: RunnerHandoffConfig,
) -> dict[str, Any]:
    operation = request["operation"]
    target = request["target"]
    target_digest = gateway_protocol.canonical_target_digest(target)
    capability_id = str(roe_step_request["capability"])
    intrusiveness = str(roe_step_request["intrusiveness_level"])

    authorization_ref = build_authorization_ref(
        {
            "authorization_ref_version": 1,
            "campaign_id": str(request["campaign_id"]),
            "run_id": str(request["run_id"]),
            "gateway_request_id": str(request["request_id"]),
            "gateway_step_id": str(request["step_id"]),
            "roe_step_request_id": str(request["roe_step_request_id"]),
            "contract_payload_sha256": str(request["contract_payload_sha256"]),
            "operation_id": str(operation["id"]),
            "operation_version": str(operation["version"]),
            "capability_id": capability_id,
            "target_sha256": target_digest,
            "intrusiveness_level": intrusiveness,
        }
    )

    operation_input = {
        "operation_id": str(operation["id"]),
        "operation_version": str(operation["version"]),
        "intrusiveness_level": intrusiveness,
        "target": {"type": str(target["type"]), "value": str(target["value"])},
        "parameters": json.loads(json.dumps(operation["parameters"])),
    }
    # Command, shell, argv, cwd and environment inputs can never reach a runner.
    gateway_protocol._reject_forbidden_fields(operation_input)

    fragments = config.dispatch_policy.as_message_fragments()
    idempotency_key = _idempotency_key(
        authorization_ref=authorization_ref,
        correlation={
            "campaign_id": str(request["campaign_id"]),
            "run_id": str(request["run_id"]),
            "step_id": str(request["step_id"]),
        },
        capability_id=capability_id,
        operation_input=operation_input,
        fragments=fragments,
    )

    message = {
        "message_type": "runner.step.request",
        "protocol_version": PROTOCOL_VERSION,
        "correlation": {
            "campaign_id": str(request["campaign_id"]),
            "run_id": str(request["run_id"]),
            "step_id": str(request["step_id"]),
            "attempt_id": str(request["attempt_id"]),
        },
        "emitted_at": datetime.now(timezone.utc)
        .isoformat(timespec="seconds")
        .replace("+00:00", "Z"),
        "authorization_ref": authorization_ref,
        "idempotency_key": idempotency_key,
        "operation": {"capability_id": capability_id, "input": operation_input},
        **fragments,
    }

    validate_semantics(message)
    return message


def _idempotency_key(
    *,
    authorization_ref: str,
    correlation: Mapping[str, str],
    capability_id: str,
    operation_input: Mapping[str, Any],
    fragments: Mapping[str, Any],
) -> str:
    """Derive the idempotency key from the logical effect and authorization.

    ``attempt_id`` and timestamps are deliberately excluded so a retry of the
    same logical effect under a new attempt keeps the same key. A different
    effect under the same authorization context yields a different key.
    """

    canonical = {
        "protocol_major": PROTOCOL_VERSION.split(".", 1)[0],
        "authorization_ref": authorization_ref,
        "campaign_id": correlation["campaign_id"],
        "run_id": correlation["run_id"],
        "step_id": correlation["step_id"],
        "capability_id": capability_id,
        "operation_input": operation_input,
        "timeout_budget": fragments["timeout_budget"],
        "retry_policy": fragments["retry_policy"],
        "cancellation_policy": fragments["cancellation_policy"],
        "progress_mode": fragments["progress_mode"],
    }
    encoded = json.dumps(
        canonical, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")
    return IDEMPOTENCY_KEY_PREFIX + hashlib.sha256(encoded).hexdigest()


def _correlation_codes(request: Mapping[str, Any]) -> list[str]:
    """Refuse non-UUID correlation identifiers instead of inventing UUIDs.

    Runner Protocol v2 requires four UUID correlation identifiers. The existing
    gateway schema still allows non-UUID identifiers; that gap is exposed here
    fail-closed. No substitute UUID is generated and no identifier is silently
    normalized.
    """

    codes: list[str] = []
    for name in CORRELATION_FIELDS:
        value = request.get(name)
        if not isinstance(value, str) or not _is_uuid(value):
            codes.append(f"CORRELATION_NOT_UUID:{name}")
    return codes


def _is_uuid(value: str) -> bool:
    try:
        return str(uuid.UUID(value)) == value.lower()
    except (ValueError, AttributeError, TypeError):
        return False


def _identifier(value: Any, key: str) -> str | None:
    if not isinstance(value, Mapping):
        return None
    candidate = value.get(key)
    return candidate if isinstance(candidate, str) else None
