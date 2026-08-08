from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
EPIC_09 = ROOT / "docs/roadmap/epics/EPIC-09-exploitation-safety.md"

INVENTORY_MAIN_SHA = "0948b73a047996c2df788b33d365e7871af758aa"
RUNTIME_DRILL_MAIN_SHA = "4c1b29192ede22611c3be8311b852136b418b81a"
SUBPROCESS_MAIN_SHA = "d489e77403c8ab1ae8f5780d875a5ec81f6d065a"
CAMPAIGN_MAIN_SHA = "9654426979b77f28fceb4bab1b9b06f97a0ee310"


def test_inventory_attestation_evidence_is_reconciled_without_final_promotion() -> None:
    text = EPIC_09.read_text(encoding="utf-8")

    assert "Document version | 1.6.0" in text
    assert "PR #202" in text
    assert INVENTORY_MAIN_SHA in text
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


def test_attestation_never_claims_deployed_dispatch_or_execution_authority() -> None:
    text = EPIC_09.read_text(encoding="utf-8")

    assert "authorization_effect=NONE" in text
    assert "execution_authority=NONE" in text
    assert "dispatch_performed=false" in text
    assert "deployed cancellation request dispatch to runtime Runner: `NOT_IMPLEMENTED` / `NOT_RUN`" in text
    assert "deployed cooperative process interruption: `NOT_IMPLEMENTED` / `NOT_RUN`" in text
    assert "deployed force-after-grace interruption: `NOT_IMPLEMENTED` / `NOT_RUN`" in text
    assert "sole execution-authorization authority" in text
    assert "never create or expand an `authorization_ref`" in text


def test_synthetic_runtime_and_transport_evidence_is_recorded_without_final_promotion() -> None:
    text = EPIC_09.read_text(encoding="utf-8")

    for pr in ("PR #204", "PR #205", "PR #206", "PR #208", "PR #209"):
        assert pr in text
    assert RUNTIME_DRILL_MAIN_SHA in text
    assert SUBPROCESS_MAIN_SHA in text
    assert CAMPAIGN_MAIN_SHA in text
    assert "RUNNER_EVENT_ATTESTATION_V1" in text
    assert "PASS_SYNTHETIC_RUNTIME" in text
    assert "PASS_SYNTHETIC_TRANSPORT" in text
    assert "force_killed=true" in text
    assert "cleanup_failed=false" in text
    assert "campaign-scoped subprocess selectivity with unrelated work preserved" in text
    assert "deployed/operational kill-switch drill evidence: `NOT_RUN`" in text
    assert "| FINAL | no |" in text
