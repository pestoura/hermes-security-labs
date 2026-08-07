"""Read-only orphan resource assessment for transactional lab lifecycle.

The assessor consumes a normalized observation supplied by a future read-only
runtime scanner. It does not enumerate Docker, Kubernetes, processes, mounts or
networks itself and it never performs cleanup, quarantine, stop, delete or any
other runtime mutation.

A structurally valid partial/unavailable scan can never produce ``CLEAR``.
Definite orphan evidence still produces ``ORPHANS_DETECTED`` even when the
snapshot is partial. Resource references are opaque identifiers only; raw paths,
targets, commands, sockets and credentials are outside this contract.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable, Mapping

import jsonschema

ROOT = Path(__file__).resolve().parent
ACTIVE_RESOURCE_STATES = {"PROVISIONING", "READY", "RUNNING", "RESETTING"}
CLEANUP_STATES = {"DESTROYING", "ROLLING_BACK", "VERIFYING_RESIDUE"}


class OrphanAssessmentError(ValueError):
    """Raised with a stable code when an observation cannot be trusted."""


@dataclass(frozen=True)
class OrphanAssessmentResult:
    assessment_built: bool
    codes: tuple[str, ...]
    result: str
    observation_id: str | None
    scanner_state: str | None
    orphan_count: int
    tracked_quarantine_count: int
    assessment: dict[str, Any] | None = field(repr=False, default=None)

    @classmethod
    def refuse(
        cls,
        codes: Iterable[str],
        observation: Mapping[str, Any] | None,
    ) -> "OrphanAssessmentResult":
        return cls(
            assessment_built=False,
            codes=tuple(dict.fromkeys(codes)) or ("ORPHAN_OBSERVATION_INVALID",),
            result="INCONCLUSIVE",
            observation_id=_safe_string(observation, "observation_id"),
            scanner_state=_safe_string(observation, "scanner_state"),
            orphan_count=0,
            tracked_quarantine_count=0,
            assessment=None,
        )

    def sanitized_summary(self) -> dict[str, Any]:
        """Return log-safe counts/codes without resource references."""

        return {
            "assessment_built": bool(self.assessment_built),
            "codes": list(self.codes),
            "result": self.result,
            "observation_id": self.observation_id,
            "scanner_state": self.scanner_state,
            "orphan_count": int(self.orphan_count),
            "tracked_quarantine_count": int(self.tracked_quarantine_count),
            "assessment_present": self.assessment is not None,
            "cleanup_performed": False,
        }


def assess_orphans(observation: Mapping[str, Any]) -> OrphanAssessmentResult:
    """Assess a normalized resource snapshot without performing cleanup."""

    try:
        validate_observation(observation)
    except OrphanAssessmentError as exc:
        return OrphanAssessmentResult.refuse((str(exc),), observation)
    except Exception:  # noqa: BLE001 - malformed integration fails closed
        return OrphanAssessmentResult.refuse(
            ("ORPHAN_OBSERVATION_INTEGRATION_ERROR",), observation
        )

    observed_at = _parse_datetime(str(observation["observed_at"]))
    records = {str(item["lab_id"]): item for item in observation["lifecycle_records"]}
    findings: list[dict[str, str]] = []

    for resource in sorted(
        observation["resources"], key=lambda item: str(item["resource_ref"])
    ):
        finding = _classify_resource(resource, records, observed_at)
        if finding is not None:
            findings.append(finding)

    orphan_count = sum(item["classification"] == "ORPHAN" for item in findings)
    tracked_quarantine_count = sum(
        item["classification"] == "TRACKED_QUARANTINE" for item in findings
    )
    scanner_state = str(observation["scanner_state"])

    codes: list[str] = []
    if orphan_count:
        result = "ORPHANS_DETECTED"
        codes.append("ORPHANS_FOUND")
    elif scanner_state == "COMPLETE":
        result = "CLEAR"
        codes.append("CLEAR_COMPLETE")
    else:
        result = "INCONCLUSIVE"

    if scanner_state == "PARTIAL":
        codes.append("SCAN_PARTIAL")
    elif scanner_state == "UNAVAILABLE":
        codes.append("SCAN_UNAVAILABLE")
    if tracked_quarantine_count:
        codes.append("TRACKED_QUARANTINE_PRESENT")

    assessment = {
        "schema_version": "1.0.0",
        "observation_id": str(observation["observation_id"]),
        "observed_at": str(observation["observed_at"]),
        "scanner_state": scanner_state,
        "result": result,
        "codes": codes,
        "orphan_count": orphan_count,
        "tracked_quarantine_count": tracked_quarantine_count,
        "cleanup_performed": False,
        "findings": findings,
    }
    try:
        validate_assessment(assessment)
    except OrphanAssessmentError as exc:
        return OrphanAssessmentResult.refuse((str(exc),), observation)

    return OrphanAssessmentResult(
        assessment_built=True,
        codes=tuple(codes),
        result=result,
        observation_id=str(observation["observation_id"]),
        scanner_state=scanner_state,
        orphan_count=orphan_count,
        tracked_quarantine_count=tracked_quarantine_count,
        assessment=assessment,
    )


def validate_observation(observation: Mapping[str, Any]) -> None:
    if not isinstance(observation, Mapping):
        raise OrphanAssessmentError("ORPHAN_OBSERVATION_SCHEMA_INVALID")
    _validate_against_schema(
        observation,
        ROOT / "orphan-observation.schema.json",
        "ORPHAN_OBSERVATION_SCHEMA_INVALID",
    )

    _parse_datetime(str(observation["observed_at"]))
    records = observation["lifecycle_records"]
    lab_ids = [str(item["lab_id"]) for item in records]
    if len(lab_ids) != len(set(lab_ids)):
        raise OrphanAssessmentError("DUPLICATE_LIFECYCLE_LAB")

    resource_refs = [str(item["resource_ref"]) for item in observation["resources"]]
    if len(resource_refs) != len(set(resource_refs)):
        raise OrphanAssessmentError("DUPLICATE_RESOURCE_REF")

    if observation["scanner_state"] == "UNAVAILABLE" and observation["resources"]:
        raise OrphanAssessmentError("UNAVAILABLE_SCAN_HAS_RESOURCES")

    for record in records:
        _parse_datetime(str(record["contract_expires_at"]))
        retention = record["quarantine_retention_until"]
        if record["state"] != "QUARANTINED" and retention is not None:
            raise OrphanAssessmentError("RETENTION_ON_NON_QUARANTINED")
        if retention is not None:
            _parse_datetime(str(retention))


def validate_assessment(assessment: Mapping[str, Any]) -> None:
    _validate_against_schema(
        assessment,
        ROOT / "orphan-assessment.schema.json",
        "ORPHAN_ASSESSMENT_SCHEMA_INVALID",
    )


def _classify_resource(
    resource: Mapping[str, Any],
    records: Mapping[str, Mapping[str, Any]],
    observed_at: datetime,
) -> dict[str, str] | None:
    lab_id = str(resource["lab_id"])
    record = records.get(lab_id)
    if record is None:
        return _finding(resource, "ORPHAN_UNKNOWN_LAB", "ORPHAN")
    if str(resource["campaign_id"]) != str(record["campaign_id"]):
        return _finding(resource, "ORPHAN_CAMPAIGN_MISMATCH", "ORPHAN")

    state = str(record["state"])
    if state == "DECLARED":
        return _finding(resource, "ORPHAN_BEFORE_PROVISIONING", "ORPHAN")
    if state == "VERIFIED":
        return _finding(resource, "ORPHAN_AFTER_VERIFIED", "ORPHAN")

    if state == "QUARANTINED":
        retention = record["quarantine_retention_until"]
        if retention is None:
            return _finding(
                resource,
                "ORPHAN_QUARANTINE_RETENTION_UNDECLARED",
                "ORPHAN",
            )
        if observed_at >= _parse_datetime(str(retention)):
            return _finding(
                resource,
                "ORPHAN_QUARANTINE_RETENTION_EXPIRED",
                "ORPHAN",
            )
        return _finding(
            resource,
            "TRACKED_QUARANTINE_RESIDUE",
            "TRACKED_QUARANTINE",
        )

    if state in ACTIVE_RESOURCE_STATES and observed_at >= _parse_datetime(
        str(record["contract_expires_at"])
    ):
        return _finding(resource, "ORPHAN_EXPIRED_CONTRACT", "ORPHAN")

    if state in ACTIVE_RESOURCE_STATES or state in CLEANUP_STATES:
        return None

    # Schema validation makes this branch unreachable, but fail-safe if the
    # lifecycle state set changes without assessor review.
    return _finding(resource, "ORPHAN_UNKNOWN_LAB", "ORPHAN")


def _finding(
    resource: Mapping[str, Any],
    code: str,
    classification: str,
) -> dict[str, str]:
    return {
        "resource_ref": str(resource["resource_ref"]),
        "kind": str(resource["kind"]),
        "lab_id": str(resource["lab_id"]),
        "code": code,
        "classification": classification,
    }


def _validate_against_schema(
    value: Mapping[str, Any],
    path: Path,
    error_code: str,
) -> None:
    schema = json.loads(path.read_text(encoding="utf-8"))
    validator = jsonschema.Draft202012Validator(
        schema,
        format_checker=jsonschema.FormatChecker(),
    )
    if list(validator.iter_errors(value)):
        raise OrphanAssessmentError(error_code)


def _parse_datetime(value: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise OrphanAssessmentError("INVALID_DATETIME") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise OrphanAssessmentError("TIMEZONE_REQUIRED")
    return parsed


def _safe_string(value: Any, key: str) -> str | None:
    if not isinstance(value, Mapping):
        return None
    candidate = value.get(key)
    return candidate if isinstance(candidate, str) else None
