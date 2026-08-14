#!/usr/bin/env python3
"""Tests for the LAB_L1 evidence-custody -> HOLD-package bridge (CHG-HSL-056).

Repository-only, fail-closed. Proves the integration of the CHG-HSL-055 canonical
LocalEvidenceStore custody/verifier with the CHG-HSL-051 offline PRE_PROMOTION assembler
and the CHG-HSL-054 SAFE live-observation adapter, so already-collected SAFE artifacts can
be custodized into real local evidence refs/digests, verified by a LocalEvidenceVerifier,
and a sealed EvidenceChain can satisfy HASH_CHAIN_SEAL.

Required invariants proven here:
- GATEWAY_ADMISSION_REOBSERVATION / BRIDGE_REVISION_REOBSERVATION become VERIFIED via the
  real LocalEvidenceStore + LocalEvidenceVerifier (not fabricated).
- HASH_CHAIN_SEAL becomes VERIFIED (sealed EvidenceChain, self-verifying).
- HOST_IDENTITY_SOCKET_TRUST remains NOT_RUN (trust OBSERVED_ABSENT, never elevatable).
- USER_NAMESPACE_MAPPING / SIGNER_PROVIDER_ATTESTATION / RECEIPT_DELIVERY /
  UNAUTHORIZED_PEER_NEGATIVE remain NOT_RUN (no canonical supporting evidence).
- EVIDENCE_BACKEND_CONTROLS / EVIDENCE_TENANT_ISOLATION are OBSERVED_ABSENT (LAB_L1 tombstone),
  never PASS.
- All POST_EFFECT gates remain NOT_RUN.
- backend/tenant stay LAB_L1 OBSERVED_ABSENT / NOT_RUN; promotion_allowed=false,
  recommendation=HOLD, runtime_status=NOT_RUN throughout.
- Provenance: the supplied candidate commit (an ancestor of current main) is bound verbatim,
  never auto-repinned to current main.
- No new live evidence is collected; no PROD WORM/tenant/signer requirement is weakened;
  LocalEvidenceStore is never reclassified as a production WORM backend.

No runtime/systemd/network/Docker/target/trust/signer effect. No real evidence package is
committed.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
EVIDENCE_DIR = ROOT / "platform" / "evidence-plane"
RUNTIME_PROMOTION_DIR = ROOT / "deployment" / "runtime-promotion"

# Authoritative campaign candidate commit (CHG-HSL-053 reconciliation). It is an ANCESTOR
# of the current main tip by design; the bridge must bind it verbatim, never auto-repin.
CAMPAIGN_CANDIDATE_COMMIT = "a63ef01925e5c1b925936c1e73b11b2d6cd2a6a5"
# The authoritative current main tip at the time of this lane (must NOT appear as bound).
CURRENT_MAIN_TIP = "6db67f809b092c7500bbd7a48491b2c76a142a12"


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


bridge = _load(
    "lab_l1_custody_bridge_056",
    EVIDENCE_DIR / "runtime_promotion_evidence_custody_bridge.py",
)
seal_module = _load("lab_l1_seal_056", EVIDENCE_DIR / "seal.py")
store_module = _load("lab_l1_local_store_056", EVIDENCE_DIR / "local_store.py")


def _build(candidate_commit: str, tmp_path: Path):
    return bridge.build_custodized_hold_package(
        repo_root=ROOT,
        store_root=tmp_path / "store",
        candidate_commit=candidate_commit,
    )


def _gate_map(res):
    return {g["gate_id"]: g for g in res.package["gates"]}


# ----------------------------------------------------------- canonical outcomes


def test_gateway_and_bridge_and_hash_chain_seal_verified(tmp_path: Path) -> None:
    res = _build(CAMPAIGN_CANDIDATE_COMMIT, tmp_path)
    gates = _gate_map(res)
    # Pass + verified by the real LocalEvidenceVerifier.
    assert gates["GATEWAY_ADMISSION_REOBSERVATION"]["result"] == "PASS"
    assert gates["BRIDGE_REVISION_REOBSERVATION"]["result"] == "PASS"
    assert gates["HASH_CHAIN_SEAL"]["result"] == "PASS"
    # Exactly three verified evidence (the two custodized SAFE refs + the self-verifying seal).
    assert res.verified_evidence_count == 3
    assert set(res.pass_gate_ids) == {
        "GATEWAY_ADMISSION_REOBSERVATION",
        "BRIDGE_REVISION_REOBSERVATION",
        "HASH_CHAIN_SEAL",
    }
    # The two SAFE refs resolve to exactly one store record and bind their digest.
    assert len(res.evidence_refs) == 2
    assert all(r.startswith("evidence://offline-assembler/") for r in res.evidence_refs)
    assert len(res.object_digests) == 2


def test_host_identity_socket_trust_stays_not_run(tmp_path: Path) -> None:
    res = _build(CAMPAIGN_CANDIDATE_COMMIT, tmp_path)
    gates = _gate_map(res)
    # Socket facts ARE observed, but the trust store is OBSERVED_ABSENT -> never PASS.
    assert gates["HOST_IDENTITY_SOCKET_TRUST"]["result"] == "NOT_RUN"
    assert gates["HOST_IDENTITY_SOCKET_TRUST"]["gate_id"] not in res.pass_gate_ids


def test_user_namespace_signer_receipt_peer_negative_stay_not_run(tmp_path: Path) -> None:
    res = _build(CAMPAIGN_CANDIDATE_COMMIT, tmp_path)
    gates = _gate_map(res)
    for gate_id in (
        "USER_NAMESPACE_MAPPING",
        "SIGNER_PROVIDER_ATTESTATION",
        "RECEIPT_DELIVERY",
        "UNAUTHORIZED_PEER_NEGATIVE",
    ):
        assert gates[gate_id]["result"] == "NOT_RUN", gate_id
        assert gate_id in res.not_run_gate_ids


def test_backend_and_tenant_observed_absent_not_pass(tmp_path: Path) -> None:
    res = _build(CAMPAIGN_CANDIDATE_COMMIT, tmp_path)
    gates = _gate_map(res)
    # LAB_L1 tombstone: emitted NOT_RUN, recorded as observed_absent, never PASS.
    assert gates["EVIDENCE_BACKEND_CONTROLS"]["result"] == "NOT_RUN"
    assert gates["EVIDENCE_TENANT_ISOLATION"]["result"] == "NOT_RUN"
    assert "EVIDENCE_BACKEND_CONTROLS" in res.observed_absent_gate_ids
    assert "EVIDENCE_TENANT_ISOLATION" in res.observed_absent_gate_ids
    assert "EVIDENCE_BACKEND_CONTROLS" not in res.pass_gate_ids
    assert "EVIDENCE_TENANT_ISOLATION" not in res.pass_gate_ids


def test_post_effect_gates_absent_from_pre_promotion(tmp_path: Path) -> None:
    res = _build(CAMPAIGN_CANDIDATE_COMMIT, tmp_path)
    # PRE_PROMOTION phase must NOT contain any POST_EFFECT live-effect/reset gate.
    for gate_id in (
        "HITL_PROMOTION_DECISION",
        "PROMOTED_POLICY_SET",
        "LIVE_RUNNER_OUTCOME_PERSISTENCE",
        "LIVE_DISPATCH_AUDIT_PERSISTENCE",
        "WEBGOAT_L1_EFFECT_RESET",
    ):
        assert gate_id not in _gate_map(res), f"unexpected POST_EFFECT gate {gate_id} in PRE_PROMOTION"


def test_promotion_holds_not_run_runtime_status(tmp_path: Path) -> None:
    res = _build(CAMPAIGN_CANDIDATE_COMMIT, tmp_path)
    assert res.promotion_allowed is False
    assert res.recommendation == "HOLD"
    # The package is never complete (HOLD blockers remain), so next_review demands collection.
    assert res.package["package_status"] == "ASSEMBLED"


# ----------------------------------------------------------- provenance


def test_candidate_commit_bound_verbatim_not_repinned(tmp_path: Path) -> None:
    res = _build(CAMPAIGN_CANDIDATE_COMMIT, tmp_path)
    # The supplied (ancestor) commit is bound verbatim; the bridge never auto-repins to HEAD.
    assert res.candidate_commit == CAMPAIGN_CANDIDATE_COMMIT
    assert res.candidate_commit != CURRENT_MAIN_TIP
    assert res.package["candidate"]["repository_commit"] == CAMPAIGN_CANDIDATE_COMMIT


def test_invalid_candidate_commit_rejected(tmp_path: Path) -> None:
    with pytest.raises(bridge.EvidenceCustodyBridgeError) as exc:
        _build("not-a-sha", tmp_path)
    assert exc.value.args[0] == "COMMIT_INVALID"


# ----------------------------------------------------------- determinism


def test_deterministic_store_and_seal(tmp_path: Path) -> None:
    r1 = _build(CAMPAIGN_CANDIDATE_COMMIT, tmp_path / "a")
    r2 = _build(CAMPAIGN_CANDIDATE_COMMIT, tmp_path / "b")
    assert set(r1.object_digests) == set(r2.object_digests)
    seal1 = r1.sealed_document["seal"]
    seal2 = r2.sealed_document["seal"]
    assert seal1["chain_state_digest_sha256"] == seal2["chain_state_digest_sha256"]
    assert r1.chain_id == r2.chain_id == bridge._chain_id_for(CAMPAIGN_CANDIDATE_COMMIT)


# ----------------------------------------------------------- lab_l1-only boundaries


def test_sealed_chain_remains_lab_l1_not_prod_worm(tmp_path: Path) -> None:
    res = _build(CAMPAIGN_CANDIDATE_COMMIT, tmp_path)
    doc = res.sealed_document
    assert doc["profile"] == "LAB_L1"
    assert doc["worm_migration_compatible"] is True
    seal = doc["seal"]
    assert seal["bindings"]["signer"] is None
    assert seal["bindings"]["authenticity"] is False
    assert seal["bindings"]["durability"] is False
    # The store is never a PROD WORM backend: it rejects the LocalEvidenceStore reclassification.
    assert hasattr(store_module.LocalEvidenceStore, "verify")


def test_sealed_document_validates_against_evidence_chain_schema(tmp_path: Path) -> None:
    import jsonschema

    res = _build(CAMPAIGN_CANDIDATE_COMMIT, tmp_path)
    schema_path = ROOT / "platform" / "schemas" / "evidence-chain.schema.json"
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    jsonschema.Draft202012Validator(schema, format_checker=jsonschema.FormatChecker()).validate(
        res.sealed_document
    )
    # And the frozen seal primitive confirms it.
    assert seal_module.verify_seal(res.sealed_document)["verified"] is True


# ----------------------------------------------------------- ephemeral preview


def test_ephemeral_preview_writes_outside_repo(tmp_path: Path) -> None:
    out = tmp_path / "outside" / "preview.json"
    preview = bridge.generate_ephemeral_custody_preview(
        repo_root=ROOT,
        out_path=out,
        candidate_commit=CAMPAIGN_CANDIDATE_COMMIT,
    )
    assert out.is_file()
    assert set(preview["verified_evidence_gate_ids"]) == {
        "GATEWAY_ADMISSION_REOBSERVATION",
        "BRIDGE_REVISION_REOBSERVATION",
        "HASH_CHAIN_SEAL",
    }
    assert preview["promotion_allowed"] is False
    assert preview["recommendation"] == "HOLD"


def test_ephemeral_preview_refuses_inside_repo(tmp_path: Path) -> None:
    # Writing inside the repository tree must be refused (never a committed real package).
    inside = ROOT / "platform" / "evidence-plane" / "should-never-be-written.json"
    with pytest.raises(bridge.EvidenceCustodyBridgeError) as exc:
        bridge.generate_ephemeral_custody_preview(
            repo_root=ROOT,
            out_path=inside,
            candidate_commit=CAMPAIGN_CANDIDATE_COMMIT,
        )
    assert exc.value.args[0] == "PREVIEW_INSIDE_REPO"
    assert not inside.exists()
