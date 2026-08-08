from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
EPIC_09 = ROOT / "docs/roadmap/epics/EPIC-09-exploitation-safety.md"
EPIC_28 = ROOT / "docs/roadmap/EPIC-28-roe-contract-candidate-as-built.md"
ROE_README = ROOT / "platform/roe-contract/README.md"

MAIN_SHA = "1713e90578cd1c31e65946f0a2ae01125464f7dc"


def test_pr200_evidence_is_reconciled_without_final_promotion() -> None:
    epic09 = EPIC_09.read_text(encoding="utf-8")
    epic28 = EPIC_28.read_text(encoding="utf-8")

    for text in (epic09, epic28):
        assert "PR #200" in text
        assert MAIN_SHA in text
        assert "trust_store_lifecycle.py" in text
        assert "NO_RUNTIME_CHANGE" in text

    assert "**AS_BUILT**" in epic09
    assert "| AS_BUILT | yes |" in epic09
    assert "| FINAL | no |" in epic09
    assert "AS_BUILT — contract candidate" in epic28
    assert "| FINAL | no |" in epic28


def test_repository_freshness_does_not_become_production_activation_claim() -> None:
    epic09 = EPIC_09.read_text(encoding="utf-8")
    epic28 = EPIC_28.read_text(encoding="utf-8")
    readme = ROE_README.read_text(encoding="utf-8")

    for text in (epic09, epic28, readme):
        assert "production trust-store distribution/activation" in text.lower()
        assert "NOT_RUN" in text
        assert "external" in text.lower()
        assert "attestation" in text.lower()
        assert "revocation" in text.lower()

    assert "automatic_activation=false" in readme
    assert "activation_effect=NONE" in readme
    assert "authorization_effect=NONE" in readme
    assert "execution_authority=NONE" in readme
    assert "ACCEPT_FOR_REVIEW" in readme


def test_operational_cancellation_nonclaims_remain_explicit() -> None:
    epic09 = EPIC_09.read_text(encoding="utf-8")
    normalized = epic09.lower()

    assert "cancellation request dispatch to runtime runner: `not_implemented` / `not_run`" in normalized
    assert "runtime active-attempt inventory authenticity/integration: `not_implemented` / `not_run`" in normalized
    assert "cooperative process interruption: `not_implemented` / `not_run`" in normalized
    assert "force-after-grace interruption: `not_implemented` / `not_run`" in normalized
    assert "runtime deployment of trust store / kill switch: `not_run`" in normalized


def test_authority_boundary_is_unchanged() -> None:
    epic09 = EPIC_09.read_text(encoding="utf-8")

    assert "sole execution-authorization authority" in epic09
    assert "never create or expand an `authorization_ref`" in epic09
    assert "caller-controlled RoE/authorization decisions: refused" in epic09
