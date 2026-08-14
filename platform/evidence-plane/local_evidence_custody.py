#!/usr/bin/env python3
"""Deterministic LAB_L1 local evidence custody + seal builder.

Repository-only, fail-closed. It accepts EXPLICIT, ALREADY-COLLECTED *SAFE*
evidence (bytes + metadata) and writes them ONLY through ``LocalEvidenceStore``
(content-addressed, immutable, fsync'd). It then builds a canonical
``EvidenceChain`` document binding every referenced object by digest + ref and
seals it with the EXISTING ``seal_chain`` primitive.

Boundaries (read before extending):

- This builder performs ZERO live collection, ZERO target/network/runtime/systemd
  effect, ZERO signer/Vault/trust/timestamp-authority interaction. It only
  persists bytes the caller already holds and derives an integrity seal.
- Authenticity and durability are LAB_L1-only / explicitly FALSE: the produced
  seal carries ``bindings.signer = null``, ``bindings.authenticity = false``,
  ``bindings.durability = false`` (enforced by ``seal.py``). This artifact is
  NOT a PROD WORM backend, NOT tenant isolation, NOT a signer attestation.
- The store ROOT is configurable and defaults to a non-repository temp-style
  path ONLY when explicitly supplied; the builder never writes into the repo by
  default. Tests use temp dirs.
- Deterministic: identical inputs (evidence bytes + metadata + correlation +
  sealed_at) yield byte-identical records, an identical chain document, and an
  identical seal. Re-running over an existing store is idempotent (the store's
  O_EXCL discipline makes repeated puts of unchanged evidence a no-op).

``NO_RUNTIME_CHANGE``.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence

HERE = Path(__file__).resolve().parent


def _load_sibling(name: str, filename: str):
    """Resolve a same-directory module without requiring it on sys.path (repo pattern)."""
    module_name = f"_lab_l1_custody_{name}"
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


_store = _load_sibling("store", "local_store.py")
_chain = _load_sibling("chain", "evidence_chain.py")
_seal = _load_sibling("seal", "seal.py")

LocalEvidenceStore = _store.LocalEvidenceStore
LocalEvidenceStoreError = _store.LocalEvidenceStoreError
EvidenceChain = _chain.EvidenceChain
build_entry = _chain.build_entry
sha256_hex = _chain.sha256_hex
chain_SHA256 = _chain.SHA256
CHAIN_ID = _chain.CHAIN_ID
OBJECT_REF_RE = _chain.OBJECT_REF
SAFE_ID = _chain.SAFE_ID
seal_chain = _seal.seal_chain
verify_seal = _seal.verify_seal


class LocalEvidenceCustodyError(ValueError):
    """Fail-closed local evidence custody contract violation."""


@dataclass(frozen=True)
class SafeEvidenceItem:
    """Explicit, already-collected SAFE evidence the caller already holds.

    ``evidence_id`` is OPTIONAL: when omitted it is derived deterministically
    from the payload + structured metadata (content-addressing), guaranteeing
    replay/idempotency semantics. When supplied it must be a canonical
    ``ev_<32 hex>`` id; otherwise persistence fails closed.
    """

    payload: bytes
    classification: str
    storage_ref: str
    media_type: str
    correlation: Mapping[str, str]
    evidence_id: str | None = None
    producer: str = "local-custody-builder"
    operation: str = "lab_l1.custody.persist"
    protocol_version: str = "1.0"
    knowledge_snapshot: str | None = None
    retention_policy_id: str = "default-30d"
    retain_until: str = "2026-09-30T00:00:00Z"
    legal_hold: bool = False
    created_at: str | None = None


@dataclass(frozen=True)
class CustodyResult:
    store_root: str
    evidence_ids: tuple[str, ...]
    evidence_refs: tuple[str, ...]
    object_digests: tuple[str, ...]
    chain_id: str
    sealed_document: dict[str, Any]
    sealed_at: str


def _valid_correlation(value: Any) -> dict[str, str]:
    _require(isinstance(value, Mapping) and set(value) == {"campaign_id", "run_id", "step_id", "attempt_id"},
             "CORRELATION_INVALID", "exact correlation keys required")
    out = {key: value[key] for key in ("campaign_id", "run_id", "step_id", "attempt_id")}
    for key, item in out.items():
        _require(isinstance(item, str) and bool(SAFE_ID.fullmatch(item)), "CORRELATION_INVALID", f"invalid {key}")
    return out


def _require(condition: bool, code: str, message: str) -> None:
    if not condition:
        raise LocalEvidenceCustodyError(f"{code}: {message}")


def _normalize_item(item: SafeEvidenceItem | Mapping[str, Any]) -> SafeEvidenceItem:
    if isinstance(item, SafeEvidenceItem):
        return item
    if not isinstance(item, Mapping):
        raise LocalEvidenceCustodyError("ITEM_INVALID: evidence item must be SafeEvidenceItem or mapping")
    payload = item.get("payload")
    if not isinstance(payload, (bytes, bytearray)):
        raise LocalEvidenceCustodyError("ITEM_INVALID: payload must be bytes")
    correlation = item.get("correlation")
    if not isinstance(correlation, Mapping):
        raise LocalEvidenceCustodyError("ITEM_INVALID: correlation required")
    return SafeEvidenceItem(
        evidence_id=item.get("evidence_id"),
        payload=bytes(payload),
        classification=str(item.get("classification", "raw")),
        storage_ref=str(item.get("storage_ref")),
        media_type=str(item.get("media_type", "application/octet-stream")),
        correlation=dict(correlation),
        producer=str(item.get("producer", "local-custody-builder")),
        operation=str(item.get("operation", "lab_l1.custody.persist")),
        protocol_version=str(item.get("protocol_version", "1.0")),
        knowledge_snapshot=item.get("knowledge_snapshot"),
        retention_policy_id=str(item.get("retention_policy_id", "default-30d")),
        retain_until=str(item.get("retain_until", "2026-09-30T00:00:00Z")),
        legal_hold=bool(item.get("legal_hold", False)),
        created_at=item.get("created_at"),
    )


def _build_record(item: SafeEvidenceItem) -> dict[str, Any]:
    digest = sha256_hex(item.payload)
    size = len(item.payload)
    _require(bool(chain_SHA256.fullmatch(digest)), "DIGEST_INVALID", "internal digest not sha256")
    _require(item.classification in {"raw", "restricted", "sanitized", "summary"}, "CLASSIFICATION_INVALID", f"classification {item.classification} not allowed")
    _require(item.storage_ref.startswith("evidence://"), "STORAGE_REF_INVALID", "storage_ref must use evidence://")
    corr = _valid_correlation(item.correlation)
    # Evidence id is content-addressed: derived deterministically so identical
    # inputs yield identical ids (idempotency/replay). A caller-supplied id is
    # accepted only if it is a canonical ev_<32 hex> form.
    if item.evidence_id is not None:
        _require(bool(_store.EVIDENCE_ID.fullmatch(item.evidence_id)), "EVIDENCE_ID_INVALID", "evidence_id must be ev_<32 hex>")
        evidence_id = item.evidence_id
    else:
        seed = {
            "classification": item.classification,
            "correlation": dict(corr),
            "producer": item.producer,
            "operation": item.operation,
            "payload_sha256": digest,
            "storage_ref": item.storage_ref,
        }
        evidence_id = f"ev_{sha256_hex(json.dumps(seed, sort_keys=True, separators=(',', ':'), ensure_ascii=True).encode('utf-8'))[:32]}"
    record: dict[str, Any] = {
        "schema_version": "2.0",
        "evidence_id": evidence_id,
        "classification": item.classification,
        "correlation": dict(corr),
        "origin": {
            "producer": item.producer,
            "operation": item.operation,
            "protocol_version": item.protocol_version,
            "knowledge_snapshot": item.knowledge_snapshot,
        },
        "content": {
            "sha256": digest,
            "size_bytes": size,
            "media_type": item.media_type,
            "storage_ref": item.storage_ref,
        },
        "retention": {
            "policy_id": item.retention_policy_id,
            "retain_until": item.retain_until,
            "legal_hold": item.legal_hold,
        },
        "parent_evidence_id": None,
        "redaction": None,
        "created_at": item.created_at or _now(),
    }
    return record


def _now() -> str:
    from datetime import UTC, datetime

    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


class LocalEvidenceCustodyBuilder:
    """Persist explicit SAFE evidence via ``LocalEvidenceStore`` and seal a chain document.

    The builder writes evidence ONLY through ``LocalEvidenceStore`` (no direct
    filesystem writes), then derives a deterministic ``EvidenceChain`` binding
    every persisted object and seals it with the existing ``seal_chain``
    primitive. The seal's ``authenticity``/``durability`` remain ``false`` by
    construction. No PROD WORM/tenant-isolation/signer is claimed.
    """

    def __init__(self, store_root: str | Path) -> None:
        self._store_root = Path(store_root).expanduser().resolve()
        self._store = LocalEvidenceStore(self._store_root)

    @property
    def store_root(self) -> Path:
        return self._store_root

    def custody(
        self,
        *,
        chain_id: str,
        items: Sequence[SafeEvidenceItem | Mapping[str, Any]],
        sealed_at: str | None = None,
        _ts: str | None = None,
    ) -> CustodyResult:
        _require(isinstance(chain_id, str) and bool(CHAIN_ID.fullmatch(chain_id)), "CHAIN_ID_INVALID", "chain_id must be chain_<hex>")
        normalized = [_normalize_item(item) for item in items]
        _require(len(normalized) >= 1, "CUSTODY_EMPTY", "custody requires >=1 evidence item")

        evidence_ids: list[str] = []
        evidence_refs: list[str] = []
        object_digests: list[str] = []
        records: list[dict[str, Any]] = []

        # Write ONLY through LocalEvidenceStore (fail-closed content-addressing).
        for index, item in enumerate(normalized):
            # Deterministic replay requires a stable created_at; a caller may pass
            # an explicit timestamp via _ts (e.g. from an already-collected SAFE artifact).
            if _ts is not None and item.created_at is None:
                item = SafeEvidenceItem(
                    payload=item.payload,
                    classification=item.classification,
                    storage_ref=item.storage_ref,
                    media_type=item.media_type,
                    correlation=dict(item.correlation),
                    evidence_id=item.evidence_id,
                    producer=item.producer,
                    operation=item.operation,
                    protocol_version=item.protocol_version,
                    knowledge_snapshot=item.knowledge_snapshot,
                    retention_policy_id=item.retention_policy_id,
                    retain_until=item.retain_until,
                    legal_hold=item.legal_hold,
                    created_at=_ts,
                )
                normalized[index] = item
            record = _build_record(item)
            try:
                evidence_id = self._store.put(record, item.payload)
            except LocalEvidenceStoreError as exc:
                raise LocalEvidenceCustodyError(f"PERSIST_FAILED: {exc}") from exc
            evidence_ids.append(evidence_id)
            evidence_refs.append(item.storage_ref)
            object_digests.append(record["content"]["sha256"])
            records.append(record)

        # Duplicate/ambiguous evidence detection across the supplied batch.
        if len(set(evidence_ids)) != len(evidence_ids):
            raise LocalEvidenceCustodyError("DUPLICATE_EVIDENCE: identical evidence_id supplied twice in one batch")
        # Re-verify each persisted record to fail closed on tamper/missing sidecar.
        for evidence_id in evidence_ids:
            if not self._store.verify(evidence_id):
                raise LocalEvidenceCustodyError(f"TAMPER_OR_MISSING: {evidence_id} failed post-write verification")

        # Build the deterministic chain: each item becomes one entry bound to its object.
        chain = EvidenceChain(chain_id)
        for item, digest, evidence_id in zip(normalized, object_digests, evidence_ids, strict=True):
            prev = chain.head_digest() if chain.entries else None
            entry = build_entry(
                index=len(chain.entries),
                object_kind="evidence_record",
                object_ref=item.storage_ref,
                object_digest_sha256=digest,
                object_size_bytes=len(item.payload),
                object_media_type=item.media_type,
                correlation=dict(item.correlation),
                evidence_ref=evidence_id,
                prev_entry_digest=prev,
                canonical_payload_sha256=digest,
                created_at=item.created_at,
            )
            chain.append(entry)

        if not chain.verify():
            raise LocalEvidenceCustodyError("CHAIN_INTEGRITY_FAILED: assembled chain did not verify")

        sealed_document = seal_chain(chain, sealed_at=sealed_at)
        seal_result = verify_seal(sealed_document)
        if not isinstance(seal_result, Mapping) or not seal_result.get("verified"):
            reason = seal_result.get("reason_code") if isinstance(seal_result, Mapping) else "SEAL_FAILED"
            raise LocalEvidenceCustodyError(f"SEAL_FAILED: {reason}")

        return CustodyResult(
            store_root=str(self._store_root),
            evidence_ids=tuple(evidence_ids),
            evidence_refs=tuple(evidence_refs),
            object_digests=tuple(object_digests),
            chain_id=chain_id,
            sealed_document=sealed_document,
            sealed_at=str(sealed_document["seal"]["sealed_at"]),
        )

    def verifier(self) -> Any:
        """Return a fail-closed ``EvidenceVerifier`` bound to the same store."""
        return _load_sibling("verifier", "local_evidence_verifier.py").LocalEvidenceVerifier(self._store)
