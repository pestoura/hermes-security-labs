from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
EPIC_09 = ROOT / "docs/roadmap/epics/EPIC-09-exploitation-safety.md"

MAIN_SHA = "0948b73a047996c2df788b33d365e7871af758aa"


def test_inventory_attestation_evidence_is_reconciled_without_final_promotion() -> None:
    text = EPIC_09.read_text(encoding="utf-8")

    assert "Document version | 1.4.0" in text
    assert "PR #202" in text
    assert MAIN_SHA in text
    assert "active_attempt_inventory_attestation.py" in text
    assert "RUNNER_SUPERVISOR_INVENTORY_ATTESTATION_V1" in text
    assert "| AS_BUILT | yes |" in text
    assert "| FINAL | no |" in text
    assert "NO_RUNTIME_CHANGE" in text


def test_verified_source_does_not_become_independent_completeness_claim() -> None:
    text = EPIC_09.read_text(encoding="utf-8")

    assert "source_authenticity=EXTERNALLY_VERIFIED" in text
    assert "source_completeness=SOURCE_DECLARED_COMPLETE_NOT_INDEPENDENTLY_VERIFIED" in text
    assert "independent inventory completeness proof: `NOT_IMPLEMENTED` / `NOT_RUN`" in text
    assert "authoritative runtime supervisor integration: `NOT_IMPLEMENTED` / `NOT_RUN`" in text
    assert (
        "production inventory-attestation trust-store/key distribution/rotation: `NOT_IMPLEMENTED` / `NOT_RUN`"
        in text
    )


def test_attestation_never_claims_dispatch_or_execution_authority() -> None:
    text = EPIC_09.read_text(encoding="utf-8")

    assert "authorization_effect=NONE" in text
    assert "execution_authority=NONE" in text
    assert "dispatch_performed=false" in text
    assert "cancellation request dispatch to runtime Runner: `NOT_IMPLEMENTED` / `NOT_RUN`" in text
    assert "cooperative process interruption: `NOT_IMPLEMENTED` / `NOT_RUN`" in text
    assert "force-after-grace interruption: `NOT_IMPLEMENTED` / `NOT_RUN`" in text
    assert "sole execution-authorization authority" in text
    assert "never create or expand an `authorization_ref`" in text
