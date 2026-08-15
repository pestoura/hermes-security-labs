#!/usr/bin/env python3
"""Compose verified signer identity with one reviewed public trust-store generation.

This module is repository-only evidence composition. It does not contact a provider,
verify raw provider evidence, install a trust store, sign anything, activate a key, or
grant authorization/execution/promotion authority. Inputs are expected to come from the
existing canonical signer-attestation verifier and trust-store lifecycle contracts.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import re
import sys
from pathlib import Path
from typing import Any, Mapping

PROMOTION_ALLOWED = False
RUNTIME_STATUS = "NOT_RUN"
_SCHEMA_VERSION = "signer-trust-manifest/v1"
_ADMISSIBLE_CUSTODY_CLASSES = frozenset({"VAULT", "KMS", "HSM"})
_SHA256_RE = re.compile(r"^[a-f0-9]{64}$")
_EVIDENCE_REF_RE = re.compile(r"^evidence://[A-Za-z0-9][A-Za-z0-9._:/-]*$")


class SignerTrustManifestError(ValueError):
    """Fail-closed composition error with a stable machine-readable code."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


def _load_lifecycle():
    module_name = "hsl_signer_trust_manifest_lifecycle"
    existing = sys.modules.get(module_name)
    if existing is not None:
        return existing
    path = Path(__file__).resolve().parents[1] / "roe-contract" / "trust_store_lifecycle.py"
    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:  # pragma: no cover
        raise RuntimeError("TRUST_STORE_LIFECYCLE_LOAD_FAILED")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


def _canonical_digest(value: Mapping[str, Any]) -> str:
    encoded = json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=True
    ).encode()
    return hashlib.sha256(encoded).hexdigest()


def _mapping(value: Any, *, code: str, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise SignerTrustManifestError(code, f"{label} must be an object")
    return value


def _require_sha256(value: Any, *, code: str, label: str) -> str:
    if not isinstance(value, str) or not _SHA256_RE.fullmatch(value):
        raise SignerTrustManifestError(code, f"{label} must be lowercase SHA-256")
    return value


def _require_evidence_ref(value: Any) -> str:
    if not isinstance(value, str) or not _EVIDENCE_REF_RE.fullmatch(value):
        raise SignerTrustManifestError(
            "SIGNER_SOURCE_EVIDENCE_INVALID", "source evidence ref must be canonical evidence://"
        )
    return value


def _validate_signer(
    signer_result: Mapping[str, Any], signer_attestation: Mapping[str, Any]
) -> dict[str, str]:
    if signer_result.get("signer_attestation_checks_passed") is not True:
        raise SignerTrustManifestError(
            "SIGNER_ATTESTATION_NOT_VERIFIED", "canonical signer attestation did not pass"
        )
    if signer_result.get("source_evidence_verified") is not True:
        raise SignerTrustManifestError(
            "SIGNER_SOURCE_EVIDENCE_NOT_VERIFIED", "provider source evidence is not verified"
        )
    if signer_result.get("promotion_allowed") is not False or signer_result.get("runtime_status") != "NOT_RUN":
        raise SignerTrustManifestError(
            "SIGNER_RESULT_AUTHORITY_INVALID", "signer verifier result must remain HOLD/NOT_RUN"
        )

    provider_kind = signer_result.get("provider_kind")
    if provider_kind not in _ADMISSIBLE_CUSTODY_CLASSES:
        raise SignerTrustManifestError(
            "SIGNER_CUSTODY_CLASS_NOT_ADMISSIBLE", "signer custody class is not admissible"
        )

    if signer_attestation.get("observation_status") != "OBSERVED":
        raise SignerTrustManifestError(
            "SIGNER_ATTESTATION_NOT_OBSERVED", "signer attestation is not an observed live record"
        )
    if signer_attestation.get("key_state") != "active":
        raise SignerTrustManifestError("SIGNER_KEY_NOT_ACTIVE", "signer key is not active")
    if signer_attestation.get("signing_enabled") is not True:
        raise SignerTrustManifestError("SIGNER_SIGNING_DISABLED", "signer is not enabled for signing")
    if signer_attestation.get("private_key_exportable") is not False:
        raise SignerTrustManifestError(
            "SIGNER_PRIVATE_KEY_EXPORTABLE", "signer private key is exportable or unknown"
        )

    identity_fields = (
        "provider_kind",
        "provider_ref",
        "key_id",
        "algorithm",
        "public_key_spki_sha256",
    )
    for field in identity_fields:
        if signer_attestation.get(field) != signer_result.get(field):
            raise SignerTrustManifestError(
                "SIGNER_IDENTITY_MISMATCH", f"signer attestation/result mismatch for {field}"
            )

    evidence_ref = _require_evidence_ref(signer_attestation.get("source_evidence_ref"))
    evidence_sha = _require_sha256(
        signer_attestation.get("source_evidence_sha256"),
        code="SIGNER_SOURCE_EVIDENCE_INVALID",
        label="source_evidence_sha256",
    )

    provenance_fields = (
        "attestation_id",
        "observed_at",
        "source_evidence_ref",
        "source_evidence_sha256",
    )
    for field in provenance_fields:
        if signer_attestation.get(field) != signer_result.get(field):
            raise SignerTrustManifestError(
                "SIGNER_PROVENANCE_MISMATCH",
                f"signer attestation/result provenance mismatch for {field}",
            )

    spki_sha = _require_sha256(
        signer_result.get("public_key_spki_sha256"),
        code="SIGNER_IDENTITY_INVALID",
        label="public_key_spki_sha256",
    )

    provider_ref = signer_result.get("provider_ref")
    key_id = signer_result.get("key_id")
    algorithm = signer_result.get("algorithm")
    if not isinstance(provider_ref, str) or not provider_ref:
        raise SignerTrustManifestError("SIGNER_IDENTITY_INVALID", "provider_ref is invalid")
    if not isinstance(key_id, str) or not key_id:
        raise SignerTrustManifestError("SIGNER_IDENTITY_INVALID", "key_id is invalid")
    if algorithm not in {"Ed25519", "ECDSA-P256-SHA256"}:
        raise SignerTrustManifestError("SIGNER_IDENTITY_INVALID", "algorithm is invalid")

    attestation_id = signer_result.get("attestation_id")
    observed_at = signer_result.get("observed_at")
    if not isinstance(attestation_id, str) or not attestation_id:
        raise SignerTrustManifestError(
            "SIGNER_PROVENANCE_INVALID", "verified attestation_id is invalid"
        )
    if not isinstance(observed_at, str) or not observed_at:
        raise SignerTrustManifestError(
            "SIGNER_PROVENANCE_INVALID", "verified observed_at is invalid"
        )

    return {
        "provider_kind": str(provider_kind),
        "provider_ref": provider_ref,
        "key_id": key_id,
        "algorithm": str(algorithm),
        "public_key_spki_sha256": spki_sha,
        "source_evidence_ref": evidence_ref,
        "source_evidence_sha256": evidence_sha,
        "attestation_id": attestation_id,
        "observed_at": observed_at,
    }


def _validate_generation(
    trust_generation: Mapping[str, Any], lifecycle_assessment: Mapping[str, Any], identity: Mapping[str, str]
) -> dict[str, Any]:
    lifecycle = _load_lifecycle()
    try:
        normalized = lifecycle.validate_generation(trust_generation)
    except Exception as exc:
        if exc.__class__.__name__ == "TrustStoreLifecycleError":
            raise SignerTrustManifestError("TRUST_GENERATION_INVALID", str(exc)) from exc
        raise

    if lifecycle_assessment.get("decision") != "ACCEPT_FOR_REVIEW" or lifecycle_assessment.get("codes") != []:
        raise SignerTrustManifestError(
            "TRUST_GENERATION_NOT_ACCEPTED_FOR_REVIEW", "trust generation lifecycle is not accepted for review"
        )
    if lifecycle_assessment.get("current_generation_id") != normalized.get("generation_id"):
        raise SignerTrustManifestError(
            "TRUST_GENERATION_ASSESSMENT_MISMATCH", "assessment is not bound to the supplied generation"
        )
    if (
        lifecycle_assessment.get("automatic_activation") is not False
        or lifecycle_assessment.get("activation_effect") != "NONE"
        or lifecycle_assessment.get("authorization_effect") != "NONE"
        or lifecycle_assessment.get("execution_authority") != "NONE"
    ):
        raise SignerTrustManifestError(
            "TRUST_GENERATION_AUTHORITY_INVALID", "lifecycle assessment must not activate or grant authority"
        )

    matching = [key for key in normalized["keys"] if key.get("key_id") == identity["key_id"]]
    if len(matching) != 1:
        raise SignerTrustManifestError(
            "TRUST_SIGNER_KEY_NOT_FOUND", "exact signer key is not uniquely present in trust generation"
        )
    key = matching[0]
    if key.get("state") != "active":
        raise SignerTrustManifestError("TRUST_SIGNER_KEY_NOT_ACTIVE", "trust generation signer key is not active")
    if key.get("algorithm") != identity["algorithm"]:
        raise SignerTrustManifestError(
            "TRUST_SIGNER_ALGORITHM_MISMATCH", "trust generation signer algorithm does not match attestation"
        )
    if key.get("public_key_sha256") != identity["public_key_spki_sha256"]:
        raise SignerTrustManifestError(
            "TRUST_SIGNER_SPKI_MISMATCH", "trust generation signer SPKI digest does not match attestation"
        )
    return normalized


def build_signer_trust_manifest(
    *,
    signer_result: Mapping[str, Any],
    signer_attestation: Mapping[str, Any],
    trust_generation: Mapping[str, Any],
    lifecycle_assessment: Mapping[str, Any],
) -> dict[str, Any]:
    """Build a deterministic public no-authority signer/trust evidence manifest."""

    signer_result = _mapping(
        signer_result, code="SIGNER_RESULT_INVALID", label="signer_result"
    )
    signer_attestation = _mapping(
        signer_attestation, code="SIGNER_ATTESTATION_INVALID", label="signer_attestation"
    )
    trust_generation = _mapping(
        trust_generation, code="TRUST_GENERATION_INVALID", label="trust_generation"
    )
    lifecycle_assessment = _mapping(
        lifecycle_assessment,
        code="TRUST_GENERATION_ASSESSMENT_INVALID",
        label="lifecycle_assessment",
    )

    identity = _validate_signer(signer_result, signer_attestation)
    generation = _validate_generation(trust_generation, lifecycle_assessment, identity)

    body: dict[str, Any] = {
        "schema_version": _SCHEMA_VERSION,
        "provider_kind": identity["provider_kind"],
        "provider_ref": identity["provider_ref"],
        "key_id": identity["key_id"],
        "algorithm": identity["algorithm"],
        "public_key_spki_sha256": identity["public_key_spki_sha256"],
        "attestation_id": identity["attestation_id"],
        "observed_at": identity["observed_at"],
        "source_evidence_ref": identity["source_evidence_ref"],
        "source_evidence_sha256": identity["source_evidence_sha256"],
        "generation_id": generation["generation_id"],
        "generation_sequence": generation["sequence"],
        "trust_store_sha256": generation["trust_store_sha256"],
        "lifecycle_decision": "ACCEPT_FOR_REVIEW",
        "trust_binding_allowed": False,
        "automatic_activation": False,
        "activation_effect": "NONE",
        "authorization_effect": "NONE",
        "execution_authority": "NONE",
        "promotion_allowed": PROMOTION_ALLOWED,
        "runtime_status": RUNTIME_STATUS,
    }
    manifest_id = f"stm_{_canonical_digest(body)[:32]}"
    return {"manifest_id": manifest_id, **body}
