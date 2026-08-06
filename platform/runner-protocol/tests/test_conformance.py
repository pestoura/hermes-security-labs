from __future__ import annotations

import json
import sys
from pathlib import Path

import jsonschema

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from conformance import CASES, REFERENCE_ADAPTER, run_conformance, self_test  # noqa: E402


def _command(*extra: str) -> list[str]:
    return [sys.executable, str(REFERENCE_ADAPTER), *extra]


def test_reference_adapter_passes_every_case() -> None:
    report = run_conformance(_command(), "reference-adapter")
    assert report["verdict"] == "PASS", report
    assert [case["case_id"] for case in report["cases"]] == [
        case_id for case_id, _ in CASES
    ]
    assert {case["status"] for case in report["cases"]} == {"PASS"}
    assert all(len(case["evidence_sha256"]) == 64 for case in report["cases"])


def test_duplicate_effects_are_rejected() -> None:
    report = run_conformance(
        _command("--mode", "duplicate-effects"), "broken-duplicate-effects"
    )
    assert report["verdict"] == "FAIL"
    failed = {case["case_id"] for case in report["cases"] if case["status"] == "FAIL"}
    assert "idempotent-replay" in failed
    detail = next(
        case["detail"]
        for case in report["cases"]
        if case["case_id"] == "idempotent-replay"
    )
    assert "duplicated an effect" in detail


def test_secret_canary_leak_is_rejected_and_not_persisted_in_report() -> None:
    report = run_conformance(_command("--mode", "secret-leak"), "broken-secret-leak")
    assert report["verdict"] in {"FAIL", "ERROR"}
    serialized = json.dumps(report, sort_keys=True)
    assert "RUNNER_PROTOCOL_CONFORMANCE_SECRET_CANARY_7F3A" not in serialized
    assert "secret canary" in serialized


def test_report_validates_against_canonical_schema() -> None:
    report = run_conformance(_command(), "reference-adapter")
    schema = json.loads(
        (ROOT / "schemas" / "conformance-report.schema.json").read_text(encoding="utf-8")
    )
    jsonschema.validate(report, schema)


def test_report_contains_no_raw_candidate_command() -> None:
    command = _command()
    report = run_conformance(command, "reference-adapter")
    serialized = json.dumps(report, sort_keys=True)
    assert str(REFERENCE_ADAPTER) not in serialized
    assert "command_sha256" in report


def test_self_test_exercises_good_and_bad_adapters() -> None:
    self_test()
