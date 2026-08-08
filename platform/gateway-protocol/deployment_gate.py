"""Fail-closed pre-deployment gate for the typed Security Execution Gateway.

This module is repository/runtime-observation agnostic: callers provide the
canonical runtime bytes and the digest observed on the deployment target.
The gate never reconciles drift automatically.
"""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from typing import Any, Mapping

SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
FORBIDDEN_OPERATION_TOKENS = {"command", "exec", "shell", "terminal"}


@dataclass(frozen=True)
class DeploymentGateDecision:
    allowed: bool
    codes: tuple[str, ...]


def evaluate_deployment_gate(
    *,
    canonical_runtime: bytes,
    observed_sha256: str,
    operation_registry: Mapping[str, Any],
) -> DeploymentGateDecision:
    """Validate canonical-runtime parity and typed-operation deployment safety."""
    canonical_sha256 = hashlib.sha256(canonical_runtime).hexdigest()
    codes: list[str] = []

    if not isinstance(observed_sha256, str) or not SHA256_RE.fullmatch(observed_sha256):
        codes.append("RUNTIME_OBSERVATION_INVALID")
    elif observed_sha256 != canonical_sha256:
        codes.append("RUNTIME_DRIFT_DETECTED")

    if operation_registry.get("generic_execution") != "forbidden":
        codes.append("GENERIC_EXECUTION_NOT_FORBIDDEN")

    profiles = operation_registry.get("profiles")
    operations = operation_registry.get("operations")
    if not isinstance(profiles, Mapping) or not isinstance(operations, list) or not operations:
        codes.append("OPERATION_REGISTRY_INVALID")
        return DeploymentGateDecision(False, tuple(dict.fromkeys(codes)))

    operation_ids: set[str] = set()
    for operation in operations:
        if not isinstance(operation, Mapping):
            codes.append("OPERATION_REGISTRY_INVALID")
            continue
        operation_id = operation.get("id")
        schema = operation.get("parameters_schema")
        if not isinstance(operation_id, str) or not operation_id:
            codes.append("OPERATION_ID_MISSING")
            continue
        if operation_id in operation_ids:
            codes.append("DUPLICATE_OPERATION_ID")
        operation_ids.add(operation_id)
        if FORBIDDEN_OPERATION_TOKENS.intersection(operation_id.split(".")):
            codes.append("GENERIC_EXECUTION_OPERATION_PRESENT")
        if not isinstance(schema, Mapping) or schema.get("type") != "object":
            codes.append(f"OPERATION_SCHEMA_MISSING:{operation_id}")
        elif schema.get("additionalProperties") is not False:
            codes.append(f"OPERATION_SCHEMA_OPEN:{operation_id}")

    for profile_name, profile in profiles.items():
        if not isinstance(profile, Mapping):
            codes.append(f"PROFILE_INVALID:{profile_name}")
            continue
        if profile.get("generic_execution") is not False:
            codes.append(f"PROFILE_GENERIC_EXECUTION_ENABLED:{profile_name}")
        refs = profile.get("operations")
        if not isinstance(refs, list):
            codes.append(f"PROFILE_OPERATIONS_INVALID:{profile_name}")
            continue
        if any(ref not in operation_ids for ref in refs):
            codes.append(f"PROFILE_OPERATION_UNRESOLVED:{profile_name}")

    unique_codes = tuple(dict.fromkeys(codes))
    return DeploymentGateDecision(not unique_codes, unique_codes or ("DEPLOYMENT_GATE_PASS",))
