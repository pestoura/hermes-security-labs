#!/usr/bin/env python3
"""Custody bridge from sanitized Runner dispatch audit events to Evidence Plane v2.

This module creates no authorization, performs no Runner effect and owns no
separate audit datastore. A validated dispatch-audit event is persisted through
the existing Evidence Plane store as restricted evidence. The canonical policy
is disabled/not-run until live acceptance.
"""

from __future__ import annotations

import argparse
import hashlib
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
AUDIT_SCHEMA = REPOSITORY_ROOT / "platform" / "runner-dispatch" / "dispatch-audit-event.schema.json"
EVIDENCE_CONTRACT_PATH = HERE / "evidence_plane.py"
POLICY_PATH = HERE / "dispatch-audit-policy.yaml"


class DispatchAuditCustodyError(ValueError):
    """Stable fail-closed dispatch-audit custody error."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class AuditCustodyResult:
    evidence_id: str
    event_fingerprint: str
    payload_sha256: str
    classification: str

    def as_safe_dict(self) -> dict[str, str]:
        return {
            "evidence_id": self.evidence_id,
            "event_fingerprint": self.event_fingerprint,
            "payload_sha256": self.payload_sha256,
            "classification": self.classification,
        }


def _load_module(name: str, path: Path) -> Any:
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
    "dispatch_audit_evidence_plane_contract", EVIDENCE_CONTRACT_PATH
)


def _canonical_bytes(value: Mapping[str, Any]) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=True
    ).encode("utf-8")


def _event_fingerprint(event: Mapping[str, Any]) -> str:
    canonical = {
        key: value
        for key, value in event.items()
        if key not in {"recorded_at", "event_fingerprint"}
    }
    return hashlib.sha256(_canonical_bytes(canonical)).hexdigest()


def _validate_event(event: Mapping[str, Any]) -> None:
    if not isinstance(event, Mapping):
        raise DispatchAuditCustodyError("AUDIT_EVENT_INVALID", "audit event must be an object")
    try:
        schema = json.loads(AUDIT_SCHEMA.read_text(encoding="utf-8"))
    except (OSError, ValueError, UnicodeDecodeError) as exc:
        raise DispatchAuditCustodyError(
            "AUDIT_SCHEMA_UNAVAILABLE", "dispatch audit schema cannot be loaded"
        ) from exc
    validator = jsonschema.Draft202012Validator(
        schema, format_checker=jsonschema.FormatChecker()
    )
    errors = sorted(validator.iter_errors(event), key=lambda error: list(error.path))
    if errors:
        raise DispatchAuditCustodyError("AUDIT_EVENT_INVALID", errors[0].message)
    if _event_fingerprint(event) != event.get("event_fingerprint"):
        raise DispatchAuditCustodyError(
            "AUDIT_FINGERPRINT_MISMATCH", "dispatch audit fingerprint does not match event body"
        )


def _parse_recorded_at(value: Any) -> datetime:
    if not isinstance(value, str) or not value.endswith("Z"):
        raise DispatchAuditCustodyError(
            "AUDIT_TIMESTAMP_INVALID", "recorded_at must be an RFC3339 UTC timestamp ending in Z"
        )
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise DispatchAuditCustodyError(
            "AUDIT_TIMESTAMP_INVALID", "recorded_at is invalid"
        ) from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise DispatchAuditCustodyError(
            "AUDIT_TIMESTAMP_INVALID", "recorded_at must be timezone-aware"
        )
    return parsed.astimezone(timezone.utc)


def _iso_z(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def validate_policy(document: Any) -> list[str]:
    if not isinstance(document, Mapping):
        return ["dispatch audit custody policy must be an object"]
    findings: list[str] = []
    if document.get("schema_version") != "1.0":
        findings.append("schema_version must be '1.0'")
    if document.get("policy_id") != "hexor.runner.dispatch.audit.custody":
        findings.append("policy_id must be hexor.runner.dispatch.audit.custody")
    if document.get("state") not in {"DISABLED", "ENABLED"}:
        findings.append("state must be DISABLED or ENABLED")
    if document.get("default") != "deny":
        findings.append("default must be deny")
    if document.get("runtime_status") != "NOT_RUN":
        findings.append("runtime_status must remain NOT_RUN before live acceptance")
    if document.get("execution_authority") != "none":
        findings.append("audit custody must never claim execution authority")

    custody = document.get("custody")
    if not isinstance(custody, Mapping):
        return findings + ["custody must be an object"]
    expected = {
        "evidence_plane_projection",
        "classification",
        "retention_policy_id",
        "retention_days",
        "include_raw_application_payloads",
    }
    if set(custody) != expected:
        findings.append("custody exact fields do not match canonical contract")
    if custody.get("evidence_plane_projection") != "required":
        findings.append("evidence_plane_projection must be required")
    if custody.get("classification") != "restricted":
        findings.append("dispatch audit evidence classification must be restricted")
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
    if custody.get("include_raw_application_payloads") is not False:
        findings.append("raw application payload custody must remain disabled")
    return findings


def load_policy(path: Path | str = POLICY_PATH) -> dict[str, Any]:
    policy_path = Path(path)
    try:
        document = yaml.safe_load(policy_path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise DispatchAuditCustodyError("POLICY_UNREADABLE", str(exc)) from exc
    except yaml.YAMLError as exc:
        raise DispatchAuditCustodyError("POLICY_INVALID", str(exc)) from exc
    findings = validate_policy(document)
    if findings:
        raise DispatchAuditCustodyError("POLICY_INVALID", "; ".join(findings))
    return dict(document)


class DispatchAuditCustody:
    """Persist strict dispatch audit events into the existing Evidence Plane store."""

    def __init__(self, policy: Mapping[str, Any]) -> None:
        findings = validate_policy(policy)
        if findings:
            raise DispatchAuditCustodyError("POLICY_INVALID", "; ".join(findings))
        self._policy = dict(policy)

    @property
    def enabled(self) -> bool:
        return self._policy.get("state") == "ENABLED"

    def persist(
        self,
        event: Mapping[str, Any],
        *,
        evidence_store: Any,
    ) -> AuditCustodyResult:
        if not self.enabled:
            raise DispatchAuditCustodyError(
                "CUSTODY_DISABLED", "dispatch audit custody policy is disabled"
            )
        if evidence_store is None or not hasattr(evidence_store, "put"):
            raise DispatchAuditCustodyError(
                "EVIDENCE_STORE_UNAVAILABLE", "canonical Evidence Plane store is required"
            )
        if not hasattr(evidence_store, "verify"):
            raise DispatchAuditCustodyError(
                "EVIDENCE_STORE_UNAVAILABLE", "Evidence Plane integrity verification is required"
            )

        _validate_event(event)
        recorded_at = _parse_recorded_at(event["recorded_at"])
        custody = self._policy["custody"]
        payload = _canonical_bytes(event)
        payload_sha256 = evidence_contract.sha256_hex(payload)
        correlation = evidence_contract.Correlation(**dict(event["correlation"]))
        retain_until = _iso_z(
            recorded_at + timedelta(days=int(custody["retention_days"]))
        )
        storage_ref = (
            f"evidence://{event['correlation']['campaign_id']}/"
            f"{event['correlation']['run_id']}/runner-dispatch-audit/"
            f"{event['event_fingerprint']}/{payload_sha256}.json"
        )
        metadata: dict[str, Any] = {
            "principal_id": event["principal_id"],
            "transport": event["transport"],
            "capability_id": event["capability_id"],
            "phase": event["phase"],
            "decision": event["decision"],
            "reason_code": event["reason_code"],
            "event_fingerprint": event["event_fingerprint"],
            "target_sha256": event["target_sha256"],
        }
        if "adapter_id" in event:
            metadata["adapter_id"] = event["adapter_id"]
        if "terminal_status" in event:
            metadata["terminal_status"] = event["terminal_status"]

        try:
            record = evidence_contract.build_record(
                correlation=correlation,
                classification=str(custody["classification"]),
                producer="runner-dispatch-audit-custody-v1",
                operation=f"runner.dispatch.audit.{event['phase']}",
                protocol_version=str(event["schema_version"]),
                payload_sha256=payload_sha256,
                payload_size=len(payload),
                media_type="application/json",
                storage_ref=storage_ref,
                retention_policy_id=str(custody["retention_policy_id"]),
                retain_until=retain_until,
                legal_hold=False,
                metadata=metadata,
                created_at=str(event["recorded_at"]),
            )
            evidence_id = evidence_store.put(record, payload)
        except Exception as exc:  # noqa: BLE001 - backend details are not exposed
            raise DispatchAuditCustodyError(
                "EVIDENCE_PROJECTION_FAILED",
                f"Evidence Plane audit projection failed safely: {type(exc).__name__}",
            ) from exc

        try:
            verified = bool(evidence_store.verify(evidence_id))
        except Exception as exc:  # noqa: BLE001
            raise DispatchAuditCustodyError(
                "EVIDENCE_VERIFICATION_FAILED",
                f"Evidence Plane verification failed safely: {type(exc).__name__}",
            ) from exc
        if not verified:
            raise DispatchAuditCustodyError(
                "EVIDENCE_VERIFICATION_FAILED",
                "Evidence Plane audit record failed integrity verification",
            )

        return AuditCustodyResult(
            evidence_id=str(evidence_id),
            event_fingerprint=str(event["event_fingerprint"]),
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
        DispatchAuditCustody(policy)
    except DispatchAuditCustodyError as exc:
        print(f"FAIL {exc.code}: {exc}", file=sys.stderr)
        return 1
    print("OK dispatch audit custody policy is fail-closed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
