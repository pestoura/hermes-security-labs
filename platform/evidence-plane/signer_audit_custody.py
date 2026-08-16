#!/usr/bin/env python3
"""Custody bridge from public signer-operation audit events to Evidence Plane v2.

The bridge persists only an already-built public ``signer-operation-audit/v1``
event through an injected canonical Evidence Plane store. It owns no datastore,
EvidenceChain, seal or EvidenceVerifier implementation and creates no signing,
provider, trust, authorization, Runner or target effect.

The canonical policy is DISABLED / NOT_RUN. Tests may enable an in-memory/temp
composition explicitly; that does not make the runtime policy enabled.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import jsonschema
import yaml

HERE = Path(__file__).resolve().parent
REPOSITORY_ROOT = HERE.parents[1]
EVENT_SCHEMA_PATH = REPOSITORY_ROOT / "platform" / "schemas" / "signer-operation-audit.schema.json"
EVIDENCE_CONTRACT_PATH = HERE / "evidence_plane.py"
POLICY_PATH = HERE / "signer-audit-custody-policy.yaml"
CORRELATION_KEYS = {"campaign_id", "run_id", "step_id", "attempt_id"}


class SignerAuditCustodyError(ValueError):
    """Stable fail-closed signer-audit custody error."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class SignerAuditCustodyResult:
    evidence_id: str
    evidence_ref: str
    payload_sha256: str
    classification: str

    def as_safe_dict(self) -> dict[str, str]:
        return {
            "evidence_id": self.evidence_id,
            "evidence_ref": self.evidence_ref,
            "payload_sha256": self.payload_sha256,
            "classification": self.classification,
        }


class EvidenceVerifierChainResolver:
    """Interface adapter: canonical EvidenceVerifier -> EvidenceChain resolver.

    This class implements no verification logic. It only translates the existing
    EvidenceChain callable signature to the existing EvidenceVerifier ``verify(ref,
    sha256)`` contract. The content digest remains the authoritative object binding;
    object size is already sealed by EvidenceChain but is not part of EvidenceVerifier's
    two-argument contract.
    """

    def __init__(self, verifier: Any) -> None:
        if verifier is None or not callable(getattr(verifier, "verify", None)):
            raise TypeError("EvidenceVerifierChainResolver requires EvidenceVerifier.verify")
        self._verifier = verifier

    def __call__(
        self,
        *,
        object_ref: str,
        object_digest_sha256: str,
        object_size_bytes: int,
    ) -> bool:
        if (
            not isinstance(object_ref, str)
            or not object_ref
            or not isinstance(object_digest_sha256, str)
            or len(object_digest_sha256) != 64
            or isinstance(object_size_bytes, bool)
            or not isinstance(object_size_bytes, int)
            or object_size_bytes < 0
        ):
            return False
        try:
            return bool(self._verifier.verify(object_ref, object_digest_sha256))
        except Exception:  # noqa: BLE001 - chain resolver must fail closed
            return False


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
    if spec is None or spec.loader is None:  # pragma: no cover - packaging defect
        raise RuntimeError(f"cannot load canonical module {path.name}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


evidence_contract = _load_module(
    "signer_audit_evidence_plane_contract", EVIDENCE_CONTRACT_PATH
)


def _canonical_bytes(value: Mapping[str, Any]) -> bytes:
    return json.dumps(
        dict(value), sort_keys=True, separators=(",", ":"), ensure_ascii=True
    ).encode("utf-8")


def _validate_event(event: Any) -> dict[str, Any]:
    if not isinstance(event, Mapping):
        raise SignerAuditCustodyError(
            "SIGNER_AUDIT_EVENT_INVALID", "signer audit event must be an object"
        )
    try:
        schema = json.loads(EVENT_SCHEMA_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError, UnicodeDecodeError) as exc:
        raise SignerAuditCustodyError(
            "SIGNER_AUDIT_SCHEMA_UNAVAILABLE",
            "signer audit event schema cannot be loaded",
        ) from exc
    validator = jsonschema.Draft202012Validator(schema)
    errors = sorted(validator.iter_errors(event), key=lambda error: list(error.path))
    if errors:
        raise SignerAuditCustodyError(
            "SIGNER_AUDIT_EVENT_INVALID", errors[0].message
        )
    return dict(event)


def _parse_recorded_at(value: Any) -> datetime:
    if not isinstance(value, str) or not value.endswith("Z"):
        raise SignerAuditCustodyError(
            "SIGNER_AUDIT_TIMESTAMP_INVALID",
            "recorded_at must be an RFC3339 UTC timestamp ending in Z",
        )
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise SignerAuditCustodyError(
            "SIGNER_AUDIT_TIMESTAMP_INVALID", "recorded_at is invalid"
        ) from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise SignerAuditCustodyError(
            "SIGNER_AUDIT_TIMESTAMP_INVALID", "recorded_at must be timezone-aware"
        )
    return parsed.astimezone(timezone.utc)


def _iso_z(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _correlation(value: Any) -> Any:
    if not isinstance(value, Mapping) or set(value) != CORRELATION_KEYS:
        raise SignerAuditCustodyError(
            "SIGNER_AUDIT_CORRELATION_INVALID", "exact correlation fields required"
        )
    try:
        return evidence_contract.Correlation(**dict(value))
    except (TypeError, ValueError) as exc:
        raise SignerAuditCustodyError(
            "SIGNER_AUDIT_CORRELATION_INVALID", "correlation identifiers are invalid"
        ) from exc


def validate_policy(document: Any) -> list[str]:
    if not isinstance(document, Mapping):
        return ["signer audit custody policy must be an object"]
    findings: list[str] = []
    if document.get("schema_version") != "1.0":
        findings.append("schema_version must be '1.0'")
    if document.get("policy_id") != "hexor.signer.audit.custody":
        findings.append("policy_id must be hexor.signer.audit.custody")
    if document.get("state") not in {"DISABLED", "ENABLED"}:
        findings.append("state must be DISABLED or ENABLED")
    if document.get("default") != "deny":
        findings.append("default must be deny")
    if document.get("runtime_status") != "NOT_RUN":
        findings.append("runtime_status must remain NOT_RUN before live acceptance")
    if document.get("execution_authority") != "none":
        findings.append("signer audit custody must never claim execution authority")

    custody = document.get("custody")
    if not isinstance(custody, Mapping):
        return findings + ["custody must be an object"]
    expected = {
        "evidence_plane_projection",
        "classification",
        "retention_policy_id",
        "retention_days",
        "include_original_signing_payload",
        "include_raw_signature",
    }
    if set(custody) != expected:
        findings.append("custody exact fields do not match canonical contract")
    if custody.get("evidence_plane_projection") != "required":
        findings.append("evidence_plane_projection must be required")
    if custody.get("classification") != "restricted":
        findings.append("signer audit evidence classification must be restricted")
    retention_policy = custody.get("retention_policy_id")
    if not isinstance(retention_policy, str) or not retention_policy:
        findings.append("retention_policy_id is required")
    retention_days = custody.get("retention_days")
    if (
        isinstance(retention_days, bool)
        or not isinstance(retention_days, int)
        or not 1 <= retention_days <= 3650
    ):
        findings.append("retention_days must be an integer between 1 and 3650")
    if custody.get("include_original_signing_payload") is not False:
        findings.append("original signing payload custody must remain disabled")
    if custody.get("include_raw_signature") is not False:
        findings.append("raw signature custody must remain disabled")
    return findings


def load_policy(path: Path | str = POLICY_PATH) -> dict[str, Any]:
    policy_path = Path(path)
    try:
        document = yaml.safe_load(policy_path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise SignerAuditCustodyError("POLICY_UNREADABLE", str(exc)) from exc
    except yaml.YAMLError as exc:
        raise SignerAuditCustodyError("POLICY_INVALID", str(exc)) from exc
    findings = validate_policy(document)
    if findings:
        raise SignerAuditCustodyError("POLICY_INVALID", "; ".join(findings))
    return dict(document)


class SignerAuditCustody:
    """Project one public signer-audit event into the existing Evidence Plane store."""

    def __init__(self, policy: Mapping[str, Any]) -> None:
        findings = validate_policy(policy)
        if findings:
            raise SignerAuditCustodyError("POLICY_INVALID", "; ".join(findings))
        self._policy = dict(policy)

    @property
    def enabled(self) -> bool:
        return self._policy.get("state") == "ENABLED"

    def persist(
        self,
        event: Mapping[str, Any],
        *,
        correlation: Mapping[str, str],
        recorded_at: str,
        evidence_store: Any,
    ) -> SignerAuditCustodyResult:
        if not self.enabled:
            raise SignerAuditCustodyError(
                "CUSTODY_DISABLED", "signer audit custody policy is disabled"
            )
        if evidence_store is None or not hasattr(evidence_store, "put"):
            raise SignerAuditCustodyError(
                "EVIDENCE_STORE_UNAVAILABLE", "canonical Evidence Plane store is required"
            )
        if not hasattr(evidence_store, "verify"):
            raise SignerAuditCustodyError(
                "EVIDENCE_STORE_UNAVAILABLE",
                "Evidence Plane integrity verification is required",
            )

        validated = _validate_event(event)
        corr = _correlation(correlation)
        timestamp = _parse_recorded_at(recorded_at)
        custody = self._policy["custody"]
        payload = _canonical_bytes(validated)
        payload_sha256 = evidence_contract.sha256_hex(payload)
        retain_until = _iso_z(
            timestamp + timedelta(days=int(custody["retention_days"]))
        )
        storage_ref = f"evidence://signer-operation/{payload_sha256}"
        metadata = {
            "operation": validated["operation"],
            "request_correlation_id": validated["request_correlation_id"],
            "signature_sha256": validated["signature_sha256"],
            "key_id": validated["key_id"],
            "algorithm": validated["algorithm"],
            "public_key_spki_sha256": validated["public_key_spki_sha256"],
            "signer_class": validated["signer_class"],
            "authority": validated["authority"],
            "audit_ref": validated["audit_ref"],
            "principal": validated["principal"],
            "provider_ref": validated["provider_ref"],
            "test_only": validated["test_only"],
            "promotion_allowed": False,
            "runtime_status": "NOT_RUN",
            "execution_authority": "NONE",
        }

        try:
            record = evidence_contract.build_record(
                correlation=corr,
                classification=str(custody["classification"]),
                producer="signer-operation-audit-custody-v1",
                operation=f"signer.audit.{validated['operation']}",
                protocol_version=str(validated["schema_version"]),
                payload_sha256=payload_sha256,
                payload_size=len(payload),
                media_type="application/json",
                storage_ref=storage_ref,
                retention_policy_id=str(custody["retention_policy_id"]),
                retain_until=retain_until,
                legal_hold=False,
                metadata=metadata,
                created_at=recorded_at,
            )
            evidence_id = evidence_store.put(record, payload)
        except Exception as exc:  # noqa: BLE001 - backend details must stay private
            raise SignerAuditCustodyError(
                "EVIDENCE_PROJECTION_FAILED",
                f"Evidence Plane signer-audit projection failed safely: {type(exc).__name__}",
            ) from exc

        try:
            verified = bool(evidence_store.verify(evidence_id))
        except Exception as exc:  # noqa: BLE001
            raise SignerAuditCustodyError(
                "EVIDENCE_VERIFICATION_FAILED",
                f"Evidence Plane verification failed safely: {type(exc).__name__}",
            ) from exc
        if not verified:
            raise SignerAuditCustodyError(
                "EVIDENCE_VERIFICATION_FAILED",
                "Evidence Plane signer-audit record failed integrity verification",
            )

        return SignerAuditCustodyResult(
            evidence_id=str(evidence_id),
            evidence_ref=f"evidence://{evidence_id}",
            payload_sha256=payload_sha256,
            classification=str(custody["classification"]),
        )


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--policy", default=str(POLICY_PATH))
    parser.add_argument("command", choices=("validate",))
    args = parser.parse_args(list(argv) if argv is not None else None)
    try:
        policy = load_policy(args.policy)
        SignerAuditCustody(policy)
    except SignerAuditCustodyError as exc:
        print(f"FAIL {exc.code}: {exc}", file=sys.stderr)
        return 1
    print("OK signer audit custody policy is fail-closed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
