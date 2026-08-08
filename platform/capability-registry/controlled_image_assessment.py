from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import sys
from pathlib import Path
from typing import Any, Mapping

HERE = Path(__file__).resolve().parent
BLOCKER_SEVERITIES = {"HIGH", "CRITICAL"}


def _load(name: str, filename: str):
    existing = sys.modules.get(name)
    if existing is not None:
        return existing
    spec = importlib.util.spec_from_file_location(name, HERE / filename)
    if not spec or not spec.loader:
        raise RuntimeError(f"cannot load {filename}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


controlled = _load("_hex0r_controlled_supply_chain", "controlled_supply_chain_ci.py")
gate = _load("_hex0r_supply_chain_gate", "supply_chain_gate.py")


class ControlledImageAssessmentError(ValueError):
    pass


def _sha256(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


def count_blockers(report: Mapping[str, Any]) -> int:
    if not isinstance(report, Mapping):
        raise ControlledImageAssessmentError("TRIVY_REPORT_REQUIRED")
    results = report.get("Results", [])
    if not isinstance(results, list):
        raise ControlledImageAssessmentError("TRIVY_RESULTS_INVALID")
    blockers = 0
    for result in results:
        if not isinstance(result, Mapping):
            raise ControlledImageAssessmentError("TRIVY_RESULT_INVALID")
        vulnerabilities = result.get("Vulnerabilities") or []
        if not isinstance(vulnerabilities, list):
            raise ControlledImageAssessmentError("TRIVY_VULNERABILITIES_INVALID")
        for vulnerability in vulnerabilities:
            if not isinstance(vulnerability, Mapping):
                raise ControlledImageAssessmentError("TRIVY_VULNERABILITY_INVALID")
            severity = str(vulnerability.get("Severity", "")).upper()
            if severity in BLOCKER_SEVERITIES:
                blockers += 1
    return blockers


def build_assessment_bundle(*, image_tar: bytes, report: Mapping[str, Any], source_ref: str) -> dict[str, Any]:
    if not image_tar:
        raise ControlledImageAssessmentError("IMAGE_TAR_REQUIRED")
    blockers = count_blockers(report)
    bundle = controlled.build_controlled_bundle(artifact=image_tar, source_ref=source_ref)
    report_bytes = json.dumps(report, sort_keys=True, separators=(",", ":")).encode("utf-8")
    bundle["scan"] = {
        "subject_digest": bundle["subject_digest"],
        "artifact_digest": _sha256(report_bytes),
        "scanner": "Trivy",
        "scanner_version": "v0.70.0",
        "blocker_severities": sorted(BLOCKER_SEVERITIES),
        "blockers": blockers,
        "status": "PASS" if blockers == 0 else "BLOCKED",
    }
    if blockers == 0:
        gate.validate_stable_supply_chain(bundle)
        bundle["stable_promotion"] = "ELIGIBLE_CONTROLLED_CI"
    else:
        bundle["stable_promotion"] = "BLOCKED_BY_SCAN"
    bundle["production_image"] = "NOT_RUN"
    return bundle


def main() -> int:
    parser = argparse.ArgumentParser(description="Build controlled C-02 image assessment evidence")
    parser.add_argument("--image-tar", required=True)
    parser.add_argument("--report", required=True)
    parser.add_argument("--source-ref", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    image_tar = Path(args.image_tar).read_bytes()
    report = json.loads(Path(args.report).read_text(encoding="utf-8"))
    bundle = build_assessment_bundle(image_tar=image_tar, report=report, source_ref=args.source_ref)
    Path(args.output).write_text(json.dumps(bundle, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    print(f"C02_IMAGE_ASSESSMENT\tblockers={bundle['scan']['blockers']}\tpromotion={bundle['stable_promotion']}")
    return 0 if bundle["scan"]["blockers"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
