"""Deterministic post-reset state attestation for SVP2-I-01.

The runtime adapter supplies sanitized state snapshots. This module proves whether
independent reset executions converge to the same canonical state without exposing
secrets, raw commands or host paths.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any, Iterable, Mapping

FORBIDDEN_FIELDS = {"secret", "token", "password", "credential", "command", "argv", "host_path", "docker_socket"}


class ResetAttestationError(ValueError):
    pass


@dataclass(frozen=True)
class ResetAttestation:
    deterministic: bool
    canonical_sha256: str
    execution_count: int
    codes: tuple[str, ...]


def _reject_forbidden(value: Any, path: str = "state") -> None:
    if isinstance(value, Mapping):
        for key, nested in value.items():
            if str(key).lower() in FORBIDDEN_FIELDS:
                raise ResetAttestationError(f"FORBIDDEN_STATE_FIELD:{path}.{key}")
            _reject_forbidden(nested, f"{path}.{key}")
    elif isinstance(value, list):
        for index, nested in enumerate(value):
            _reject_forbidden(nested, f"{path}[{index}]")


def canonical_state_sha256(state: Mapping[str, Any]) -> str:
    if not isinstance(state, Mapping) or not state:
        raise ResetAttestationError("POST_RESET_STATE_REQUIRED")
    _reject_forbidden(state)
    encoded = json.dumps(state, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def attest_reset_determinism(states: Iterable[Mapping[str, Any]]) -> ResetAttestation:
    snapshots = list(states)
    if len(snapshots) < 2:
        raise ResetAttestationError("AT_LEAST_TWO_RESET_EXECUTIONS_REQUIRED")
    digests = [canonical_state_sha256(state) for state in snapshots]
    deterministic = len(set(digests)) == 1
    return ResetAttestation(
        deterministic=deterministic,
        canonical_sha256=digests[0],
        execution_count=len(digests),
        codes=("RESET_STATE_IDENTICAL",) if deterministic else ("RESET_STATE_DIVERGED",),
    )
