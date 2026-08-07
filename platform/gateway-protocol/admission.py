"""Canonical admission boundary for the typed security gateway.

This module is the **canonical enforcement API**. It never trusts a
caller-supplied Rules of Engagement decision. Instead it *derives* the RoE
decision internally from:

- the signed RoE contract (structure, semantics, Ed25519 / ECDSA-P256-SHA256
  signature verified against a file-backed trust store);
- the RoE step request;
- the external, file-backed kill switch (fail-closed).

The derived decision is then bound deterministically to the typed gateway
request (campaign, step request, operation/capability, target digest,
intrusiveness level and contract payload hash) before the existing typed
operation checks run.

Boundary: contract-level only. Nothing here dispatches, executes, schedules,
connects to a runner, a laboratory, a network or any target. No command,
shell, argv, cwd or environment input is accepted anywhere on this path.

Refusals are fail-closed and carry stable codes only. Targets, operation
parameters and any signature or key material never appear in a decision.
"""

from __future__ import annotations

import importlib.util
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping

import jsonschema

ROOT = Path(__file__).resolve().parent
REPOSITORY_ROOT = ROOT.parents[1]
ROE_DIR = REPOSITORY_ROOT / "platform" / "roe-contract"

CALLER_SUPPLIED_DECISION_FIELDS = ("roe_decision", "roe_decision_ref", "authorized")


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


gateway_protocol = _load_module(
    "gateway_protocol_admission_core", ROOT / "gateway_protocol.py"
)
roe_contract = _load_module("roe_contract_admission", ROE_DIR / "roe_contract.py")

GatewayValidationError = gateway_protocol.GatewayValidationError


class AdmissionError(ValueError):
    """Raised with a stable code when an admission input cannot be trusted."""


@dataclass(frozen=True)
class AdmissionDecision:
    """Deterministic admission outcome.

    Only stable identifiers and stable codes are exposed. Target values,
    operation parameters, signatures and key material are never carried here.
    """

    admitted: bool
    codes: tuple[str, ...]
    request_id: str | None
    campaign_id: str | None
    operation_id: str | None
    operation_version: str | None
    roe_step_request_id: str | None
    roe_decision_source: str

    @classmethod
    def refuse(
        cls,
        codes: Iterable[str],
        request: Mapping[str, Any] | None,
        operation: Mapping[str, Any] | None = None,
    ) -> "AdmissionDecision":
        unique = tuple(dict.fromkeys(codes)) or ("ADMISSION_REFUSED",)
        requested = request.get("operation") if isinstance(request, Mapping) else None
        return cls(
            admitted=False,
            codes=unique,
            request_id=_identifier(request, "request_id"),
            campaign_id=_identifier(request, "campaign_id"),
            operation_id=_identifier(operation or requested, "id"),
            operation_version=_identifier(operation or requested, "version"),
            roe_step_request_id=_identifier(request, "roe_step_request_id"),
            roe_decision_source="DERIVED",
        )

    @classmethod
    def admit(
        cls,
        request: Mapping[str, Any],
        operation: Mapping[str, Any],
    ) -> "AdmissionDecision":
        return cls(
            admitted=True,
            codes=("ADMIT_TYPED_OPERATION",),
            request_id=_identifier(request, "request_id"),
            campaign_id=_identifier(request, "campaign_id"),
            operation_id=str(operation["id"]),
            operation_version=str(operation["version"]),
            roe_step_request_id=_identifier(request, "roe_step_request_id"),
            roe_decision_source="DERIVED",
        )


def validate_admission_request(request: Mapping[str, Any]) -> None:
    """Validate the admission request; reject caller-supplied RoE decisions."""

    if not isinstance(request, Mapping):
        raise AdmissionError("ADMISSION_SCHEMA_INVALID")
    for field in CALLER_SUPPLIED_DECISION_FIELDS:
        if field in request:
            raise AdmissionError("ROE_DECISION_CALLER_SUPPLIED")
    gateway_protocol._reject_forbidden_fields(request)
    schema = gateway_protocol.load_json(ROOT / "admission-request.schema.json")
    validator = jsonschema.Draft202012Validator(
        schema,
        format_checker=jsonschema.FormatChecker(),
    )
    if list(validator.iter_errors(request)):
        raise AdmissionError("ADMISSION_SCHEMA_INVALID")


def authorize_admission(
    request: Mapping[str, Any],
    contract: Mapping[str, Any],
    roe_step_request: Mapping[str, Any],
    *,
    trust_store_path: Path | None = None,
    kill_switch_path: Path | None = None,
    verifier: Any | None = None,
    verifier_now: Any | None = None,
    policy_path: Path | None = None,
    registry_path: Path | None = None,
    runtime_registry_path: Path | None = None,
) -> AdmissionDecision:
    """Canonical admission entry point.

    The RoE decision is derived here; it is never accepted from the caller.
    Any inconsistency, unavailable trust store or kill switch, negative RoE
    decision or integration defect refuses fail-closed.
    """

    try:
        validate_admission_request(request)
    except AdmissionError as exc:
        return AdmissionDecision.refuse((str(exc),), request)
    except GatewayValidationError as exc:
        return AdmissionDecision.refuse((str(exc),), request)

    if kill_switch_path is None:
        return AdmissionDecision.refuse(("KILL_SWITCH_SOURCE_REQUIRED",), request)

    if verifier is None:
        if trust_store_path is None:
            return AdmissionDecision.refuse(
                ("SIGNATURE_VERIFIER_UNAVAILABLE",), request
            )
        verifier = roe_contract.build_trust_store_verifier(
            trust_store_path, now=verifier_now
        )

    try:
        roe_decision = roe_contract.authorize_step(
            contract,
            roe_step_request,
            verifier,
            policy_path=policy_path,
            kill_switch_path=kill_switch_path,
        )
    except Exception:  # noqa: BLE001 - any integration defect is fail-closed
        return AdmissionDecision.refuse(("ROE_INTEGRATION_ERROR",), request)

    if roe_decision.allowed is not True or roe_decision.codes != ("ALLOW",):
        codes = [f"ROE_REFUSED:{code}" for code in roe_decision.codes] or [
            "ROE_REFUSED"
        ]
        return AdmissionDecision.refuse(codes, request)

    try:
        binding_codes = _binding_codes(
            request, contract, roe_step_request, registry_path=registry_path
        )
    except Exception:  # noqa: BLE001 - malformed derived inputs are fail-closed
        return AdmissionDecision.refuse(("ROE_BINDING_INVALID",), request)
    if binding_codes:
        return AdmissionDecision.refuse(binding_codes, request)

    derived = {
        "allowed": True,
        "codes": ["ALLOW"],
        "contract_id": str(contract["contract_id"]),
        "campaign_id": str(roe_step_request["campaign_id"]),
        "step_request_id": str(roe_step_request["request_id"]),
        "authorized_operation_id": str(request["operation"]["id"]),
        "authorized_target_sha256": gateway_protocol.canonical_target_digest(
            request["target"]
        ),
        "contract_payload_sha256": roe_contract.payload_sha256(contract),
        "intrusiveness_ceiling": str(
            contract["authorization"]["intrusiveness_ceiling"]
        ),
    }

    typed_request = {
        key: value
        for key, value in request.items()
        if key not in {"roe_step_request_id", "contract_payload_sha256"}
    }
    typed_request["roe_decision"] = derived

    try:
        typed_decision = gateway_protocol.authorize_typed_operation(
            typed_request,
            registry_path=registry_path,
            runtime_registry_path=runtime_registry_path,
        )
    except Exception:  # noqa: BLE001 - fail-closed on any typed-layer defect
        return AdmissionDecision.refuse(("TYPED_GATEWAY_ERROR",), request)

    if not typed_decision.allowed:
        return AdmissionDecision.refuse(typed_decision.codes, request)

    return AdmissionDecision.admit(
        request,
        {
            "id": typed_decision.operation_id,
            "version": typed_decision.operation_version,
        },
    )


def _binding_codes(
    request: Mapping[str, Any],
    contract: Mapping[str, Any],
    roe_step_request: Mapping[str, Any],
    *,
    registry_path: Path | None = None,
) -> list[str]:
    """Bind the RoE step deterministically to the typed gateway request."""

    codes: list[str] = []

    if request["roe_step_request_id"] != roe_step_request["request_id"]:
        codes.append("ROE_STEP_REQUEST_MISMATCH")
    if request["campaign_id"] != roe_step_request["campaign_id"]:
        codes.append("ROE_CAMPAIGN_MISMATCH")
    if request["campaign_id"] != contract["campaign_id"]:
        codes.append("ROE_CONTRACT_CAMPAIGN_MISMATCH")
    if request["contract_payload_sha256"] != roe_contract.payload_sha256(contract):
        codes.append("ROE_CONTRACT_PAYLOAD_MISMATCH")

    target_digest = gateway_protocol.canonical_target_digest(request["target"])
    step_target_digest = gateway_protocol.canonical_target_digest(
        {
            "type": roe_step_request["target"]["type"],
            "value": roe_step_request["target"]["value"],
        }
    )
    if target_digest != step_target_digest:
        codes.append("ROE_TARGET_MISMATCH")

    operation = gateway_protocol._find_operation(
        gateway_protocol.load_registry(registry_path), str(request["operation"]["id"])
    )
    if operation is None:
        codes.append("OPERATION_UNKNOWN")
        return codes

    if str(roe_step_request["capability"]) not in set(
        operation["required_capabilities"]
    ):
        codes.append("ROE_CAPABILITY_MISMATCH")
    if str(roe_step_request["intrusiveness_level"]) != str(
        operation["intrusiveness_level"]
    ):
        codes.append("ROE_INTRUSIVENESS_MISMATCH")

    return codes


def _identifier(value: Any, key: str) -> str | None:
    if not isinstance(value, Mapping):
        return None
    candidate = value.get(key)
    return candidate if isinstance(candidate, str) else None
