"""Canonical gateway -> Runner Protocol v2 handoff boundary.

This module constructs a Runner Protocol v2 ``runner.step.request`` only after
THREE contract gates have succeeded:

1. the external admission request uses canonical schema ``2.0.0``, where
   campaign/run/step/attempt correlation identifiers are UUIDs;
2. a TB1 authorization receipt issued and signed by the Hermes control plane is
   verified against the dedicated, purpose-bound authorization trust store;
3. ``authorize_admission()`` independently revalidates the signed Rules of
   Engagement contract, kill switch, typed operation and runtime bindings.

Legacy admission schema ``1.0.0`` remains available to ``authorize_admission``
for compatibility but is not accepted at this Runner boundary. A legacy caller
must explicitly promote its request through
``admission.promote_legacy_request_to_v2``; that helper succeeds only when the
existing identifiers are already UUIDs and never generates or normalizes IDs.

The execution plane never creates, expands or approves authorization. The
``authorization_ref`` placed in the Runner Protocol message is copied from the
verified Hermes receipt. A naked reference, caller-supplied ALLOW or embedded
receipt is never accepted as proof of authorization.

Boundary: message construction only. Nothing here dispatches, connects,
executes, schedules, spawns a process, touches a runner, a laboratory, a
network or a target. A positive result means exactly one thing: a valid
``runner.step.request`` message was built. It never means the request was
dispatched, sent, accepted or executed.
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
AUTHORIZATION_DIR = REPOSITORY_ROOT / "platform" / "authorization-contract"

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
authorization_contract = _load_module(
    "tb1_authorization_receipt_handoff",
    AUTHORIZATION_DIR / "authorization_receipt.py",
)

IDEMPOTENCY_KEY_PREFIX = "rp2-step-"
PROTOCOL_VERSION = "2.0.0"
CORRELATION_FIELDS = ("campaign_id", "run_id", "step_id", "attempt_id")

CALLER_SUPPLIED_AUTHORIZATION_FIELDS = (
    "admission_decision",
    "authorization_receipt",
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
    """Raised with a stable code when service configuration is unusable."""


@dataclass(frozen=True)
class RunnerDispatchPolicy:
    """Typed SERVICE-level policy carried inside the built runner message."""

    soft_timeout_ms: int = 30_000
    hard_timeout_ms: int = 120_000
    max_attempts: int = 2
    retryable_error_codes: tuple[str, ...] = (
        "TRANSIENT_DEPENDENCY",
        "RUNNER_UNAVAILABLE",
    )
    cancellation_mode: str = "cooperative"
    grace_period_ms: int = 5_000
    progress_mode: str = "optional"

    def validate(self) -> None:
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
            raise RunnerHandoffConfigError(
                "DISPATCH_POLICY_CANCELLATION_MODE_INVALID"
            )
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
    """Typed SERVICE configuration for the TB1-to-runner handoff boundary."""

    trust_store_path: Path | None = None
    authorization_trust_store_path: Path | None = None
    kill_switch_path: Path | None = None
    policy_path: Path | None = None
    registry_path: Path | None = None
    runtime_registry_path: Path | None = None
    dispatch_policy: RunnerDispatchPolicy = field(default_factory=RunnerDispatchPolicy)


@dataclass(frozen=True)
class RunnerHandoffResult:
    """Outcome of building a ``runner.step.request``.

    ``request_built`` means construction only. Metadata is sanitized and
    log-safe. ``runner_request`` is RESTRICTED operational payload containing
    the raw target and validated parameters required by a future runner; it is
    excluded from ``repr`` and must not be logged as a decision record.
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


def build_step_request(
    request: Mapping[str, Any],
    contract: Mapping[str, Any],
    roe_step_request: Mapping[str, Any],
    config: RunnerHandoffConfig | None = None,
    *,
    authorization_receipt: Mapping[str, Any] | None = None,
) -> RunnerHandoffResult:
    """Canonical TB1 authorization -> gateway admission -> runner handoff."""

    config = config or RunnerHandoffConfig()

    if not isinstance(request, Mapping):
        return RunnerHandoffResult.refuse(("HANDOFF_REQUEST_INVALID",), None)

    for name in CALLER_SUPPLIED_AUTHORIZATION_FIELDS:
        if name in request:
            return RunnerHandoffResult.refuse(
                ("HANDOFF_CALLER_SUPPLIED_AUTHORIZATION",), request
            )

    if request.get("schema_version") != admission.CANONICAL_ADMISSION_SCHEMA_VERSION:
        return RunnerHandoffResult.refuse(
            ("HANDOFF_CANONICAL_SCHEMA_REQUIRED",), request
        )

    try:
        config.dispatch_policy.validate()
    except RunnerHandoffConfigError as exc:
        return RunnerHandoffResult.refuse((str(exc),), request)
    except Exception:  # noqa: BLE001 - malformed configuration is fail-closed
        return RunnerHandoffResult.refuse(("DISPATCH_POLICY_INVALID",), request)

    if authorization_receipt is None:
        return RunnerHandoffResult.refuse(("AUTH_RECEIPT_REQUIRED",), request)

    try:
        verified = authorization_contract.verify_authorization_receipt(
            authorization_receipt, config.authorization_trust_store_path
        )
    except authorization_contract.AuthorizationReceiptError as exc:
        return RunnerHandoffResult.refuse((str(exc),), request)
    except Exception:  # noqa: BLE001 - receipt integration defects fail closed
        return RunnerHandoffResult.refuse(("AUTH_RECEIPT_INTEGRATION_ERROR",), request)

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

    try:
        binding_codes = _authorization_binding_codes(
            verified, request, contract, roe_step_request
        )
    except Exception:  # noqa: BLE001 - malformed context is fail-closed
        return RunnerHandoffResult.refuse(
            ("AUTH_BINDING_INVALID",), request, admission_codes=decision.codes
        )
    if binding_codes:
        return RunnerHandoffResult.refuse(
            binding_codes, request, admission_codes=decision.codes
        )

    correlation_codes = _correlation_codes(request)
    if correlation_codes:
        return RunnerHandoffResult.refuse(
            correlation_codes, request, admission_codes=decision.codes
        )

    try:
        message = _assemble_message(
            request, roe_step_request, decision, verified, config
        )
    except ProtocolValidationError:
        return RunnerHandoffResult.refuse(
            ("RUNNER_REQUEST_INVALID",), request, admission_codes=decision.codes
        )
    except gateway_protocol.GatewayValidationError:
        return RunnerHandoffResult.refuse(
            ("RUNNER_INPUT_FORBIDDEN_FIELD",),
            request,
            admission_codes=decision.codes,
        )
    except Exception:  # noqa: BLE001 - never emit a partial message
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
        authorization_ref=verified.authorization_ref,
        idempotency_key=message["idempotency_key"],
        request_fingerprint=request_fingerprint(message),
        runner_request=message,
    )


def _authorization_binding_codes(
    verified: Any,
    request: Mapping[str, Any],
    contract: Mapping[str, Any],
    roe_step_request: Mapping[str, Any],
) -> list[str]:
    """Require the Hermes receipt to match the freshly admitted exact effect."""

    parameters_digest = authorization_contract.canonical_parameters_sha256(
        request["operation"]["parameters"]
    )
    checks = (
        (verified.campaign_id, str(request["campaign_id"]), "AUTH_CAMPAIGN_MISMATCH"),
        (verified.run_id, str(request["run_id"]), "AUTH_RUN_MISMATCH"),
        (verified.step_id, str(request["step_id"]), "AUTH_STEP_MISMATCH"),
        (
            verified.roe_contract_id,
            str(contract["contract_id"]),
            "AUTH_ROE_CONTRACT_MISMATCH",
        ),
        (
            verified.roe_contract_payload_sha256,
            str(request["contract_payload_sha256"]),
            "AUTH_ROE_PAYLOAD_MISMATCH",
        ),
        (
            verified.roe_step_request_id,
            str(roe_step_request["request_id"]),
            "AUTH_ROE_STEP_REQUEST_MISMATCH",
        ),
        (
            verified.operation_id,
            str(request["operation"]["id"]),
            "AUTH_OPERATION_MISMATCH",
        ),
        (
            verified.operation_version,
            str(request["operation"]["version"]),
            "AUTH_OPERATION_VERSION_MISMATCH",
        ),
        (
            verified.operation_parameters_sha256,
            parameters_digest,
            "AUTH_OPERATION_PARAMETERS_MISMATCH",
        ),
        (
            verified.capability_id,
            str(roe_step_request["capability"]),
            "AUTH_CAPABILITY_MISMATCH",
        ),
        (
            verified.intrusiveness_level,
            str(roe_step_request["intrusiveness_level"]),
            "AUTH_INTRUSIVENESS_MISMATCH",
        ),
    )
    codes = [code for actual, expected, code in checks if actual != expected]

    target_digest = gateway_protocol.canonical_target_digest(request["target"])
    if verified.target_sha256 != target_digest:
        codes.append("AUTH_TARGET_MISMATCH")
    return codes


def _assemble_message(
    request: Mapping[str, Any],
    roe_step_request: Mapping[str, Any],
    decision: Any,
    verified: Any,
    config: RunnerHandoffConfig,
) -> dict[str, Any]:
    del decision
    operation = request["operation"]
    target = request["target"]
    capability_id = str(roe_step_request["capability"])
    intrusiveness = str(roe_step_request["intrusiveness_level"])

    operation_input = {
        "operation_id": str(operation["id"]),
        "operation_version": str(operation["version"]),
        "intrusiveness_level": intrusiveness,
        "target": {"type": str(target["type"]), "value": str(target["value"])},
        "parameters": json.loads(json.dumps(operation["parameters"])),
    }
    gateway_protocol._reject_forbidden_fields(operation_input)

    fragments = config.dispatch_policy.as_message_fragments()
    idempotency_key = _idempotency_key(
        authorization_ref=verified.authorization_ref,
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
        "authorization_ref": verified.authorization_ref,
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
    """Defense-in-depth: Runner correlation remains UUID even after v2 validation."""

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
