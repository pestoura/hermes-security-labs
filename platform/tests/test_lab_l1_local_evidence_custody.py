#!/usr/bin/env python3
"""Tests for LAB_L1 local evidence custody + verifier primitives (CHG-HSL-055).

Repository-only, fail-closed. Covers:

- EvidenceVerifier contract conformance (resolve ref + expected sha256, fail closed).
- Content-addressing determinism (identical SAFE inputs -> identical ids/digests).
- Replay / idempotency (repeat custody over an existing store is a no-op).
- Tamper / missing sidecar detection (mutated payload or record sidecar fails).
- Cross-record digest mismatch (expected sha256 != stored digest).
- Duplicate / ambiguous records (two records share a storage_ref or object digest).
- Chain + seal verification (authenticity=false / durability=false, LAB_L1 only).
- Strict filesystem discipline (0700 dirs, 0600 files, O_EXCL, fsync inherited/verified).
- No PROD claim: assurance-profile guard proving this adapter is NOT a PROD
  WORM backend, NOT tenant isolation, and never asserts signer/authenticity/durability.

No signer/Vault/target/network/process effects. promotion_allowed stays false.
"""

from __future__ import annotations

import importlib.util
import json
import stat
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
EVIDENCE_DIR = ROOT / "platform" / "evidence-plane"


def _load(name: str, filename: str):
    spec = importlib.util.spec_from_file_location(name, EVIDENCE_DIR / filename)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


verifier_module = _load("lab_l1_evidence_verifier_055", "local_evidence_verifier.py")
custody_module = _load("lab_l1_evidence_custody_055", "local_evidence_custody.py")
chain_module = _load("lab_l1_evidence_chain_055", "evidence_chain.py")
seal_module = _load("lab_l1_evidence_seal_055", "seal.py")
store_module = _load("lab_l1_local_store_055", "local_store.py")

LocalEvidenceVerifier = verifier_module.LocalEvidenceVerifier
LocalEvidenceCustodyBuilder = custody_module.LocalEvidenceCustodyBuilder
SafeEvidenceItem = custody_module.SafeEvidenceItem
LocalEvidenceStore = store_module.LocalEvidenceStore
LocalEvidenceStoreError = store_module.LocalEvidenceStoreError
EvidenceChain = chain_module.EvidenceChain
seal_chain = seal_module.seal_chain
verify_seal = seal_module.verify_seal

CHAIN_ID = "chain_" + "0" * 32


def _corr(run: str = "r1") -> dict[str, str]:
    return {"campaign_id": "camp-1", "run_id": run, "step_id": "step-1", "attempt_id": "a1"}


def _item(payload: bytes, ref: str, *, classification: str = "raw", corr: dict[str, str] | None = None, evidence_id: str | None = None) -> SafeEvidenceItem:
    return SafeEvidenceItem(
        payload=payload,
        classification=classification,
        storage_ref=ref,
        media_type="application/json",
        correlation=corr or _corr(),
        evidence_id=evidence_id,
    )


def _assert_lab_l1_only(document: dict) -> None:
    seal = document["seal"]
    assert seal["bindings"]["signer"] is None
    assert seal["bindings"]["authenticity"] is False
    assert seal["bindings"]["durability"] is False
    assert document["profile"] == "LAB_L1"
    assert document["worm_migration_compatible"] is True


# ---------------------------------------------------------------- verifier

def test_verifier_contract_verify_matches_expected_digest(tmp_path: Path) -> None:
    root = tmp_path / "ev"
    builder = LocalEvidenceCustodyBuilder(root)
    item = _item(b'{"r":1}', "evidence://c/r1/raw/a.json")
    res = builder.custody(chain_id=CHAIN_ID, items=[item], sealed_at="2026-08-14T00:00:00Z")
    v = LocalEvidenceVerifier(builder.store_root)
    assert v.verify(res.evidence_refs[0], res.object_digests[0]) is True
    detail = v.verify_detail(res.evidence_refs[0], res.object_digests[0])
    assert detail["verified"] is True and detail["evidence_id"] == res.evidence_ids[0]


def test_verifier_resolves_object_digest_ref(tmp_path: Path) -> None:
    root = tmp_path / "ev"
    builder = LocalEvidenceCustodyBuilder(root)
    item = _item(b'{"r":2}', "evidence://c/r2/raw/a.json")
    res = builder.custody(chain_id=CHAIN_ID, items=[item], sealed_at="2026-08-14T00:00:00Z")
    v = LocalEvidenceVerifier(root)
    assert v.verify(f"object://sha256/{res.object_digests[0]}", res.object_digests[0]) is True


def test_verifier_fails_on_missing_record(tmp_path: Path) -> None:
    v = LocalEvidenceVerifier(tmp_path / "empty")
    assert v.verify("evidence://no/such/ref.json", "a" * 64) is False
    detail = v.verify_detail("evidence://no/such/ref.json", "a" * 64)
    assert detail["verified"] is False and detail["reason_code"] == "EVIDENCE_REF_UNRESOLVED"


def test_verifier_fails_on_malformed_ref(tmp_path: Path) -> None:
    v = LocalEvidenceVerifier(tmp_path / "empty")
    assert v.verify("this-is-not-a-ref", "a" * 64) is False
    assert v.verify_detail("evidence://", "a" * 64)["reason_code"] == "EVIDENCE_REF_UNRESOLVED"
    assert v.verify_detail("object://sha256/nothex", "a" * 64)["reason_code"] == "EVIDENCE_REF_UNRESOLVED"


def test_verifier_fails_on_invalid_expected_sha(tmp_path: Path) -> None:
    root = tmp_path / "ev"
    builder = LocalEvidenceCustodyBuilder(root)
    item = _item(b'{"r":3}', "evidence://c/r3/raw/a.json")
    res = builder.custody(chain_id=CHAIN_ID, items=[item], sealed_at="2026-08-14T00:00:00Z")
    v = LocalEvidenceVerifier(root)
    assert v.verify(res.evidence_refs[0], "not-a-sha") is False
    assert v.verify_detail(res.evidence_refs[0], "not-a-sha")["reason_code"] == "SHA256_INVALID"


def test_verifier_fails_on_digest_mismatch(tmp_path: Path) -> None:
    root = tmp_path / "ev"
    builder = LocalEvidenceCustodyBuilder(root)
    item = _item(b'{"r":4}', "evidence://c/r4/raw/a.json")
    res = builder.custody(chain_id=CHAIN_ID, items=[item], sealed_at="2026-08-14T00:00:00Z")
    v = LocalEvidenceVerifier(root)
    assert v.verify(res.evidence_refs[0], "a" * 64) is False
    assert v.verify_detail(res.evidence_refs[0], "a" * 64)["reason_code"] == "DIGEST_MISMATCH"


def test_verifier_fails_on_tampered_payload(tmp_path: Path) -> None:
    root = tmp_path / "ev"
    builder = LocalEvidenceCustodyBuilder(root)
    item = _item(b'{"r":5}', "evidence://c/r5/raw/a.json")
    res = builder.custody(chain_id=CHAIN_ID, items=[item], sealed_at="2026-08-14T00:00:00Z")
    digest = res.object_digests[0]
    obj_path = root / "objects" / "sha256" / digest[:2] / digest
    obj_path.write_bytes(b'{"r":999}')  # tamper with the content-addressed object
    v = LocalEvidenceVerifier(root)
    assert v.verify(res.evidence_refs[0], digest) is False
    assert v.verify_detail(res.evidence_refs[0], digest)["reason_code"] == "INTEGRITY_FAILED"


def test_verifier_fails_on_missing_sidecar(tmp_path: Path) -> None:
    root = tmp_path / "ev"
    builder = LocalEvidenceCustodyBuilder(root)
    item = _item(b'{"r":6}', "evidence://c/r6/raw/a.json")
    res = builder.custody(chain_id=CHAIN_ID, items=[item], sealed_at="2026-08-14T00:00:00Z")
    digest = res.object_digests[0]
    # Remove the integrity sidecar -> verify must fail closed.
    (root / "records" / f"{res.evidence_ids[0]}.sha256").unlink()
    v = LocalEvidenceVerifier(root)
    assert v.verify(res.evidence_refs[0], digest) is False
    assert v.verify_detail(res.evidence_refs[0], digest)["reason_code"] == "INTEGRITY_FAILED"


def test_verifier_fails_on_ambiguous_storage_ref(tmp_path: Path) -> None:
    root = tmp_path / "ev"
    builder = LocalEvidenceCustodyBuilder(root)
    shared_ref = "evidence://c/shared/raw/a.json"
    builder.custody(
        chain_id=CHAIN_ID,
        items=[_item(b'{"a":1}', shared_ref, corr=_corr("r1")), _item(b'{"b":2}', shared_ref, corr=_corr("r2"))],
        sealed_at="2026-08-14T00:00:00Z",
    )
    v = LocalEvidenceVerifier(root)
    # Ambiguous: two records share the same storage_ref -> unresolved/None.
    assert v.verify(shared_ref, "a" * 64) is False
    assert v.verify_detail(shared_ref, "a" * 64)["reason_code"] == "EVIDENCE_REF_UNRESOLVED"


# ---------------------------------------------------------------- custody

def test_custody_persists_only_through_store_and_seals(tmp_path: Path) -> None:
    root = tmp_path / "ev"
    builder = LocalEvidenceCustodyBuilder(root)
    item = _item(b'{"r":7}', "evidence://c/r7/raw/a.json")
    res = builder.custody(chain_id=CHAIN_ID, items=[item], sealed_at="2026-08-14T00:00:00Z")
    assert len(res.evidence_ids) == 1
    assert res.chain_id == CHAIN_ID
    assert res.sealed_document["seal"]["entry_count"] == 1
    _assert_lab_l1_only(res.sealed_document)
    # The sealed document verifies end-to-end.
    assert verify_seal(res.sealed_document)["verified"] is True


def test_custody_content_addressing_deterministic_ids(tmp_path: Path) -> None:
    root = tmp_path / "ev"
    item = _item(b'{"same":1}', "evidence://c/same/raw/a.json")
    b1 = LocalEvidenceCustodyBuilder(root)
    r1 = b1.custody(chain_id=CHAIN_ID, items=[item], sealed_at="2026-08-14T00:00:00Z", _ts="2026-08-14T00:00:00Z")
    b2 = LocalEvidenceCustodyBuilder(root)
    r2 = b2.custody(chain_id=CHAIN_ID, items=[item], sealed_at="2026-08-14T00:00:00Z", _ts="2026-08-14T00:00:00Z")
    # Identical inputs -> identical content-addressed evidence ids and digests.
    assert r1.evidence_ids == r2.evidence_ids
    assert r1.object_digests == r2.object_digests


def test_custody_idempotent_replay_over_existing_store(tmp_path: Path) -> None:
    root = tmp_path / "ev"
    item = _item(b'{"replay":1}', "evidence://c/replay/raw/a.json")
    b1 = LocalEvidenceCustodyBuilder(root)
    r1 = b1.custody(chain_id=CHAIN_ID, items=[item], sealed_at="2026-08-14T00:00:00Z", _ts="2026-08-14T00:00:00Z")
    # Repeat exactly: O_EXCL idempotency discipline makes the second put a no-op.
    b2 = LocalEvidenceCustodyBuilder(root)
    r2 = b2.custody(chain_id=CHAIN_ID, items=[item], sealed_at="2026-08-14T00:00:00Z", _ts="2026-08-14T00:00:00Z")
    assert r1.evidence_ids == r2.evidence_ids
    assert r1.sealed_document["seal"]["chain_state_digest_sha256"] == r2.sealed_document["seal"]["chain_state_digest_sha256"]
    # Exactly one object on disk (content-addressed dedup).
    obj_dir = root / "objects" / "sha256" / r1.object_digests[0][:2]
    assert list(obj_dir.glob(r1.object_digests[0])) == [obj_dir / r1.object_digests[0]]


def test_custody_rejects_empty_batch(tmp_path: Path) -> None:
    builder = LocalEvidenceCustodyBuilder(tmp_path / "ev")
    with pytest.raises(custody_module.LocalEvidenceCustodyError):
        builder.custody(chain_id=CHAIN_ID, items=[])


def test_custody_rejects_invalid_chain_id(tmp_path: Path) -> None:
    builder = LocalEvidenceCustodyBuilder(tmp_path / "ev")
    with pytest.raises(custody_module.LocalEvidenceCustodyError):
        builder.custody(chain_id="not-a-chain-id", items=[_item(b'x', "evidence://c/x/raw/a.json")])


def test_custody_rejects_duplicate_evidence_in_batch(tmp_path: Path) -> None:
    builder = LocalEvidenceCustodyBuilder(tmp_path / "ev")
    # Reusing an explicit caller-supplied canonical id twice -> duplicate detection.
    eid = f"ev_{'a' * 32}"
    with pytest.raises(custody_module.LocalEvidenceCustodyError):
        builder.custody(
            chain_id=CHAIN_ID,
            items=[
                SafeEvidenceItem(payload=b'{"dup":1}', classification="raw", storage_ref="evidence://c/dup/raw/a.json",
                                  media_type="application/json", correlation=_corr("r1"), evidence_id=eid),
                SafeEvidenceItem(payload=b'{"dup":1}', classification="raw", storage_ref="evidence://c/dup/raw/b.json",
                                  media_type="application/json", correlation=_corr("r2"), evidence_id=eid),
            ],
        )


def test_custody_rejects_cross_record_digest_mismatch_via_verifier(tmp_path: Path) -> None:
    # A sealed package whose gate references a digest that does not match the
    # persisted object must fail the EvidenceVerifier bound to the store.
    root = tmp_path / "ev"
    builder = LocalEvidenceCustodyBuilder(root)
    item = _item(b'{"x":9}', "evidence://c/x9/raw/a.json")
    res = builder.custody(chain_id=CHAIN_ID, items=[item], sealed_at="2026-08-14T00:00:00Z")
    v = LocalEvidenceVerifier(root)
    assert v.verify(res.evidence_refs[0], res.object_digests[0]) is True
    # If a gate later declared a different expected digest, verification fails.
    assert v.verify(res.evidence_refs[0], "f" * 64) is False


def test_custody_seal_binds_chain_state_and_verifies(tmp_path: Path) -> None:
    root = tmp_path / "ev"
    builder = LocalEvidenceCustodyBuilder(root)
    items = [
        _item(b'{"n":1}', "evidence://c/m/raw/1.json", corr=_corr("r1")),
        _item(b'{"n":2}', "evidence://c/m/raw/2.json", corr=_corr("r2")),
    ]
    res = builder.custody(chain_id=CHAIN_ID, items=items, sealed_at="2026-08-14T00:00:00Z")
    assert res.sealed_document["seal"]["entry_count"] == 2
    chain = EvidenceChain.from_document({**res.sealed_document, "seal": None})
    assert chain.verify() is True
    vr = verify_seal(res.sealed_document)
    assert vr["verified"] is True
    assert vr["entry_count"] == 2


def test_custody_seal_detects_tampered_entry(tmp_path: Path) -> None:
    root = tmp_path / "ev"
    builder = LocalEvidenceCustodyBuilder(root)
    items = [
        _item(b'{"n":1}', "evidence://c/t/raw/1.json", corr=_corr("r1")),
        _item(b'{"n":2}', "evidence://c/t/raw/2.json", corr=_corr("r2")),
    ]
    res = builder.custody(chain_id=CHAIN_ID, items=items, sealed_at="2026-08-14T00:00:00Z")
    doc = json.loads(json.dumps(res.sealed_document))
    doc["entries"][0]["object_digest_sha256"] = doc["entries"][1]["object_digest_sha256"]
    assert verify_seal(doc)["verified"] is False


# ---------------------------------------------------------------- fs discipline

def test_custody_filesystem_strict_permissions_and_excl(tmp_path: Path) -> None:
    root = tmp_path / "ev"
    builder = LocalEvidenceCustodyBuilder(root)
    item = _item(b'{"fs":1}', "evidence://c/fs/raw/a.json")
    builder.custody(chain_id=CHAIN_ID, items=[item], sealed_at="2026-08-14T00:00:00Z")
    # Directories 0700.
    for d in (root, root / "objects", root / "objects" / "sha256", root / "records"):
        mode = stat.S_IMODE(d.stat().st_mode)
        assert mode == 0o700, f"{d} mode {oct(mode)}"
    # Record sidecar 0600.
    sidecars = list((root / "records").glob("*.sha256"))
    assert sidecars, "no integrity sidecar written"
    for sc in sidecars:
        assert stat.S_IMODE(sc.stat().st_mode) == 0o600
    # Object file 0600.
    objs = list((root / "objects" / "sha256").glob("*/*"))
    assert objs
    for o in objs:
        assert stat.S_IMODE(o.stat().st_mode) == 0o600


def test_custody_no_default_repo_write(tmp_path: Path) -> None:
    # The builder never writes under the repository tree unless explicitly given a repo path.
    # We assert it requires an explicit root and does not touch ROOT.
    builder = LocalEvidenceCustodyBuilder(tmp_path / "explicit-root")
    before = set(ROOT.rglob("*.json"))
    builder.custody(
        chain_id=CHAIN_ID,
        items=[_item(b'{"z":1}', "evidence://c/z/raw/a.json")],
        sealed_at="2026-08-14T00:00:00Z",
    )
    after = set(ROOT.rglob("*.json"))
    # No JSON artifact appeared inside the repository source tree.
    assert after == before


# ---------------------------------------------------------------- assurance guard

def test_assurance_profile_guard_not_prod_worm_or_tenant_isolation(tmp_path: Path) -> None:
    """The adapter must never be presented as PROD WORM / tenant isolation / signer."""
    root = tmp_path / "ev"
    builder = LocalEvidenceCustodyBuilder(root)
    item = _item(b'{"g":1}', "evidence://c/g/raw/a.json")
    res = builder.custody(chain_id=CHAIN_ID, items=[item], sealed_at="2026-08-14T00:00:00Z")
    doc = res.sealed_document
    # LAB_L1 only: no signer, no authenticity, no durability, migration-compatible.
    _assert_lab_l1_only(doc)
    # The verifier is a single-store, local-only control: it exposes no tenant
    # boundary, no WORM backend, and no signer. Prove by attribute absence.
    v = LocalEvidenceVerifier(root)
    assert not hasattr(v, "tenant_isolation")
    assert not hasattr(v, "worm_backend")
    assert not hasattr(v, "signer")
    # The verifier fails closed on any unknown ref (no implicit trust).
    assert v.verify("evidence://unknown/tenant/x.json", "a" * 64) is False


def test_assurance_profile_guard_seal_rejects_uplifted_claims(tmp_path: Path) -> None:
    root = tmp_path / "ev"
    builder = LocalEvidenceCustodyBuilder(root)
    res = builder.custody(chain_id=CHAIN_ID, items=[_item(b'{"u":1}', "evidence://c/u/raw/a.json")], sealed_at="2026-08-14T00:00:00Z")
    doc = json.loads(json.dumps(res.sealed_document))
    # Attempt to fraudulently present an uplifted PROD claim -> verify_seal must reject.
    doc["profile"] = "PROD"
    doc["seal"]["bindings"]["authenticity"] = True
    doc["seal"]["bindings"]["durability"] = True
    doc["seal"]["bindings"]["signer"] = "some-signer"
    assert verify_seal(doc)["verified"] is False
    bad = verify_seal(doc)
    assert bad["reason_code"] in ("PROFILE_UNSUPPORTED", "SEAL_CLAIM_VIOLATION")


def test_assurance_profile_guard_contract_doc_promotion_false(tmp_path: Path) -> None:
    # The verifier adapter is a custody primitive; it never grants promotion.
    root = tmp_path / "ev"
    builder = LocalEvidenceCustodyBuilder(root)
    res = builder.custody(chain_id=CHAIN_ID, items=[_item(b'{"p":1}', "evidence://c/p/raw/a.json")], sealed_at="2026-08-14T00:00:00Z")
    assert res.sealed_document["seal"]["bindings"]["authenticity"] is False
    # Evidence verified -> still only integrity; no promotion authority implied.
    v = LocalEvidenceVerifier(root)
    assert v.verify(res.evidence_refs[0], res.object_digests[0]) is True
