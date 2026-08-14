"""Repository-only tests for the provider-neutral assurance-profile contract (ADR-0011).

No runtime mutation, no target interaction, no promotion. The profile only selects
which requirement set applies; it never weakens signer/trust, SO_PEERCRED + audit,
evidence integrity, PRE/POST packages, reset or HITL, and it never promotes.
"""

from __future__ import annotations

import ast
import copy
import importlib.util
import sys
from pathlib import Path
from typing import Any

import pytest
import yaml


def _doc(profile: str, **overrides: Any) -> dict[str, Any]:
    evaluation = {
        "requires_external_signer": True,
        "requires_purpose_bound_trust_store": True,
        "requires_non_exportable_private_key": True,
        "requires_explicit_trust_store": True,
        "requires_accepted_signer_baseline": True,
        "requires_so_peerccred_with_audit": True,
        "requires_audit_sink": True,
        "requires_tamper_evident_evidence": True,
        "requires_hash_chain": True,
        "requires_pre_promotion_package": True,
        "requires_post_effect_package": True,
        "requires_mandatory_reset": True,
        "requires_request_bound_hitl": True,
        "allows_automatic_supplier_choice": False,
        "requires_external_worm_backend": profile == module.PROD,
        "requires_tenant_isolation": profile == module.PROD,
    }
    evaluation.update(overrides)
    return {
        "schema_version": "assurance-profile/v1",
        "assurance_profile": profile,
        "derived_from": "ADR-0011",
        "evaluation": evaluation,
    }

ROOT = Path(__file__).resolve().parents[2]
ASSURANCE_DIR = ROOT / "platform" / "assurance"
PROFILE_PATH = ASSURANCE_DIR / "current-assurance-profile.yaml"
SCHEMA_PATH = ROOT / "platform" / "schemas" / "assurance-profile.schema.json"


spec = importlib.util.spec_from_file_location(
    "assurance_profile_test", ASSURANCE_DIR / "assurance_profile.py"
)
assert spec and spec.loader
module = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = module
spec.loader.exec_module(module)

AssuranceProfileError = module.AssuranceProfileError
validate_profile_document = module.validate_profile_document
resolve_profile = module.resolve_profile
load_profile = module.load_profile
validate_profile_schema = module.validate_profile_schema
PROD = module.PROD
LAB_L1 = module.LAB_L1


# ---------------------------------------------------------------------------
# Fail-closed default resolution
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    "raw,expected",
    [
        ("PROD", "PROD"),
        ("LAB_L1", "LAB_L1"),
        (None, "PROD"),
        ("", "PROD"),
        ("lab_l1", "PROD"),  # case-sensitive enum
        ("INVALID", "PROD"),
        (42, "PROD"),
    ],
)
def test_invalid_or_missing_profile_fails_closed_to_prod(raw: Any, expected: str) -> None:
    assert resolve_profile(raw) == expected


def test_missing_profile_load_resolves_prod_and_records_failure() -> None:
    doc = _doc("PROD")
    doc.pop("assurance_profile")
    result = validate_profile_document(doc)
    assert result.resolved_profile == "PROD"
    assert any("failing closed to PROD" in f for f in result.failures)
    assert result.promotion_allowed is False


# ---------------------------------------------------------------------------
# LAB_L1 cannot bypass the non-omissible controls
# ---------------------------------------------------------------------------
def test_lab_l1_resolves_with_worm_and_tenant_omitted_only() -> None:
    result = validate_profile_document(_doc(LAB_L1))
    assert result.resolved_profile == LAB_L1
    assert result.failures == ()
    assert result.requires_external_worm_backend is False
    assert result.requires_tenant_isolation is False
    assert result.promotion_allowed is False


@pytest.mark.parametrize(
    "weak_key",
    [
        "requires_external_signer",
        "requires_purpose_bound_trust_store",
        "requires_non_exportable_private_key",
        "requires_explicit_trust_store",
        "requires_so_peerccred_with_audit",
        "requires_audit_sink",
        "requires_tamper_evident_evidence",
        "requires_hash_chain",
        "requires_pre_promotion_package",
        "requires_post_effect_package",
        "requires_mandatory_reset",
        "requires_request_bound_hitl",
    ],
)
def test_lab_l1_cannot_relax_required_control(weak_key: str) -> None:
    result = validate_profile_document(_doc(LAB_L1, **{weak_key: False}))
    assert result.resolved_profile == LAB_L1
    assert any(weak_key in f and "expected True" in f for f in result.failures)


def test_lab_l1_cannot_enable_automatic_supplier_choice() -> None:
    result = validate_profile_document(_doc(LAB_L1, allows_automatic_supplier_choice=True))
    assert any(
        "allows_automatic_supplier_choice" in f and "expected False" in f
        for f in result.failures
    )


def test_lab_l1_cannot_falsely_claim_worm_or_tenant_isolation() -> None:
    # A LAB_L1 doc that claims it requires WORM/tenant must be caught as weakened.
    result = validate_profile_document(
        _doc(LAB_L1, requires_external_worm_backend=True, requires_tenant_isolation=True)
    )
    assert any("requires_external_worm_backend" in f for f in result.failures)
    assert any("requires_tenant_isolation" in f for f in result.failures)


# ---------------------------------------------------------------------------
# PROD must stay at least as strict as current behaviour
# ---------------------------------------------------------------------------
def test_prod_keeps_every_control_on() -> None:
    result = validate_profile_document(_doc(PROD))
    assert result.resolved_profile == PROD
    assert result.failures == ()
    assert result.requires_external_worm_backend is True
    assert result.requires_tenant_isolation is True
    assert result.promotion_allowed is False


def test_prod_weakens_fails_closed() -> None:
    result = validate_profile_document(
        _doc(PROD, requires_external_signer=False)
    )
    assert result.resolved_profile == PROD
    assert any(
        "requires_external_signer" in f and "expected True" in f for f in result.failures
    )


def test_prod_cannot_enable_automatic_supplier_choice() -> None:
    result = validate_profile_document(_doc(PROD, allows_automatic_supplier_choice=True))
    assert any(
        "allows_automatic_supplier_choice" in f and "expected False" in f
        for f in result.failures
    )


# ---------------------------------------------------------------------------
# Canonical committed artifact is valid and matches the schema
# ---------------------------------------------------------------------------
def test_committed_current_assurance_profile_is_valid() -> None:
    assert PROFILE_PATH.is_file()
    doc = yaml.safe_load(PROFILE_PATH.read_text(encoding="utf-8"))
    validate_profile_schema(doc)
    result = load_profile(PROFILE_PATH)
    assert result.resolved_profile == LAB_L1
    assert result.failures == ()


def test_committed_lab_l1_requires_accepted_signer_baseline_and_trust_store() -> None:
    doc = yaml.safe_load(PROFILE_PATH.read_text(encoding="utf-8"))
    assert doc["evaluation"]["requires_accepted_signer_baseline"] is True
    assert doc["evaluation"]["requires_explicit_trust_store"] is True


def test_committed_prod_assurance_profile_requires_signer_baseline() -> None:
    prod_path = ASSURANCE_DIR / "prod-assurance-profile.yaml"
    assert prod_path.is_file()
    doc = yaml.safe_load(prod_path.read_text(encoding="utf-8"))
    validate_profile_schema(doc)
    result = load_profile(prod_path)
    assert result.resolved_profile == PROD
    assert result.failures == ()
    assert doc["evaluation"]["requires_accepted_signer_baseline"] is True
    assert doc["evaluation"]["requires_explicit_trust_store"] is True
    assert doc["evaluation"]["requires_external_worm_backend"] is True
    assert doc["evaluation"]["requires_tenant_isolation"] is True


def test_schema_requires_signer_baseline_and_trust_store_on_either_profile() -> None:
    # Both profiles must declare the signer baseline + explicit trust store as true.
    for profile in (LAB_L1, PROD):
        doc = _doc(profile)
        validate_profile_schema(doc)
        assert doc["evaluation"]["requires_accepted_signer_baseline"] is True
        assert doc["evaluation"]["requires_explicit_trust_store"] is True


def test_schema_rejects_signer_baseline_false() -> None:
    doc = _doc(LAB_L1, requires_accepted_signer_baseline=False)
    with pytest.raises(AssuranceProfileError):
        validate_profile_schema(doc)


def test_schema_rejects_explicit_trust_store_false() -> None:
    doc = _doc(PROD, requires_explicit_trust_store=False)
    with pytest.raises(AssuranceProfileError):
        validate_profile_schema(doc)


def test_schema_rejects_unknown_profile_value() -> None:
    doc = _doc("LAB_L1")
    doc["assurance_profile"] = "STAGING"
    with pytest.raises(AssuranceProfileError):
        validate_profile_schema(doc)


def test_schema_rejects_extra_properties() -> None:
    doc = _doc(LAB_L1)
    doc["extra_field"] = "nope"
    with pytest.raises(AssuranceProfileError):
        validate_profile_schema(doc)


# ---------------------------------------------------------------------------
# No runtime/target effects: the module must not import or call mutation APIs
# ---------------------------------------------------------------------------
def test_module_has_no_runtime_mutation_or_promotion_imports() -> None:
    source = (ASSURANCE_DIR / "assurance_profile.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module.split(".")[0])
    assert not imported & {"subprocess", "socket", "requests", "urllib", "os", "shutil"}
    for forbidden in (
        "chmod(",
        "chown(",
        "write_text(",
        "write_bytes(",
        "unlink(",
        "docker",
        "execute_command",
        "promote(",
        "apply_policy(",
    ):
        assert forbidden not in source


def test_load_profile_does_not_mutate_any_runtime_state() -> None:
    # load_profile only reads + validates; assert it returns a fresh evaluation.
    before = copy.deepcopy(_doc(LAB_L1))
    result = load_profile(PROFILE_PATH)
    assert result.resolved_profile == LAB_L1
    # The function must not have altered the canonical file.
    after = yaml.safe_load(PROFILE_PATH.read_text(encoding="utf-8"))
    assert after == before


# ---------------------------------------------------------------------------
# CHG-HSL-050: locked assurance-profile invariants (repository-only, HOLD)
# ---------------------------------------------------------------------------


def test_committed_lab_l1_profile_omits_only_worm_and_tenant_isolation() -> None:
    doc = yaml.safe_load(PROFILE_PATH.read_text(encoding="utf-8"))
    evaluation = doc["evaluation"]
    # LAB_L1 may set ONLY these two to False; every other control stays True.
    assert evaluation["requires_external_worm_backend"] is False
    assert evaluation["requires_tenant_isolation"] is False
    for key in (
        "requires_external_signer",
        "requires_purpose_bound_trust_store",
        "requires_non_exportable_private_key",
        "requires_explicit_trust_store",
        "requires_accepted_signer_baseline",
        "requires_so_peerccred_with_audit",
        "requires_audit_sink",
        "requires_tamper_evident_evidence",
        "requires_hash_chain",
        "requires_pre_promotion_package",
        "requires_post_effect_package",
        "requires_mandatory_reset",
        "requires_request_bound_hitl",
    ):
        assert evaluation[key] is True


def test_committed_lab_l1_profile_forbids_automatic_supplier_choice() -> None:
    doc = yaml.safe_load(PROFILE_PATH.read_text(encoding="utf-8"))
    assert doc["evaluation"]["allows_automatic_supplier_choice"] is False


def test_committed_lab_l1_profile_is_always_unpromoted() -> None:
    result = load_profile(PROFILE_PATH)
    assert result.promotion_allowed is False
    assert result.resolved_profile == LAB_L1


def test_lab_l1_profile_rejects_any_unexpected_additional_control() -> None:
    # A LAB_L1 doc that weakens by ADDING a control flag set False must fail
    # (only the two omissible keys are allowed to be False).
    doc = _doc(LAB_L1, requires_mandatory_reset=False)
    result = validate_profile_document(doc)
    assert result.resolved_profile == LAB_L1
    assert any("requires_mandatory_reset" in f and "expected True" in f for f in result.failures)
