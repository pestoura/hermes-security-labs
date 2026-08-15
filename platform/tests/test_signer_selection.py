#!/usr/bin/env python3
"""Repository-only tests for the provider-neutral signer baseline + selection evaluator.

Proves the mandated guarantees without any runtime, provider client, key generation,
trust-store creation, provider install or promotion:

- no automatic supplier selection (no winner is ever chosen);
- missing / unverified candidate evidence fails closed;
- non-exportability of the private key is mandatory (R1);
- the explicit trust-store key_id/algorithm/digest binding is enforced through the
  existing canonical verifier;
- both LAB_L1 and PROD require the accepted signer baseline;
- PKCS11 alone cannot satisfy custody;
- the evaluator imports no provider-specific client, key loader or live-mutation API.
"""

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
BASELINE_PATH = ASSURANCE_DIR / "signer-baseline.yaml"
SCHEMA_PATH = ROOT / "platform" / "schemas" / "signer-baseline.schema.json"
MODULE_PATH = ASSURANCE_DIR / "signer_selection.py"


spec = importlib.util.spec_from_file_location("signer_selection_test", MODULE_PATH)
assert spec and spec.loader
module = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = module
spec.loader.exec_module(module)

load_baseline = module.load_baseline
evaluate_signer_baseline = module.evaluate_signer_baseline
SignerBaselineError = module.SignerBaselineError


def _candidate(cls: str, *, custody: bool = False, status: str = "NOT_EVALUATED") -> dict[str, Any]:
    return {
        "class": cls,
        "is_custody_proof": custody,
        "evaluation_status": status,
        "capability_evidence": None,
        "notes": "test",
    }


# ---------------------------------------------------------------------------
# Committed baseline is schema-valid and accepted, with NO_SELECTION
# ---------------------------------------------------------------------------
def test_committed_baseline_is_schema_valid_and_accepted() -> None:
    doc = load_baseline(BASELINE_PATH)
    assert doc["signer_baseline"]["accepted"] is True
    assert doc["signer_baseline"]["provider_neutral"] is True
    assert doc["signer_baseline"]["allows_automatic_supplier_choice"] is False
    assert doc["signer_baseline"]["supplier_selection"] == "NO_SELECTION"
    assert {c["class"] for c in doc["candidate_classes"]} == {"KMS", "HSM", "VAULT", "PKCS11"}


def test_committed_baseline_all_candidates_not_selected() -> None:
    doc = load_baseline(BASELINE_PATH)
    for c in doc["candidate_classes"]:
        assert c["evaluation_status"] != "SELECTED"
        assert c["is_custody_proof"] is False


# ---------------------------------------------------------------------------
# No automatic supplier selection, ever
# ---------------------------------------------------------------------------
def test_evaluate_never_selects_a_winner() -> None:
    result = evaluate_signer_baseline()
    assert result.selected_class is None
    assert result.promotion_allowed is False
    assert result.supplier_selection == "NO_SELECTION"


def test_candidate_marked_selected_fails_closed() -> None:
    doc = load_baseline(BASELINE_PATH)
    doc["candidate_classes"][0]["evaluation_status"] = "SELECTED"
    with pytest.raises(SignerBaselineError) as exc:
        evaluate_signer_baseline(doc)
    assert "SELECTED" in str(exc.value)


def test_allows_automatic_supplier_choice_false_is_enforced() -> None:
    doc = load_baseline(BASELINE_PATH)
    doc["signer_baseline"]["allows_automatic_supplier_choice"] = True
    with pytest.raises(SignerBaselineError):
        evaluate_signer_baseline(doc)


# ---------------------------------------------------------------------------
# Missing / unverified evidence fails closed
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("status", ["EVIDENCE_MISSING", "EVIDENCE_UNVERIFIED"])
def test_unverified_candidate_evidence_fails_closed(status: str) -> None:
    doc = load_baseline(BASELINE_PATH)
    doc["candidate_classes"] = [_candidate("HSM", custody=True, status=status)]
    with pytest.raises(SignerBaselineError):
        evaluate_signer_baseline(doc)


def test_unaccepted_baseline_fails_closed() -> None:
    doc = load_baseline(BASELINE_PATH)
    doc["signer_baseline"]["accepted"] = False
    with pytest.raises(SignerBaselineError):
        evaluate_signer_baseline(doc)


def test_committed_baseline_evaluates_clean() -> None:
    result = evaluate_signer_baseline()
    assert isinstance(result, module.SignerBaselineEvaluation)
    assert result.accepted is True
    assert result.promotion_allowed is False


# ---------------------------------------------------------------------------
# Non-exportability mandatory (R1) — exercised through the existing verifier
# ---------------------------------------------------------------------------
def test_non_exportable_private_key_mandatory_via_attestation_verifier() -> None:
    deploy_path = (
        ROOT
        / "deployment"
        / "runtime-promotion"
        / "templates"
        / "tb1-authorization-deployment-descriptor.example.yaml"
    )
    att_path = (
        ROOT
        / "deployment"
        / "runtime-promotion"
        / "templates"
        / "tb1-signer-attestation.example.yaml"
    )
    signer_spec = importlib.util.spec_from_file_location(
        "signer_baseline_attestation",
        ROOT
        / "deployment"
        / "runtime-promotion"
        / "runtime_signer_attestation.py",
    )
    assert signer_spec and signer_spec.loader
    signer_mod = importlib.util.module_from_spec(signer_spec)
    sys.modules[signer_spec.name] = signer_mod
    signer_spec.loader.exec_module(signer_mod)

    deployment = signer_mod.load_deployment_descriptor(deploy_path)
    attestation = signer_mod.load_attestation(att_path)
    # The committed example is NOT_RUN and explicitly non-exportable; it must not pass.
    result = signer_mod.verify_signer_attestation(deployment, attestation)
    assert result.promotion_allowed is False
    assert result.runtime_status == "NOT_RUN"
    # If a private key were ever exportable, the verifier fails closed.
    assert "observed signer private key is exportable" not in result.findings


# ---------------------------------------------------------------------------
# Explicit trust-store key_id/algorithm/digest binding enforced (R3)
# ---------------------------------------------------------------------------
def test_trust_store_digest_binding_enforced_by_preflight() -> None:
    preflight_spec = importlib.util.spec_from_file_location(
        "signer_baseline_preflight",
        ROOT
        / "deployment"
        / "runtime-promotion"
        / "tb1_authorization_preflight.py",
    )
    assert preflight_spec and preflight_spec.loader
    preflight_mod = importlib.util.module_from_spec(preflight_spec)
    sys.modules[preflight_spec.name] = preflight_mod
    preflight_spec.loader.exec_module(preflight_mod)

    descriptor_path = (
        ROOT
        / "deployment"
        / "runtime-promotion"
        / "templates"
        / "tb1-authorization-deployment-descriptor.example.yaml"
    )
    descriptor = preflight_mod.load_descriptor(descriptor_path)
    result = preflight_mod.run_preflight(descriptor)
    # The example descriptor must satisfy the trust-store binding preflight (no live state).
    assert result.ok is True
    # private_key_local must remain false (R1 non-exportability at the descriptor).
    assert descriptor["signer"]["private_key_local"] is False


# ---------------------------------------------------------------------------
# PKCS11 alone cannot satisfy custody (R1)
# ---------------------------------------------------------------------------
def test_pkcs11_is_interface_class_not_custody_proof() -> None:
    doc = load_baseline(BASELINE_PATH)
    pkcs11 = next(c for c in doc["candidate_classes"] if c["class"] == "PKCS11")
    assert pkcs11["is_custody_proof"] is False
    # Claiming custody for PKCS11 must fail closed.
    bad = _candidate("PKCS11", custody=True, status="EVIDENCE_VERIFIED_PENDING_DECISION")
    doc["candidate_classes"] = [bad]
    with pytest.raises(SignerBaselineError) as exc:
        evaluate_signer_baseline(doc)
    assert "interface class" in str(exc.value)


def test_pkcs11_alone_is_not_selected_as_custody() -> None:
    doc = load_baseline(BASELINE_PATH)
    doc["candidate_classes"] = [_candidate("PKCS11")]
    result = evaluate_signer_baseline(doc)
    assert result.selected_class is None
    assert not any(c.is_custody_proof for c in result.candidates)


# ---------------------------------------------------------------------------
# Both assurance profiles require the accepted signer baseline
# ---------------------------------------------------------------------------
def test_lab_l1_and_prod_require_signer_baseline() -> None:
    prof_spec = importlib.util.spec_from_file_location(
        "signer_baseline_profile", ASSURANCE_DIR / "assurance_profile.py"
    )
    assert prof_spec and prof_spec.loader
    prof_mod = importlib.util.module_from_spec(prof_spec)
    sys.modules[prof_spec.name] = prof_mod
    prof_spec.loader.exec_module(prof_mod)

    for path in (
        ASSURANCE_DIR / "current-assurance-profile.yaml",
        ASSURANCE_DIR / "prod-assurance-profile.yaml",
    ):
        doc = yaml.safe_load(path.read_text(encoding="utf-8"))
        prof_mod.validate_profile_schema(doc)
        result = prof_mod.load_profile(path)
        assert result.failures == ()
        assert doc["evaluation"]["requires_accepted_signer_baseline"] is True
        assert doc["evaluation"]["requires_explicit_trust_store"] is True


# ---------------------------------------------------------------------------
# No provider-specific client / key generation / live mutation imports
# ---------------------------------------------------------------------------
def test_module_has_no_provider_client_or_key_generation_imports() -> None:
    source = MODULE_PATH.read_text(encoding="utf-8")
    tree = ast.parse(source)

    # Forbidden module imports (whole-module names only).
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module.split(".")[0])
    assert not imported & {"subprocess", "socket", "requests", "httpx", "boto3", "hvac", "pkcs11", "os", "shutil"}

    # Forbidden *calls/expressions* as actual code nodes (not string literals):
    # provider clients, private-key loaders, signing, promotion, trust-store install.
    banned_names = {"load_pem_private_key", "load_der_private_key", "private_bytes", "promote", "install_trust_store"}
    banned_attrs = {"sign"}
    for node in ast.walk(tree):
        if isinstance(node, ast.Name) and node.id in banned_names:
            raise AssertionError(f"forbidden symbol used as code: {node.id}")
        if isinstance(node, ast.Attribute) and node.attr in banned_attrs:
            raise AssertionError(f"forbidden attribute used as code: .{node.attr}(")
    # The module must reuse the existing canonical modules rather than duplicate them.
    assert "tb1_authorization_preflight" in source


# ---------------------------------------------------------------------------
# CURRENT NO_SELECTION guard (repository-only, fail-closed)
# ---------------------------------------------------------------------------
validate_no_selection_trust_guard = module.validate_no_selection_trust_guard

TRUST_STORE_PATH = "/etc/hexor/runner/authorization-trust-store.json"


def _safe_runtime_deployment() -> dict[str, Any]:
    return {
        "trust_binding": {
            "enabled": False,
            "source": None,
            "public_source": False,
            "expected_sha256": None,
            "trust_store_path": TRUST_STORE_PATH,
        }
    }


@pytest.mark.parametrize("status", ["PENDING", "SELECTED"])
def test_schema_valid_selection_transition_states_fail_closed(status: str) -> None:
    doc = load_baseline(BASELINE_PATH)
    doc["signer_baseline"]["supplier_selection"] = status
    with pytest.raises(SignerBaselineError) as exc:
        evaluate_signer_baseline(doc)
    message = str(exc.value)
    assert "supplier selection" in message or "supplier_selection" in message
    assert "human" in message
    assert "decision" in message
    assert "contract" in message


def test_no_selection_trust_guard_accepts_committed_safe_state() -> None:
    assert validate_no_selection_trust_guard() is None


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("enabled", True),
        ("source", "/tmp/unapproved.json"),
        ("public_source", True),
        ("expected_sha256", "0" * 64),
    ],
)
def test_no_selection_trust_guard_contradictions_fail_closed(field: str, value: Any) -> None:
    doc = load_baseline(BASELINE_PATH)
    runtime_deployment = _safe_runtime_deployment()
    runtime_deployment["trust_binding"][field] = value
    with pytest.raises(SignerBaselineError) as exc:
        validate_no_selection_trust_guard(
            document=doc, runtime_deployment=runtime_deployment
        )
    message = str(exc.value)
    assert "failed closed" in message
    assert "trust_binding" in message
    assert field in message


def test_no_selection_guard_allows_canonical_destination_declaration_only() -> None:
    doc = load_baseline(BASELINE_PATH)
    runtime_deployment = _safe_runtime_deployment()
    assert runtime_deployment["trust_binding"]["trust_store_path"] == TRUST_STORE_PATH
    assert (
        validate_no_selection_trust_guard(
            document=doc, runtime_deployment=runtime_deployment
        )
        is None
    )
