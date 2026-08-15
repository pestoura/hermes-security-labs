#!/usr/bin/env python3
"""Repository-only tests for the human signer-selection transition guard."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[2]
ASSURANCE_DIR = ROOT / "platform" / "assurance"
MODULE_PATH = ASSURANCE_DIR / "signer_selection.py"

spec = importlib.util.spec_from_file_location("signer_selection_transition_test", MODULE_PATH)
assert spec and spec.loader
module = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = module
spec.loader.exec_module(module)

load_baseline = module.load_baseline
validate_selection_transition_contract = module.validate_selection_transition_contract
SignerBaselineError = module.SignerBaselineError

TRUST_STORE_PATH = "/etc/hexor/runner/authorization-trust-store.json"


def _safe_runtime() -> dict[str, Any]:
    return {
        "trust_binding": {
            "enabled": False,
            "source": None,
            "public_source": False,
            "expected_sha256": None,
            "trust_store_path": TRUST_STORE_PATH,
        }
    }


def _approved_decision(cls: str = "VAULT", decision_id: str = "DEC-HSL-SIGNER-001") -> dict[str, Any]:
    digest = "a" * 64
    return {
        "schema_version": "signer-human-decision/v1",
        "decision": {
            "state": "APPROVED",
            "decision_id": decision_id,
            "selected_class": cls,
            "decided_by": "human-owner",
            "decided_at": "2026-08-15T12:00:00+01:00",
            "rationale": "Explicit human selection after verified R1-R8 evidence review.",
            "evidence_refs": [
                {"kind": "capability_evidence", "ref": "evidence://signer/capability.json", "sha256": digest},
                {"kind": "signer_attestation", "ref": "evidence://signer/attestation.json", "sha256": digest},
                {"kind": "trust_store_manifest", "ref": "evidence://signer/trust-store.json", "sha256": digest},
                {"kind": "r1_r8_review", "ref": "evidence://signer/r1-r8-review.json", "sha256": digest},
            ],
        },
    }


def _transition_baseline(state: str = "PENDING", cls: str = "VAULT", decision_id: str = "DEC-HSL-SIGNER-001") -> dict[str, Any]:
    document = load_baseline()
    baseline = document["signer_baseline"]
    baseline["supplier_selection"] = state
    baseline["selected_class"] = cls
    baseline["human_decision_id"] = decision_id

    candidate = next(c for c in document["candidate_classes"] if c["class"] == cls)
    candidate["is_custody_proof"] = True
    candidate["evaluation_status"] = "EVIDENCE_VERIFIED_PENDING_DECISION"
    candidate["capability_evidence"] = {
        "ref": "evidence://signer/capability.json",
        "sha256": "a" * 64,
    }
    return document


def test_committed_no_selection_is_consistent_and_never_promotes() -> None:
    result = validate_selection_transition_contract(runtime_deployment=_safe_runtime())
    assert result.supplier_selection == "NO_SELECTION"
    assert result.decision_state == "NO_DECISION"
    assert result.selected_class is None
    assert result.human_decision_id is None
    assert result.candidate_evidence_ready is False
    assert result.transition_contract_valid is True
    assert result.trust_binding_allowed is False
    assert result.promotion_allowed is False
    assert result.runtime_status == "NOT_RUN"


def test_approved_human_decision_can_be_staged_while_selection_remains_no_selection() -> None:
    result = validate_selection_transition_contract(
        human_decision=_approved_decision(),
        runtime_deployment=_safe_runtime(),
    )
    assert result.supplier_selection == "NO_SELECTION"
    assert result.decision_state == "APPROVED"
    assert result.selected_class is None
    assert result.human_decision_id is None
    assert result.candidate_evidence_ready is False
    assert result.transition_contract_valid is True
    assert result.trust_binding_allowed is False
    assert result.promotion_allowed is False
    assert result.runtime_status == "NOT_RUN"


@pytest.mark.parametrize("state", ["PENDING", "SELECTED"])
def test_future_human_transition_can_be_contract_valid_but_never_promotes(state: str) -> None:
    result = validate_selection_transition_contract(
        document=_transition_baseline(state=state),
        human_decision=_approved_decision(),
        runtime_deployment=_safe_runtime(),
    )
    assert result.supplier_selection == state
    assert result.decision_state == "APPROVED"
    assert result.selected_class == "VAULT"
    assert result.human_decision_id == "DEC-HSL-SIGNER-001"
    assert result.candidate_evidence_ready is True
    assert result.transition_contract_valid is True
    assert result.trust_binding_allowed is False
    assert result.promotion_allowed is False
    assert result.runtime_status == "NOT_RUN"


def test_transition_requires_matching_selected_class() -> None:
    with pytest.raises(SignerBaselineError) as exc:
        validate_selection_transition_contract(
            document=_transition_baseline(cls="VAULT"),
            human_decision=_approved_decision(cls="KMS"),
            runtime_deployment=_safe_runtime(),
        )
    assert "selected_class" in str(exc.value)
    assert "does not match" in str(exc.value)


def test_transition_requires_matching_human_decision_id() -> None:
    with pytest.raises(SignerBaselineError) as exc:
        validate_selection_transition_contract(
            document=_transition_baseline(decision_id="DEC-HSL-SIGNER-999"),
            human_decision=_approved_decision(decision_id="DEC-HSL-SIGNER-001"),
            runtime_deployment=_safe_runtime(),
        )
    assert "human_decision_id" in str(exc.value)
    assert "does not match" in str(exc.value)


def test_transition_rejects_unverified_candidate() -> None:
    document = _transition_baseline()
    candidate = next(c for c in document["candidate_classes"] if c["class"] == "VAULT")
    candidate["evaluation_status"] = "NOT_EVALUATED"
    with pytest.raises(SignerBaselineError) as exc:
        validate_selection_transition_contract(
            document=document,
            human_decision=_approved_decision(),
            runtime_deployment=_safe_runtime(),
        )
    assert "evidence is not verified" in str(exc.value)


def test_transition_rejects_missing_custody_proof() -> None:
    document = _transition_baseline()
    candidate = next(c for c in document["candidate_classes"] if c["class"] == "VAULT")
    candidate["is_custody_proof"] = False
    with pytest.raises(SignerBaselineError) as exc:
        validate_selection_transition_contract(
            document=document,
            human_decision=_approved_decision(),
            runtime_deployment=_safe_runtime(),
        )
    assert "custody proof" in str(exc.value)


def test_transition_rejects_missing_capability_evidence_record() -> None:
    document = _transition_baseline()
    candidate = next(c for c in document["candidate_classes"] if c["class"] == "VAULT")
    candidate["capability_evidence"] = None
    with pytest.raises(SignerBaselineError) as exc:
        validate_selection_transition_contract(
            document=document,
            human_decision=_approved_decision(),
            runtime_deployment=_safe_runtime(),
        )
    assert "capability_evidence" in str(exc.value)


def test_selection_contract_never_allows_implicit_trust_binding() -> None:
    runtime = _safe_runtime()
    runtime["trust_binding"]["enabled"] = True
    with pytest.raises(SignerBaselineError) as exc:
        validate_selection_transition_contract(
            document=_transition_baseline(),
            human_decision=_approved_decision(),
            runtime_deployment=runtime,
        )
    assert "trust guard failed closed" in str(exc.value)
    assert "enabled" in str(exc.value)


def test_staged_approved_decision_never_allows_implicit_trust_binding() -> None:
    runtime = _safe_runtime()
    runtime["trust_binding"]["source"] = "repository://unexpected"
    with pytest.raises(SignerBaselineError) as exc:
        validate_selection_transition_contract(
            human_decision=_approved_decision(),
            runtime_deployment=runtime,
        )
    assert "NO_SELECTION trust guard failed closed" in str(exc.value)
    assert "source" in str(exc.value)


def test_pkcs11_cannot_be_encoded_as_selected_custody_class() -> None:
    document = load_baseline()
    baseline = document["signer_baseline"]
    baseline["supplier_selection"] = "PENDING"
    baseline["selected_class"] = "PKCS11"
    baseline["human_decision_id"] = "DEC-HSL-SIGNER-001"
    with pytest.raises(SignerBaselineError) as exc:
        validate_selection_transition_contract(
            document=document,
            human_decision=_approved_decision(),
            runtime_deployment=_safe_runtime(),
        )
    assert "schema violation" in str(exc.value)
    assert "selected_class" in str(exc.value)
