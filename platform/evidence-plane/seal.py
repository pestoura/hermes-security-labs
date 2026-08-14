#!/usr/bin/env python3
"""LAB_L1 evidence-chain seal / envelope (ADR-0011 Option B migration-compatible subset).

This module produces a cryptographic *seal* that binds the chain state (genesis digest,
head digest, ordered entries digest and canonical-serialization digest) into a single
content-addressed envelope WITHOUT a private signing key. The seal is explicitly a
STRICT SUBSET / migration-compatible INPUT to the future PROD WORM ingestion contract.

Integrity vs authenticity vs durability — keep these separate:

- INTEGRITY / TAMPER-EVIDENCE: any change to an entry, its order, the linkage, the
  referenced object digest, or the chain id breaks the seal's digest binding. This is
  locally verifiable and is what this module guarantees.
- AUTHENTICITY: the seal does NOT prove *who* produced it. `bindings.signer` is `null`
  and `bindings.authenticity` is `false` by construction. A future WORM ingestion step
  may attach a signer/attestation; this module does not.
- DURABILITY: the seal does NOT provide WORM immutability against an actor with write
  access to the full store. `bindings.durability` is `false` by construction. LAB_L1
  tamper-evidence is detectability, not regulated retention.

No provider-specific crypto, key material, trust store or network interaction exists in
this module. `NO_RUNTIME_CHANGE`.
"""

from __future__ import annotations

import importlib.util
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Mapping

HERE = Path(__file__).resolve().parent


def _load_sibling(name: str, filename: str):
    """Resolve a same-directory module without requiring it on sys.path (repo pattern)."""
    module_name = f"_lab_l1_seal_{name}"
    existing = sys.modules.get(module_name)
    if existing is not None:
        return existing
    spec = importlib.util.spec_from_file_location(module_name, HERE / filename)
    if not spec or not spec.loader:
        raise RuntimeError(f"cannot load evidence-plane sibling: {filename}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


_chain = _load_sibling("chain", "evidence_chain.py")
PROFILE = _chain.PROFILE
SCHEMA_VERSION = _chain.SCHEMA_VERSION
SHA256 = _chain.SHA256
SEAL_ID = _chain.SEAL_ID
canonical_bytes = _chain.canonical_bytes
sha256_hex = _chain.sha256_hex
EvidenceChain = _chain.EvidenceChain
EvidenceChainError = _chain.EvidenceChainError

WORM_INGEST_CONTRACT_REF = "hex0r.local/worm-ingest/v1#integrity-hash-binding"

SEAL_NOTE = (
    "LAB_L1 hash seal: integrity/tamper-evidence only. Not a signer, not a WORM claim. "
    "Integrity != external authenticity != durability."
)


class SealError(ValueError):
    """Fail-closed seal contract violation."""


def _now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def _is_sha256(value: Any) -> bool:
    return isinstance(value, str) and bool(SHA256.fullmatch(value))


def build_seal(chain: EvidenceChain, *, sealed_at: str | None = None) -> dict[str, Any]:
    """Bind current chain state into a verifiable hash seal. Deterministic given (chain, sealed_at)."""
    if not chain.entries:
        raise SealError("CHAIN_EMPTY: cannot seal an empty chain")
    entries_digest = chain.chain_state_digest()
    canonical_serialization_digest = sha256_hex(canonical_bytes({"entries": [e.as_dict() for e in chain.entries]}))
    genesis = chain.genesis_digest()
    head = chain.head_digest()
    # The seal's top-level chain_state_digest_sha256 is bound directly to the chain's
    # canonical state digest (== entries_digest) so verification can compare it without
    # an extra non-canonical wrapper. entries_digest and canonical_serialization_digest
    # remain as the two explicit WORM-migration bindings.
    chain_state_digest = entries_digest
    timestamp = sealed_at or _now()
    seal_id = f"seal_{sha256_hex(canonical_bytes({'chain_id': chain.chain_id, 'chain_state_digest_sha256': chain_state_digest, 'sealed_at': timestamp}))[:48]}"
    return {
        "seal_id": seal_id,
        "sealed_at": timestamp,
        "chain_state_digest_sha256": chain_state_digest,
        "entry_count": len(chain.entries),
        "genesis_digest_sha256": genesis,
        "head_digest_sha256": head,
        "kind": "integrity_hash_binding",
        "bindings": {
            "profile": PROFILE,
            "chain_id": chain.chain_id,
            "entries_digest": entries_digest,
            "canonical_serialization_digest": canonical_serialization_digest,
            "worm_ingest_contract_ref": WORM_INGEST_CONTRACT_REF,
            "signer": None,
            "authenticity": False,
            "durability": False,
        },
        "note": SEAL_NOTE,
    }


def seal_chain(chain: EvidenceChain, *, sealed_at: str | None = None) -> dict[str, Any]:
    """Return the complete sealed chain document (chain + seal), migration-compatible with WORM ingest."""
    sealed = build_seal(chain, sealed_at=sealed_at)
    return {
        "schema_version": SCHEMA_VERSION,
        "profile": PROFILE,
        "chain_id": chain.chain_id,
        "worm_migration_compatible": True,
        "entries": [e.as_dict() for e in chain.entries],
        "seal": sealed,
    }


def verify_seal(document: Mapping[str, Any], *, resolver: Any | None = None) -> dict[str, Any]:
    """Fail-closed verification of a sealed chain document.

    Returns a result dict with `verified` (bool) and `reason_code`/`detail`. Never raises
    for tamper conditions; only raises SealError/EvidenceChainError on malformed inputs.
    """
    if document.get("schema_version") != SCHEMA_VERSION:
        return {"verified": False, "reason_code": "SCHEMA_VERSION_UNSUPPORTED", "detail": "expected 1.0"}
    if document.get("profile") != PROFILE:
        return {"verified": False, "reason_code": "PROFILE_UNSUPPORTED", "detail": "only LAB_L1 accepted"}
    if document.get("worm_migration_compatible") is not True:
        return {"verified": False, "reason_code": "WORM_MIGRATION_FLAG_MISSING", "detail": "must remain migration-compatible"}
    seal = document.get("seal")
    if not isinstance(seal, Mapping):
        return {"verified": False, "reason_code": "SEAL_MISSING", "detail": "document has no seal"}

    # Rebuild the chain from entries and re-verify linkage/index/object binding.
    try:
        chain = EvidenceChain.from_document(
            {
                "schema_version": SCHEMA_VERSION,
                "profile": PROFILE,
                "chain_id": document["chain_id"],
                "entries": document["entries"],
                "seal": None,
            }
        )
    except EvidenceChainError as exc:
        return {"verified": False, "reason_code": "CHAIN_REBUILD_FAILED", "detail": str(exc)}
    except Exception as exc:  # noqa: BLE001
        return {"verified": False, "reason_code": "CHAIN_REBUILD_FAILED", "detail": f"{type(exc).__name__}: {exc}"}

    if not chain.verify(resolver=resolver):
        return {"verified": False, "reason_code": "CHAIN_INTEGRITY_FAILED", "detail": "linkage/index/object binding broken or referenced object missing"}

    # Recompute the seal digests and compare against the stored seal.
    recomputed = build_seal(chain, sealed_at=seal.get("sealed_at"))
    if recomputed["chain_state_digest_sha256"] != seal.get("chain_state_digest_sha256"):
        return {"verified": False, "reason_code": "SEAL_CHAIN_STATE_MISMATCH", "detail": "stored chain_state_digest does not match recomputed chain state"}
    if recomputed["entry_count"] != seal.get("entry_count"):
        return {"verified": False, "reason_code": "SEAL_ENTRY_COUNT_MISMATCH", "detail": "seal entry_count does not match chain"}
    if recomputed["genesis_digest_sha256"] != seal.get("genesis_digest_sha256"):
        return {"verified": False, "reason_code": "SEAL_GENESIS_MISMATCH", "detail": "stored genesis digest does not match chain genesis"}
    if recomputed["head_digest_sha256"] != seal.get("head_digest_sha256"):
        return {"verified": False, "reason_code": "SEAL_HEAD_MISMATCH", "detail": "stored head digest does not match chain head"}
    if recomputed["seal_id"] != seal.get("seal_id"):
        return {"verified": False, "reason_code": "SEAL_ID_MISMATCH", "detail": "seal_id does not match recomputed seal"}

    bindings = seal.get("bindings")
    if not isinstance(bindings, Mapping):
        return {"verified": False, "reason_code": "SEAL_BINDINGS_MISSING", "detail": "seal bindings missing"}
    if bindings.get("signer") is not None or bindings.get("authenticity") is not False or bindings.get("durability") is not False:
        return {"verified": False, "reason_code": "SEAL_CLAIM_VIOLATION", "detail": "LAB_L1 seal must not claim signer/authenticity/durability"}

    return {
        "verified": True,
        "reason_code": "SEAL_OK",
        "detail": "integrity/tamper-evidence verified; signer/authenticity/durability NOT asserted",
        "chain_id": chain.chain_id,
        "entry_count": len(chain.entries),
        "head_digest_sha256": recomputed["head_digest_sha256"],
        "chain_state_digest_sha256": recomputed["chain_state_digest_sha256"],
        "worm_migration_compatible": True,
    }
