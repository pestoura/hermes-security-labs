from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
PATH = ROOT / "platform/vulnerability-validation/controlled_provider_session.py"
spec = importlib.util.spec_from_file_location("controlled_provider_session", PATH)
assert spec and spec.loader
module = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = module
spec.loader.exec_module(module)


def _kwargs() -> dict:
    return {
        "provider_type": "vendor_validation",
        "artifact_sha256": "b" * 64,
        "observed_at": "2026-08-08T22:20:00Z",
        "reviewed_by": "reviewer-01",
        "reviewed_at": "2026-08-08T22:25:00Z",
        "trust_level": "SIGNED_VENDOR",
        "vulnerability_id": "CVE-2099-0001",
        "knowledge_snapshot_id": "ks_" + "a" * 32,
        "rationale": "controlled provider governance evidence",
    }


def test_session_proves_quarantine_review_and_non_authorizing_proposal() -> None:
    result = module.assess_external_provider(**_kwargs())
    assert result["runtime_eligible"] is True
    assert result["proposal_state"] == "PROPOSAL_ONLY"
    assert result["proposal_executable"] is False
    assert result["authorization_source"] == "CONTROL_PLANE_ONLY"
    assert result["external_content_executed"] is False
    assert result["execution_authority"] == "NONE"
    assert result["quarantine_receipt_id"].startswith("qr_")
    assert result["review_receipt_id"].startswith("rr_")


def test_invalid_artifact_digest_fails_closed() -> None:
    value = _kwargs()
    value["artifact_sha256"] = "not-a-digest"
    with pytest.raises(Exception, match="ARTIFACT_SHA256_INVALID"):
        module.assess_external_provider(**value)


def test_unreviewed_trust_level_cannot_be_released() -> None:
    value = _kwargs()
    value["trust_level"] = "TRUSTED_BUILTIN"
    with pytest.raises(Exception, match="reviewed trust level"):
        module.assess_external_provider(**value)
