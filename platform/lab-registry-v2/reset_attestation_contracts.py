"""Deterministic repository-only contracts for controlled lab lifecycle reset.

Repository-only, fail-closed evidence for ``SVP2-I-01`` / ``SVP2-B-03``. It proves
that independent reset executions converge to the same canonical known state and
that the reset/cleanup envelope preserves zero-residue invariants without invoking
Docker, Kubernetes, VMs, cloud sandboxes, targets, networks, systemd, trust, signer
or any provider.

No subprocess, socket, mount, image, credential or runtime mutation exists in this
module. It consumes sanitized state snapshots and stable policy values supplied by
the caller and returns deterministic verdicts with stable codes only.
"""

from __future__ import annotations

import importlib.util
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping

HERE = Path(__file__).resolve().parent


def _load_attestation():
    name = "_hex0r_reset_contracts_attestation"
    existing = sys.modules.get(name)
    if existing is not None:
        return existing
    spec = importlib.util.spec_from_file_location(name, HERE / "reset_attestation.py")
    if not spec or not spec.loader:
        raise RuntimeError("cannot load reset attestation")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


_ATTEST = _load_attestation()
FORBIDDEN_FIELDS = _ATTEST.FORBIDDEN_FIELDS
ResetAttestation = _ATTEST.ResetAttestation
ResetAttestationError = _ATTEST.ResetAttestationError
attest_reset_determinism = _ATTEST.attest_reset_determinism
canonical_state_sha256 = _ATTEST.canonical_state_sha256

# Fingerprint-stable field contract for a single reset execution record. Keys are
# deliberately bounded to non-execution, non-secret, non-runtime values.
REQUIRED_RESET_RECORD_FIELDS = (
    "reset_attempt_id",
    "lifecycle_before",
    "lifecycle_after",
    "observed_at",
    "network_present",
    "volume_present",
    "residue_resources",
)

FORBIDDEN_RECORD_FIELDS = FORBIDDEN_FIELDS | {
    "docker_image",
    "volume_name",
    "network_name",
    "socket",
    "mount",
    "process",
}


class ResetContractError(ValueError):
    """Stable-code failure for repository-only reset contract violations."""


@dataclass(frozen=True)
class ResetContract:
    deterministic: bool
    canonical_sha256: str
    total_executions: int
    definitive_executions: int
    codes: tuple[str, ...]
    residue_clear: bool
    verified_attestation_sha256: str | None


@dataclass(frozen=True)
class ReplayIntegrity:
    canonical_sha256: str
    tamper_detected: bool
    codes: tuple[str, ...]
    expected_sha256: str | None


def _reject_forbidden_record(record: Mapping[str, Any]) -> None:
    for key in record:
        if str(key).lower() in FORBIDDEN_RECORD_FIELDS:
            raise ResetContractError(f"FORBIDDEN_RECORD_FIELD:{key}")


def _validate_reset_record(record: Mapping[str, Any], *, index: int) -> None:
    if not isinstance(record, Mapping):
        raise ResetContractError(f"RESET_RECORD_NOT_MAPPING[{index}]")
    missing = [f for f in REQUIRED_RESET_RECORD_FIELDS if f not in record]
    if missing:
        raise ResetContractError(f"RESET_RECORD_MISSING_FIELDS[{index}]:{','.join(missing)}")
    _reject_forbidden_record(record)
    if not isinstance(record["reset_attempt_id"], str) or not record["reset_attempt_id"]:
        raise ResetContractError(f"RESET_RECORD_BAD_ATTEMPT_ID[{index}]")
    if record["network_present"] not in (True, False):
        raise ResetContractError(f"RESET_RECORD_BAD_NETWORK_PRESENT[{index}]")
    if record["volume_present"] not in (True, False):
        raise ResetContractError(f"RESET_RECORD_BAD_VOLUME_PRESENT[{index}]")
    if not isinstance(record["residue_resources"], list):
        raise ResetContractError(f"RESET_RECORD_BAD_RESIDUE[{index}]")
    for item in record["residue_resources"]:
        if not isinstance(item, str) or not item:
            raise ResetContractError(f"RESET_RECORD_BAD_RESIDUE_ITEM[{index}]")
    try:
        canonical_state_sha256(record["lifecycle_after"])
    except ResetAttestationError as exc:
        raise ResetContractError(f"ATTESTATION_{exc}") from exc


def _is_definitive(record: Mapping[str, Any]) -> bool:
    """A definitive reset proves zero residue and a non-divergent post state."""
    if record["network_present"] or record["volume_present"]:
        return False
    if record["residue_resources"]:
        return False
    return True


def contract_reset_attestation(records: Iterable[Mapping[str, Any]]) -> ResetContract:
    """Prove reset determinism + zero-residue invariants without target effect.

    Fails closed on missing/forbidden/ambiguous records, partial reset evidence
    (fewer than two executions) or non-convergent post-reset state. ``production_lab_runtime``
    is always ``NOT_RUN`` in the returned contract: this module never executes a lab.
    """
    snapshots = list(records)
    if len(snapshots) < 2:
        raise ResetContractError("AT_LEAST_TWO_RESET_EXECUTIONS_REQUIRED")

    for index, record in enumerate(snapshots):
        _validate_reset_record(record, index=index)

    attempt_ids = [str(record["reset_attempt_id"]) for record in snapshots]
    if len(attempt_ids) != len(set(attempt_ids)):
        raise ResetContractError("DUPLICATE_RESET_ATTEMPT_ID")

    post_states = [record["lifecycle_after"] for record in snapshots]
    try:
        attestation: ResetAttestation = attest_reset_determinism(post_states)
    except ResetAttestationError as exc:
        raise ResetContractError(f"ATTESTATION_{exc}") from exc

    definitive = [record for record in snapshots if _is_definitive(record)]
    total = len(snapshots)
    residue_clear = len(definitive) == total

    codes: list[str] = []
    if attestation.deterministic:
        codes.append("RESET_STATE_IDENTICAL")
    else:
        codes.append("RESET_STATE_DIVERGED")
    if residue_clear:
        codes.append("ZERO_RESIDUE_VERIFIED")
    else:
        codes.append("RESIDUE_PRESENT")
    if attestation.deterministic and residue_clear:
        codes.append("RESET_ENVELOPE_CONVERGED")

    verified_sha: str | None = None
    if attestation.deterministic and residue_clear:
        verified_sha = attestation.canonical_sha256

    return ResetContract(
        deterministic=bool(attestation.deterministic),
        canonical_sha256=attestation.canonical_sha256,
        total_executions=total,
        definitive_executions=len(definitive),
        codes=tuple(dict.fromkeys(codes)),
        residue_clear=residue_clear,
        verified_attestation_sha256=verified_sha,
    )


def known_state_proof(
    *,
    expected_sha256: str,
    observed_states: Iterable[Mapping[str, Any]],
) -> ReplayIntegrity:
    """Prove a known post-reset state is reproduced exactly across observations.

    Fails closed if any observed post-reset state diverges from the expected
    canonical digest. No runtime, image, mount or target is touched.
    """
    if not isinstance(expected_sha256, str) or len(expected_sha256) != 64:
        raise ResetContractError("KNOWN_STATE_BAD_EXPECTED_SHA256")
    states = list(observed_states)
    if not states:
        raise ResetContractError("KNOWN_STATE_REQUIRES_OBSERVATIONS")

    for index, state in enumerate(states):
        try:
            canonical_state_sha256(state)
        except ResetAttestationError as exc:
            raise ResetContractError(f"KNOWN_STATE_INVALID_STATE[{index}]:{exc}") from exc

    digests = [canonical_state_sha256(state) for state in states]
    tamper = any(digest != expected_sha256 for digest in digests)
    codes: list[str] = []
    if tamper:
        codes.append("KNOWN_STATE_DRIFT")
    else:
        codes.append("KNOWN_STATE_REPRODUCED")

    return ReplayIntegrity(
        canonical_sha256=expected_sha256,
        tamper_detected=tamper,
        codes=tuple(dict.fromkeys(codes)),
        expected_sha256=expected_sha256,
    )


def replay_integrity_check(
    *,
    expected_sha256: str,
    replayed_records: Iterable[Mapping[str, Any]],
    tamper_seed: Mapping[str, Any] | None = None,
) -> ReplayIntegrity:
    """Replay reset records and detect tampering of the canonical known state.

    ``tamper_seed`` is an optional synthetic post-reset state injected to prove the
    check rejects tampering; it is never written to disk, a socket or a lab.
    """
    if not isinstance(expected_sha256, str) or len(expected_sha256) != 64:
        raise ResetContractError("REPLAY_BAD_EXPECTED_SHA256")

    records = list(replayed_records)
    if not records:
        raise ResetContractError("REPLAY_REQUIRES_RECORDS")

    observed: list[Mapping[str, Any]] = [
        record["lifecycle_after"] for record in records
    ]
    if tamper_seed is not None:
        observed.append(tamper_seed)

    return known_state_proof(
        expected_sha256=expected_sha256,
        observed_states=observed,
    )


def verify_reset_attestation_not_tampered(
    *,
    evidence_sha256: str,
    expected_sha256: str,
) -> ReplayIntegrity:
    """Fail-closed tamper/attestation replay check for stored reset evidence.

    Compares the supplied evidence digest against the expected canonical digest.
    No file, socket or provider is read; callers pass already-computed digests.
    """
    if not isinstance(evidence_sha256, str) or len(evidence_sha256) != 64:
        raise ResetContractError("ATTESTATION_BAD_EVIDENCE_SHA256")
    if not isinstance(expected_sha256, str) or len(expected_sha256) != 64:
        raise ResetContractError("ATTESTATION_BAD_EXPECTED_SHA256")
    tamper = evidence_sha256 != expected_sha256
    return ReplayIntegrity(
        canonical_sha256=expected_sha256,
        tamper_detected=tamper,
        codes=("ATTESTATION_TAMPER_DETECTED",) if tamper else ("ATTESTATION_INTACT",),
        expected_sha256=expected_sha256,
    )


def render_reset_contract_report(contract: ResetContract) -> dict[str, Any]:
    """Log-safe, secret-free summary of a reset contract verdict."""
    return {
        "schema_version": "1.0.0",
        "boundary": "REPOSITORY_ONLY_RESET_CONTRACT",
        "deterministic": contract.deterministic,
        "canonical_sha256": contract.canonical_sha256,
        "total_executions": contract.total_executions,
        "definitive_executions": contract.definitive_executions,
        "residue_clear": contract.residue_clear,
        "production_lab_runtime": "NOT_RUN",
        "codes": list(contract.codes),
    }


def render_replay_report(integrity: ReplayIntegrity) -> dict[str, Any]:
    return {
        "schema_version": "1.0.0",
        "boundary": "REPOSITORY_ONLY_REPLAY_INTEGRITY",
        "canonical_sha256": integrity.canonical_sha256,
        "tamper_detected": integrity.tamper_detected,
        "production_lab_runtime": "NOT_RUN",
        "codes": list(integrity.codes),
    }
