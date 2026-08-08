from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
PATH = ROOT / "platform/capability-registry/controlled_image_assessment.py"
spec = importlib.util.spec_from_file_location("controlled_image_assessment", PATH)
assert spec and spec.loader
module = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = module
spec.loader.exec_module(module)


def test_zero_high_critical_findings_has_zero_blockers() -> None:
    report = {
        "Results": [
            {
                "Target": "fixture",
                "Vulnerabilities": [
                    {"VulnerabilityID": "CVE-1", "Severity": "LOW"},
                    {"VulnerabilityID": "CVE-2", "Severity": "MEDIUM"},
                ],
            }
        ]
    }
    assert module.count_blockers(report) == 0


def test_high_and_critical_findings_are_blockers() -> None:
    report = {
        "Results": [
            {
                "Vulnerabilities": [
                    {"VulnerabilityID": "CVE-1", "Severity": "HIGH"},
                    {"VulnerabilityID": "CVE-2", "Severity": "CRITICAL"},
                ]
            }
        ]
    }
    assert module.count_blockers(report) == 2


def test_invalid_report_fails_closed() -> None:
    with pytest.raises(module.ControlledImageAssessmentError, match="TRIVY_RESULTS_INVALID"):
        module.count_blockers({"Results": {}})
