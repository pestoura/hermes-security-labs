from __future__ import annotations

import copy
import hashlib
import importlib.util
import sys
from datetime import datetime, timezone
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
ASSURANCE_PROFILE_PATH = ROOT / "platform" / "assurance" / "current-assurance-profile.yaml"


def _load(name: str, path: Path) -> Any:
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


live = _load("runtime_live_promotion_evidence_test", MODULE_PATH)
_seal = _load("runtime_live_promotion_evidence_seal_test", ROOT / "platform" / "evidence-plane" / "seal.py")

# The canonical hash-chain/seal gate is required for LAB_L1 and PROD because both
# assurance profiles set `requires_hash_chain: true`.
HASH_GATE = live.HASH_CHAIN_SEAL_GATE


def _campaign() -> dict[str, Any]:
    document = yaml.safe_load(CAMPAIGN_PATH.read_text(encoding="utf-8"))
    assert isinstance(document, dict)
    return document


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace(
        "+00:00", "Z"
    )


def _digest(gate_id: str) -> str:
    return hashlib.sha256(f"evidence:{gate_id}".encode()).hexdigest()


def _build_sealed_chain(chain_state_digest_out: list[str] | None = None) -> dict[str, Any]:
    """Build a real, valid LAB_L1 sealed evidence-chain document via the frozen primitive."""
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
    sealed = _seal.seal_chain(chain, sealed_at="2026-08-14T16:30:00Z")
    if chain_state_digest_out is not None:
        chain_state_digest_out.append(sealed["seal"]["chain_state_digest_sha256"])
    return sealed


def _assembled(phase: str) -> dict[str, Any]:
    """Profile-aware ASSEMBLED fixture with a real sealed-chain document for HASH_CHAIN_SEAL."""
    out: list[str] = []
    sealed = _build_sealed_chain(out)
    seal_digest = out[0]
    gates = []
    for gate_id in sorted(live.required_gate_ids(phase, True)):
        if gate_id == HASH_GATE:
            gates.append(
                {
                    "gate_id": gate_id,
                    "result": "PASS",
                    "observed_at": _now(),
                    "evidence_ref": "evidence://runner-live/promotion/hash-chain-seal.json",
                    "evidence_sha256": seal_digest,
                }
            )
        else:
            gates.append(
                {
                    "gate_id": gate_id,
                    "result": "PASS",
                    "observed_at": _now(),
                    "evidence_ref": f"evidence://runner-live/promotion/{gate_id.lower()}.json",
                    "evidence_sha256": _digest(gate_id),
                }
            )
    return {
        "schema_version": "1.0",
        "package_id": f"webgoat-l1-{phase.lower()}-fixture",
        "package_status": "ASSEMBLED",
        "phase": phase,
        "created_at": _now(),
        "candidate": {
            "environment_id": "webgoat",
            "adapter_id": "webgoat-l1",
            "capability_id": "web.discovery.headers",
            "intrusiveness_level": "L1",
            "repository_commit": _campaign()["candidate"]["commit"],
        },
        "evidence_chain_document": sealed,
        "gates": gates,
    }


class StaticEvidenceVerifier:
    def __init__(self, accepted: bool = True) -> None:
        self.accepted = accepted
        self.calls: list[tuple[str, str]] = []

    def verify(self, evidence_ref: str, sha256: str) -> bool:
        self.calls.append((evidence_ref, sha256))
        return self.accepted and evidence_ref.startswith("evidence://") and len(sha256) == 64


# ---------------------------------------------------------------------------
# Profile-aware gate-set composition
# ---------------------------------------------------------------------------


def test_lab_l1_required_gate_set_includes_hash_chain_seal() -> None:
    # The live assurance profile is LAB_L1 with requires_hash_chain: true.
    profile = yaml.safe_load(ASSURANCE_PROFILE_PATH.read_text(encoding="utf-8"))
    assert profile["assurance_profile"] == "LAB_L1"
    assert profile["evaluation"]["requires_hash_chain"] is True

    _, requires_hash_chain = live._resolve_assurance()
    assert requires_hash_chain is True

    for phase in ("PRE_PROMOTION", "POST_EFFECT"):
        gates = live.required_gate_ids(phase, requires_hash_chain)
        assert HASH_GATE in gates
    # Base PRE_PROMOTION gates are preserved (no PROD gate weakened for LAB_L1).
    pre = live.required_gate_ids("PRE_PROMOTION", requires_hash_chain)
    assert "EVIDENCE_BACKEND_CONTROLS" in pre
    assert "EVIDENCE_TENANT_ISOLATION" in pre


def test_prod_required_gate_set_keeps_external_worm_and_tenant_isolation() -> None:
    # PROD requires_hash_chain: true and must keep every PROD gate.
    prod_gates = live.required_gate_ids("PRE_PROMOTION", requires_hash_chain=True)
    assert HASH_GATE in prod_gates
    # External WORM backend control + multi-tenant isolation gates are NOT dropped.
    assert "EVIDENCE_BACKEND_CONTROLS" in prod_gates
    assert "EVIDENCE_TENANT_ISOLATION" in prod_gates


def test_lab_l1_and_prod_gate_sets_are_equal_when_both_require_chain() -> None:
    for phase in ("PRE_PROMOTION", "POST_EFFECT"):
        lab = live.required_gate_ids(phase, requires_hash_chain=True)
        prod = live.required_gate_ids(phase, requires_hash_chain=True)
        assert lab == prod


# ---------------------------------------------------------------------------
# Committed example stays inert / fail-closed
# ---------------------------------------------------------------------------


def test_committed_example_is_inert_and_incomplete() -> None:
    package = live.load_package(PACKAGE_PATH)
    assert package["evidence_chain_document"] is None
    result = live.verify_live_evidence_package(
        package, _campaign(), evidence_verifier=StaticEvidenceVerifier()
    )
    assert result.package_valid is True
    assert result.package_complete is False
    assert result.promotion_allowed is False
    assert result.recommendation == "HOLD"
    assert result.next_review == "EVIDENCE_COLLECTION_REQUIRED"
    assert result.required_gate_count == len(live.required_gate_ids("PRE_PROMOTION", True))
    assert all(blocker.endswith(":NOT_RUN") for blocker in result.blockers)


# ---------------------------------------------------------------------------
# Complete package (real sealed chain) requires human/acceptance review only
# ---------------------------------------------------------------------------


def test_complete_pre_promotion_package_requires_human_review_not_promotion() -> None:
    verifier = StaticEvidenceVerifier()
    package = _assembled("PRE_PROMOTION")
    result = live.verify_live_evidence_package(package, _campaign(), evidence_verifier=verifier)
    assert result.package_complete is True
    assert result.promotion_allowed is False
    assert result.recommendation == "HOLD"
    assert result.next_review == "HUMAN_PROMOTION_REVIEW_REQUIRED"
    assert result.verified_evidence_count == len(live.required_gate_ids("PRE_PROMOTION", True))
    assert result.blockers == ()


def test_complete_post_effect_package_requires_campaign_acceptance_review() -> None:
    verifier = StaticEvidenceVerifier()
    package = _assembled("POST_EFFECT")
    result = live.verify_live_evidence_package(package, _campaign(), evidence_verifier=verifier)
    assert result.package_complete is True
    assert result.promotion_allowed is False
    assert result.recommendation == "HOLD"
    assert result.next_review == "CAMPAIGN_ACCEPTANCE_REVIEW_REQUIRED"
    assert result.verified_evidence_count == len(live.required_gate_ids("POST_EFFECT", True))


# ---------------------------------------------------------------------------
# HASH_CHAIN_SEAL integrity verification through the real frozen primitive
# ---------------------------------------------------------------------------


def test_hash_chain_seal_verified_by_real_primitive_with_valid_seal() -> None:
    package = _assembled("PRE_PROMOTION")
    result = live.verify_live_evidence_package(package, _campaign())
    # No delegated verifier -> only the self-verifying seal is verified; the
    # other delegated gates are unverified.
    assert "HASH_CHAIN_SEAL:EVIDENCE_UNVERIFIED" not in result.blockers
    assert result.verified_evidence_count == 1
    delegated = [
        b for b in result.blockers if b != "HASH_CHAIN_SEAL:EVIDENCE_UNVERIFIED"
    ]
    assert len(delegated) == len(live.required_gate_ids("PRE_PROMOTION", True)) - 1


def test_hash_chain_seal_rejects_missing_document() -> None:
    package = _assembled("PRE_PROMOTION")
    for gate in package["gates"]:
        if gate["gate_id"] == HASH_GATE:
            gate.update(
                {
                    "result": "PASS",
                    "observed_at": _now(),
                    "evidence_ref": "evidence://x.json",
                    "evidence_sha256": "0" * 64,
                }
            )
    package["evidence_chain_document"] = None
    result = live.verify_live_evidence_package(package, _campaign())
    assert "HASH_CHAIN_SEAL:EVIDENCE_UNVERIFIED" in result.blockers
    assert result.package_complete is False


def test_hash_chain_seal_rejects_tampered_chain_entry() -> None:
    package = _assembled("PRE_PROMOTION")
    sealed = copy.deepcopy(package["evidence_chain_document"])
    sealed["entries"][0]["object_digest_sha256"] = "f" * 64
    package["evidence_chain_document"] = sealed
    result = live.verify_live_evidence_package(package, _campaign())
    assert "HASH_CHAIN_SEAL:EVIDENCE_UNVERIFIED" in result.blockers
    assert result.package_complete is False


def test_hash_chain_seal_rejects_tampered_seal_digest() -> None:
    package = _assembled("PRE_PROMOTION")
    sealed = copy.deepcopy(package["evidence_chain_document"])
    sealed["seal"]["chain_state_digest_sha256"] = "f" * 64
    package["evidence_chain_document"] = sealed
    result = live.verify_live_evidence_package(package, _campaign())
    assert "HASH_CHAIN_SEAL:EVIDENCE_UNVERIFIED" in result.blockers
    assert result.package_complete is False


def test_hash_chain_seal_rejects_digest_binding_mismatch() -> None:
    package = _assembled("PRE_PROMOTION")
    # Valid sealed doc but gate evidence_sha256 does not bind the seal's chain state.
    for gate in package["gates"]:
        if gate["gate_id"] == HASH_GATE:
            gate["evidence_sha256"] = "f" * 64
    result = live.verify_live_evidence_package(package, _campaign())
    assert "HASH_CHAIN_SEAL:EVIDENCE_UNVERIFIED" in result.blockers
    assert result.package_complete is False


def test_hash_chain_seal_rejects_schema_violation() -> None:
    package = _assembled("PRE_PROMOTION")
    sealed = copy.deepcopy(package["evidence_chain_document"])
    sealed.pop("seal")  # drops a required property -> schema violation
    package["evidence_chain_document"] = sealed
    result = live.verify_live_evidence_package(package, _campaign())
    assert "HASH_CHAIN_SEAL:EVIDENCE_UNVERIFIED" in result.blockers
    assert result.package_complete is False


# ---------------------------------------------------------------------------
# Package gate-set validity
# ---------------------------------------------------------------------------


def test_default_verifier_refuses_self_declared_pass_evidence() -> None:
    result = live.verify_live_evidence_package(_assembled("PRE_PROMOTION"), _campaign())
    # Only the self-verifying seal is verified; all delegated gates are unverified.
    assert result.package_complete is False
    delegated = [
        b for b in result.blockers if b != "HASH_CHAIN_SEAL:EVIDENCE_UNVERIFIED"
    ]
    assert all("EVIDENCE_UNVERIFIED" in b for b in delegated)


def test_verified_fail_is_valid_evidence_but_blocks_phase() -> None:
    package = _assembled("PRE_PROMOTION")
    gate = next(
        item for item in package["gates"] if item["gate_id"] == "UNAUTHORIZED_PEER_NEGATIVE"
    )
    gate["result"] = "FAIL"
    result = live.verify_live_evidence_package(package, _campaign(), evidence_verifier=StaticEvidenceVerifier())
    assert result.package_valid is True
    assert result.package_complete is False
    assert "UNAUTHORIZED_PEER_NEGATIVE:FAIL" in result.blockers


def test_not_run_gate_blocks_assembled_phase() -> None:
    package = _assembled("PRE_PROMOTION")
    gate = next(item for item in package["gates"] if item["gate_id"] == "RECEIPT_DELIVERY")
    gate.update(
        {
            "result": "NOT_RUN",
            "observed_at": None,
            "evidence_ref": None,
            "evidence_sha256": None,
        }
    )
    result = live.verify_live_evidence_package(package, _campaign(), evidence_verifier=StaticEvidenceVerifier())
    assert result.package_complete is False
    assert "RECEIPT_DELIVERY:NOT_RUN" in result.blockers


def test_assembled_package_must_bind_exact_campaign_commit() -> None:
    package = _assembled("PRE_PROMOTION")
    package["candidate"]["repository_commit"] = "f" * 40
    with pytest.raises(live.LiveEvidencePackageError) as exc:
        live.verify_live_evidence_package(package, _campaign(), evidence_verifier=StaticEvidenceVerifier())
    assert exc.value.code == "PACKAGE_CANDIDATE_MISMATCH"


def test_phase_gate_set_is_exact_and_cannot_skip_human_decision() -> None:
    package = _assembled("POST_EFFECT")
    package["gates"] = [
        item for item in package["gates"] if item["gate_id"] != "HITL_PROMOTION_DECISION"
    ]
    with pytest.raises(live.LiveEvidencePackageError) as exc:
        live.verify_live_evidence_package(package, _campaign(), evidence_verifier=StaticEvidenceVerifier())
    assert exc.value.code == "PACKAGE_GATE_SET_INVALID"


def test_extra_gate_is_rejected_instead_of_silently_ignored() -> None:
    package = _assembled("PRE_PROMOTION")
    extra = copy.deepcopy(package["gates"][0])
    extra["gate_id"] = "UNDECLARED_GATE"
    package["gates"].append(extra)
    with pytest.raises(live.LiveEvidencePackageError) as exc:
        live.verify_live_evidence_package(package, _campaign(), evidence_verifier=StaticEvidenceVerifier())
    assert exc.value.code == "PACKAGE_GATE_SET_INVALID"


def test_duplicate_gate_is_rejected() -> None:
    package = _assembled("PRE_PROMOTION")
    package["gates"].append(copy.deepcopy(package["gates"][0]))
    with pytest.raises(live.LiveEvidencePackageError) as exc:
        live.verify_live_evidence_package(package, _campaign(), evidence_verifier=StaticEvidenceVerifier())
    assert exc.value.code == "PACKAGE_INVALID"


def test_missing_hash_chain_seal_gate_is_rejected() -> None:
    package = _assembled("PRE_PROMOTION")
    package["gates"] = [g for g in package["gates"] if g["gate_id"] != HASH_GATE]
    with pytest.raises(live.LiveEvidencePackageError) as exc:
        live.verify_live_evidence_package(package, _campaign(), evidence_verifier=StaticEvidenceVerifier())
    assert exc.value.code == "PACKAGE_GATE_SET_INVALID"


def test_not_run_package_cannot_smuggle_executed_gate() -> None:
    package = live.load_package(PACKAGE_PATH)
    package["gates"][0] = {
        "gate_id": package["gates"][0]["gate_id"],
        "result": "PASS",
        "observed_at": _now(),
        "evidence_ref": "evidence://runner-live/promotion/smuggled.json",
        "evidence_sha256": hashlib.sha256(b"smuggled").hexdigest(),
    }
    with pytest.raises(live.LiveEvidencePackageError) as exc:
        live.verify_live_evidence_package(package, _campaign(), evidence_verifier=StaticEvidenceVerifier())
    assert exc.value.code == "PACKAGE_INVALID"


# ---------------------------------------------------------------------------
# Reconciliation literals (package verifier vs campaign governance state)
# ---------------------------------------------------------------------------


def test_package_verifier_reconciles_with_blocked_hold_campaign() -> None:
    campaign = _campaign()
    # The campaign that drives the candidate commit stays BLOCKED / HOLD.
    assert campaign["state"] == "BLOCKED"
    assert campaign["promotionRecommendation"] == "HOLD"
    # The verifier never changes promotion: any complete package stays HOLD.
    result = live.verify_live_evidence_package(_assembled("PRE_PROMOTION"), campaign)
    assert result.promotion_allowed is False
    assert result.recommendation == "HOLD"


def test_cli_returns_red_for_incomplete_committed_example() -> None:
    assert live.main(["--package", str(PACKAGE_PATH), "check"]) == 2


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
    ):
        assert forbidden not in source
    assert "DenyAllEvidenceVerifier" in source
    assert "promotion_allowed=False" in source
    assert 'recommendation="HOLD"' in source
    # The new gate id is referenced and fail-closed.
    assert HASH_GATE in source
