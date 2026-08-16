#!/usr/bin/env python3
"""Custody bridge from sanitized authorization-decision audit events to Evidence Plane v2.

The bridge persists only an already-built public ``authorization-receipt-audit/v1``
record through an injected canonical Evidence Plane store. It owns no datastore,
EvidenceChain, seal or EvidenceVerifier implementation and creates no receipt delivery,
trust, authorization, Runner or target effect.

The canonical policy is DISABLED / NOT_RUN. Tests may enable a temporary composition
explicitly; that does not make the committed runtime policy enabled.
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
EVENT_SCHEMA_PATH = (
    REPOSITORY_ROOT / "platform" / "schemas" / "authorization-receipt-audit.schema.json"
)
EVIDENCE_CONTRACT_PATH = HERE / "evidence_plane.py"
POLICY_PATH = HERE / "authorization-audit-custody-policy.yaml"
CORRELATION_KEYS = {"campaign_id", "run_id", "step_id", "attempt_id"}
POLICY_KEYS = {
    "schema_version",
    "policy_id",
    "state",
    "default",
    "runtime_status",
    "execution_authority",
    "custody",
}
CUSTODY_KEYS = {
    "evidence_plane_projection",
    "classification",
    "retention_policy_id",
    "retention_days",
    "include_raw_receipt",
    "include_raw_authorization_ref",
}


class AuthorizationAuditCustodyError(ValueError):
    """Stable fail-closed authorization-audit custody error."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class AuthorizationAuditCustodyResult:
    evidence_id: str
    evidence_ref: str
    payload_sha256: str
    payload_size_bytes: int
    classification: str

    def as_safe_dict(self) -> dict[str, str | int]:
        return {
            "evidence_id": self.evidence_id,
            "evidence_ref": self.evidence_ref,
            "payload_sha256": self.payload_sha256,
            "payload_size_bytes": self.payload_size_bytes,
            "classification": self.classification,
        }


class EvidenceVerifierChainResolver:
    """Interface adapter: canonical EvidenceVerifier -> EvidenceChain resolver.

    Verification remains owned by the injected EvidenceVerifier. This adapter only
    translates the existing EvidenceChain callable contract and always fails closed.
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
        except Exception:  # noqa: BLE001 - resolver must fail closed
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
    "authorization_audit_evidence_plane_contract", EVIDENCE_CONTRACT_PATH
)


def _canonical_bytes(value: Mapping[str, Any]) -> bytes:
    return json.dumps(
        dict(value), sort_keys=True, separators=(",", ":"), ensure_ascii=True
    ).encode("utf-8")


def _validate_event(event: Any) -> dict[str, Any]:
    if not isinstance(event, Mapping):
        raise AuthorizationAuditCustodyError(
            "AUTHORIZATION_AUDIT_EVENT_INVALID",
            "authorization audit event must be an object",
        )
    try:
        schema = json.loads(EVENT_SCHEMA_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError, UnicodeDecodeError) as exc:
        raise AuthorizationAuditCustodyError(
            "AUTHORIZATION_AUDIT_SCHEMA_UNAVAILABLE",
            "authorization audit event schema cannot be loaded",
        ) from exc
    validator = jsonschema.Draft202012Validator(schema)
    errors = sorted(validator.iter_errors(event), key=lambda error: list(error.path))
    if errors:
        raise AuthorizationAuditCustodyError(
            "AUTHORIZATION_AUDIT_EVENT_INVALID",
            errors[0].message,
        )
    return dict(event)


def _parse_recorded_at(value: Any) -> datetime:
    if not isinstance(value, str) or not value.endswith("Z"):
        raise AuthorizationAuditCustodyError(
            "AUTHORIZATION_AUDIT_TIMESTAMP_INVALID",
            "recorded_at must be an RFC3339 UTC timestamp ending in Z",
        )
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise AuthorizationAuditCustodyError(
            "AUTHORIZATION_AUDIT_TIMESTAMP_INVALID",
            "recorded_at is invalid",
        ) from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise AuthorizationAuditCustodyError(
            "AUTHORIZATION_AUDIT_TIMESTAMP_INVALID",
            "recorded_at must be timezone-aware",
        )
    return parsed.astimezone(timezone.utc)


def _iso_z(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _correlation(value: Any) -> Any:
    if not isinstance(value, Mapping) or set(value) != CORRELATION_KEYS:
        raise AuthorizationAuditCustodyError(
            "AUTHORIZATION_AUDIT_CORRELATION_INVALID",
            "exact correlation fields required",
        )
    try:
        return evidence_contract.Correlation(**dict(value))
    except (TypeError, ValueError) as exc:
        raise AuthorizationAuditCustodyError(
            "AUTHORIZATION_AUDIT_CORRELATION_INVALID",
            "correlation identifiers are invalid",
        ) from exc


def validate_policy(document: Any) -> list[str]:
    if not isinstance(document, Mapping):
        return ["authorization audit custody policy must be an object"]

    findings: list[str] = []
    if set(document) != POLICY_KEYS:
        findings.append("policy exact fields do not match canonical contract")
    if document.get("schema_version") != "1.0":
        findings.append("schema_version must be '1.0'")
    if document.get("policy_id") != "hexor.authorization.audit.custody":
        findings.append("policy_id must be hexor.authorization.audit.custody")
    if document.get("state") not in {"DISABLED", "ENABLED"}:
        findings.append("state must be DISABLED or ENABLED")
    if document.get("default") != "deny":
        findings.append("default must be deny")
    if document.get("runtime_status") != "NOT_RUN":
        findings.append("runtime_status must remain NOT_RUN before live acceptance")
    if document.get("execution_authority") != "none":
        findings.append("authorization audit custody must never claim execution authority")

    custody = document.get("custody")
    if not isinstance(custody, Mapping):
        return findings + ["custody must be an object"]
    if set(custody) != CUSTODY_KEYS:
        findings.append("custody exact fields do not match canonical contract")
    if custody.get("evidence_plane_projection") != "required":
        findings.append("evidence_plane_projection must be required")
    if custody.get("classification") != "restricted":
        findings.append("authorization audit evidence classification must be restricted")
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
    if custody.get("include_raw_receipt") is not False:
        findings.append("raw authorization receipt custody must remain disabled")
    if custody.get("include_raw_authorization_ref") is not False:
        findings.append("raw authorization reference custody must remain disabled")
    return findings


def load_policy(path: Path | str = POLICY_PATH) -> dict[str, Any]:
    policy_path = Path(path)
    try:
        document = yaml.safe_load(policy_path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise AuthorizationAuditCustodyError(
            "POLICY_UNREADABLE",
            f"authorization audit custody policy cannot be read safely: {type(exc).__name__}",
        ) from exc
    except yaml.YAMLError as exc:
        raise AuthorizationAuditCustodyError(
            "POLICY_INVALID",
            f"authorization audit custody policy is invalid: {type(exc).__name__}",
        ) from exc
    findings = validate_policy(document)
    if findings:
        raise AuthorizationAuditCustodyError("POLICY_INVALID", "; ".join(findings))
    return dict(document)


class AuthorizationAuditCustody:
    """Project one sanitized authorization-audit record into Evidence Plane v2."""

    def __init__(self, policy: Mapping[str, Any]) -> None:
        findings = validate_policy(policy)
        if findings:
            raise AuthorizationAuditCustodyError("POLICY_INVALID", "; ".join(findings))
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
    ) -> AuthorizationAuditCustodyResult:
        if not self.enabled:
            raise AuthorizationAuditCustodyError(
                "CUSTODY_DISABLED",
                "authorization audit custody policy is disabled",
            )

        validated = _validate_event(event)
        corr = _correlation(correlation)
        timestamp = _parse_recorded_at(recorded_at)

        if evidence_store is None or not callable(getattr(evidence_store, "put", None)):
            raise AuthorizationAuditCustodyError(
                "EVIDENCE_STORE_UNAVAILABLE",
                "canonical Evidence Plane store is required",
            )
        if not callable(getattr(evidence_store, "verify", None)):
            raise AuthorizationAuditCustodyError(
                "EVIDENCE_STORE_UNAVAILABLE",
                "Evidence Plane integrity verification is required",
            )

        custody = self._policy["custody"]
        payload = _canonical_bytes(validated)
        payload_sha256 = evidence_contract.sha256_hex(payload)
        retain_until = _iso_z(
            timestamp + timedelta(days=int(custody["retention_days"]))
        )
        storage_ref = f"evidence://authorization-receipt-audit/{payload_sha256}"
        metadata = {
            "event_type": validated["event_type"],
            "phase": validated["phase"],
            "decision": validated["decision"],
            "reason_code": validated["reason_code"],
            "authorization_ref_sha256": validated["authorization_ref_sha256"],
            "duplicate": validated["duplicate"],
            "capability_id": validated["capability_id"],
            "intrusiveness_level": validated["intrusiveness_level"],
            "promotion_allowed": False,
            "runtime_status": "NOT_RUN",
            "execution_authority": "NONE",
        }

        try:
            record = evidence_contract.build_record(
                correlation=corr,
                classification=str(custody["classification"]),
                producer="authorization-receipt-audit-custody-v1",
                operation=f"authorization.audit.{validated['event_type']}",
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
        except Exception as exc:  # noqa: BLE001 - backend details must remain private
            raise AuthorizationAuditCustodyError(
                "EVIDENCE_PROJECTION_FAILED",
                "Evidence Plane authorization-audit projection failed safely: "
                f"{type(exc).__name__}",
            ) from exc

        try:
            verified = bool(evidence_store.verify(evidence_id))
        except Exception as exc:  # noqa: BLE001 - verification must fail closed
            raise AuthorizationAuditCustodyError(
                "EVIDENCE_VERIFICATION_FAILED",
                f"Evidence Plane verification failed safely: {type(exc).__name__}",
            ) from exc
        if not verified:
            raise AuthorizationAuditCustodyError(
                "EVIDENCE_VERIFICATION_FAILED",
                "Evidence Plane authorization-audit record failed integrity verification",
            )

        return AuthorizationAuditCustodyResult(
            evidence_id=str(evidence_id),
            evidence_ref=f"evidence://{evidence_id}",
            payload_sha256=payload_sha256,
            payload_size_bytes=len(payload),
            classification=str(custody["classification"]),
        )


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--policy", default=str(POLICY_PATH))
    parser.add_argument("command", choices=("validate",))
    args = parser.parse_args(list(argv) if argv is not None else None)
    try:
        policy = load_policy(args.policy)
        AuthorizationAuditCustody(policy)
    except AuthorizationAuditCustodyError as exc:
        print(f"FAIL {exc.code}: {exc}", file=sys.stderr)
        return 1
    print("OK authorization audit custody policy is fail-closed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
