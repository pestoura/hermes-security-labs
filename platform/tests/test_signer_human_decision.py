#!/usr/bin/env python3
"""Repository-only tests for the explicit human signer-decision contract."""

from __future__ import annotations

import ast
import importlib.util
import sys
from pathlib import Path
from typing import Any

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
ASSURANCE_DIR = ROOT / "platform" / "assurance"
MODULE_PATH = ASSURANCE_DIR / "signer_human_decision.py"
DECISION_PATH = ASSURANCE_DIR / "signer-human-decision.yaml"

spec = importlib.util.spec_from_file_location("signer_human_decision_test", MODULE_PATH)
assert spec and spec.loader
module = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = module
spec.loader.exec_module(module)

load_decision = module.load_decision
evaluate_human_decision = module.evaluate_human_decision
SignerHumanDecisionError = module.SignerHumanDecisionError


def _approved_decision() -> dict[str, Any]:
    digest = "a" * 64
    return {
        "schema_version": "signer-human-decision/v1",
        "decision": {
            "state": "APPROVED",
            "decision_id": "DEC-HSL-SIGNER-001",
            "selected_class": "VAULT",
            "decided_by": "human-owner",
            "decided_at": "2026-08-15T12:00:00+01:00",
            "rationale": "Explicit human selection after review of the accepted R1-R8 baseline.",
            "evidence_refs": [
                {"kind": "capability_evidence", "ref": "evidence://signer/capability.json", "sha256": digest},
                {"kind": "signer_attestation", "ref": "evidence://signer/attestation.json", "sha256": digest},
                {"kind": "trust_store_manifest", "ref": "evidence://signer/trust-store.json", "sha256": digest},
                {"kind": "r1_r8_review", "ref": "evidence://signer/r1-r8-review.json", "sha256": digest},
            ],
        },
    }


def test_committed_decision_is_no_decision_and_selects_nothing() -> None:
    document = load_decision(DECISION_PATH)
    assert document["decision"]["state"] == "NO_DECISION"
    assert document["decision"]["selected_class"] is None
    assert document["decision"]["evidence_refs"] == []

    result = evaluate_human_decision(document)
    assert result.state == "NO_DECISION"
    assert result.selected_class is None
    assert result.evidence_refs_complete is False
    assert result.promotion_allowed is False
    assert result.runtime_status == "NOT_RUN"


def test_no_decision_rejects_hidden_selection_fields() -> None:
    document = yaml.safe_load(DECISION_PATH.read_text(encoding="utf-8"))
    document["decision"]["selected_class"] = "VAULT"
    with pytest.raises(SignerHumanDecisionError):
        evaluate_human_decision(document)


def test_approved_human_decision_binds_evidence_but_never_promotes() -> None:
    result = evaluate_human_decision(_approved_decision())
    assert result.state == "APPROVED"
    assert result.decision_id == "DEC-HSL-SIGNER-001"
    assert result.selected_class == "VAULT"
    assert result.evidence_refs_complete is True
    assert result.promotion_allowed is False
    assert result.runtime_status == "NOT_RUN"


def test_pkcs11_cannot_be_selected_as_custody_backend() -> None:
    document = _approved_decision()
    document["decision"]["selected_class"] = "PKCS11"
    with pytest.raises(SignerHumanDecisionError):
        evaluate_human_decision(document)


def test_missing_required_evidence_kind_fails_closed() -> None:
    document = _approved_decision()
    document["decision"]["evidence_refs"] = document["decision"]["evidence_refs"][:-1]
    with pytest.raises(SignerHumanDecisionError) as exc:
        evaluate_human_decision(document)
    assert "missing required" in str(exc.value)


def test_duplicate_evidence_kind_fails_closed() -> None:
    document = _approved_decision()
    duplicate = dict(document["decision"]["evidence_refs"][0])
    document["decision"]["evidence_refs"][3] = duplicate
    with pytest.raises(SignerHumanDecisionError) as exc:
        evaluate_human_decision(document)
    assert "duplicate" in str(exc.value)


def test_bad_evidence_ref_fails_schema_closed() -> None:
    document = _approved_decision()
    document["decision"]["evidence_refs"][0]["ref"] = "/tmp/not-canonical"
    with pytest.raises(SignerHumanDecisionError):
        evaluate_human_decision(document)


def test_bad_evidence_digest_fails_schema_closed() -> None:
    document = _approved_decision()
    document["decision"]["evidence_refs"][0]["sha256"] = "bad"
    with pytest.raises(SignerHumanDecisionError):
        evaluate_human_decision(document)


def test_approved_decision_requires_timezone_aware_timestamp() -> None:
    document = _approved_decision()
    document["decision"]["decided_at"] = "2026-08-15T12:00:00"
    with pytest.raises(SignerHumanDecisionError) as exc:
        evaluate_human_decision(document)
    assert "timezone" in str(exc.value)


def test_module_has_no_provider_runtime_or_write_surface() -> None:
    source = MODULE_PATH.read_text(encoding="utf-8")
    tree = ast.parse(source)

    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module.split(".")[0])

    assert not imported & {
        "subprocess",
        "socket",
        "requests",
        "httpx",
        "boto3",
        "hvac",
        "pkcs11",
        "os",
        "shutil",
    }

    for banned in (
        "write_text(",
        "write_bytes(",
        "unlink(",
        "chmod(",
        "load_pem_private_key",
        "load_der_private_key",
        "private_bytes",
        ".sign(",
        "promote(",
        "install_trust_store",
    ):
        assert banned not in source
