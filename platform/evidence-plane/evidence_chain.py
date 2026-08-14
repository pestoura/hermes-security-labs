#!/usr/bin/env python3
"""LAB_L1 tamper-evident content-addressed evidence chain (ADR-0011 Option B).

This module implements the narrow `LAB_L1` evidence-integrity control that ADR-0011
Option B keeps: a local, append-only, content-addressed chain that deterministically
binds each referenced evidence object to its predecessor and a monotonically ordered
chain index, plus a cryptographic *seal* that hashes/binds the chain state WITHOUT a
private signing key.

Design boundaries (read before extending):

- This is a STRICT SUBSET / migration-compatible input to the future PROD WORM
  ingestion contract. The seal carries `worm_migration_compatible: true` and explicit
  `bindings.signer: null`, `bindings.authenticity: false`, `bindings.durability: false`
  so no downstream consumer can mistake the hash seal for a signer or a WORM backend.
- The seal provides INTEGRITY / TAMPER-EVIDENCE only. It does NOT assert external
  authenticity (who sealed it) or durability (WORM immutability against an actor with
  write access to the whole store). Those remain PROD-only properties.
- Immutable content-addressed objects remain canonical; the chain is a derived,
  secondary integrity structure that references them by digest + ref.
- The chain FAILS CLOSED on: malformed linkage, index discontinuity, digest mismatch,
  tampering, replay/reordering, or a missing referenced object. Prior entries are never
  overwritten.
- No provider-specific crypto, key material, trust store or network interaction exists
  in this module. `NO_RUNTIME_CHANGE`.

Reuse conventions: it mirrors `evidence_plane.py` canonical JSON serialization
(`sort_keys`, compact separators, `ensure_ascii`) and the `LocalEvidenceStore` content-
addressed + exclusive-create discipline, but it does NOT instantiate a datastore.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Mapping, Sequence

SCHEMA_VERSION = "1.0"
PROFILE = "LAB_L1"
EVIDENCE_ID = re.compile(r"^ev_[a-f0-9]{32}$")
CHAIN_ID = re.compile(r"^chain_[a-f0-9]{32,64}$")
ENTRY_ID = re.compile(r"^evc_[a-f0-9]{32,64}$")
SEAL_ID = re.compile(r"^seal_[a-f0-9]{32,64}$")
SHA256 = re.compile(r"^[a-f0-9]{64}$")
SAFE_ID = re.compile(r"^[A-Za-z0-9._:-]{1,128}$")
OBJECT_REF = re.compile(r"^evidence://[A-Za-z0-9._/-]+$|^object://sha256/[a-f0-9]{64}$")

CORRELATION_KEYS = {"campaign_id", "run_id", "step_id", "attempt_id"}
OBJECT_KINDS = {"evidence_record", "exec_manifest", "raw_object", "migration_bundle"}


class EvidenceChainError(ValueError):
    """Fail-closed evidence-chain contract violation."""


def sha256_hex(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def canonical_bytes(value: Mapping[str, Any]) -> bytes:
    """Deterministic canonical serialization shared by chain and seal."""
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")


def _now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def _require(condition: bool, code: str, message: str) -> None:
    if not condition:
        raise EvidenceChainError(f"{code}: {message}")


def _is_sha256(value: Any) -> bool:
    return isinstance(value, str) and bool(SHA256.fullmatch(value))


def _valid_correlation(value: Any) -> dict[str, str]:
    _require(isinstance(value, Mapping), "CORRELATION_INVALID", "correlation must be a mapping")
    if set(value) != CORRELATION_KEYS:
        raise EvidenceChainError("CORRELATION_INVALID: exact correlation keys required")
    out = {key: value[key] for key in CORRELATION_KEYS}
    for key, item in out.items():
        _require(isinstance(item, str) and bool(SAFE_ID.fullmatch(item)), "CORRELATION_INVALID", f"invalid {key}")
    return out


@dataclass(frozen=True)
class ChainEntry:
    index: int
    entry_id: str
    object_kind: str
    object_ref: str
    object_digest_sha256: str
    object_size_bytes: int
    object_media_type: str
    correlation: dict[str, str]
    evidence_ref: str | None
    prev_entry_digest: str | None
    canonical_payload_sha256: str
    created_at: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "index": self.index,
            "entry_id": self.entry_id,
            "object_kind": self.object_kind,
            "object_ref": self.object_ref,
            "object_digest_sha256": self.object_digest_sha256,
            "object_size_bytes": self.object_size_bytes,
            "object_media_type": self.object_media_type,
            "correlation": dict(self.correlation),
            "evidence_ref": self.evidence_ref,
            "prev_entry_digest": self.prev_entry_digest,
            "canonical_payload_sha256": self.canonical_payload_sha256,
            "created_at": self.created_at,
        }

    def digest(self) -> str:
        return sha256_hex(canonical_bytes(self.as_dict()))


def entry_digest(entry: Mapping[str, Any]) -> str:
    """Content-addressed digest of a single canonical entry."""
    return sha256_hex(canonical_bytes(entry))


def build_entry(
    *,
    index: int,
    object_kind: str,
    object_ref: str,
    object_digest_sha256: str,
    object_size_bytes: int,
    object_media_type: str,
    correlation: Mapping[str, str],
    evidence_ref: str | None = None,
    prev_entry_digest: str | None = None,
    canonical_payload_sha256: str | None = None,
    created_at: str | None = None,
) -> ChainEntry:
    _require(isinstance(index, int) and index >= 0, "ENTRY_INDEX_INVALID", "index must be >= 0")
    _require(object_kind in OBJECT_KINDS, "OBJECT_KIND_INVALID", f"object_kind {object_kind} not allowed")
    _require(isinstance(object_ref, str) and bool(OBJECT_REF.fullmatch(object_ref)), "OBJECT_REF_INVALID", "object_ref must be evidence:// or object://sha256/")
    _require(_is_sha256(object_digest_sha256), "OBJECT_DIGEST_INVALID", "object_digest_sha256 must be lowercase sha256")
    _require(isinstance(object_size_bytes, int) and object_size_bytes >= 0, "OBJECT_SIZE_INVALID", "object_size_bytes cannot be negative")
    _require(isinstance(object_media_type, str) and bool(object_media_type), "OBJECT_MEDIA_INVALID", "object_media_type required")
    corr = _valid_correlation(correlation)
    if evidence_ref is not None:
        _require(isinstance(evidence_ref, str) and bool(EVIDENCE_ID.fullmatch(evidence_ref)), "EVIDENCE_REF_INVALID", "evidence_ref must be ev_<32 hex>")
    if index == 0:
        _require(prev_entry_digest is None, "GENESIS_LINK_INVALID", "genesis entry requires prev_entry_digest null")
    else:
        _require(_is_sha256(prev_entry_digest), "PREV_DIGEST_INVALID", "non-genesis entry requires 64-hex prev_entry_digest")
    if canonical_payload_sha256 is None:
        canonical_payload_sha256 = object_digest_sha256

    timestamp = created_at or _now()
    # entry_id binds to LOGICAL content only (never wall-clock), so identical
    # content yields an identical, deterministic entry id regardless of created_at.
    identity_seed = {
        "index": index,
        "object_kind": object_kind,
        "object_ref": object_ref,
        "object_digest_sha256": object_digest_sha256,
        "object_size_bytes": object_size_bytes,
        "object_media_type": object_media_type,
        "correlation": corr,
        "evidence_ref": evidence_ref,
        "prev_entry_digest": prev_entry_digest,
        "canonical_payload_sha256": canonical_payload_sha256,
    }
    entry_id = f"evc_{sha256_hex(canonical_bytes(identity_seed))[:48]}"
    return ChainEntry(
        index=index,
        entry_id=entry_id,
        object_kind=object_kind,
        object_ref=object_ref,
        object_digest_sha256=object_digest_sha256,
        object_size_bytes=object_size_bytes,
        object_media_type=object_media_type,
        correlation=corr,
        evidence_ref=evidence_ref,
        prev_entry_digest=prev_entry_digest,
        canonical_payload_sha256=canonical_payload_sha256,
        created_at=timestamp,
    )


def _entries_canonical_digest(entries: Sequence[Mapping[str, Any]]) -> str:
    """Digest over the ordered, canonical serialization of all entries (chain state)."""
    parts = [canonical_bytes(entry) for entry in entries]
    return sha256_hex(b"\x00".join(parts))


class EvidenceChain:
    """Append-only, content-addressed, tamper-evident evidence chain for LAB_L1.

    The chain NEVER mutates prior entries and NEVER instantiates a datastore. Callers
    supply referenced object digests/sizes; the verifier MAY optionally receive a
    `resolver` that proves a referenced object exists (fail-closed on missing object).
    """

    def __init__(self, chain_id: str, *, entries: Sequence[ChainEntry] | None = None) -> None:
        _require(isinstance(chain_id, str) and bool(CHAIN_ID.fullmatch(chain_id)), "CHAIN_ID_INVALID", "chain_id must be chain_<hex>")
        self.chain_id = chain_id
        self._entries: list[ChainEntry] = []
        if entries:
            for entry in entries:
                self._append_validated(entry)

    @property
    def entries(self) -> list[ChainEntry]:
        return list(self._entries)

    @property
    def length(self) -> int:
        return len(self._entries)

    def _append_validated(self, entry: ChainEntry) -> None:
        expected_index = len(self._entries)
        _require(entry.index == expected_index, "INDEX_DISCONTINUITY", f"expected index {expected_index}, got {entry.index}")
        if expected_index == 0:
            _require(entry.prev_entry_digest is None, "GENESIS_LINK_INVALID", "genesis prev_entry_digest must be null")
        else:
            prev = self._entries[-1]
            _require(entry.prev_entry_digest == prev.digest(), "LINK_DIGEST_MISMATCH", "prev_entry_digest does not bind the previous entry")
        for prior in self._entries:
            if prior.entry_id == entry.entry_id:
                raise EvidenceChainError("REPLAY_DETECTED: duplicate entry_id")
            if prior.object_ref == entry.object_ref and prior.object_digest_sha256 == entry.object_digest_sha256:
                raise EvidenceChainError("REPLAY_DETECTED: identical object ref+digest reused at new index")
        self._entries.append(entry)

    def append(self, entry: ChainEntry) -> int:
        self._append_validated(entry)
        return entry.index

    def append_object(
        self,
        *,
        object_kind: str,
        object_ref: str,
        object_digest_sha256: str,
        object_size_bytes: int,
        object_media_type: str,
        correlation: Mapping[str, str],
        evidence_ref: str | None = None,
        canonical_payload_sha256: str | None = None,
        created_at: str | None = None,
    ) -> ChainEntry:
        prev = self._entries[-1].digest() if self._entries else None
        entry = build_entry(
            index=len(self._entries),
            object_kind=object_kind,
            object_ref=object_ref,
            object_digest_sha256=object_digest_sha256,
            object_size_bytes=object_size_bytes,
            object_media_type=object_media_type,
            correlation=correlation,
            evidence_ref=evidence_ref,
            prev_entry_digest=prev,
            canonical_payload_sha256=canonical_payload_sha256,
            created_at=created_at,
        )
        self.append(entry)
        return entry

    def genesis_digest(self) -> str:
        _require(bool(self._entries), "CHAIN_EMPTY", "cannot compute genesis digest of empty chain")
        return self._entries[0].digest()

    def head_digest(self) -> str:
        _require(bool(self._entries), "CHAIN_EMPTY", "cannot compute head digest of empty chain")
        return self._entries[-1].digest()

    def chain_state_digest(self) -> str:
        return _entries_canonical_digest([e.as_dict() for e in self._entries])

    def verify(self, *, resolver: Any | None = None) -> bool:
        """Fail-closed verification: linkage, index continuity, object binding, optional object existence."""
        try:
            prev_digest: str | None = None
            for index, entry in enumerate(self._entries):
                if entry.index != index:
                    return False
                if index == 0:
                    if entry.prev_entry_digest is not None:
                        return False
                elif entry.prev_entry_digest != prev_digest:
                    return False
                if not _is_sha256(entry.object_digest_sha256):
                    return False
                if not _is_sha256(entry.canonical_payload_sha256):
                    return False
                if resolver is not None:
                    try:
                        ok = bool(resolver(object_ref=entry.object_ref, object_digest_sha256=entry.object_digest_sha256, object_size_bytes=entry.object_size_bytes))
                    except Exception:
                        return False
                    if not ok:
                        return False
                prev_digest = entry.digest()
            return True
        except EvidenceChainError:
            return False

    def as_document(self) -> dict[str, Any]:
        return {
            "schema_version": SCHEMA_VERSION,
            "profile": PROFILE,
            "chain_id": self.chain_id,
            "worm_migration_compatible": True,
            "entries": [e.as_dict() for e in self._entries],
            "seal": None,
        }

    @classmethod
    def from_document(cls, document: Mapping[str, Any]) -> "EvidenceChain":
        if document.get("schema_version") != SCHEMA_VERSION:
            raise EvidenceChainError("SCHEMA_VERSION_UNSUPPORTED")
        if document.get("profile") != PROFILE:
            raise EvidenceChainError("PROFILE_UNSUPPORTED: only LAB_L1 chain documents are accepted")
        if not bool(CHAIN_ID.fullmatch(str(document.get("chain_id")))):
            raise EvidenceChainError("CHAIN_ID_INVALID")
        raw_entries = document.get("entries")
        if not isinstance(raw_entries, list) or not raw_entries:
            raise EvidenceChainError("ENTRIES_INVALID: chain requires >=1 entry")
        chain = cls(document["chain_id"])
        for raw in raw_entries:
            if not isinstance(raw, Mapping):
                raise EvidenceChainError("ENTRY_INVALID: not a mapping")
            entry = ChainEntry(
                index=int(raw["index"]),
                entry_id=str(raw["entry_id"]),
                object_kind=str(raw["object_kind"]),
                object_ref=str(raw["object_ref"]),
                object_digest_sha256=str(raw["object_digest_sha256"]),
                object_size_bytes=int(raw["object_size_bytes"]),
                object_media_type=str(raw["object_media_type"]),
                correlation=dict(raw["correlation"]),
                evidence_ref=raw.get("evidence_ref"),
                prev_entry_digest=raw.get("prev_entry_digest"),
                canonical_payload_sha256=str(raw["canonical_payload_sha256"]),
                created_at=str(raw["created_at"]),
            )
            chain.append(entry)
        return chain
