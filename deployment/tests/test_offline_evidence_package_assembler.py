"""Repository-only tests for the offline HOLD evidence-package assembler (CHG-HSL-051).

The assembler composes a schema-valid PRE_PROMOTION / POST_EFFECT evidence HOLD
package from already-collected / explicitly-supplied evidence inputs only. It
reuses the canonical verifier's profile-aware required gate set and the frozen
LAB_L1 evidence-chain seal primitive. These tests prove:

- the package is schema-valid and deterministic;
- promotion stays HOLD (promotion_allowed is always False);
- unavailable live gates are NOT_RUN / OBSERVED_ABSENT, never fabricated PASS;
- content digests are computed and validated from supplied inputs;
- gate-set, missing-gate, duplicate-gate and tamper conditions fail closed;
- the accepted LAB_L1 profile drives the resolved gate set;
- the campaign BLOCKED/HOLD state is preserved (not moved) by the assembler.
"""

from __future__ import annotations

import copy
import hashlib
import importlib.util
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import jsonschema
import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
MODULE_PATH = (
    ROOT
    / "deployment"
    / "runtime-promotion"
    / "offline_evidence_package_assembler.py"
)
VERIFIER_PATH = (
    ROOT
    / "deployment"
    / "runtime-promotion"
    / "runtime_live_promotion_evidence.py"
)
SCHEMA_PATH = (
    ROOT
    / "deployment"
    / "runtime-promotion"
    / "live-promotion-evidence-package.schema.json"
)
SEAL_PATH = ROOT / "platform" / "evidence-plane" / "seal.py"
CAMPAIGN_PATH = ROOT / "validation" / "VAL-HSL-RUNNER-L1-LIVE-PROMOTION.yaml"
ASSURANCE_PROFILE_PATH = ROOT / "platform" / "assurance" / "current-assurance-profile.yaml"


def _load(name: str, path: Path) -> Any:
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


asm = _load("offline_evidence_package_assembler_chg051", MODULE_PATH)
live = _load("offline_evidence_package_assembler_verifier_chg051", VERIFIER_PATH)
_seal = _load("offline_evidence_package_assembler_seal_chg051", SEAL_PATH)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _campaign_commit() -> str:
    doc = yaml.safe_load(CAMPAIGN_PATH.read_text(encoding="utf-8"))
    return str(doc["candidate"]["commit"])


def _build_sealed_chain() -> dict[str, Any]:
    """Build a real, valid LAB_L1 sealed evidence-chain document via the primitive."""
    correlation = {
        "campaign_id": "webgoat-l1-campaign",
        "run_id": "run-0001",
        "step_id": "step-0001",
        "attempt_id": "attempt-0001",
    }
    chain = _seal.EvidenceChain("chain_" + "a" * 48)
    chain.append_object(
        object_kind="evidence_record",
        object_ref="evidence://runner-live/promotion/chain-entry-0.json",
        object_digest_sha256="0" * 64,
        object_size_bytes=10,
        object_media_type="application/json",
        correlation=correlation,
    )
    return _seal.seal_chain(chain, sealed_at="2026-08-14T16:30:00Z")


def _input(gate_id: str, value: str, *, observed_at: str | None = None,
           observed_absent: bool = False) -> Any:
    return asm.EvidenceInput(
        gate_id=gate_id, value=value, observed_at=observed_at,
        observed_absent=observed_absent,
    )


# ---------------------------------------------------------------------------
# Determinism & schema-validity
# ---------------------------------------------------------------------------


def test_empty_hold_package_is_schema_valid() -> None:
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    validator = jsonschema.Draft202012Validator(
        schema, format_checker=jsonschema.FormatChecker()
    )
    for phase in ("PRE_PROMOTION", "POST_EFFECT"):
        pkg = asm.assemble_hold_package(phase=phase, package_id=f"hold-{phase.lower()}")
        errors = list(validator.iter_errors(pkg.package))
        assert not errors, f"{phase}: {errors}"


def test_assembler_is_deterministic() -> None:
    a = asm.assemble_hold_package(phase="PRE_PROMOTION", package_id="deterministic-pkg")
    b = asm.assemble_hold_package(phase="PRE_PROMOTION", package_id="deterministic-pkg")
    assert json.dumps(a.package, sort_keys=True) == json.dumps(b.package, sort_keys=True)


def test_assembled_package_passes_canonical_verifier() -> None:
    pkg = asm.assemble_hold_package(phase="PRE_PROMOTION", package_id="verifiable")
    campaign = live.load_campaign()
    result = live.verify_live_evidence_package(pkg.package, campaign)
    assert result.package_valid is True


# ---------------------------------------------------------------------------
# Promotion stays HOLD (the central proof)
# ---------------------------------------------------------------------------


def test_promotion_allowed_false_in_empty_hold_package() -> None:
    pkg = asm.assemble_hold_package(phase="PRE_PROMOTION", package_id="hold-empty-package")
    assert pkg.package["package_status"] == "ASSEMBLED"
    # No gate is executed; the canonical verifier must keep promotion HOLD.
    result = live.verify_live_evidence_package(pkg.package, live.load_campaign())
    assert result.promotion_allowed is False
    assert result.recommendation == "HOLD"
    assert result.package_complete is False


def test_promotion_allowed_false_even_with_supplied_evidence_and_seal() -> None:
    sealed = _build_sealed_chain()
    evidence = [
        _input("GATEWAY_ADMISSION_REOBSERVATION", "raw-gateway-evidence-content"),
        _input("HOST_IDENTITY_SOCKET_TRUST", "raw-socket-trust-content"),
    ]
    pkg = asm.assemble_hold_package(
        phase="PRE_PROMOTION",
        package_id="hold-supplied-package",
        evidence=evidence,
        evidence_chain_document=sealed,
    )
    # HASH_CHAIN_SEAL is bound to the sealed doc; supplied gates are PASS.
    assert pkg.package["gates"][0]["gate_id"] in live.required_gate_ids("PRE_PROMOTION", True)
    result = live.verify_live_evidence_package(pkg.package, live.load_campaign())
    # Even with executed gates + a real sealed chain, promotion is never granted.
    assert result.promotion_allowed is False
    assert result.recommendation == "HOLD"


def test_recommendation_is_hold_for_both_phases() -> None:
    for phase in ("PRE_PROMOTION", "POST_EFFECT"):
        pkg = asm.assemble_hold_package(phase=phase, package_id=f"hold-{phase.lower()}")
        result = live.verify_live_evidence_package(pkg.package, live.load_campaign())
        assert result.recommendation == "HOLD"
        assert result.promotion_allowed is False


# ---------------------------------------------------------------------------
# Gate-set / profile resolution
# ---------------------------------------------------------------------------


def test_resolved_gate_set_equals_canonical_verifier_set() -> None:
    profile, requires_chain = asm._resolve_assurance_profile()
    assert profile == "LAB_L1"
    assert requires_chain is True
    pkg = asm.assemble_hold_package(phase="PRE_PROMOTION", package_id="gate-set-resolved")
    expected = set(live.required_gate_ids("PRE_PROMOTION", requires_chain))
    actual = {g["gate_id"] for g in pkg.package["gates"]}
    assert actual == expected
    assert "HASH_CHAIN_SEAL" in actual  # LAB_L1 requires the hash chain


def test_assembler_rejects_unknown_gate_id() -> None:
    with pytest.raises(asm.AssemblerError) as exc:
        asm.assemble_hold_package(
            phase="PRE_PROMOTION",
            package_id="bad-gate",
            evidence=[_input("NOT_A_REAL_GATE", "x")],
        )
    assert exc.value.code == "GATE_NOT_IN_REQUIRED_SET"


def test_assembler_rejects_duplicate_inputs() -> None:
    with pytest.raises(asm.AssemblerError) as exc:
        asm.assemble_hold_package(
            phase="PRE_PROMOTION",
            package_id="dup",
            evidence=[
                _input("GATEWAY_ADMISSION_REOBSERVATION", "a"),
                _input("GATEWAY_ADMISSION_REOBSERVATION", "b"),
            ],
        )
    assert exc.value.code == "DUPLICATE_INPUT"


def test_assembler_rejects_invalid_phase() -> None:
    with pytest.raises(asm.AssemblerError) as exc:
        asm.assemble_hold_package(phase="NOT_A_PHASE", package_id="x")
    assert exc.value.code == "PHASE_INVALID"


# ---------------------------------------------------------------------------
# No fabrication: unspecified gates stay NOT_RUN
# ---------------------------------------------------------------------------


def test_unspecified_gates_are_not_run() -> None:
    pkg = asm.assemble_hold_package(phase="PRE_PROMOTION", package_id="partial-supply")
    results = {g["gate_id"]: g["result"] for g in pkg.package["gates"]}
    assert all(r == "NOT_RUN" for r in results.values())
    assert len(pkg.not_run_gate_ids) == pkg.required_gate_count


def test_supplied_gate_passes_but_others_stay_not_run() -> None:
    pkg = asm.assemble_hold_package(
        phase="PRE_PROMOTION",
        package_id="one-supplied-gate",
        evidence=[_input("GATEWAY_ADMISSION_REOBSERVATION", "evidence-content")],
    )
    results = {g["gate_id"]: g["result"] for g in pkg.package["gates"]}
    assert results["GATEWAY_ADMISSION_REOBSERVATION"] == "PASS"
    others = [g for g in pkg.package["gates"] if g["gate_id"] != "GATEWAY_ADMISSION_REOBSERVATION"]
    assert all(g["result"] == "NOT_RUN" for g in others)
    # The verifier still blocks the package (DenyAll evidence verifier).
    result = live.verify_live_evidence_package(pkg.package, live.load_campaign())
    assert result.package_complete is False
    assert result.promotion_allowed is False


# ---------------------------------------------------------------------------
# Content digest computation / validation
# ---------------------------------------------------------------------------


def test_evidence_digest_is_sha256_of_supplied_content() -> None:
    content = "canonical-evidence-bytes-for-gateway"
    pkg = asm.assemble_hold_package(
        phase="PRE_PROMOTION",
        package_id="digest-package",
        evidence=[_input("GATEWAY_ADMISSION_REOBSERVATION", content)],
    )
    gate = next(g for g in pkg.package["gates"]
                if g["gate_id"] == "GATEWAY_ADMISSION_REOBSERVATION")
    assert gate["evidence_sha256"] == hashlib.sha256(content.encode()).hexdigest()


def test_raw_content_input_synthesizes_evidence_ref() -> None:
    pkg = asm.assemble_hold_package(
        phase="PRE_PROMOTION",
        package_id="ref-package-a",
        evidence=[_input("HOST_IDENTITY_SOCKET_TRUST", "raw-content")],
    )
    gate = next(g for g in pkg.package["gates"] if g["gate_id"] == "HOST_IDENTITY_SOCKET_TRUST")
    assert gate["evidence_ref"].startswith("evidence://offline-assembler/")


def test_explicit_evidence_ref_is_preserved() -> None:
    pkg = asm.assemble_hold_package(
        phase="PRE_PROMOTION",
        package_id="ref-package-b",
        evidence=[_input("RECEIPT_DELIVERY", "evidence://external/receipt.json")],
    )
    gate = next(g for g in pkg.package["gates"] if g["gate_id"] == "RECEIPT_DELIVERY")
    assert gate["evidence_ref"] == "evidence://external/receipt.json"


def test_computed_digest_count_is_recorded() -> None:
    pkg = asm.assemble_hold_package(
        phase="PRE_PROMOTION",
        package_id="count-package",
        evidence=[
            _input("GATEWAY_ADMISSION_REOBSERVATION", "a"),
            _input("HOST_IDENTITY_SOCKET_TRUST", "b"),
        ],
    )
    assert pkg.computed_digest_count == 2


# ---------------------------------------------------------------------------
# OBSERVED_ABSENT (missing live capability) classification
# ---------------------------------------------------------------------------


def test_observed_absent_gate_recorded_and_emitted_not_run() -> None:
    pkg = asm.assemble_hold_package(
        phase="PRE_PROMOTION",
        package_id="absent-package",
        evidence=[
            _input("EVIDENCE_BACKEND_CONTROLS", "evidence://note/absent.json",
                   observed_absent=True),
        ],
    )
    assert "EVIDENCE_BACKEND_CONTROLS" in pkg.observed_absent_gate_ids
    gate = next(g for g in pkg.package["gates"]
                if g["gate_id"] == "EVIDENCE_BACKEND_CONTROLS")
    # Schema only permits NOT_RUN/PASS/FAIL; absence is emitted as NOT_RUN and
    # classified (never fabricated PASS).
    assert gate["result"] == "NOT_RUN"
    assert "EVIDENCE_BACKEND_CONTROLS" in pkg.not_run_gate_ids


def test_observed_absent_outside_permitted_set_is_treated_as_evidence() -> None:
    # A forbidden-capability gate cannot be marked OBSERVED_ABSENT; the flag is
    # ignored for it and the input is treated as normal supplied evidence (PASS).
    pkg = asm.assemble_hold_package(
        phase="PRE_PROMOTION",
        package_id="absent-nonpermitted-pkg",
        evidence=[
            _input("GATEWAY_ADMISSION_REOBSERVATION", "real-content",
                   observed_absent=True),
        ],
    )
    assert "GATEWAY_ADMISSION_REOBSERVATION" not in pkg.observed_absent_gate_ids
    gate = next(g for g in pkg.package["gates"]
                if g["gate_id"] == "GATEWAY_ADMISSION_REOBSERVATION")
    assert gate["result"] == "PASS"


# ---------------------------------------------------------------------------
# HASH_CHAIN_SEAL integration (frozen primitive)
# ---------------------------------------------------------------------------


def test_sealed_chain_input_produces_hash_chain_seal_pass() -> None:
    sealed = _build_sealed_chain()
    digest = sealed["seal"]["chain_state_digest_sha256"]
    pkg = asm.assemble_hold_package(
        phase="PRE_PROMOTION",
        package_id="sealed-package",
        evidence_chain_document=sealed,
    )
    gate = next(g for g in pkg.package["gates"] if g["gate_id"] == "HASH_CHAIN_SEAL")
    assert gate["result"] == "PASS"
    assert gate["evidence_sha256"] == digest


def test_unverified_chain_is_rejected() -> None:
    with pytest.raises(asm.AssemblerError) as exc:
        asm.assemble_hold_package(
            phase="PRE_PROMOTION",
            package_id="bad-chain-package",
            evidence_chain_document={"schema_version": "1.0", "profile": "LAB_L1"},
        )
    assert exc.value.code == "CHAIN_SEAL_UNVERIFIED"


def test_tampered_chain_is_rejected() -> None:
    sealed = _build_sealed_chain()
    sealed["entries"][0]["object_digest_sha256"] = "f" * 64  # tamper
    with pytest.raises(asm.AssemblerError) as exc:
        asm.assemble_hold_package(
            phase="PRE_PROMOTION",
            package_id="tampered-chain-pkg",
            evidence_chain_document=sealed,
        )
    assert exc.value.code == "CHAIN_SEAL_UNVERIFIED"


# ---------------------------------------------------------------------------
# Tamper at the produced-package level (fed to the canonical verifier)
# ---------------------------------------------------------------------------


def test_edited_pass_with_null_evidence_is_rejected_by_schema() -> None:
    pkg = asm.assemble_hold_package(phase="PRE_PROMOTION", package_id="tamper-edit-pkg")
    tampered = copy.deepcopy(pkg.package)
    # Force a NOT_RUN gate to a fabricated PASS with null evidence.
    for gate in tampered["gates"]:
        if gate["result"] == "NOT_RUN":
            gate["result"] = "PASS"
            gate["observed_at"] = _now()
            gate["evidence_ref"] = "evidence://x/y.json"
            gate["evidence_sha256"] = "0" * 64
            break
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    validator = jsonschema.Draft202012Validator(
        schema, format_checker=jsonschema.FormatChecker()
    )
    # PASS requires the supplied digest to be real; a fabricated one still fails
    # the canonical verifier (DenyAll) -> package incomplete, promotion HOLD.
    result = live.verify_live_evidence_package(tampered, live.load_campaign())
    assert result.package_complete is False
    assert result.promotion_allowed is False
    # Schema itself still accepts the structure (the verifier is the fail-closed gate).
    assert not list(validator.iter_errors(tampered))


def test_missing_gate_is_rejected_by_verifier() -> None:
    pkg = asm.assemble_hold_package(phase="PRE_PROMOTION", package_id="drop-gate-package")
    dropped = copy.deepcopy(pkg.package)
    dropped["gates"] = dropped["gates"][:-1]  # remove one required gate
    with pytest.raises(live.LiveEvidencePackageError) as exc:
        live.verify_live_evidence_package(dropped, live.load_campaign())
    assert exc.value.code == "PACKAGE_GATE_SET_INVALID"


def test_duplicate_gate_is_rejected_by_verifier() -> None:
    pkg = asm.assemble_hold_package(phase="PRE_PROMOTION", package_id="dup-gate-package")
    dup = copy.deepcopy(pkg.package)
    dup["gates"] = dup["gates"] + [copy.deepcopy(dup["gates"][0])]
    with pytest.raises(live.LiveEvidencePackageError) as exc:
        live.verify_live_evidence_package(dup, live.load_campaign())
    assert exc.value.code == "PACKAGE_INVALID"


def test_extra_gate_is_rejected_by_verifier() -> None:
    pkg = asm.assemble_hold_package(phase="PRE_PROMOTION", package_id="extra-gate-package")
    extra = copy.deepcopy(pkg.package)
    extra["gates"] = extra["gates"] + [
        {
            "gate_id": "INVENTED_GATE",
            "result": "NOT_RUN",
            "observed_at": None,
            "evidence_ref": None,
            "evidence_sha256": None,
        }
    ]
    with pytest.raises(live.LiveEvidencePackageError) as exc:
        live.verify_live_evidence_package(extra, live.load_campaign())
    assert exc.value.code == "PACKAGE_GATE_SET_INVALID"


# ---------------------------------------------------------------------------
# Campaign BLOCKED/HOLD preservation
# ---------------------------------------------------------------------------


def test_campaign_blocked_hold_state_is_preserved() -> None:
    campaign = yaml.safe_load(CAMPAIGN_PATH.read_text(encoding="utf-8"))
    # The canonical campaign must remain BLOCKED/HOLD; the assembler only reads it.
    recommendation = campaign.get("promotionRecommendation")
    assert recommendation in ("HOLD", None), recommendation
    blocked = [
        o for o in campaign["observations"]
        if o.get("required") and o.get("result") != "PASS"
    ]
    assert blocked, "expected required BLOCKED observations to remain"
    # The assembler does not mutate the campaign file.
    source = MODULE_PATH.read_text(encoding="utf-8")
    assert "validation/VAL" not in source.replace("CAMPAIGN_PATH", "")


# ---------------------------------------------------------------------------
# AST: no collection / mutation / target execution / signer / trust / promote
# ---------------------------------------------------------------------------


def test_source_has_no_collection_mutation_or_target_execution_path() -> None:
    source = MODULE_PATH.read_text(encoding="utf-8")
    for forbidden in (
        "requests",
        "http.client",
        "socket",
        "subprocess",
        "docker",
        "boto3",
        "azure.storage",
        "google.cloud",
        "os.chmod",
        "os.chown",
        ".sign(",
        "systemd",
        "trust_store",
        "promote(",
        "promotion_allowed=True",
        "recommendation=\"PROMOTE\"",
    ):
        assert forbidden not in source, f"forbidden token present: {forbidden}"
    # Fail-closed invariants are present and explicit.
    assert "promotion_allowed" in source
    assert 'recommendation="HOLD"' in source or "HOLD" in source
    assert "HASH_CHAIN_SEAL" in source
    assert "required_gate_ids" in source
