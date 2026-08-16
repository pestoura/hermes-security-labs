#!/usr/bin/env python3
"""Custody bridge for public signer trust manifests into Evidence Plane v2.

Persists only an already-composed public ``signer-trust-manifest/v1`` through an
injected canonical Evidence Plane store. The canonical policy is DISABLED/NOT_RUN;
this module owns no datastore, verifier, chain, AuditSink, signer provider, trust
installer, key material, runtime authority or promotion authority.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import sys
from collections.abc import Mapping, Sequence
from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import jsonschema
import yaml

HERE = Path(__file__).resolve().parent
REPOSITORY_ROOT = HERE.parents[1]
MANIFEST_SCHEMA_PATH = REPOSITORY_ROOT / "platform" / "schemas" / "signer-trust-manifest.schema.json"
EVIDENCE_CONTRACT_PATH = HERE / "evidence_plane.py"
POLICY_PATH = HERE / "signer-trust-manifest-custody-policy.yaml"
CORRELATION_KEYS = {"campaign_id", "run_id", "step_id", "attempt_id"}
TOP_LEVEL_POLICY_FIELDS = {
    "schema_version",
    "policy_id",
    "state",
    "default",
    "runtime_status",
    "execution_authority",
    "custody",
}
CUSTODY_FIELDS = {
    "evidence_plane_projection",
    "classification",
    "retention_policy_id",
    "retention_days",
    "include_private_key",
    "include_raw_signing_payload",
    "include_raw_signature",
    "install_trust",
}


class SignerTrustManifestCustodyError(ValueError):
    """Stable fail-closed signer trust manifest custody error."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class SignerTrustManifestCustodyResult:
    evidence_id: str
    evidence_ref: str
    payload_sha256: str
    classification: str
    manifest_id: str

    def as_safe_dict(self) -> dict[str, str]:
        return {
            "evidence_id": self.evidence_id,
            "evidence_ref": self.evidence_ref,
            "payload_sha256": self.payload_sha256,
            "classification": self.classification,
            "manifest_id": self.manifest_id,
        }


def _load_module(name: str, path: Path) -> Any:
    resolved = path.resolve()
    for module in tuple(sys.modules.values()):
        module_file = getattr(module, "__file__", None)
        if module_file and Path(module_file).resolve() == resolved:
            return module
    existing = sys.modules.get(name)
    if existing is not None:
        return existing
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:  # pragma: no cover
        raise RuntimeError(f"cannot load canonical module {path.name}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


evidence_contract = _load_module(
    "signer_trust_manifest_evidence_plane_contract", EVIDENCE_CONTRACT_PATH
)


def _canonical_bytes(value: Mapping[str, Any]) -> bytes:
    return json.dumps(
        dict(value), sort_keys=True, separators=(",", ":"), ensure_ascii=True
    ).encode("utf-8")


def _load_manifest_schema() -> dict[str, Any]:
    try:
        loaded = json.loads(MANIFEST_SCHEMA_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError, UnicodeDecodeError) as exc:
        raise SignerTrustManifestCustodyError(
            "MANIFEST_INVALID", "signer trust manifest schema cannot be loaded"
        ) from exc
    if not isinstance(loaded, dict):
        raise SignerTrustManifestCustodyError(
            "MANIFEST_INVALID", "signer trust manifest schema is invalid"
        )
    return loaded


def _validate_manifest(manifest: Any) -> dict[str, Any]:
    if not isinstance(manifest, Mapping):
        raise SignerTrustManifestCustodyError(
            "MANIFEST_INVALID", "signer trust manifest must be an object"
        )
    normalized = dict(manifest)
    errors = sorted(
        jsonschema.Draft7Validator(_load_manifest_schema()).iter_errors(normalized),
        key=lambda error: list(error.path),
    )
    if errors:
        raise SignerTrustManifestCustodyError("MANIFEST_INVALID", errors[0].message)

    supplied_id = normalized.get("manifest_id")
    body = dict(normalized)
    body.pop("manifest_id", None)
    expected_id = "stm_" + hashlib.sha256(_canonical_bytes(body)).hexdigest()[:32]
    if supplied_id != expected_id:
        raise SignerTrustManifestCustodyError(
            "MANIFEST_ID_MISMATCH",
            "signer trust manifest id does not match canonical content",
        )
    return normalized


def _parse_recorded_at(value: Any) -> datetime:
    if not isinstance(value, str) or not value.endswith("Z"):
        raise SignerTrustManifestCustodyError(
            "MANIFEST_INVALID", "recorded_at must be an RFC3339 UTC timestamp ending in Z"
        )
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise SignerTrustManifestCustodyError(
            "MANIFEST_INVALID", "recorded_at is invalid"
        ) from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise SignerTrustManifestCustodyError(
            "MANIFEST_INVALID", "recorded_at must be timezone-aware"
        )
    return parsed.astimezone(timezone.utc)


def _iso_z(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _correlation(value: Any) -> Any:
    if not isinstance(value, Mapping) or set(value) != CORRELATION_KEYS:
        raise SignerTrustManifestCustodyError(
            "MANIFEST_INVALID", "exact correlation fields required"
        )
    try:
        return evidence_contract.Correlation(**dict(value))
    except (TypeError, ValueError) as exc:
        raise SignerTrustManifestCustodyError(
            "MANIFEST_INVALID", "correlation identifiers are invalid"
        ) from exc


def validate_policy(document: Any) -> list[str]:
    if not isinstance(document, Mapping):
        return ["signer trust manifest custody policy must be an object"]
    findings: list[str] = []
    if set(document) != TOP_LEVEL_POLICY_FIELDS:
        findings.append("policy exact fields do not match canonical contract")
    if document.get("schema_version") != "1.0":
        findings.append("schema_version must be '1.0'")
    if document.get("policy_id") != "hexor.signer.trust_manifest.custody":
        findings.append("policy_id must be hexor.signer.trust_manifest.custody")
    if document.get("state") not in {"DISABLED", "ENABLED"}:
        findings.append("state must be DISABLED or ENABLED")
    if document.get("default") != "deny":
        findings.append("default must be deny")
    if document.get("runtime_status") != "NOT_RUN":
        findings.append("runtime_status must remain NOT_RUN")
    if document.get("execution_authority") != "none":
        findings.append("signer trust manifest custody must never claim execution authority")

    custody = document.get("custody")
    if not isinstance(custody, Mapping):
        return findings + ["custody must be an object"]
    if set(custody) != CUSTODY_FIELDS:
        findings.append("custody exact fields do not match canonical contract")
    if custody.get("evidence_plane_projection") != "required":
        findings.append("evidence_plane_projection must be required")
    if custody.get("classification") != "restricted":
        findings.append("classification must be restricted")
    if custody.get("retention_policy_id") != "default-30d":
        findings.append("retention_policy_id must be default-30d")
    if custody.get("retention_days") != 30:
        findings.append("retention_days must be 30")
    if custody.get("include_private_key") is not False:
        findings.append("private key custody must remain disabled")
    if custody.get("include_raw_signing_payload") is not False:
        findings.append("raw signing payload custody must remain disabled")
    if custody.get("include_raw_signature") is not False:
        findings.append("raw signature custody must remain disabled")
    if custody.get("install_trust") is not False:
        findings.append("trust installation must remain disabled")
    return findings


def load_policy(path: Path | str = POLICY_PATH) -> dict[str, Any]:
    try:
        document = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        raise SignerTrustManifestCustodyError(
            "POLICY_INVALID", "policy is unreadable or invalid"
        ) from exc
    findings = validate_policy(document)
    if findings:
        raise SignerTrustManifestCustodyError("POLICY_INVALID", "; ".join(findings))
    return dict(document)


class SignerTrustManifestCustody:
    """Project one public signer trust manifest into an existing Evidence Plane store."""

    def __init__(self, policy: Mapping[str, Any]) -> None:
        findings = validate_policy(policy)
        if findings:
            raise SignerTrustManifestCustodyError("POLICY_INVALID", "; ".join(findings))
        # Snapshot the already-validated caller-owned policy deeply. A shallow copy
        # would leave the nested custody map mutable after the validation boundary.
        self._policy = deepcopy(dict(policy))

    @property
    def enabled(self) -> bool:
        return self._policy.get("state") == "ENABLED"

    def persist(
        self,
        manifest: Mapping[str, Any],
        *,
        correlation: Mapping[str, str],
        recorded_at: str,
        evidence_store: Any,
    ) -> SignerTrustManifestCustodyResult:
        if not self.enabled:
            raise SignerTrustManifestCustodyError(
                "CUSTODY_DISABLED", "signer trust manifest custody policy is disabled"
            )
        if evidence_store is None or not callable(getattr(evidence_store, "put", None)):
            raise SignerTrustManifestCustodyError(
                "EVIDENCE_STORE_UNAVAILABLE", "canonical Evidence Plane store is required"
            )
        if not callable(getattr(evidence_store, "verify", None)):
            raise SignerTrustManifestCustodyError(
                "EVIDENCE_STORE_UNAVAILABLE",
                "Evidence Plane integrity verification is required",
            )

        validated = _validate_manifest(manifest)
        corr = _correlation(correlation)
        timestamp = _parse_recorded_at(recorded_at)
        custody = self._policy["custody"]
        payload = _canonical_bytes(validated)
        payload_sha256 = evidence_contract.sha256_hex(payload)
        retain_until = _iso_z(timestamp + timedelta(days=30))
        storage_ref = f"evidence://signer-trust-manifest/{payload_sha256}"
        metadata = {
            "manifest_id": validated["manifest_id"],
            "provider_kind": validated["provider_kind"],
            "provider_ref": validated["provider_ref"],
            "key_id": validated["key_id"],
            "algorithm": validated["algorithm"],
            "public_key_spki_sha256": validated["public_key_spki_sha256"],
            "attestation_id": validated["attestation_id"],
            "generation_id": validated["generation_id"],
            "generation_sequence": validated["generation_sequence"],
            "trust_store_sha256": validated["trust_store_sha256"],
            "source_evidence_ref": validated["source_evidence_ref"],
            "source_evidence_sha256": validated["source_evidence_sha256"],
            "promotion_allowed": False,
            "runtime_status": "NOT_RUN",
            "execution_authority": "NONE",
            "trust_installation": "NONE",
        }

        try:
            record = evidence_contract.build_record(
                correlation=corr,
                classification=str(custody["classification"]),
                producer="signer-trust-manifest-custody-v1",
                operation="signer.trust_manifest.custody",
                protocol_version="signer-trust-manifest/v1",
                payload_sha256=payload_sha256,
                payload_size=len(payload),
                media_type="application/json",
                storage_ref=storage_ref,
                retention_policy_id="default-30d",
                retain_until=retain_until,
                legal_hold=False,
                metadata=metadata,
                created_at=recorded_at,
            )
            evidence_id = evidence_store.put(record, payload)
        except Exception as exc:  # noqa: BLE001
            raise SignerTrustManifestCustodyError(
                "EVIDENCE_PROJECTION_FAILED",
                f"Evidence Plane projection failed safely: {type(exc).__name__}",
            ) from exc

        try:
            verified = bool(evidence_store.verify(evidence_id))
        except Exception as exc:  # noqa: BLE001
            raise SignerTrustManifestCustodyError(
                "EVIDENCE_VERIFICATION_FAILED",
                f"Evidence Plane verification failed safely: {type(exc).__name__}",
            ) from exc
        if not verified:
            raise SignerTrustManifestCustodyError(
                "EVIDENCE_VERIFICATION_FAILED",
                "Evidence Plane signer trust manifest failed integrity verification",
            )

        return SignerTrustManifestCustodyResult(
            evidence_id=str(evidence_id),
            evidence_ref=f"evidence://{evidence_id}",
            payload_sha256=payload_sha256,
            classification=str(custody["classification"]),
            manifest_id=str(validated["manifest_id"]),
        )


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--policy", default=str(POLICY_PATH))
    parser.add_argument("command", choices=("validate",))
    args = parser.parse_args(list(argv) if argv is not None else None)
    try:
        SignerTrustManifestCustody(load_policy(args.policy))
    except SignerTrustManifestCustodyError as exc:
        print(f"FAIL {exc.code}: {exc}", file=sys.stderr)
        return 1
    print("OK signer trust manifest custody policy is fail-closed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
