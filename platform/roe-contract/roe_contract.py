from __future__ import annotations

import hashlib
import importlib.util
import ipaddress
import json
import re
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping
from urllib.parse import urlsplit

import jsonschema
import yaml

ROOT = Path(__file__).resolve().parent
LEVELS = ("L0", "L1", "L2", "L3", "L4")
_STABLE_CODE = re.compile(r"[A-Z][A-Z0-9_]{2,63}(:[A-Za-z0-9._-]{1,64})?")


def _load_sibling(module_name: str) -> Any:
    """Load a sibling module by path.

    This directory is not an importable package (it contains a hyphen), so
    sibling modules are loaded explicitly instead of via ``import``.
    """

    existing = sys.modules.get(f"roe_contract_{module_name}")
    if existing is not None:
        return existing
    spec = importlib.util.spec_from_file_location(
        f"roe_contract_{module_name}", ROOT / f"{module_name}.py"
    )
    if spec is None or spec.loader is None:  # pragma: no cover - packaging defect
        raise RuntimeError(f"cannot load {module_name}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[f"roe_contract_{module_name}"] = module
    spec.loader.exec_module(module)
    return module


_kill_switch = _load_sibling("kill_switch")
evaluate_kill_switch = _kill_switch.evaluate_kill_switch
KillSwitchError = _kill_switch.KillSwitchError

_trust_store = _load_sibling("trust_store")
TrustStoreError = _trust_store.TrustStoreError
TrustStoreVerifier = _trust_store.TrustStoreVerifier
build_trust_store_verifier = _trust_store.build_verifier


FORBIDDEN_FIELD_NAMES = {
    "api_key",
    "authorization_header",
    "cookie",
    "cookies",
    "password",
    "private_key",
    "secret",
    "token",
}


class RoEValidationError(ValueError):
    """Raised when a Rules of Engagement artefact cannot be trusted."""


@dataclass(frozen=True)
class AuthorizationDecision:
    allowed: bool
    codes: tuple[str, ...]
    contract_id: str | None
    campaign_id: str | None
    request_id: str | None

    @classmethod
    def allow(cls, contract: Mapping[str, Any], request: Mapping[str, Any]) -> "AuthorizationDecision":
        return cls(
            allowed=True,
            codes=("ALLOW",),
            contract_id=str(contract["contract_id"]),
            campaign_id=str(request["campaign_id"]),
            request_id=str(request["request_id"]),
        )

    @classmethod
    def refuse(
        cls,
        codes: Iterable[str],
        contract: Mapping[str, Any] | None,
        request: Mapping[str, Any] | None,
    ) -> "AuthorizationDecision":
        unique = tuple(dict.fromkeys(codes))
        return cls(
            allowed=False,
            codes=unique or ("CONTRACT_INVALID",),
            contract_id=_safe_identifier(contract, "contract_id"),
            campaign_id=_safe_identifier(request, "campaign_id"),
            request_id=_safe_identifier(request, "request_id"),
        )


SignatureVerifier = Callable[[bytes, Mapping[str, Any]], bool]


def load_schema(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def load_policy(path: Path | None = None) -> dict[str, Any]:
    selected = path or ROOT / "intrusiveness-policy.yaml"
    data = yaml.safe_load(selected.read_text(encoding="utf-8"))
    if data.get("version") != "1.0.0":
        raise RoEValidationError("UNSUPPORTED_INTRUSIVENESS_POLICY")
    if tuple(data.get("levels", {})) != LEVELS:
        raise RoEValidationError("INVALID_INTRUSIVENESS_POLICY")
    return data


def canonical_payload(contract: Mapping[str, Any]) -> bytes:
    payload = {key: value for key, value in contract.items() if key != "signature"}
    return json.dumps(
        payload,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


def payload_sha256(contract: Mapping[str, Any]) -> str:
    return hashlib.sha256(canonical_payload(contract)).hexdigest()


def validate_contract_structure(contract: Mapping[str, Any]) -> None:
    _reject_forbidden_fields(contract)
    schema = load_schema(ROOT / "roe-contract.schema.json")
    validator = jsonschema.Draft202012Validator(
        schema,
        format_checker=jsonschema.FormatChecker(),
    )
    errors = sorted(validator.iter_errors(contract), key=lambda item: list(item.path))
    if errors:
        raise RoEValidationError("CONTRACT_SCHEMA_INVALID")
    _validate_contract_semantics(contract)


def validate_request_structure(request: Mapping[str, Any]) -> None:
    _reject_forbidden_fields(request)
    schema = load_schema(ROOT / "roe-step-request.schema.json")
    validator = jsonschema.Draft202012Validator(
        schema,
        format_checker=jsonschema.FormatChecker(),
    )
    errors = sorted(validator.iter_errors(request), key=lambda item: list(item.path))
    if errors:
        raise RoEValidationError("REQUEST_SCHEMA_INVALID")


def validate_contract_for_execution(
    contract: Mapping[str, Any],
    verifier: SignatureVerifier | None,
) -> None:
    validate_contract_structure(contract)
    signature = contract.get("signature")
    if not isinstance(signature, Mapping):
        raise RoEValidationError("SIGNATURE_REQUIRED")
    if signature["payload_sha256"] != payload_sha256(contract):
        raise RoEValidationError("SIGNATURE_PAYLOAD_MISMATCH")
    if verifier is None:
        raise RoEValidationError("SIGNATURE_VERIFIER_UNAVAILABLE")
    try:
        verified = verifier(canonical_payload(contract), signature)
    except RoEValidationError:
        raise
    except Exception as exc:  # noqa: BLE001
        raise RoEValidationError(_verifier_failure_code(exc)) from exc
    if verified is not True:
        raise RoEValidationError("SIGNATURE_INVALID")


def _verifier_failure_code(exc: Exception) -> str:
    """Map a verifier exception to a stable, deterministic refusal code.

    Trust-store failures carry their own precise code (unknown key, revoked,
    expired, algorithm mismatch, unavailable store, ...). Anything else is
    collapsed into the generic failure code, and no exception text from an
    arbitrary verifier is ever propagated into a decision.
    """

    code = getattr(exc, "decision_code", None)
    if isinstance(code, str) and _STABLE_CODE.fullmatch(code):
        return code
    return "SIGNATURE_VERIFICATION_FAILED"



def authorize_step(
    contract: Mapping[str, Any],
    request: Mapping[str, Any],
    verifier: SignatureVerifier | None,
    *,
    policy_path: Path | None = None,
    kill_switch_path: Path | None = None,
) -> AuthorizationDecision:
    """Produce a deterministic allow/refuse decision for a proposed step.

    ``kill_switch_path`` is optional. When omitted the historical behaviour is
    preserved and only the in-request ``kill_switch`` flag applies. When
    supplied, the external file-backed switch is consulted as well and any
    defect in that source refuses the step (fail-closed).
    """

    external_kill_switch_codes: list[str] = []
    if kill_switch_path is not None:
        external_kill_switch_codes = evaluate_kill_switch(
            kill_switch_path, _safe_identifier(request, "campaign_id")
        )

    try:
        validate_contract_for_execution(contract, verifier)
        validate_request_structure(request)
        policy = load_policy(policy_path)
    except RoEValidationError as exc:
        return AuthorizationDecision.refuse(
            (*external_kill_switch_codes, str(exc)), contract, request
        )

    codes: list[str] = list(external_kill_switch_codes)

    requested_at = _parse_datetime(str(request["requested_at"]))
    valid_from = _parse_datetime(str(contract["valid_from"]))
    valid_until = _parse_datetime(str(contract["valid_until"]))

    state = str(contract["state"])
    if state != "active":
        codes.append(
            {
                "draft": "CONTRACT_NOT_ACTIVE",
                "expired": "CONTRACT_EXPIRED",
                "revoked": "CONTRACT_REVOKED",
            }.get(state, "CONTRACT_NOT_ACTIVE")
        )
    if requested_at < valid_from:
        codes.append("CONTRACT_NOT_YET_VALID")
    if requested_at >= valid_until:
        codes.append("CONTRACT_EXPIRED")
    if request["campaign_id"] != contract["campaign_id"]:
        codes.append("CAMPAIGN_MISMATCH")

    if request["kill_switch"]:
        codes.append("KILL_SWITCH_ACTIVE")
    if request["campaign_state"] != policy["active_campaign_state"]:
        codes.append("CAMPAIGN_NOT_RUNNING")

    authorization = contract["authorization"]
    configured_stop_ids = {
        item["condition_id"] for item in authorization["stop_conditions"]
    }
    active_stop_ids = set(request["active_stop_conditions"])
    if active_stop_ids:
        if not active_stop_ids <= configured_stop_ids:
            codes.append("UNKNOWN_STOP_CONDITION")
        codes.append("STOP_CONDITION_ACTIVE")

    target = request["target"]
    if any(_target_matches(rule, target) for rule in authorization["excluded_targets"]):
        codes.append("TARGET_EXCLUDED")
    elif not any(_target_matches(rule, target) for rule in authorization["allowed_targets"]):
        codes.append("TARGET_OUT_OF_SCOPE")

    capability = str(request["capability"])
    if _capability_matches_any(capability, authorization["prohibited_capabilities"]):
        codes.append("CAPABILITY_PROHIBITED")
    elif not _capability_matches_any(capability, authorization["allowed_capabilities"]):
        codes.append("CAPABILITY_NOT_ALLOWED")

    level = str(request["intrusiveness_level"])
    ceiling = str(authorization["intrusiveness_ceiling"])
    if _level_index(level) > _level_index(ceiling):
        codes.append("INTRUSIVENESS_EXCEEDED")

    if not any(
        _parse_datetime(window["start"]) <= requested_at < _parse_datetime(window["end"])
        for window in authorization["execution_windows"]
    ):
        codes.append("OUTSIDE_EXECUTION_WINDOW")

    approval_codes = _validate_step_approvals(
        authorization["approvers"],
        request["approval_ids"],
        level,
        requested_at,
        policy,
    )
    codes.extend(approval_codes)

    if policy["levels"][level]["rollback_plan_required"] and not request.get(
        "rollback_plan_ref"
    ):
        codes.append("ROLLBACK_PLAN_REQUIRED")

    codes.extend(_validate_high_risk_controls(authorization, request))
    codes.extend(_validate_limits(authorization["limits"], request["estimated_limits"]))

    if codes:
        return AuthorizationDecision.refuse(codes, contract, request)
    return AuthorizationDecision.allow(contract, request)


def _validate_contract_semantics(contract: Mapping[str, Any]) -> None:
    issued = _parse_datetime(str(contract["issued_at"]))
    valid_from = _parse_datetime(str(contract["valid_from"]))
    valid_until = _parse_datetime(str(contract["valid_until"]))
    if not issued <= valid_from < valid_until:
        raise RoEValidationError("CONTRACT_WINDOW_INVALID")

    authorization = contract["authorization"]
    for window in authorization["execution_windows"]:
        start = _parse_datetime(window["start"])
        end = _parse_datetime(window["end"])
        if not valid_from <= start < end <= valid_until:
            raise RoEValidationError("EXECUTION_WINDOW_INVALID")

    approval_ids = [item["approval_id"] for item in authorization["approvers"]]
    if len(approval_ids) != len(set(approval_ids)):
        raise RoEValidationError("DUPLICATE_APPROVAL_ID")
    subject_ids = [item["subject_id"] for item in authorization["approvers"]]
    if len(subject_ids) != len(set(subject_ids)):
        raise RoEValidationError("DUPLICATE_APPROVER_SUBJECT")

    stop_ids = [item["condition_id"] for item in authorization["stop_conditions"]]
    if len(stop_ids) != len(set(stop_ids)):
        raise RoEValidationError("DUPLICATE_STOP_CONDITION")

    for item in authorization["allowed_targets"] + authorization["excluded_targets"]:
        _validate_target_rule(item)

    allowed = set(authorization["allowed_capabilities"])
    prohibited = set(authorization["prohibited_capabilities"])
    if allowed & prohibited:
        raise RoEValidationError("CAPABILITY_POLICY_CONFLICT")


def _validate_target_rule(rule: Mapping[str, Any]) -> None:
    target_type = rule["type"]
    value = str(rule["value"])
    match = rule["match"]

    try:
        if target_type == "domain":
            _normalize_domain(value)
            if match not in {"exact", "subdomains"}:
                raise RoEValidationError("TARGET_MATCH_INVALID")
        elif target_type == "ip":
            ipaddress.ip_address(value)
            if match != "exact":
                raise RoEValidationError("TARGET_MATCH_INVALID")
        elif target_type == "cidr":
            ipaddress.ip_network(value, strict=True)
            if match != "contained":
                raise RoEValidationError("TARGET_MATCH_INVALID")
        elif target_type == "uri-prefix":
            parsed = urlsplit(value)
            if (
                parsed.scheme not in {"http", "https"}
                or not parsed.hostname
                or parsed.username
                or parsed.password
                or parsed.query
                or parsed.fragment
                or match != "contained"
            ):
                raise RoEValidationError("TARGET_MATCH_INVALID")
        elif target_type == "lab-asset" and match != "exact":
            raise RoEValidationError("TARGET_MATCH_INVALID")
    except RoEValidationError:
        raise
    except (TypeError, ValueError) as exc:
        raise RoEValidationError("TARGET_RULE_INVALID") from exc


def _target_matches(rule: Mapping[str, Any], target: Mapping[str, Any]) -> bool:
    rule_type = str(rule["type"])
    target_type = str(target["type"])
    rule_value = str(rule["value"])
    target_value = str(target["value"])
    match = str(rule["match"])

    try:
        if rule_type == "domain" and target_type == "domain":
            expected = _normalize_domain(rule_value)
            actual = _normalize_domain(target_value)
            return actual == expected or (
                match == "subdomains" and actual.endswith(f".{expected}")
            )
        if rule_type == "ip" and target_type == "ip":
            return ipaddress.ip_address(target_value) == ipaddress.ip_address(rule_value)
        if rule_type == "cidr":
            network = ipaddress.ip_network(rule_value, strict=True)
            if target_type == "ip":
                return ipaddress.ip_address(target_value) in network
            if target_type == "cidr":
                return ipaddress.ip_network(target_value, strict=True).subnet_of(network)
            return False
        if rule_type == "uri-prefix" and target_type == "uri-prefix":
            return _uri_prefix_matches(rule_value, target_value)
        if rule_type == "lab-asset" and target_type == "lab-asset":
            return target_value == rule_value
    except ValueError:
        return False
    return False


def _uri_prefix_matches(prefix: str, candidate: str) -> bool:
    expected = urlsplit(prefix)
    actual = urlsplit(candidate)
    if (
        actual.scheme not in {"http", "https"}
        or not actual.hostname
        or actual.username
        or actual.password
        or actual.fragment
    ):
        return False
    expected_port = expected.port or (443 if expected.scheme == "https" else 80)
    actual_port = actual.port or (443 if actual.scheme == "https" else 80)
    if (
        expected.scheme,
        expected.hostname.lower(),
        expected_port,
    ) != (
        actual.scheme,
        actual.hostname.lower(),
        actual_port,
    ):
        return False
    expected_path = expected.path.rstrip("/") or "/"
    actual_path = actual.path.rstrip("/") or "/"
    return actual_path == expected_path or actual_path.startswith(f"{expected_path}/")


def _capability_matches_any(capability: str, patterns: Iterable[str]) -> bool:
    for pattern in patterns:
        if pattern.endswith(".*"):
            prefix = pattern[:-2]
            if capability == prefix or capability.startswith(f"{prefix}."):
                return True
        elif capability == pattern:
            return True
    return False


def _validate_step_approvals(
    approvers: list[Mapping[str, Any]],
    requested_ids: list[str],
    level: str,
    requested_at: datetime,
    policy: Mapping[str, Any],
) -> list[str]:
    level_policy = policy["levels"][level]
    required = int(level_policy["minimum_step_approvals"])
    sides_required = int(level_policy["distinct_approval_sides"])
    selected = [
        item
        for item in approvers
        if item["approval_id"] in requested_ids
        and level in item["levels"]
        and _parse_datetime(item["approved_at"]) <= requested_at
        < _parse_datetime(item["valid_until"])
    ]
    codes: list[str] = []
    if len(selected) < required:
        codes.append("APPROVAL_REQUIRED")
    if len({item["side"] for item in selected}) < sides_required:
        codes.append("APPROVAL_SEPARATION_REQUIRED")
    return codes


def _validate_high_risk_controls(
    authorization: Mapping[str, Any],
    request: Mapping[str, Any],
) -> list[str]:
    codes: list[str] = []
    requested_level = str(request["intrusiveness_level"])
    policies = authorization["high_risk_actions"]
    for control in request["requested_controls"]:
        policy = policies[control]
        if policy["status"] != "allowed":
            codes.append(f"HIGH_RISK_ACTION_DENIED:{control}")
        elif _level_index(requested_level) < _level_index(policy["minimum_level"]):
            codes.append(f"HIGH_RISK_LEVEL_TOO_LOW:{control}")
    return codes


def _validate_limits(
    allowed: Mapping[str, Any],
    estimated: Mapping[str, Any],
) -> list[str]:
    codes: list[str] = []
    comparisons = (
        ("requests_per_second", "requests_per_second"),
        ("max_concurrency", "concurrency"),
        ("max_data_bytes", "data_bytes"),
        ("max_duration_seconds", "duration_seconds"),
    )
    for allowed_name, estimated_name in comparisons:
        if estimated[estimated_name] > allowed[allowed_name]:
            codes.append(f"LIMIT_EXCEEDED:{estimated_name}")
    return codes


def _reject_forbidden_fields(value: Any, path: tuple[str, ...] = ()) -> None:
    if isinstance(value, Mapping):
        for key, child in value.items():
            normalized = str(key).lower()
            if normalized in FORBIDDEN_FIELD_NAMES:
                raise RoEValidationError(
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
        raise RoEValidationError("INVALID_DATETIME") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise RoEValidationError("TIMEZONE_REQUIRED")
    return parsed


def _normalize_domain(value: str) -> str:
    normalized = value.rstrip(".").lower()
    if (
        not normalized
        or len(normalized) > 253
        or "/" in normalized
        or ":" in normalized
        or normalized.startswith(".")
        or normalized.endswith(".")
    ):
        raise ValueError("invalid domain")
    labels = normalized.split(".")
    if any(
        not label
        or len(label) > 63
        or label.startswith("-")
        or label.endswith("-")
        or not all(character.isalnum() or character == "-" for character in label)
        for label in labels
    ):
        raise ValueError("invalid domain")
    return normalized


def _level_index(level: str) -> int:
    return LEVELS.index(level)


def _safe_identifier(value: Mapping[str, Any] | None, key: str) -> str | None:
    if not isinstance(value, Mapping):
        return None
    candidate = value.get(key)
    return candidate if isinstance(candidate, str) else None
