#!/usr/bin/env python3
"""Adapt the runner transport audit decision interface to the canonical AuditSink.

This adapter eliminates the conceptual "second production audit sink" in the
runner transport: ``authenticate_unix_peer`` depends only on the minimal
``AuditSinkProtocol`` (``record_decision``) and may be injected with THIS adapter,
which funnels every decision into the already-merged LAB_L1 canonical
``AuditSink`` (PR #369/#370). The canonical sink is built on the frozen
``EvidenceChain`` / ``seal`` primitives; the adapter reuses that path and
reimplements NO chain or seal logic.

Design boundaries (read before extending):

- The adapter implements the runner transport's minimal ``record_decision``
  contract, so it is a drop-in ``audit_sink`` for ``authenticate_unix_peer``.
- It performs NO filesystem / network / process I/O and chooses NO signer,
  provider or trust store. A decision is appended to an in-memory canonical
  ``AuditSink``; the sealed document is returned to the caller for inspection or
  content-addressed persistence of their choosing. NO_RUNTIME_CHANGE.
- It honors the frozen ``EvidenceChain`` contract exactly: only the allowed
  ``object_kind`` ``evidence_record``, only ``evidence://`` / ``object://sha256/``
  ``object_ref`` formats, canonical SHA-256 object binding, valid size / media
  type, and a valid ``AuditContext``. No custom ``object_kind`` (e.g.
  ``authn-decision``) is used. No secrets.
- The canonical seal is integrity / tamper-evidence only (``signer`` is ``None``,
  ``authenticity`` / ``durability`` are ``False``). This adapter does NOT move
  promotion; campaign stays BLOCKED/HOLD, ``promotion_allowed = false``.

The canonical evidence-plane module is NOT a Python package, so it is loaded
standalone via ``importlib.util.spec_from_file_location`` -- the same repo
pattern ``unix_peer_identity.py`` / ``seal.py`` use. No ``__init__.py`` is added
and no packaging is altered.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
from pathlib import Path
from typing import Any, Mapping

HERE = Path(__file__).resolve().parent
EVIDENCE_PLANE = HERE.parent / "evidence-plane"

# Frozen evidence-chain contract (do NOT invent object kinds / ref formats):
_FROZEN_OBJECT_KIND = "evidence_record"
_OBJECT_MEDIA_TYPE = "application/json"

_SINK_MODULE_NAME = "_runner_transport_canonical_audit_sink"


def _load_canonical_audit_sink():
    """Load the merged canonical audit sink standalone (no package context)."""
    existing = sys.modules.get(_SINK_MODULE_NAME)
    if existing is not None:
        return existing
    spec = importlib.util.spec_from_file_location(
        _SINK_MODULE_NAME, EVIDENCE_PLANE / "audit_sink.py"
    )
    if not spec or not spec.loader:
        raise RuntimeError("cannot load canonical evidence-plane audit_sink.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[_SINK_MODULE_NAME] = module
    spec.loader.exec_module(module)
    return module


_canonical = _load_canonical_audit_sink()
AuditSink = _canonical.AuditSink
AuditContext = _canonical.AuditContext
AuditSinkError = _canonical.AuditSinkError

_CORRELATION_KEYS = ("campaign_id", "run_id", "step_id", "attempt_id")
_ALLOWED_DECISIONS = frozenset({"ALLOW", "DENY"})


def _canonical_record_digest(record: Mapping[str, Any]) -> tuple[str, int]:
    """SHA-256 binding of the authn decision record (canonical JSON)."""
    payload = json.dumps(record, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode(
        "utf-8"
    )
    return hashlib.sha256(payload).hexdigest(), len(payload)


class CanonicalAuditSinkAdapter:
    """Runner transport -> canonical AuditSink adapter (minimal ``record_decision``).

    Implements the same ``record_decision(*, decision, reason_code, detail)``
    surface ``authenticate_unix_peer`` expects, appending each decision to an
    in-memory canonical ``AuditSink``. Reuses the canonical ``append`` / ``seal`` /
    ``verify`` path; reimplements no chain or seal logic.
    """

    def __init__(self, *, chain_id: str, correlation: Mapping[str, str]) -> None:
        for key in _CORRELATION_KEYS:
            if key not in correlation:
                raise AuditSinkError("CONTEXT_INVALID", f"correlation requires {key}")
        self._sink = AuditSink(chain_id)
        self._correlation = {key: str(correlation[key]) for key in _CORRELATION_KEYS}
        self._sequence = 0

    def record_decision(
        self, *, decision: str, reason_code: str, detail: Mapping[str, Any]
    ) -> None:
        if decision not in _ALLOWED_DECISIONS:
            raise AuditSinkError("AUDIT_DECISION_INVALID", "unsupported decision")
        # Principal defaults to an opaque non-authenticated label when the peer
        # was denied (no principal identity was derived from SO_PEERCRED). It is
        # never caller-supplied beyond the kernel-derived mapping already enforced
        # by the authenticator.
        principal = detail.get("principal_id") or "unauthenticated-peer"
        context = AuditContext(
            campaign_id=self._correlation["campaign_id"],
            run_id=self._correlation["run_id"],
            step_id=self._correlation["step_id"],
            attempt_id=self._correlation["attempt_id"],
            principal=str(principal),
            decision=decision,
            correlation_id=str(reason_code),
            outcome="recorded" if decision == "ALLOW" else "denied",
            notes=str(reason_code),
        )
        record = {
            "decision": decision,
            "reason_code": reason_code,
            "evidence_source": detail.get("evidence_source"),
            "peer_uid": detail.get("peer_uid"),
            "peer_gid": detail.get("peer_gid"),
            "principal_id": detail.get("principal_id"),
        }
        digest, size = _canonical_record_digest(record)
        self._sink.append(
            object_kind=_FROZEN_OBJECT_KIND,
            object_ref=f"evidence://runner-transport/authn-decision/{self._sequence}",
            object_digest_sha256=digest,
            object_size_bytes=size,
            object_media_type=_OBJECT_MEDIA_TYPE,
            context=context,
        )
        self._sequence += 1

    @property
    def length(self) -> int:
        return self._sink.length

    def seal(self, *, sealed_at: str | None = None) -> dict[str, Any]:
        return self._sink.seal(sealed_at=sealed_at)

    def verify(self, *, resolver: Any | None = None) -> dict[str, Any]:
        return self._sink.verify(resolver=resolver)
