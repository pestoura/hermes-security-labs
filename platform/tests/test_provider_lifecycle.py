from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
PATH = ROOT / "platform/vulnerability-validation/provider_lifecycle.py"
spec = importlib.util.spec_from_file_location("provider_lifecycle", PATH)
assert spec and spec.loader
module = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = module
spec.loader.exec_module(module)

PROVIDER_ID = "vp_" + "a" * 32
ARTIFACT = "b" * 64


def _chain():
    quarantine = module.quarantine_receipt(
        provider_id=PROVIDER_ID,
        artifact_sha256=ARTIFACT,
        observed_at="2026-08-08T22:00:00Z",
    )
    review = module.review_receipt(
        quarantine=quarantine,
        reviewed_by="reviewer-01",
        reviewed_at="2026-08-08T22:05:00Z",
        signature_verified=True,
    )
    return quarantine, review


def test_external_provider_release_requires_complete_quarantine_review_chain() -> None:
    quarantine, review = _chain()
    assert module.external_provider_release_allowed(
        provider_id=PROVIDER_ID,
        artifact_sha256=ARTIFACT,
        quarantine=quarantine,
        review=review,
    ) is True


def test_review_cannot_be_created_without_quarantine_receipt() -> None:
    with pytest.raises(module.ProviderLifecycleError, match="VALID_QUARANTINE_RECEIPT_REQUIRED"):
        module.review_receipt(
            quarantine={"state": "REVIEWED"},
            reviewed_by="reviewer-01",
            reviewed_at="2026-08-08T22:05:00Z",
            signature_verified=True,
        )


def test_tampered_quarantine_receipt_blocks_release() -> None:
    quarantine, review = _chain()
    quarantine["artifact_sha256"] = "c" * 64
    assert module.external_provider_release_allowed(
        provider_id=PROVIDER_ID,
        artifact_sha256=ARTIFACT,
        quarantine=quarantine,
        review=review,
    ) is False


def test_review_without_verified_signature_is_rejected() -> None:
    quarantine, _ = _chain()
    with pytest.raises(module.ProviderLifecycleError, match="VERIFIED_SIGNATURE_REQUIRED"):
        module.review_receipt(
            quarantine=quarantine,
            reviewed_by="reviewer-01",
            reviewed_at="2026-08-08T22:05:00Z",
            signature_verified=False,
        )


def test_review_receipt_is_bound_to_exact_provider_artifact() -> None:
    quarantine, review = _chain()
    assert module.external_provider_release_allowed(
        provider_id=PROVIDER_ID,
        artifact_sha256="d" * 64,
        quarantine=quarantine,
        review=review,
    ) is False
