"""Repository-only tests for the read-only B-03 orphan resource assessor."""

from __future__ import annotations

import copy
import importlib.util
import json
import sys
from pathlib import Path
from typing import Any

import jsonschema

ROOT = Path(__file__).resolve().parents[2]
LIFECYCLE_DIR = ROOT / "platform/lab-lifecycle"


def _load(module_name: str, path: Path) -> Any:
    spec = importlib.util.spec_from_file_location(module_name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


orphan = _load("lab_orphan_detector_under_test", LIFECYCLE_DIR / "orphan_detector.py")


def _record(
    *,
    lab_id: str = "lab-001",
    campaign_id: str = "campaign-001",
    state: str = "RUNNING",
    expires_at: str = "2026-08-07T20:00:00Z",
    retention: str | None = None,
) -> dict[str, Any]:
    return {
        "lab_id": lab_id,
        "campaign_id": campaign_id,
        "state": state,
        "contract_expires_at": expires_at,
        "quarantine_retention_until": retention,
    }


def _resource(
    *,
    ref: str = "resource-001",
    kind: str = "container",
    lab_id: str = "lab-001",
    campaign_id: str = "campaign-001",
) -> dict[str, Any]:
    return {
        "resource_ref": ref,
        "kind": kind,
        "lab_id": lab_id,
        "campaign_id": campaign_id,
    }


def _observation(
    *,
    scanner_state: str = "COMPLETE",
    records: list[dict[str, Any]] | None = None,
    resources: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    return {
        "schema_version": "1.0.0",
        "observation_id": "orphan-observation-001",
        "observed_at": "2026-08-07T18:30:00Z",
        "scanner_state": scanner_state,
        "lifecycle_records": records if records is not None else [_record()],
        "resources": resources if resources is not None else [_resource()],
    }


def _finding_code(result: Any) -> str:
    assert result.assessment is not None
    assert len(result.assessment["findings"]) == 1
    return str(result.assessment["findings"][0]["code"])


def test_complete_scan_with_known_active_resource_is_clear() -> None:
    result = orphan.assess_orphans(_observation())

    assert result.assessment_built is True
    assert result.result == "CLEAR"
    assert result.codes == ("CLEAR_COMPLETE",)
    assert result.orphan_count == 0
    assert result.tracked_quarantine_count == 0
    assert result.assessment is not None
    assert result.assessment["cleanup_performed"] is False
    assert result.assessment["findings"] == []


def test_partial_scan_without_definite_orphan_is_inconclusive() -> None:
    result = orphan.assess_orphans(_observation(scanner_state="PARTIAL"))

    assert result.assessment_built is True
    assert result.result == "INCONCLUSIVE"
    assert result.codes == ("SCAN_PARTIAL",)
    assert result.orphan_count == 0


def test_partial_scan_with_definite_orphan_reports_orphan_and_scan_limitation() -> None:
    value = _observation(scanner_state="PARTIAL", records=[])
    result = orphan.assess_orphans(value)

    assert result.assessment_built is True
    assert result.result == "ORPHANS_DETECTED"
    assert result.codes == ("ORPHANS_FOUND", "SCAN_PARTIAL")
    assert _finding_code(result) == "ORPHAN_UNKNOWN_LAB"


def test_unavailable_scan_is_inconclusive_only_when_resource_snapshot_is_empty() -> None:
    valid = orphan.assess_orphans(
        _observation(scanner_state="UNAVAILABLE", resources=[])
    )
    assert valid.assessment_built is True
    assert valid.result == "INCONCLUSIVE"
    assert valid.codes == ("SCAN_UNAVAILABLE",)

    invalid = orphan.assess_orphans(_observation(scanner_state="UNAVAILABLE"))
    assert invalid.assessment_built is False
    assert invalid.codes == ("UNAVAILABLE_SCAN_HAS_RESOURCES",)


def test_unknown_lab_resource_is_orphan() -> None:
    result = orphan.assess_orphans(_observation(records=[]))

    assert result.result == "ORPHANS_DETECTED"
    assert _finding_code(result) == "ORPHAN_UNKNOWN_LAB"


def test_campaign_mismatch_is_orphan() -> None:
    result = orphan.assess_orphans(
        _observation(resources=[_resource(campaign_id="campaign-other")])
    )

    assert result.result == "ORPHANS_DETECTED"
    assert _finding_code(result) == "ORPHAN_CAMPAIGN_MISMATCH"


def test_resource_before_provisioning_is_orphan() -> None:
    result = orphan.assess_orphans(_observation(records=[_record(state="DECLARED")]))

    assert result.result == "ORPHANS_DETECTED"
    assert _finding_code(result) == "ORPHAN_BEFORE_PROVISIONING"


def test_resource_after_verified_is_orphan() -> None:
    result = orphan.assess_orphans(_observation(records=[_record(state="VERIFIED")]))

    assert result.result == "ORPHANS_DETECTED"
    assert _finding_code(result) == "ORPHAN_AFTER_VERIFIED"


def test_expired_active_contract_resource_is_orphan() -> None:
    result = orphan.assess_orphans(
        _observation(
            records=[
                _record(state="RUNNING", expires_at="2026-08-07T18:00:00Z")
            ]
        )
    )

    assert result.result == "ORPHANS_DETECTED"
    assert _finding_code(result) == "ORPHAN_EXPIRED_CONTRACT"


def test_cleanup_state_resource_is_not_orphan_even_after_contract_expiry() -> None:
    for state in ("DESTROYING", "ROLLING_BACK", "VERIFYING_RESIDUE"):
        result = orphan.assess_orphans(
            _observation(
                records=[_record(state=state, expires_at="2026-08-07T18:00:00Z")]
            )
        )
        assert result.result == "CLEAR"
        assert result.orphan_count == 0


def test_quarantine_residue_with_live_retention_is_explicitly_tracked() -> None:
    result = orphan.assess_orphans(
        _observation(
            records=[
                _record(
                    state="QUARANTINED",
                    expires_at="2026-08-07T17:00:00Z",
                    retention="2026-08-08T18:30:00Z",
                )
            ]
        )
    )

    assert result.result == "TRACKED_RESIDUE"
    assert result.orphan_count == 0
    assert result.tracked_quarantine_count == 1
    assert result.codes == ("TRACKED_QUARANTINE_PRESENT",)
    assert _finding_code(result) == "TRACKED_QUARANTINE_RESIDUE"
    assert result.assessment is not None
    assert result.assessment["findings"][0]["classification"] == "TRACKED_QUARANTINE"


def test_quarantine_without_retention_is_orphan() -> None:
    result = orphan.assess_orphans(
        _observation(records=[_record(state="QUARANTINED", retention=None)])
    )

    assert result.result == "ORPHANS_DETECTED"
    assert _finding_code(result) == "ORPHAN_QUARANTINE_RETENTION_UNDECLARED"


def test_expired_quarantine_retention_is_orphan() -> None:
    result = orphan.assess_orphans(
        _observation(
            records=[
                _record(
                    state="QUARANTINED",
                    retention="2026-08-07T18:00:00Z",
                )
            ]
        )
    )

    assert result.result == "ORPHANS_DETECTED"
    assert _finding_code(result) == "ORPHAN_QUARANTINE_RETENTION_EXPIRED"


def test_retention_is_not_artificially_bound_to_authorization_expiry() -> None:
    result = orphan.assess_orphans(
        _observation(
            records=[
                _record(
                    state="QUARANTINED",
                    expires_at="2026-08-08T20:00:00Z",
                    retention="2026-08-07T19:00:00Z",
                )
            ]
        )
    )

    assert result.result == "TRACKED_RESIDUE"
    assert result.tracked_quarantine_count == 1


def test_retention_on_non_quarantined_lab_is_invalid() -> None:
    result = orphan.assess_orphans(
        _observation(records=[_record(retention="2026-08-08T18:30:00Z")])
    )

    assert result.assessment_built is False
    assert result.codes == ("RETENTION_ON_NON_QUARANTINED",)


def test_duplicate_lifecycle_lab_is_rejected() -> None:
    value = _observation(records=[_record(), copy.deepcopy(_record())])
    result = orphan.assess_orphans(value)

    assert result.assessment_built is False
    assert result.codes == ("DUPLICATE_LIFECYCLE_LAB",)


def test_duplicate_resource_reference_is_rejected() -> None:
    value = _observation(resources=[_resource(), copy.deepcopy(_resource())])
    result = orphan.assess_orphans(value)

    assert result.assessment_built is False
    assert result.codes == ("DUPLICATE_RESOURCE_REF",)


def test_raw_paths_and_extra_secret_fields_are_not_accepted() -> None:
    path_value = _observation(resources=[_resource(ref="/var/run/docker.sock")])
    assert orphan.assess_orphans(path_value).codes == (
        "ORPHAN_OBSERVATION_SCHEMA_INVALID",
    )

    secret_value = _observation()
    secret_value["resources"][0]["token"] = "not-allowed"
    assert orphan.assess_orphans(secret_value).codes == (
        "ORPHAN_OBSERVATION_SCHEMA_INVALID",
    )


def test_findings_are_deterministically_sorted_by_opaque_resource_ref() -> None:
    value = _observation(
        records=[],
        resources=[
            _resource(ref="resource-z", lab_id="unknown-z"),
            _resource(ref="resource-a", lab_id="unknown-a"),
        ],
    )
    result = orphan.assess_orphans(value)

    assert result.assessment is not None
    assert [item["resource_ref"] for item in result.assessment["findings"]] == [
        "resource-a",
        "resource-z",
    ]


def test_assessment_validates_against_strict_schema_and_never_claims_cleanup() -> None:
    result = orphan.assess_orphans(_observation(records=[]))
    assert result.assessment is not None

    schema = json.loads(
        (LIFECYCLE_DIR / "orphan-assessment.schema.json").read_text(
            encoding="utf-8"
        )
    )
    jsonschema.Draft202012Validator(
        schema, format_checker=jsonschema.FormatChecker()
    ).validate(result.assessment)
    assert result.assessment["cleanup_performed"] is False


def test_result_repr_and_sanitized_summary_do_not_expose_resource_refs() -> None:
    value = _observation(records=[], resources=[_resource(ref="opaque-sensitive-ref")])
    result = orphan.assess_orphans(value)

    assert "opaque-sensitive-ref" not in repr(result)
    summary = json.dumps(result.sanitized_summary(), sort_keys=True)
    assert "opaque-sensitive-ref" not in summary
    assert "cleanup_performed" in summary
    assert result.sanitized_summary()["cleanup_performed"] is False
