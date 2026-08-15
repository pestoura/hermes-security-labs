from __future__ import annotations

import copy
import importlib.util
import sys
from pathlib import Path
from typing import Any

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
MODULE_PATH = (
    ROOT
    / "deployment"
    / "runtime-promotion"
    / "runtime_live_promotion_evidence.py"
)
PACKAGE_PATH = (
    ROOT
    / "deployment"
    / "runtime-promotion"
    / "templates"
    / "live-promotion-evidence-package.example.yaml"
)
CAMPAIGN_PATH = ROOT / "validation" / "VAL-HSL-RUNNER-L1-LIVE-PROMOTION.yaml"
PROFILE_PATH = ROOT / "platform" / "assurance" / "current-assurance-profile.yaml"


def _load(name: str, path: Path) -> Any:
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


live = _load("chg_hsl_066_profile_gate_test", MODULE_PATH)


def _campaign() -> dict[str, Any]:
    document = yaml.safe_load(CAMPAIGN_PATH.read_text(encoding="utf-8"))
    assert isinstance(document, dict)
    return document


def _minimal_lab_not_run_package() -> dict[str, Any]:
    document = yaml.safe_load(PACKAGE_PATH.read_text(encoding="utf-8"))
    assert isinstance(document, dict)
    document["gates"] = [
        gate
        for gate in document["gates"]
        if gate["gate_id"] not in live.PROD_ONLY_PRE_PROMOTION_GATES
    ]
    return document


def test_current_profile_resolves_to_valid_lab_l1() -> None:
    profile = yaml.safe_load(PROFILE_PATH.read_text(encoding="utf-8"))
    assert profile["assurance_profile"] == "LAB_L1"
    assert profile["evaluation"]["requires_external_worm_backend"] is False
    assert profile["evaluation"]["requires_tenant_isolation"] is False
    assert profile["evaluation"]["requires_hash_chain"] is True

    resolved, requires_hash_chain = live._resolve_assurance()
    assert resolved == "LAB_L1"
    assert requires_hash_chain is True


def test_lab_l1_true_required_pre_gate_set_omits_exactly_two_prod_gates() -> None:
    lab = live.profile_required_gate_ids(
        "PRE_PROMOTION", "LAB_L1", requires_hash_chain=True
    )
    prod = live.profile_required_gate_ids(
        "PRE_PROMOTION", "PROD", requires_hash_chain=True
    )

    assert "HASH_CHAIN_SEAL" in lab
    assert "EVIDENCE_BACKEND_CONTROLS" not in lab
    assert "EVIDENCE_TENANT_ISOLATION" not in lab
    assert prod - lab == {
        "EVIDENCE_BACKEND_CONTROLS",
        "EVIDENCE_TENANT_ISOLATION",
    }
    assert lab - prod == set()


def test_post_effect_gate_set_is_profile_invariant() -> None:
    lab = live.profile_required_gate_ids(
        "POST_EFFECT", "LAB_L1", requires_hash_chain=True
    )
    prod = live.profile_required_gate_ids(
        "POST_EFFECT", "PROD", requires_hash_chain=True
    )
    assert lab == prod
    assert "HASH_CHAIN_SEAL" in lab
    assert "HITL_PROMOTION_DECISION" in lab
    assert "WEBGOAT_L1_EFFECT_RESET" in lab


def test_invalid_explicit_profile_fails_closed_to_prod_gate_set() -> None:
    invalid = live.profile_required_gate_ids(
        "PRE_PROMOTION", "NOT_A_PROFILE", requires_hash_chain=True
    )
    prod = live.profile_required_gate_ids(
        "PRE_PROMOTION", "PROD", requires_hash_chain=True
    )
    assert invalid == prod


def test_lab_l1_package_may_omit_prod_only_gates_without_becoming_invalid() -> None:
    package = _minimal_lab_not_run_package()
    result = live.verify_live_evidence_package(package, _campaign())

    assert result.package_valid is True
    assert result.package_complete is False
    assert result.promotion_allowed is False
    assert result.recommendation == "HOLD"
    assert result.required_gate_count == len(package["gates"])
    assert not any(
        blocker.startswith("EVIDENCE_BACKEND_CONTROLS:")
        or blocker.startswith("EVIDENCE_TENANT_ISOLATION:")
        for blocker in result.blockers
    )


def test_legacy_lab_package_may_keep_prod_only_gates_not_run_without_blocking_them() -> None:
    package = yaml.safe_load(PACKAGE_PATH.read_text(encoding="utf-8"))
    assert isinstance(package, dict)

    result = live.verify_live_evidence_package(package, _campaign())
    assert result.package_valid is True
    assert result.package_complete is False
    assert not any(
        blocker.startswith("EVIDENCE_BACKEND_CONTROLS:")
        or blocker.startswith("EVIDENCE_TENANT_ISOLATION:")
        for blocker in result.blockers
    )


def test_lab_l1_still_rejects_an_undeclared_extra_gate() -> None:
    package = _minimal_lab_not_run_package()
    package["gates"].append(
        {
            "gate_id": "UNDECLARED_GATE",
            "result": "NOT_RUN",
            "observed_at": None,
            "evidence_ref": None,
            "evidence_sha256": None,
        }
    )

    with pytest.raises(live.LiveEvidencePackageError) as exc:
        live.verify_live_evidence_package(package, _campaign())
    assert exc.value.code == "PACKAGE_GATE_SET_INVALID"
    assert "UNDECLARED_GATE" in str(exc.value)


def test_inconsistent_lab_profile_fails_closed_to_prod(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    profile = yaml.safe_load(PROFILE_PATH.read_text(encoding="utf-8"))
    assert isinstance(profile, dict)
    profile = copy.deepcopy(profile)
    # Contradicts ADR-0011: LAB_L1 is allowed to omit this control, and the
    # canonical profile declaration requires it to be False.
    profile["evaluation"]["requires_external_worm_backend"] = True

    bad_profile = tmp_path / "bad-profile.yaml"
    bad_profile.write_text(yaml.safe_dump(profile, sort_keys=False), encoding="utf-8")
    monkeypatch.setattr(live, "ASSURANCE_PROFILE_PATH", bad_profile)

    resolved, requires_hash_chain = live._resolve_assurance()
    assert resolved == "PROD"
    assert requires_hash_chain is True

    # A package that is valid for LAB_L1 but omits PROD-only gates must now fail
    # closed because the broken profile resolved to PROD.
    with pytest.raises(live.LiveEvidencePackageError) as exc:
        live.verify_live_evidence_package(_minimal_lab_not_run_package(), _campaign())
    assert exc.value.code == "PACKAGE_GATE_SET_INVALID"
    assert "EVIDENCE_BACKEND_CONTROLS" in str(exc.value)
    assert "EVIDENCE_TENANT_ISOLATION" in str(exc.value)
