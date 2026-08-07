from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable, Mapping

import jsonschema
import yaml

ROOT = Path(__file__).resolve().parent
LEVELS = ("L0", "L1", "L2", "L3", "L4")
FORBIDDEN_FIELDS = {
    "api_key",
    "authorization_header",
    "cookie",
    "cookies",
    "docker_socket_path",
    "host_path",
    "password",
    "private_key",
    "secret",
    "token",
}


class LifecycleValidationError(ValueError):
    """Raised when a lifecycle contract or transition cannot be trusted."""


@dataclass(frozen=True)
class TransitionDecision:
    allowed: bool
    codes: tuple[str, ...]
    request_id: str | None
    lab_id: str | None
    from_state: str | None
    to_state: str | None
    resulting_state: str | None

    @classmethod
    def allow(
        cls,
        request: Mapping[str, Any],
        resulting_state: str,
    ) -> "TransitionDecision":
        return cls(
            allowed=True,
            codes=("ALLOW_TRANSITION",),
            request_id=_safe_string(request, "request_id"),
            lab_id=_safe_string(request, "lab_id"),
            from_state=_safe_string(request, "from_state"),
            to_state=_safe_string(request, "to_state"),
            resulting_state=resulting_state,
        )

    @classmethod
    def refuse(
        cls,
        codes: Iterable[str],
        request: Mapping[str, Any] | None,
        resulting_state: str | None = None,
    ) -> "TransitionDecision":
        unique = tuple(dict.fromkeys(codes))
        return cls(
            allowed=False,
            codes=unique or ("TRANSITION_INVALID",),
            request_id=_safe_string(request, "request_id"),
            lab_id=_safe_string(request, "lab_id"),
            from_state=_safe_string(request, "from_state"),
            to_state=_safe_string(request, "to_state"),
            resulting_state=resulting_state,
        )


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def load_policy(path: Path | None = None) -> dict[str, Any]:
    selected = path or ROOT / "lifecycle-policy.yaml"
    data = yaml.safe_load(selected.read_text(encoding="utf-8"))
    if data.get("schema_version") != "1.0.0":
        raise LifecycleValidationError("POLICY_VERSION_UNSUPPORTED")
    if data.get("default_network_profile") != "isolated":
        raise LifecycleValidationError("DEFAULT_EGRESS_NOT_ISOLATED")
    if data["profiles"]["isolated"] != {
        "egress": "deny-all",
        "exceptions_allowed": False,
    }:
        raise LifecycleValidationError("ISOLATED_PROFILE_INVALID")
    return data


def validate_contract(contract: Mapping[str, Any]) -> None:
    _reject_forbidden_fields(contract)
    _validate_against_schema(
        contract,
        ROOT / "lab-lifecycle-contract.schema.json",
        "CONTRACT_SCHEMA_INVALID",
    )
    expires_at = _parse_datetime(str(contract["expires_at"]))
    for exception in contract["network"]["egress_exceptions"]:
        valid_from = _parse_datetime(exception["valid_from"])
        valid_until = _parse_datetime(exception["valid_until"])
        if not valid_from < valid_until <= expires_at:
            raise LifecycleValidationError("EGRESS_EXCEPTION_WINDOW_INVALID")
    if (
        contract["network"]["profile"] == "isolated"
        and contract["network"]["egress_exceptions"]
    ):
        raise LifecycleValidationError("ISOLATED_PROFILE_HAS_EXCEPTION")
    if contract["network"]["profile"] == "restricted":
        seen = [
            item["exception_id"]
            for item in contract["network"]["egress_exceptions"]
        ]
        if len(seen) != len(set(seen)):
            raise LifecycleValidationError("DUPLICATE_EGRESS_EXCEPTION")
    if _level_index(contract["intrusiveness_level"]) >= _level_index("L3"):
        recovery = contract["recovery"]
        if not recovery["snapshot_ref"] or not recovery["rollback_plan_ref"]:
            raise LifecycleValidationError("HIGH_IMPACT_RECOVERY_REQUIRED")


def validate_transition_request(request: Mapping[str, Any]) -> None:
    _reject_forbidden_fields(request)
    _validate_against_schema(
        request,
        ROOT / "lab-transition-request.schema.json",
        "TRANSITION_SCHEMA_INVALID",
    )


def validate_zero_residue_proof(proof: Mapping[str, Any]) -> None:
    _reject_forbidden_fields(proof)
    _validate_against_schema(
        proof,
        ROOT / "zero-residue-proof.schema.json",
        "ZERO_RESIDUE_PROOF_SCHEMA_INVALID",
    )
    expected = residue_verification_digest(proof)
    if proof["verification_sha256"] != expected:
        raise LifecycleValidationError("ZERO_RESIDUE_DIGEST_MISMATCH")


def residue_verification_digest(proof: Mapping[str, Any]) -> str:
    payload = {
        key: value
        for key, value in proof.items()
        if key != "verification_sha256"
    }
    canonical = json.dumps(
        payload,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


def authorize_transition(
    contract: Mapping[str, Any],
    request: Mapping[str, Any],
    *,
    policy_path: Path | None = None,
) -> TransitionDecision:
    try:
        validate_contract(contract)
        validate_transition_request(request)
        policy = load_policy(policy_path)
    except LifecycleValidationError as exc:
        return TransitionDecision.refuse((str(exc),), request)

    codes: list[str] = []
    if request["contract_id"] != contract["contract_id"]:
        codes.append("CONTRACT_MISMATCH")
    if request["lab_id"] != contract["lab_id"]:
        codes.append("LAB_MISMATCH")
    if request["campaign_id"] != contract["campaign_id"]:
        codes.append("CAMPAIGN_MISMATCH")

    requested_at = _parse_datetime(str(request["requested_at"]))
    if requested_at >= _parse_datetime(str(contract["expires_at"])):
        codes.append("CONTRACT_EXPIRED")

    allowed = policy["state_transitions"].get(request["from_state"], [])
    if request["to_state"] not in allowed:
        codes.append("TRANSITION_NOT_ALLOWED")

    if request["to_state"] in {"READY", "RUNNING"}:
        codes.extend(_validate_effective_network(contract, request, requested_at))
        codes.extend(_validate_runtime_observation(request))
    if request["to_state"] == "RUNNING":
        codes.extend(_validate_start_constraints(contract))

    transition = f'{request["from_state"]}->{request["to_state"]}'
    if transition in policy["proof_required_transitions"]:
        proof = request.get("zero_residue_proof")
        if not isinstance(proof, Mapping):
            codes.append("ZERO_RESIDUE_PROOF_REQUIRED")
        else:
            proof_codes, proof_is_zero = _assess_zero_residue_proof(
                proof,
                contract,
            )
            codes.extend(proof_codes)
            if request["to_state"] == "VERIFIED" and not proof_is_zero:
                codes.append("ZERO_RESIDUE_NOT_PROVEN")
            if request["to_state"] == "QUARANTINED" and proof_is_zero:
                codes.append("QUARANTINE_REASON_ABSENT")

    if request["from_state"] == "QUARANTINED":
        codes.append("QUARANTINED_REUSE_BLOCKED")

    if codes:
        resulting = (
            "QUARANTINED"
            if _must_quarantine(codes)
            else str(request["from_state"])
        )
        return TransitionDecision.refuse(codes, request, resulting)
    return TransitionDecision.allow(request, str(request["to_state"]))


def _validate_effective_network(
    contract: Mapping[str, Any],
    request: Mapping[str, Any],
    requested_at: datetime,
) -> list[str]:
    effective = request.get("effective_network")
    if not isinstance(effective, Mapping):
        return ["EFFECTIVE_NETWORK_REQUIRED"]
    codes: list[str] = []
    declared = contract["network"]
    if effective["network_id"] != declared["network_id"]:
        codes.append("NETWORK_ID_MISMATCH")
    if effective["profile"] != declared["profile"]:
        codes.append("NETWORK_PROFILE_MISMATCH")
    if effective["profile"] == "open":
        codes.append("OPEN_EGRESS_FORBIDDEN")

    destinations = set(effective["egress_destinations"])
    if declared["profile"] == "isolated" and destinations:
        codes.append("ISOLATED_EGRESS_PRESENT")
    elif declared["profile"] == "restricted":
        active = {
            item["destination"]
            for item in declared["egress_exceptions"]
            if _parse_datetime(item["valid_from"]) <= requested_at
            < _parse_datetime(item["valid_until"])
        }
        if not destinations <= active:
            codes.append("EGRESS_DESTINATION_UNAUTHORIZED")
    return codes


def _validate_runtime_observation(request: Mapping[str, Any]) -> list[str]:
    state = request["runtime_observation"]["state"]
    if state == "NOT_RUN":
        return ["RUNTIME_OBSERVATION_NOT_RUN"]
    if state != "OBSERVED":
        return ["RUNTIME_OBSERVATION_SYNTHETIC"]
    return []


def _validate_start_constraints(contract: Mapping[str, Any]) -> list[str]:
    isolation = contract["isolation"]
    codes: list[str] = []
    if isolation["privileged"]:
        codes.append("PRIVILEGED_FORBIDDEN")
    if isolation["host_network"]:
        codes.append("HOST_NETWORK_FORBIDDEN")
    if isolation["docker_socket"]:
        codes.append("DOCKER_SOCKET_FORBIDDEN")
    if isolation["host_mounts"]:
        codes.append("HOST_MOUNTS_FORBIDDEN")
    if isolation["shared_network"]:
        codes.append("SHARED_NETWORK_FORBIDDEN")
    return codes


def _assess_zero_residue_proof(
    proof: Mapping[str, Any],
    contract: Mapping[str, Any],
) -> tuple[list[str], bool]:
    try:
        validate_zero_residue_proof(proof)
    except LifecycleValidationError as exc:
        return [str(exc)], False

    codes: list[str] = []
    if proof["lab_id"] != contract["lab_id"]:
        codes.append("PROOF_LAB_MISMATCH")
    if proof["campaign_id"] != contract["campaign_id"]:
        codes.append("PROOF_CAMPAIGN_MISMATCH")
    if proof["scanner_state"] != "COMPLETE":
        codes.append("RESIDUE_SCANNER_INCOMPLETE")
    if not proof["network_absent"]:
        codes.append("LAB_NETWORK_REMAINS")
    resource_lists = list(proof["resources"].values())
    if any(resource_lists) or proof["temporary_paths"]:
        codes.append("RESIDUE_DETECTED")
    proof_is_zero = not codes
    return codes, proof_is_zero


def _must_quarantine(codes: Iterable[str]) -> bool:
    quarantine_codes = {
        "ZERO_RESIDUE_PROOF_REQUIRED",
        "ZERO_RESIDUE_PROOF_SCHEMA_INVALID",
        "ZERO_RESIDUE_DIGEST_MISMATCH",
        "ZERO_RESIDUE_NOT_PROVEN",
        "RESIDUE_SCANNER_INCOMPLETE",
        "LAB_NETWORK_REMAINS",
        "RESIDUE_DETECTED",
        "PROOF_LAB_MISMATCH",
        "PROOF_CAMPAIGN_MISMATCH",
    }
    return any(code in quarantine_codes for code in codes)


def _validate_against_schema(
    value: Mapping[str, Any],
    path: Path,
    error_code: str,
) -> None:
    validator = jsonschema.Draft202012Validator(
        _load_json(path),
        format_checker=jsonschema.FormatChecker(),
    )
    if list(validator.iter_errors(value)):
        raise LifecycleValidationError(error_code)


def _reject_forbidden_fields(
    value: Any,
    path: tuple[str, ...] = (),
) -> None:
    if isinstance(value, Mapping):
        for key, child in value.items():
            normalized = str(key).lower()
            if normalized in FORBIDDEN_FIELDS:
                raise LifecycleValidationError(
                    f"FORBIDDEN_FIELD:{'.'.join((*path, normalized))}"
                )
            _reject_forbidden_fields(child, (*path, normalized))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            _reject_forbidden_fields(child, (*path, str(index)))


def _parse_datetime(value: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise LifecycleValidationError("INVALID_DATETIME") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise LifecycleValidationError("TIMEZONE_REQUIRED")
    return parsed


def _level_index(level: str) -> int:
    return LEVELS.index(level)


def _safe_string(value: Any, key: str) -> str | None:
    if not isinstance(value, Mapping):
        return None
    candidate = value.get(key)
    return candidate if isinstance(candidate, str) else None
