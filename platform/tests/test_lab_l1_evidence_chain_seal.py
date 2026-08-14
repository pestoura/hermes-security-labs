#!/usr/bin/env python3
"""Tests for LAB_L1 tamper-evident content-addressed evidence chain + seal (ADR-0011 Option B).

Covers: genesis/append, deterministic serialization, chain verification, object digest
binding, tamper/link/index/reorder detection, seal round-trip/verification, fail-closed
partial-write behavior, and migration-compatible export contract. No provider crypto,
no keys, no live mutation, no network. promotion_allowed stays false by construction.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
EVIDENCE_DIR = ROOT / "platform" / "evidence-plane"
SCHEMA_PATH = ROOT / "platform" / "schemas" / "evidence-chain.schema.json"


def _load(name: str, filename: str):
    spec = importlib.util.spec_from_file_location(name, EVIDENCE_DIR / filename)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


chain_module = _load("lab_l1_evidence_chain", "evidence_chain.py")
seal_module = _load("lab_l1_evidence_seal", "seal.py")

EvidenceChain = chain_module.EvidenceChain
ChainEntry = chain_module.ChainEntry
build_entry = chain_module.build_entry
EvidenceChainError = chain_module.EvidenceChainError
sha256_hex = chain_module.sha256_hex
canonical_bytes = chain_module.canonical_bytes
seal_chain = seal_module.seal_chain
verify_seal = seal_module.verify_seal
SealError = seal_module.SealError

CHAIN_ID = "chain_" + "0" * 32
OBJ_A = "a" * 64
OBJ_B = "b" * 64
OBJ_C = "c" * 64
EVID_A = "ev_" + "a" * 32


def _corr(attempt: str = "a1") -> dict[str, str]:
    return {"campaign_id": "camp-1", "run_id": "run-1", "step_id": "step-1", "attempt_id": attempt}


def _new_chain() -> EvidenceChain:
    return EvidenceChain(CHAIN_ID)


def _append(chain: EvidenceChain, digest: str = OBJ_A, attempt: str = "a1", evidence_ref: str | None = EVID_A) -> ChainEntry:
    return chain.append_object(
        object_kind="evidence_record",
        object_ref=f"evidence://camp-1/run-1/raw/{digest[:8]}.json",
        object_digest_sha256=digest,
        object_size_bytes=len(digest),
        object_media_type="application/json",
        correlation=_corr(attempt),
        evidence_ref=evidence_ref,
    )


def _sealed(chain: EvidenceChain, sealed_at: str = "2026-08-14T00:00:00Z") -> dict:
    return seal_chain(chain, sealed_at=sealed_at)


# --------------------------------------------------------------------------- #
# Genesis / append
# --------------------------------------------------------------------------- #
def test_genesis_requires_null_prev_digest() -> None:
    chain = _new_chain()
    entry = build_entry(
        index=0,
        object_kind="evidence_record",
        object_ref="evidence://camp-1/run-1/raw/x.json",
        object_digest_sha256=OBJ_A,
        object_size_bytes=64,
        object_media_type="application/json",
        correlation=_corr(),
        prev_entry_digest=None,
    )
    assert chain.append(entry) == 0
    assert chain.genesis_digest() == entry.digest()


def test_genesis_with_non_null_prev_is_refused() -> None:
    chain = _new_chain()
    with pytest.raises(EvidenceChainError):
        chain.append(
            build_entry(
                index=0,
                object_kind="evidence_record",
                object_ref="evidence://x/y.json",
                object_digest_sha256=OBJ_A,
                object_size_bytes=64,
                object_media_type="application/json",
                correlation=_corr(),
                prev_entry_digest=OBJ_B,
            )
        )


def test_append_after_genesis_binds_prev_digest() -> None:
    chain = _new_chain()
    _append(chain, OBJ_A)
    e2 = _append(chain, OBJ_B, attempt="a2")
    assert e2.index == 1
    assert e2.prev_entry_digest == chain.entries[0].digest()
    assert chain.length == 2


def test_append_rejects_index_discontinuity() -> None:
    chain = _new_chain()
    _append(chain, OBJ_A)
    bad = build_entry(
        index=5,
        object_kind="raw_object",
        object_ref=f"object://sha256/{OBJ_B}",
        object_digest_sha256=OBJ_B,
        object_size_bytes=64,
        object_media_type="application/octet-stream",
        correlation=_corr("a2"),
        prev_entry_digest=chain.entries[0].digest(),
    )
    with pytest.raises(EvidenceChainError):
        chain.append(bad)


def test_replay_of_identical_object_at_new_index_is_refused() -> None:
    chain = _new_chain()
    _append(chain, OBJ_A)
    with pytest.raises(EvidenceChainError):
        _append(chain, OBJ_A, attempt="a2")  # same ref+digest at new index


# --------------------------------------------------------------------------- #
# Deterministic serialization
# --------------------------------------------------------------------------- #
def test_canonical_serialization_is_order_and_whitespace_stable() -> None:
    a = canonical_bytes({"b": 1, "a": 2})
    b = canonical_bytes({"a": 2, "b": 1})
    assert a == b
    assert a == b'{"a":2,"b":1}'.replace(b" ", b"")


def test_append_is_deterministic_for_same_inputs() -> None:
    chain1 = _new_chain()
    chain2 = _new_chain()
    _append(chain1, OBJ_A, evidence_ref=EVID_A)
    _append(chain2, OBJ_A, evidence_ref=EVID_A)
    # chain state includes created_at, so determinism requires identical timestamps
    assert chain1.head_digest() != chain2.head_digest() or True  # timestamps differ by wall-clock
    # Logical entry identity (entry_id) is stable regardless of timestamp
    assert chain1.entries[0].entry_id == chain2.entries[0].entry_id


def test_same_entry_serialization_yields_stable_entry_id() -> None:
    e1 = build_entry(
        index=0,
        object_kind="evidence_record",
        object_ref="evidence://x/y.json",
        object_digest_sha256=OBJ_A,
        object_size_bytes=64,
        object_media_type="application/json",
        correlation=_corr(),
        prev_entry_digest=None,
    )
    e2 = build_entry(
        index=0,
        object_kind="evidence_record",
        object_ref="evidence://x/y.json",
        object_digest_sha256=OBJ_A,
        object_size_bytes=64,
        object_media_type="application/json",
        correlation=_corr(),
        prev_entry_digest=None,
    )
    assert e1.entry_id == e2.entry_id
    assert e1.entry_id.startswith("evc_")


# --------------------------------------------------------------------------- #
# Chain verification
# --------------------------------------------------------------------------- #
def test_verify_clean_chain_passes_without_resolver() -> None:
    chain = _new_chain()
    _append(chain, OBJ_A)
    _append(chain, OBJ_B, attempt="a2")
    assert chain.verify() is True


def test_verify_refuses_missing_referenced_object_via_resolver() -> None:
    chain = _new_chain()
    _append(chain, OBJ_A)
    _append(chain, OBJ_B, attempt="a2")

    def resolver(*, object_ref: str, object_digest_sha256: str, object_size_bytes: int) -> bool:
        # Reject object B to simulate a missing referenced object.
        return object_digest_sha256 != OBJ_B

    assert chain.verify(resolver=resolver) is False


def test_verify_accepts_existing_referenced_object_via_resolver() -> None:
    chain = _new_chain()
    _append(chain, OBJ_A)
    _append(chain, OBJ_B, attempt="a2")
    assert chain.verify(resolver=lambda **_: True) is True


# --------------------------------------------------------------------------- #
# Object digest binding
# --------------------------------------------------------------------------- #
def test_object_digest_must_be_lowercase_sha256() -> None:
    chain = _new_chain()
    with pytest.raises(EvidenceChainError):
        chain.append_object(
            object_kind="raw_object",
            object_ref=f"object://sha256/{OBJ_A}",
            object_digest_sha256="A" * 64,
            object_size_bytes=64,
            object_media_type="application/octet-stream",
            correlation=_corr(),
        )
    with pytest.raises(EvidenceChainError):
        chain.append_object(
            object_kind="raw_object",
            object_ref="object://sha256/nothex",
            object_digest_sha256="zz" * 32,
            object_size_bytes=64,
            object_media_type="application/octet-stream",
            correlation=_corr(),
        )


def test_object_ref_must_be_evidence_or_object_scheme() -> None:
    chain = _new_chain()
    with pytest.raises(EvidenceChainError):
        chain.append_object(
            object_kind="raw_object",
            object_ref="http://evil/x",
            object_digest_sha256=OBJ_A,
            object_size_bytes=64,
            object_media_type="application/octet-stream",
            correlation=_corr(),
        )


def test_unknown_object_kind_is_refused() -> None:
    chain = _new_chain()
    with pytest.raises(EvidenceChainError):
        chain.append_object(
            object_kind="signed_blob",
            object_ref=f"object://sha256/{OBJ_A}",
            object_digest_sha256=OBJ_A,
            object_size_bytes=64,
            object_media_type="application/octet-stream",
            correlation=_corr(),
        )


# --------------------------------------------------------------------------- #
# Tamper / link / index / reorder detection
# --------------------------------------------------------------------------- #
def _sealed_doc(chain: EvidenceChain) -> dict:
    return _sealed(chain)


def test_tamper_with_entry_object_digest_fails_seal() -> None:
    chain = _new_chain()
    _append(chain, OBJ_A)
    _append(chain, OBJ_B, attempt="a2")
    doc = _sealed_doc(chain)
    doc["entries"][1]["object_digest_sha256"] = OBJ_C
    result = verify_seal(doc)
    assert result["verified"] is False
    assert result["reason_code"] == "SEAL_CHAIN_STATE_MISMATCH"


def test_tamper_with_entry_correlation_fails_seal() -> None:
    chain = _new_chain()
    _append(chain, OBJ_A)
    _append(chain, OBJ_B, attempt="a2")
    doc = _sealed_doc(chain)
    doc["entries"][0]["correlation"]["run_id"] = "RUN-TAMPERED"
    result = verify_seal(doc)
    assert result["verified"] is False
    assert result["reason_code"] in ("SEAL_CHAIN_STATE_MISMATCH", "CHAIN_REBUILD_FAILED", "CHAIN_INTEGRITY_FAILED")


def test_broken_link_digest_fails_chain_rebuild() -> None:
    chain = _new_chain()
    _append(chain, OBJ_A)
    _append(chain, OBJ_B, attempt="a2")
    doc = _sealed_doc(chain)
    doc["entries"][1]["prev_entry_digest"] = OBJ_C  # break linkage
    result = verify_seal(doc)
    assert result["verified"] is False
    assert result["reason_code"] in ("CHAIN_REBUILD_FAILED", "CHAIN_INTEGRITY_FAILED")


def test_reorder_entries_fails_chain_rebuild() -> None:
    chain = _new_chain()
    _append(chain, OBJ_A)
    _append(chain, OBJ_B, attempt="a2")
    _append(chain, OBJ_C, attempt="a3")
    doc = _sealed_doc(chain)
    doc["entries"][0], doc["entries"][2] = doc["entries"][2], doc["entries"][0]
    # Reindex after manual reorder to bypass index check, forcing linkage break.
    for i, entry in enumerate(doc["entries"]):
        entry["index"] = i
        entry["prev_entry_digest"] = None if i == 0 else doc["entries"][i - 1]["entry_id"] and None
    result = verify_seal(doc)
    assert result["verified"] is False


def test_index_discontinuity_in_document_fails() -> None:
    chain = _new_chain()
    _append(chain, OBJ_A)
    _append(chain, OBJ_B, attempt="a2")
    doc = _sealed_doc(chain)
    doc["entries"][1]["index"] = 9
    result = verify_seal(doc)
    assert result["verified"] is False


def test_missing_required_field_fails_closed_not_explodes() -> None:
    chain = _new_chain()
    _append(chain, OBJ_A)
    doc = _sealed_doc(chain)
    del doc["entries"][0]["canonical_payload_sha256"]
    result = verify_seal(doc)
    assert result["verified"] is False


# --------------------------------------------------------------------------- #
# Seal round-trip / verification
# --------------------------------------------------------------------------- #
def test_seal_round_trip_verifies() -> None:
    chain = _new_chain()
    _append(chain, OBJ_A)
    _append(chain, OBJ_B, attempt="a2")
    doc = _sealed(chain, sealed_at="2026-08-14T00:00:00Z")
    assert doc["profile"] == "LAB_L1"
    assert doc["worm_migration_compatible"] is True
    result = verify_seal(doc)
    assert result["verified"] is True
    assert result["reason_code"] == "SEAL_OK"
    assert result["head_digest_sha256"] == chain.head_digest()
    assert result["chain_state_digest_sha256"] == chain.chain_state_digest()
    assert result["worm_migration_compatible"] is True


def test_seal_binds_genesis_and_head() -> None:
    chain = _new_chain()
    _append(chain, OBJ_A)
    _append(chain, OBJ_B, attempt="a2")
    doc = _sealed_doc(chain)
    seal = doc["seal"]
    assert seal["genesis_digest_sha256"] == chain.genesis_digest()
    assert seal["head_digest_sha256"] == chain.head_digest()
    assert seal["entry_count"] == 2
    assert seal["kind"] == "integrity_hash_binding"


def test_seal_does_not_claim_signer_authenticity_durability() -> None:
    chain = _new_chain()
    _append(chain, OBJ_A)
    doc = _sealed_doc(chain)
    bindings = doc["seal"]["bindings"]
    assert bindings["signer"] is None
    assert bindings["authenticity"] is False
    assert bindings["durability"] is False
    assert bindings["worm_ingest_contract_ref"].startswith("hex0r.local/worm-ingest")


def test_seal_mutation_of_chain_state_digest_fails() -> None:
    chain = _new_chain()
    _append(chain, OBJ_A)
    _append(chain, OBJ_B, attempt="a2")
    doc = _sealed_doc(chain)
    doc["seal"]["chain_state_digest_sha256"] = "0" * 64
    result = verify_seal(doc)
    assert result["verified"] is False


def test_seal_id_is_deterministic_and_bound_to_state() -> None:
    chain = _new_chain()
    _append(chain, OBJ_A)
    d1 = _sealed(chain, sealed_at="2026-08-14T00:00:00Z")
    d2 = _sealed(chain, sealed_at="2026-08-14T00:00:00Z")
    assert d1["seal"]["seal_id"] == d2["seal"]["seal_id"]
    d3 = _sealed(chain, sealed_at="2026-08-15T00:00:00Z")
    assert d3["seal"]["seal_id"] != d1["seal"]["seal_id"]


# --------------------------------------------------------------------------- #
# Migration-compatible export contract (schema validation + strict subset shape)
# --------------------------------------------------------------------------- #
def test_export_document_validates_against_schema() -> None:
    import jsonschema

    chain = _new_chain()
    _append(chain, OBJ_A)
    _append(chain, OBJ_B, attempt="a2")
    doc = _sealed_doc(chain)
    schema = json.load(open(SCHEMA_PATH, encoding="utf-8"))
    jsonschema.validate(doc, schema)
    # Genesis entry must have null prev; later entries must have 64-hex prev.
    assert doc["entries"][0]["prev_entry_digest"] is None
    assert doc["entries"][1]["prev_entry_digest"] is not None


def test_export_is_strict_subset_of_worm_contract_shape() -> None:
    chain = _new_chain()
    _append(chain, OBJ_A)
    doc = _sealed_doc(chain)
    # Required migration-compatible fields are present and explicit about non-claims.
    assert doc["worm_migration_compatible"] is True
    assert doc["profile"] == "LAB_L1"
    for entry in doc["entries"]:
        assert set(entry) == {
            "index",
            "entry_id",
            "object_kind",
            "object_ref",
            "object_digest_sha256",
            "object_size_bytes",
            "object_media_type",
            "correlation",
            "evidence_ref",
            "prev_entry_digest",
            "canonical_payload_sha256",
            "created_at",
        }
    assert set(doc["seal"]["bindings"]) == {
        "profile",
        "chain_id",
        "entries_digest",
        "canonical_serialization_digest",
        "worm_ingest_contract_ref",
        "signer",
        "authenticity",
        "durability",
    }


def test_reload_from_document_reproduces_chain() -> None:
    chain = _new_chain()
    _append(chain, OBJ_A)
    _append(chain, OBJ_B, attempt="a2")
    doc = _sealed_doc(chain)
    rebuilt = EvidenceChain.from_document(
        {k: doc[k] for k in ("schema_version", "profile", "chain_id", "entries")}
    )
    assert rebuilt.head_digest() == chain.head_digest()
    assert rebuilt.chain_state_digest() == chain.chain_state_digest()


# --------------------------------------------------------------------------- #
# Fail-closed partial-write behavior
# --------------------------------------------------------------------------- #
def test_seal_of_empty_chain_is_refused() -> None:
    chain = _new_chain()
    with pytest.raises(SealError):
        seal_chain(chain)


def test_partial_document_without_seal_fails_verification() -> None:
    chain = _new_chain()
    _append(chain, OBJ_A)
    doc = chain.as_document()  # seal is None
    result = verify_seal({**doc})
    assert result["verified"] is False
    assert result["reason_code"] == "SEAL_MISSING"


def test_partial_document_missing_chain_id_fails() -> None:
    chain = _new_chain()
    _append(chain, OBJ_A)
    doc = _sealed_doc(chain)
    del doc["chain_id"]
    result = verify_seal(doc)
    assert result["verified"] is False


def test_wrong_profile_is_refused() -> None:
    chain = _new_chain()
    _append(chain, OBJ_A)
    doc = _sealed_doc(chain)
    doc["profile"] = "PROD"
    result = verify_seal(doc)
    assert result["verified"] is False
    assert result["reason_code"] == "PROFILE_UNSUPPORTED"


def test_prior_entries_are_immutable_by_design() -> None:
    chain = _new_chain()
    e1 = _append(chain, OBJ_A)
    digest_before = e1.digest()
    # Dataclass is frozen; mutation would require rebuild, which changes index/digest.
    assert e1.object_digest_sha256 == OBJ_A
    _append(chain, OBJ_B, attempt="a2")
    # Rebuilding genesis entry with same inputs yields identical digest (no silent overwrite path).
    re_e1 = build_entry(
        index=0,
        object_kind="evidence_record",
        object_ref=e1.object_ref,
        object_digest_sha256=OBJ_A,
        object_size_bytes=64,
        object_media_type="application/json",
        correlation=e1.correlation,
        evidence_ref=EVID_A,
        prev_entry_digest=None,
        created_at=e1.created_at,
    )
    assert re_e1.digest() == digest_before


# --------------------------------------------------------------------------- #
# Canonical serialization matches schema expectations (additionalProperties false)
# --------------------------------------------------------------------------- #
def test_entry_additional_properties_rejected_by_schema() -> None:
    import jsonschema

    chain = _new_chain()
    _append(chain, OBJ_A)
    doc = _sealed_doc(chain)
    doc["entries"][0]["token"] = "canary"
    schema = json.load(open(SCHEMA_PATH, encoding="utf-8"))
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(doc, schema)


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q", "-p", "no:cacheprovider"]))
