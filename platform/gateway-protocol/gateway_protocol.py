from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping

import jsonschema
import yaml

ROOT = Path(__file__).resolve().parent
REPOSITORY_ROOT = ROOT.parents[1]
LEVELS = ("L0", "L1", "L2", "L3", "L4")
LEGACY_SCHEMA_VERSION = "1.0.0"
CANONICAL_SCHEMA_VERSION = "2.0.0"
GATEWAY_REQUEST_SCHEMAS = {
    LEGACY_SCHEMA_VERSION: "gateway-request.schema.json",
    CANONICAL_SCHEMA_VERSION: "gateway-request-v2.schema.json",
}
FORBIDDEN_FIELD_NAMES = {
    "api_key",
    "argv",
    "authorization_header",
    "command",
    "cookie",
    "cookies",
    "cwd",
    "env",
    "environment",
    "execute_command",
    "password",
    "private_key",
    "secret",
    "shell",
    "token",
}
FORBIDDEN_OPERATION_TOKENS = ("command", "exec", "shell", "terminal")


class GatewayValidationError(ValueError):
    """Raised when a gateway contract or request cannot be trusted."""


@dataclass(frozen=True)
class GatewayDecision:
    allowed: bool
    codes: tuple[str, ...]
    request_id: str | None
    campaign_id: str | None
    operation_id: str | None
    operation_version: str | None

    @classmethod
    def allow(
        cls,
        request: Mapping[str, Any],
        operation: Mapping[str, Any],
    ) -> "GatewayDecision":
        return cls(
            allowed=True,
            codes=("ALLOW_TYPED_OPERATION",),
            request_id=_safe_identifier(request, "request_id"),
            campaign_id=_safe_identifier(request, "campaign_id"),
            operation_id=str(operation["id"]),
            operation_version=str(operation["version"]),
        )

    @classmethod
    def refuse(
        cls,
        codes: Iterable[str],
        request: Mapping[str, Any] | None,
    ) -> "GatewayDecision":
        unique = tuple(dict.fromkeys(codes))
        operation = request.get("operation") if isinstance(request, Mapping) else None
        return cls(
            allowed=False,
            codes=unique or ("REQUEST_INVALID",),
            request_id=_safe_identifier(request, "request_id"),
            campaign_id=_safe_identifier(request, "campaign_id"),
            operation_id=_safe_identifier(operation, "id"),
            operation_version=_safe_identifier(operation, "version"),
        )


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def load_registry(path: Path | None = None) -> dict[str, Any]:
    selected = path or ROOT / "operation-registry.yaml"
    data = yaml.safe_load(selected.read_text(encoding="utf-8"))
    schema = load_json(ROOT / "operation-registry.schema.json")
    validator = jsonschema.Draft202012Validator(schema)
    errors = sorted(validator.iter_errors(data), key=lambda item: list(item.path))
    if errors:
        raise GatewayValidationError("REGISTRY_SCHEMA_INVALID")
    _validate_registry_semantics(data)
    return data


def canonical_runtime_digest(path: Path | None = None) -> str:
    selected = path or REPOSITORY_ROOT / "platform" / "registry.yaml"
    return hashlib.sha256(selected.read_bytes()).hexdigest()


def canonical_target_digest(target: Mapping[str, Any]) -> str:
    payload = json.dumps(
        target,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def gateway_request_schema_version(request: Mapping[str, Any]) -> str:
    """Return the supported request schema version or fail closed.

    Missing/malformed versions remain structural invalidity for legacy
    compatibility. A syntactically valid but unknown version is distinguished
    as unsupported so migrations cannot silently reinterpret a new contract.
    """

    version = request.get("schema_version") if isinstance(request, Mapping) else None
    if not isinstance(version, str):
        raise GatewayValidationError("REQUEST_SCHEMA_INVALID")
    if version not in GATEWAY_REQUEST_SCHEMAS:
        raise GatewayValidationError("REQUEST_SCHEMA_UNSUPPORTED")
    return version


def validate_request_structure(request: Mapping[str, Any]) -> None:
    _reject_forbidden_fields(request)
    version = gateway_request_schema_version(request)
    schema = load_json(ROOT / GATEWAY_REQUEST_SCHEMAS[version])
    validator = jsonschema.Draft202012Validator(
        schema,
        format_checker=jsonschema.FormatChecker(),
    )
    errors = sorted(validator.iter_errors(request), key=lambda item: list(item.path))
    if errors:
        raise GatewayValidationError("REQUEST_SCHEMA_INVALID")


def authorize_typed_operation(
    request: Mapping[str, Any],
    *,
    registry_path: Path | None = None,
    runtime_registry_path: Path | None = None,
) -> GatewayDecision:
    try:
        registry = load_registry(registry_path)
        validate_request_structure(request)
    except GatewayValidationError as exc:
        return GatewayDecision.refuse((str(exc),), request)

    codes: list[str] = []
    requested_operation = request["operation"]
    operation = _find_operation(registry, str(requested_operation["id"]))
    if operation is None:
        return GatewayDecision.refuse(("OPERATION_UNKNOWN",), request)

    if requested_operation["version"] != operation["version"]:
        codes.append("OPERATION_VERSION_MISMATCH")

    parameter_validator = jsonschema.Draft202012Validator(
        operation["parameters_schema"],
        format_checker=jsonschema.FormatChecker(),
    )
    if list(parameter_validator.iter_errors(requested_operation["parameters"])):
        codes.append("OPERATION_PARAMETERS_INVALID")

    profile = registry["profiles"][request["profile"]]
    if operation["id"] not in profile["operations"]:
        codes.append("OPERATION_NOT_ALLOWED_IN_PROFILE")

    required_capabilities = set(operation["required_capabilities"])
    attested_capabilities = set(request["capability_attestations"])
    if not required_capabilities <= attested_capabilities:
        codes.append("CAPABILITY_ATTESTATION_MISSING")

    roe = request["roe_decision"]
    if roe["allowed"] is not True or roe["codes"] != ["ALLOW"]:
        codes.append("ROE_DECISION_NOT_ALLOW")
    if roe["campaign_id"] != request["campaign_id"]:
        codes.append("ROE_CAMPAIGN_MISMATCH")
    if roe["authorized_operation_id"] != operation["id"]:
        codes.append("ROE_OPERATION_MISMATCH")
    if roe["authorized_target_sha256"] != canonical_target_digest(request["target"]):
        codes.append("ROE_TARGET_MISMATCH")
    if _level_index(operation["intrusiveness_level"]) > _level_index(
        roe["intrusiveness_ceiling"]
    ):
        codes.append("ROE_INTRUSIVENESS_EXCEEDED")

    observation = request["runtime_observation"]
    if observation["state"] == "DRIFT_DETECTED":
        codes.append("RUNTIME_DRIFT_DETECTED")
    elif observation["state"] == "UNKNOWN":
        codes.append("RUNTIME_STATE_UNKNOWN")
    expected_digest = canonical_runtime_digest(runtime_registry_path)
    if observation["canonical_root"] != registry["canonical_runtime_root"]:
        codes.append("RUNTIME_CANONICAL_ROOT_MISMATCH")
    if observation["canonical_sha256"] != expected_digest:
        codes.append("RUNTIME_CANONICAL_DIGEST_MISMATCH")
    if observation["observed_sha256"] != observation["canonical_sha256"]:
        codes.append("RUNTIME_OBSERVED_DIGEST_MISMATCH")

    if codes:
        return GatewayDecision.refuse(codes, request)
    return GatewayDecision.allow(request, operation)


def _validate_registry_semantics(registry: Mapping[str, Any]) -> None:
    operations = registry["operations"]
    identities = [(item["id"], item["version"]) for item in operations]
    if len(identities) != len(set(identities)):
        raise GatewayValidationError("DUPLICATE_OPERATION_IDENTITY")

    operation_ids = {item["id"] for item in operations}
    for item in operations:
        lowered = item["id"].lower()
        if any(token in lowered.split(".") for token in FORBIDDEN_OPERATION_TOKENS):
            raise GatewayValidationError("GENERIC_EXECUTION_OPERATION_FORBIDDEN")
        handler = str(item["handler_ref"])
        if any(character in handler for character in ("/", "\\", " ", ";", "|", "&")):
            raise GatewayValidationError("HANDLER_REFERENCE_UNSAFE")
        _reject_forbidden_fields(item["parameters_schema"])

    for profile_name, profile in registry["profiles"].items():
        unresolved = set(profile["operations"]) - operation_ids
        if unresolved:
            raise GatewayValidationError("PROFILE_OPERATION_UNRESOLVED")
        if profile["generic_execution"] is not False:
            raise GatewayValidationError("GENERIC_EXECUTION_PROFILE_FORBIDDEN")
        if profile_name == "normal":
            indexed = {item["id"]: item for item in operations}
            if any(
                _level_index(indexed[operation_id]["intrusiveness_level"]) > 1
                for operation_id in profile["operations"]
            ):
                raise GatewayValidationError("NORMAL_PROFILE_TOO_INTRUSIVE")


def _find_operation(
    registry: Mapping[str, Any],
    operation_id: str,
) -> Mapping[str, Any] | None:
    return next(
        (item for item in registry["operations"] if item["id"] == operation_id),
        None,
    )


def _reject_forbidden_fields(value: Any, path: tuple[str, ...] = ()) -> None:
    if isinstance(value, Mapping):
        for key, child in value.items():
            normalized = str(key).lower()
            if normalized in FORBIDDEN_FIELD_NAMES:
                raise GatewayValidationError(
                    f"FORBIDDEN_FIELD:{'.'.join((*path, normalized))}"
                )
            _reject_forbidden_fields(child, (*path, normalized))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            _reject_forbidden_fields(child, (*path, str(index)))


def _level_index(level: str) -> int:
    return LEVELS.index(level)


def _safe_identifier(value: Any, key: str) -> str | None:
    if not isinstance(value, Mapping):
        return None
    candidate = value.get(key)
    return candidate if isinstance(candidate, str) else None
