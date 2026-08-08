from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
PATH = ROOT / "platform/extensions/certification_evidence.py"
spec = importlib.util.spec_from_file_location("certification_evidence", PATH)
assert spec and spec.loader
evidence = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = evidence
spec.loader.exec_module(evidence)


def _manifest():
    return {
        "permissions": ["evidence:read"],
        "signature": {"state": "verified", "artifact_sha256": "a" * 64},
        "conformance": {"passed": True, "report_sha256": "b" * 64},
        "compatibility": {"compatible": True},
    }


def test_green_certification_evidence_is_accepted() -> None:
    evidence.validate_certification_evidence(_manifest())


@pytest.mark.parametrize("field,value,code", [
    ("artifact", "z" * 64, "ARTIFACT_SHA256_INVALID"),
    ("report", "g" * 64, "CONFORMANCE_REPORT_SHA256_INVALID"),
])
def test_non_hex_digest_is_rejected(field: str, value: str, code: str) -> None:
    manifest = _manifest()
    if field == "artifact":
        manifest["signature"]["artifact_sha256"] = value
    else:
        manifest["conformance"]["report_sha256"] = value
    with pytest.raises(evidence.CertificationEvidenceError, match=code):
        evidence.validate_certification_evidence(manifest)


def test_failed_conformance_or_compatibility_blocks_certification_evidence() -> None:
    manifest = _manifest()
    manifest["conformance"]["passed"] = False
    with pytest.raises(evidence.CertificationEvidenceError, match="CONFORMANCE_NOT_PASSED"):
        evidence.validate_certification_evidence(manifest)
    manifest = _manifest()
    manifest["compatibility"]["compatible"] = False
    with pytest.raises(evidence.CertificationEvidenceError, match="CONTRACT_INCOMPATIBLE"):
        evidence.validate_certification_evidence(manifest)
