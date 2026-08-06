from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any

import jsonschema
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from supervised_conformance import (  # noqa: E402
    CASES,
    FAMILY_ADAPTERS,
    SECRET_CANARY,
    build_parity,
    run_supervised_conformance,
)


@pytest.fixture(scope="module")
def report() -> dict[str, Any]:
    return run_supervised_conformance()


def test_supervised_family_inventory_is_fixed_and_repository_owned() -> None:
    assert set(FAMILY_ADAPTERS) == {"api", "devsecops", "ai-mcp"}
    for adapter in FAMILY_ADAPTERS.values():
        resolved = adapter.resolve()
        assert resolved.is_file()
        assert ROOT.parents[1] in resolved.parents


def test_repository_candidates_pass_cross_family_supervised_conformance(
    report: dict[str, Any],
) -> None:
    assert report["verdict"] == "PASS", report
    assert [family["family"] for family in report["families"]] == sorted(
        FAMILY_ADAPTERS
    )
    expected_cases = [case.case_id for case in CASES]
    for family in report["families"]:
        assert family["verdict"] == "PASS", family
        assert [case["case_id"] for case in family["cases"]] == expected_cases
        assert {case["status"] for case in family["cases"]} == {"PASS"}

    assert [case["case_id"] for case in report["parity"]] == expected_cases
    assert {case["status"] for case in report["parity"]} == {"PASS"}


def test_report_validates_against_canonical_schema(
    report: dict[str, Any],
) -> None:
    schema = json.loads(
        (
            ROOT / "schemas" / "supervised-conformance-report.schema.json"
        ).read_text(encoding="utf-8")
    )
    jsonschema.validate(report, schema)


def test_report_is_deterministic_and_contains_no_raw_process_material(
    report: dict[str, Any],
) -> None:
    second = run_supervised_conformance()

    assert report == second
    serialized = json.dumps(report, sort_keys=True)
    for forbidden in (
        SECRET_CANARY,
        "/bin/sh",
        "exit 99",
        "caller-controlled",
        "--durable-ledger",
        ".sqlite3",
        str(ROOT),
    ):
        assert forbidden not in serialized
    assert report["safety"] == {
        "raw_process_output_persisted": False,
        "request_controls_process_spec": False,
        "production_effect_claim": "none",
        "sandbox_status": "NOT_IMPLEMENTED",
        "runtime_declaration": "NO_RUNTIME_CHANGE",
    }


def test_parity_fails_when_one_family_signature_differs(
    report: dict[str, Any],
) -> None:
    mutated = json.loads(json.dumps(report["families"]))
    mutated[0]["cases"][0]["signature_sha256"] = "0" * 64

    parity = build_parity(mutated)

    success = next(case for case in parity if case["case_id"] == "success")
    assert success["status"] == "FAIL"
    assert "signatures differ" in success["detail"]


def test_cli_exposes_no_user_supplied_candidate_command() -> None:
    completed = subprocess.run(
        [sys.executable, str(ROOT / "supervised_conformance.py"), "--help"],
        check=True,
        capture_output=True,
        text=True,
    )

    assert "--command" not in completed.stdout
    assert "--output" in completed.stdout
