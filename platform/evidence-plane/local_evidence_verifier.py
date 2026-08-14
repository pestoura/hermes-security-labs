#!/usr/bin/env python3
"""LocalEvidenceVerifier: fail-closed EvidenceVerifier adapter for LAB_L1 local custody.

This is a REPOSITORY-ONLY adapter implementing the
``runtime_live_promotion_evidence.EvidenceVerifier`` contract
(``verify(evidence_ref: str, sha256: str) -> bool``). It resolves a canonical
local evidence reference to exactly ONE ``LocalEvidenceStore`` record, proves
integrity via ``LocalEvidenceStore.verify``, and binds the record's content
digest to the expected ``sha256``. It FAILS CLOSED on every irregularity:

- malformed references (not a parseable evidence id or storage/digest ref);
- missing records;
- digest mismatch (expected sha256 != stored content digest);
- tamper (``LocalEvidenceStore.verify`` returns False);
- duplicate/ambiguous records (more than one local record resolves to the ref).

This adapter is explicitly LAB_L1-only. It performs NO tenant isolation, NO
WORM durability, NO signer/authenticity, NO Vault, NO network, NO target or
runtime effect. It is a local, single-store content-addressing verifier that
reuses ``LocalEvidenceStore``; it must never be presented as a PROD
WORM/tenant-isolation control.

``NO_RUNTIME_CHANGE``. No default write into any repository path.
"""

from __future__ import annotations

import importlib.util
import json
import re
import sys
from pathlib import Path
from typing import Any, Mapping

HERE = Path(__file__).resolve().parent

EVIDENCE_ID = re.compile(r"^ev_[a-f0-9]{32}$")
OBJECT_DIGEST_REF = re.compile(r"^object://sha256/[a-f0-9]{64}$")
SHA256 = re.compile(r"^[a-f0-9]{64}$")


def _load_sibling(name: str, filename: str):
    """Resolve a same-directory module without requiring it on sys.path (repo pattern)."""
    module_name = f"_lab_l1_verifier_{name}"
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
LocalEvidenceStore = _store.LocalEvidenceStore
LocalEvidenceStoreError = _store.LocalEvidenceStoreError


class LocalEvidenceVerifier:
    """Fail-closed ``EvidenceVerifier`` over a single ``LocalEvidenceStore``.

    The store is the ONLY source of truth. The verifier never trusts a ref
    implicitly, never fabricates a record, and never writes. It resolves the
    ref to a single record, proves integrity with ``store.verify``, and binds
    the record digest to the caller-supplied expected ``sha256``.
    """

    def __init__(self, store: Any) -> None:
        # Accept a LocalEvidenceStore instance OR a root path/str (fail-closed build).
        if isinstance(store, (str, Path)):
            store = LocalEvidenceStore(store)
        # Duck-type rather than isinstance: the store may be loaded as a sibling
        # module under a distinct sys.modules key in the custody builder.
        if not (hasattr(store, "verify") and hasattr(store, "get_record") and hasattr(store, "records")):
            raise TypeError("LocalEvidenceVerifier requires a LocalEvidenceStore instance or root")
        self._store = store

    # --- ref resolution helpers (fail-closed) ---

    def _resolve_evidence_id(self, evidence_ref: str) -> str | None:
        """Return exactly one evidence_id for the ref, or None if malformed/missing/ambiguous."""
        if not isinstance(evidence_ref, str):
            return None
        candidate = evidence_ref
        if candidate.startswith("evidence://"):
            candidate = candidate[len("evidence://"):]
        # Canonical direct id is unambiguous by construction.
        if EVIDENCE_ID.fullmatch(candidate):
            return candidate
        # Digest-based or generic storage_ref: scan records, fail closed on ambiguity.
        return self._resolve_by_scan(evidence_ref)

    def _iter_records(self):
        for path in sorted(self._store.records.glob("*.json")):
            try:
                record = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            if not isinstance(record, dict):
                continue
            yield record

    def _resolve_by_scan(self, evidence_ref: str) -> str | None:
        if OBJECT_DIGEST_REF.fullmatch(evidence_ref):
            key = "digest"
            target = evidence_ref.split("/")[-1]
        else:
            key = "storage_ref"
            target = evidence_ref
        matches: list[str] = []
        for record in self._iter_records():
            content = record.get("content")
            if not isinstance(content, Mapping):
                continue
            if key == "digest":
                if content.get("sha256") == target:
                    matches.append(str(record.get("evidence_id")))
            else:
                if content.get("storage_ref") == target:
                    matches.append(str(record.get("evidence_id")))
        if len(matches) != 1:
            return None
        return matches[0]

    # --- EvidenceVerifier contract ---

    def verify(self, evidence_ref: str, sha256: str) -> bool:
        result = self.verify_detail(evidence_ref, sha256)
        return result["verified"]

    def verify_detail(self, evidence_ref: str, sha256: str) -> dict[str, Any]:
        """Verify and return a structured fail-closed result (never raises for tamper)."""
        evidence_id = self._resolve_evidence_id(evidence_ref)
        if evidence_id is None:
            return {"verified": False, "reason_code": "EVIDENCE_REF_UNRESOLVED", "detail": "malformed/missing/ambiguous ref"}
        if not isinstance(sha256, str) or not SHA256.fullmatch(sha256):
            return {"verified": False, "reason_code": "SHA256_INVALID", "detail": "expected sha256 is not lowercase 64-hex"}
        try:
            if not self._store.verify(evidence_id):
                return {"verified": False, "reason_code": "INTEGRITY_FAILED", "detail": "LocalEvidenceStore.verify returned False"}
            record = self._store.get_record(evidence_id)
        except LocalEvidenceStoreError:
            return {"verified": False, "reason_code": "STORE_ERROR", "detail": "record unavailable or invalid"}
        content = record.get("content") or {}
        stored_digest = content.get("sha256")
        if not isinstance(stored_digest, str) or stored_digest != sha256:
            return {"verified": False, "reason_code": "DIGEST_MISMATCH", "detail": "stored content digest != expected sha256"}
        return {"verified": True, "reason_code": "VERIFIED", "detail": "local evidence integrity + digest binding confirmed", "evidence_id": evidence_id}
