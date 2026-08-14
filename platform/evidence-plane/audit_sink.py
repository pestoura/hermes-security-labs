#!/usr/bin/env python3
"""LAB_L1 local append-only, hash-linked audit sink (Evidence Plane).

This module is a STRICT repository-only extension of the frozen LAB_L1 evidence
chain + seal primitives introduced by PR #369 (``evidence_chain.py`` /
``seal.py``). It does NOT duplicate chain logic: every record is appended to an
``EvidenceChain`` and the chain is sealed with the canonical ``seal_chain`` /
``verify_seal`` API.

Design boundaries (read before extending):

- Append-only / hash-linked: records bind to their predecessor via the evidence
  chain's ``prev_entry_digest`` and monotonic ``index``. Prior entries are never
  mutated or overwritten.
- Explicit audit context: each record carries ``campaign_id``, ``run_id``,
  ``step_id``, ``attempt_id`` (correlation), plus ``principal``, ``decision``,
  ``correlation_id`` and an optional ``outcome`` / ``notes``. ``principal`` and
  ``decision`` are opaque low-cardinality labels; they are NEVER secrets.
- Integrity binding: the audit envelope is folded into the entry's
  ``canonical_payload_sha256`` so the frozen evidence-chain seal covers every
  audit field. Tampering with any audit field breaks the seal.
- Fail-closed reads/writes: any malformed linkage, index gap, digest mismatch,
  tamper, replay/reorder, or missing referenced object causes a hard
  ``AuditSinkError`` (or a ``verified=False`` result on verification). No partial
  silent acceptance.
- Ordered replay: records are replayed in chain index order; a non-contiguous or
  out-of-order import is rejected fail-closed.
- No external delivery, no secrets, no live system/runtime/network/Docker/target
  effect. The module never opens sockets, writes outside the supplied in-memory
  document, or mutates the host. ``NO_RUNTIME_CHANGE``.
- The seal remains integrity/tamper-evidence only (``seal.signer`` is ``None``,
  ``authenticity``/``durability`` are ``False``). This sink does NOT choose a
  signer/provider, create keys, or build a trust store.

Reuse conventions: siblings are loaded standalone (no package context) exactly
like ``seal.py``. Canonical serialization mirrors ``evidence_chain``.
"""

from __future__ import annotations

import importlib.util
import sys
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Mapping, Sequence

HERE = Path(__file__).resolve().parent

SCHEMA_VERSION = "1.0"
PROFILE = "LAB_L1"

SINK_ID = __import__("re").compile(r"^audit_sink_[a-f0-9]{32,64}$")
SAFE_ID = __import__("re").compile(r"^[A-Za-z0-9._:@/-]{1,256}$")
SHA256 = __import__("re").compile(r"^[a-f0-9]{64}$")
OUTCOMES = {"observed", "recorded", "denied", "error", "unknown"}

# Forbidden strings: this module must never introduce a runtime/secret/external
# delivery effect. Used by AST guards in the test suite (NOT by scanning source
# text — the guard list itself contains these tokens).
FORBIDDEN_RUNTIME_TOKENS = (
    "socket.socket",
    "subprocess",
    "requests.",
    "httpx.",
    "smtplib",
    "boto3",
    "signer",
    "private_key",
)


def _load_sibling(name: str, filename: str):
    """Resolve a same-directory module without requiring it on sys.path (repo pattern)."""
    module_name = f"_lab_l1_audit_sink_{name}"
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
_seal = _load_sibling("seal", "seal.py")

EvidenceChain = _chain.EvidenceChain
ChainEntry = _chain.ChainEntry
build_entry = _chain.build_entry
EvidenceChainError = _chain.EvidenceChainError
sha256_hex = _chain.sha256_hex
canonical_bytes = _chain.canonical_bytes
SEAL_ID = _chain.SEAL_ID
CHAIN_ID = _chain.CHAIN_ID

seal_chain = _seal.seal_chain
verify_seal = _seal.verify_seal
SealError = _seal.SealError


class AuditSinkError(ValueError):
    """Fail-closed audit-sink contract violation."""


def _now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def _require(condition: bool, code: str, message: str) -> None:
    if not condition:
        raise AuditSinkError(f"{code}: {message}")


def _is_sha256(value: Any) -> bool:
    return isinstance(value, str) and bool(SHA256.fullmatch(value))


@dataclass(frozen=True)
class AuditContext:
    """Explicit campaign/run/step/attempt/principal/decision context for one audit event."""

    campaign_id: str
    run_id: str
    step_id: str
    attempt_id: str
    principal: str
    decision: str
    correlation_id: str
    outcome: str = "observed"
    notes: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {
            "campaign_id": self.campaign_id,
            "run_id": self.run_id,
            "step_id": self.step_id,
            "attempt_id": self.attempt_id,
            "principal": self.principal,
            "decision": self.decision,
            "correlation_id": self.correlation_id,
            "outcome": self.outcome,
            "notes": self.notes,
        }


def _validate_context(ctx: AuditContext) -> None:
    _require(isinstance(ctx, AuditContext), "CONTEXT_INVALID", "AuditContext required")
    for field in ("campaign_id", "run_id", "step_id", "attempt_id"):
        value = getattr(ctx, field)
        _require(isinstance(value, str) and bool(value), "CORRELATION_INVALID", f"{field} required")
        _require(bool(SAFE_ID.fullmatch(value)), "CORRELATION_INVALID", f"{field} has unsafe chars")
    for field in ("principal", "decision", "correlation_id"):
        value = getattr(ctx, field)
        _require(isinstance(value, str) and bool(value), "AUDIT_FIELD_INVALID", f"{field} required")
        _require(bool(SAFE_ID.fullmatch(value)), "AUDIT_FIELD_INVALID", f"{field} has unsafe chars")
    _require(ctx.outcome in OUTCOMES, "AUDIT_OUTCOME_INVALID", f"outcome {ctx.outcome} not allowed")
    _require(isinstance(ctx.notes, str), "AUDIT_NOTES_INVALID", "notes must be a string")


def derive_sink_id(chain_id: str) -> str:
    """Deterministic sink id bound to the underlying chain id (content-addressed)."""
    _require(bool(CHAIN_ID.fullmatch(chain_id)), "CHAIN_ID_INVALID", "chain_id must be chain_<hex>")
    return f"audit_sink_{sha256_hex(canonical_bytes({'chain_id': chain_id}))[:48]}"


class AuditEvent:
    """A single audit event: a chain entry plus its explicit audit context."""

    __slots__ = ("entry", "context")

    def __init__(self, *, entry: ChainEntry, context: AuditContext) -> None:
        self.entry = entry
        self.context = context

    def as_chain_dict(self) -> dict[str, Any]:
        return self.entry.as_dict()

    def as_dict(self) -> dict[str, Any]:
        return {**self.entry.as_dict(), "audit": self.context.as_dict()}


def _verify_audit_envelope_binding(document: Mapping[str, Any]) -> dict[str, Any] | None:
    """Return a fail dict if any audit envelope is missing, malformed, or its digest
    is not bound into the entry's ``canonical_payload_sha256``; else ``None``."""
    for item in document.get("entries", []):
        audit = item.get("audit")
        if not isinstance(audit, Mapping):
            return {"verified": False, "reason_code": "AUDIT_ENVELOPE_MISSING", "detail": "entry missing audit envelope"}
        for key in ("campaign_id", "run_id", "step_id", "attempt_id", "principal", "decision", "correlation_id"):
            if not isinstance(audit.get(key), str) or not audit.get(key):
                return {"verified": False, "reason_code": "AUDIT_FIELD_INVALID", "detail": f"missing/empty audit field {key}"}
        if audit.get("outcome") not in OUTCOMES:
            return {"verified": False, "reason_code": "AUDIT_OUTCOME_INVALID", "detail": "unknown outcome"}
        try:
            ctx = AuditContext(
                campaign_id=audit["campaign_id"],
                run_id=audit["run_id"],
                step_id=audit["step_id"],
                attempt_id=audit["attempt_id"],
                principal=audit["principal"],
                decision=audit["decision"],
                correlation_id=audit["correlation_id"],
                outcome=audit.get("outcome", "observed"),
                notes=audit.get("notes", ""),
            )
        except KeyError as exc:
            return {"verified": False, "reason_code": "AUDIT_ENVELOPE_INVALID", "detail": f"missing {exc}"}
        expected_payload_digest = sha256_hex(canonical_bytes(ctx.as_dict()))
        if item.get("canonical_payload_sha256") != expected_payload_digest:
            return {"verified": False, "reason_code": "AUDIT_ENVELOPE_TAMPERED", "detail": "canonical_payload_sha256 does not bind the audit envelope"}
    return None


class AuditSink:
    """Append-only, hash-linked, fail-closed local audit sink over an EvidenceChain.

    The sink never instantiates a datastore or performs I/O. It builds an in-memory
    sealed document; callers may persist the returned dict with their own
    content-addressed store. No external delivery, no secrets, no runtime effect.
    """

    def __init__(self, chain_id: str, *, entries: Sequence[AuditEvent] | None = None) -> None:
        _require(bool(CHAIN_ID.fullmatch(chain_id)), "CHAIN_ID_INVALID", "chain_id must be chain_<hex>")
        self.chain_id = chain_id
        self.sink_id = derive_sink_id(chain_id)
        self._chain = EvidenceChain(chain_id)
        self._audit: list[AuditEvent] = []
        if entries:
            for event in entries:
                self._append_validated(event)

    @property
    def length(self) -> int:
        return len(self._audit)

    @property
    def events(self) -> list[AuditEvent]:
        return list(self._audit)

    def append(
        self,
        *,
        object_kind: str,
        object_ref: str,
        object_digest_sha256: str,
        object_size_bytes: int,
        object_media_type: str,
        context: AuditContext,
        evidence_ref: str | None = None,
        created_at: str | None = None,
    ) -> AuditEvent:
        """Append one audit event. Fail-closed on any invalid field or broken linkage."""
        _validate_context(context)
        # Fail-closed duplicate correlation+decision guard (replay detection at the
        # audit layer, independent of the chain's object-ref replay guard).
        for prior in self._audit:
            if (
                prior.context.campaign_id == context.campaign_id
                and prior.context.run_id == context.run_id
                and prior.context.step_id == context.step_id
                and prior.context.attempt_id == context.attempt_id
                and prior.context.decision == context.decision
                and prior.entry.object_ref == object_ref
                and prior.entry.object_digest_sha256 == object_digest_sha256
            ):
                raise AuditSinkError("REPLAY_DETECTED: identical audit event already present")
        # Bind the audit envelope into the chain entry's canonical payload digest so
        # the frozen evidence-chain seal covers every audit field (tamper-evident).
        audit_payload_digest = sha256_hex(canonical_bytes(context.as_dict()))
        try:
            entry = self._chain.append_object(
                object_kind=object_kind,
                object_ref=object_ref,
                object_digest_sha256=object_digest_sha256,
                object_size_bytes=object_size_bytes,
                object_media_type=object_media_type,
                correlation={
                    "campaign_id": context.campaign_id,
                    "run_id": context.run_id,
                    "step_id": context.step_id,
                    "attempt_id": context.attempt_id,
                },
                evidence_ref=evidence_ref,
                canonical_payload_sha256=audit_payload_digest,
                created_at=created_at or _now(),
            )
        except EvidenceChainError as exc:
            raise AuditSinkError(str(exc)) from exc
        event = AuditEvent(entry=entry, context=context)
        self._audit.append(event)
        return event

    def _append_validated(self, event: AuditEvent) -> None:
        _validate_context(event.context)
        self._chain.append(event.entry)
        self._audit.append(event)

    def as_document(self, *, sealed_at: str | None = None) -> dict[str, Any]:
        """Return the sealed chain document plus the audit envelope, schema-shaped."""
        sealed = seal_chain(self._chain, sealed_at=sealed_at)
        sealed["sink_id"] = self.sink_id
        sealed["no_external_delivery"] = True
        sealed["no_secrets"] = True
        sealed["no_runtime_effect"] = True
        sealed["entries"] = [
            {**e.as_chain_dict(), "audit": e.context.as_dict()} for e in self._audit
        ]
        return sealed

    def seal(self, *, sealed_at: str | None = None) -> dict[str, Any]:
        return self.as_document(sealed_at=sealed_at)

    def verify(self, *, resolver: Any | None = None) -> dict[str, Any]:
        """Fail-closed verification of the sealed audit document.

        Reuses ``verify_seal`` for chain integrity/seal binding and additionally
        enforces that every entry carries a valid audit envelope whose digest is
        bound into the entry (tamper-evident) and that replay/reorder conditions are
        absent. Returns a result dict; never raises for tamper conditions.
        """
        document = self.as_document()
        result = verify_seal(document, resolver=resolver)
        if not result.get("verified"):
            return result
        binding = _verify_audit_envelope_binding(document)
        if binding is not None:
            return binding
        return {**result, "sink_id": self.sink_id, "entry_count": len(self._audit)}

    @classmethod
    def verify_document(cls, document: Mapping[str, Any], *, resolver: Any | None = None) -> dict[str, Any]:
        """Fail-closed verification of an external sealed audit document (no reconstruction).

        Verifies the chain seal and the audit-envelope invariants without mutating any
        state. Returns a result dict with ``verified``; never raises for tamper conditions.
        """
        result = verify_seal(document, resolver=resolver)
        if not result.get("verified"):
            return result
        if document.get("no_external_delivery") is not True:
            return {"verified": False, "reason_code": "EXTERNAL_DELIVERY_VIOLATION", "detail": "sink must declare no external delivery"}
        if document.get("no_secrets") is not True:
            return {"verified": False, "reason_code": "SECRETS_VIOLATION", "detail": "sink must declare no secrets"}
        if document.get("no_runtime_effect") is not True:
            return {"verified": False, "reason_code": "RUNTIME_EFFECT_VIOLATION", "detail": "sink must declare no runtime effect"}
        binding = _verify_audit_envelope_binding(document)
        if binding is not None:
            return binding
        return {**result, "sink_id": document.get("sink_id"), "entry_count": len(document.get("entries", []))}

    @classmethod
    def from_document(cls, document: Mapping[str, Any]) -> "AuditSink":
        """Reconstruct a sink from a sealed audit document (ordered replay).

        Fail-closed: schema version/profile mismatch, bad chain id, missing audit
        envelope, index discontinuity, or out-of-order entries are rejected.
        """
        if document.get("schema_version") != SCHEMA_VERSION:
            raise AuditSinkError("SCHEMA_VERSION_UNSUPPORTED")
        if document.get("profile") != PROFILE:
            raise AuditSinkError("PROFILE_UNSUPPORTED: only LAB_L1 audit documents are accepted")
        if not bool(CHAIN_ID.fullmatch(str(document.get("chain_id")))):
            raise AuditSinkError("CHAIN_ID_INVALID")
        if document.get("no_external_delivery") is not True:
            raise AuditSinkError("EXTERNAL_DELIVERY_VIOLATION: sink must declare no external delivery")
        if document.get("no_secrets") is not True:
            raise AuditSinkError("SECRETS_VIOLATION: sink must declare no secrets")
        if document.get("no_runtime_effect") is not True:
            raise AuditSinkError("RUNTIME_EFFECT_VIOLATION: sink must declare no runtime effect")
        raw_entries = document.get("entries")
        if not isinstance(raw_entries, list) or not raw_entries:
            raise AuditSinkError("ENTRIES_INVALID: audit sink requires >=1 entry")
        sink = cls(document["chain_id"])
        expected_index = 0
        for raw in raw_entries:
            if not isinstance(raw, Mapping):
                raise AuditSinkError("AUDIT_ENTRY_INVALID: not a mapping")
            audit = raw.get("audit")
            if not isinstance(audit, Mapping):
                raise AuditSinkError("AUDIT_ENVELOPE_MISSING: entry missing audit envelope")
            try:
                ctx = AuditContext(
                    campaign_id=audit["campaign_id"],
                    run_id=audit["run_id"],
                    step_id=audit["step_id"],
                    attempt_id=audit["attempt_id"],
                    principal=audit["principal"],
                    decision=audit["decision"],
                    correlation_id=audit["correlation_id"],
                    outcome=audit.get("outcome", "observed"),
                    notes=audit.get("notes", ""),
                )
            except KeyError as exc:
                raise AuditSinkError(f"AUDIT_ENVELOPE_INVALID: missing {exc}") from exc
            if raw.get("index") != expected_index:
                raise AuditSinkError("REPLAY_REORDER_DETECTED: non-contiguous index during replay")
            # Recompute the audit-envelope digest and compare against the entry's
            # canonical_payload_sha256: tampering with any audit field breaks the bind.
            expected_payload_digest = sha256_hex(canonical_bytes(ctx.as_dict()))
            if raw.get("canonical_payload_sha256") != expected_payload_digest:
                raise AuditSinkError("AUDIT_ENVELOPE_TAMPERED: canonical_payload_sha256 does not bind the audit envelope")
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
            try:
                sink._append_validated(AuditEvent(entry=entry, context=ctx))
            except EvidenceChainError as exc:
                raise AuditSinkError(str(exc)) from exc
            expected_index += 1
        return sink
