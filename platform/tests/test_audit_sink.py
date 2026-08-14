#!/usr/bin/env python3
"""Tests for LAB_L1 local append-only hash-linked audit sink (ADR-0011 Option B lane).

Covers: append, monotonic ordering, deterministic serialization, tamper detection,
replay/reorder detection, partial-failure fail-closed behavior, schema validation,
and AST guards proving the module performs no runtime/secret/external-delivery effect.

No provider crypto, no keys, no live mutation, no network, no Docker/target effect.
promotion_allowed stays false by construction; VAL-HSL-RUNNER-L1-LIVE-PROMOTION is
untouched and remains BLOCKED/HOLD.
"""

from __future__ import annotations

import ast
import importlib.util
import json
import sys
from pathlib import Path

import jsonschema
import pytest

ROOT = Path(__file__).resolve().parents[2]
SINK_DIR = ROOT / "platform" / "evidence-plane"
SCHEMA_PATH = ROOT / "platform" / "schemas" / "audit-sink.schema.json"


def _load(name: str, filename: str):
    spec = importlib.util.spec_from_file_location(name, SINK_DIR / filename)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


sink_module = _load("lab_l1_audit_sink", "audit_sink.py")

AuditSink = sink_module.AuditSink
AuditContext = sink_module.AuditContext
AuditSinkError = sink_module.AuditSinkError
derive_sink_id = sink_module.derive_sink_id

CHAIN_ID = "chain_" + "0" * 32
OBJ_A = "a" * 64
OBJ_B = "b" * 64
OBJ_C = "c" * 64
SEALED_AT = "2026-08-15T00:00:00Z"


def _ctx(attempt: str = "a1", decision: str = "allow", principal: str = "runner-gateway", outcome: str = "observed") -> AuditContext:
    return AuditContext(
        campaign_id="camp-1",
        run_id="run-1",
        step_id="step-1",
        attempt_id=attempt,
        principal=principal,
        decision=decision,
        correlation_id=f"corr-{attempt}-{decision}",
        outcome=outcome,
    )


def _new_sink() -> AuditSink:
    return AuditSink(CHAIN_ID)


def _append(sink: AuditSink, digest: str = OBJ_A, attempt: str = "a1", decision: str = "allow", outcome: str = "observed") -> None:
    sink.append(
        object_kind="evidence_record",
        object_ref=f"evidence://camp-1/run-1/raw/{digest[:8]}.json",
        object_digest_sha256=digest,
        object_size_bytes=len(digest),
        object_media_type="application/json",
        context=_ctx(attempt=attempt, decision=decision, outcome=outcome),
        created_at=SEALED_AT,
    )


def _sealed(sink: AuditSink) -> dict:
    return sink.seal(sealed_at=SEALED_AT)


# --------------------------------------------------------------------------- #
# Append / ordering
# --------------------------------------------------------------------------- #
def test_append_assigns_monotonic_index_and_binds_prev() -> None:
    sink = _new_sink()
    _append(sink, OBJ_A, attempt="a1")
    _append(sink, OBJ_B, attempt="a2")
    events = sink.events
    assert events[0].entry.index == 0
    assert events[1].entry.index == 1
    assert events[0].entry.prev_entry_digest is None
    assert events[1].entry.prev_entry_digest == events[0].entry.digest()
    assert sink.length == 2


def test_correlation_and_audit_fields_round_trip() -> None:
    sink = _new_sink()
    ctx = _ctx(attempt="a1", decision="deny", principal="runner-dispatch", outcome="denied")
    sink.append(
        object_kind="exec_manifest",
        object_ref="evidence://camp-1/run-1/manifest/x.json",
        object_digest_sha256=OBJ_A,
        object_size_bytes=64,
        object_media_type="application/json",
        context=ctx,
    )
    doc = _sealed(sink)
    audit = doc["entries"][0]["audit"]
    assert audit["campaign_id"] == "camp-1"
    assert audit["run_id"] == "run-1"
    assert audit["step_id"] == "step-1"
    assert audit["attempt_id"] == "a1"
    assert audit["principal"] == "runner-dispatch"
    assert audit["decision"] == "deny"
    assert audit["outcome"] == "denied"
    assert audit["correlation_id"] == "corr-a1-deny"


# --------------------------------------------------------------------------- #
# Deterministic serialization
# --------------------------------------------------------------------------- #
def test_serialization_is_deterministic() -> None:
    s1 = _new_sink()
    _append(s1, OBJ_A, "a1")
    _append(s1, OBJ_B, "a2")
    s2 = _new_sink()
    _append(s2, OBJ_A, "a1")
    _append(s2, OBJ_B, "a2")
    d1 = _sealed(s1)
    d2 = _sealed(s2)
    assert d1["seal"]["seal_id"] == d2["seal"]["seal_id"]
    assert d1["seal"]["chain_state_digest_sha256"] == d2["seal"]["chain_state_digest_sha256"]
    assert d1["seal"]["head_digest_sha256"] == d2["seal"]["head_digest_sha256"]
    # byte-identical canonical serialization of the entries+audit envelope
    assert json.dumps(d1["entries"], sort_keys=True, separators=(",", ":")) == json.dumps(
        d2["entries"], sort_keys=True, separators=(",", ":")
    )


def test_sealed_at_is_deterministic() -> None:
    s1 = _new_sink()
    _append(s1, OBJ_A, "a1")
    a = s1.seal(sealed_at=SEALED_AT)
    b = s1.seal(sealed_at=SEALED_AT)
    assert a["seal"]["seal_id"] == b["seal"]["seal_id"]


# --------------------------------------------------------------------------- #
# Tamper detection (fail-closed)
# --------------------------------------------------------------------------- #
def test_tamper_with_entry_payload_fails_verification() -> None:
    sink = _new_sink()
    _append(sink, OBJ_A, "a1")
    _append(sink, OBJ_B, "a2")
    doc = _sealed(sink)
    # mutate an entry's object digest (tamper)
    doc["entries"][0]["object_digest_sha256"] = OBJ_C
    res = AuditSink.verify_document(doc)
    assert res["verified"] is False


def test_tamper_with_audit_field_fails_verification() -> None:
    sink = _new_sink()
    _append(sink, OBJ_A, "a1", decision="allow")
    doc = _sealed(sink)
    doc["entries"][0]["audit"]["decision"] = "forged-decision"
    res = AuditSink.verify_document(doc)
    assert res["verified"] is False


def test_tamper_with_seal_chain_state_fails() -> None:
    sink = _new_sink()
    _append(sink, OBJ_A, "a1")
    doc = _sealed(sink)
    doc["seal"]["chain_state_digest_sha256"] = "f" * 64
    res = AuditSink.verify_document(doc)
    assert res["verified"] is False


def test_reconstruction_detects_tampered_document() -> None:
    sink = _new_sink()
    _append(sink, OBJ_A, "a1")
    doc = _sealed(sink)
    doc["entries"][0]["audit"]["principal"] = "forged"
    with pytest.raises(AuditSinkError):
        AuditSink.from_document(doc)


# --------------------------------------------------------------------------- #
# Replay / reorder detection (fail-closed)
# --------------------------------------------------------------------------- #
def test_replay_same_correlation_and_object_refused() -> None:
    sink = _new_sink()
    _append(sink, OBJ_A, "a1", decision="allow")
    with pytest.raises(AuditSinkError):
        _append(sink, OBJ_A, "a1", decision="allow")


def test_chain_level_replay_detected_on_reconstruction() -> None:
    sink = _new_sink()
    _append(sink, OBJ_A, "a1")
    _append(sink, OBJ_B, "a2")
    doc = _sealed(sink)
    # duplicate the last entry with a fresh index+prev (chain replay via reconstruction)
    last = dict(doc["entries"][-1])
    dup = dict(last)
    dup["index"] = 2
    dup["entry_id"] = "evc_" + "f" * 48
    dup["prev_entry_digest"] = last["entry_id"] and last["prev_entry_digest"]  # keep prev; index gap
    dup["prev_entry_digest"] = doc["seal"]["head_digest_sha256"]
    doc["entries"].append(dup)
    with pytest.raises(AuditSinkError):
        AuditSink.from_document(doc)


def test_reorder_non_contiguous_index_rejected_on_replay() -> None:
    sink = _new_sink()
    _append(sink, OBJ_A, "a1")
    _append(sink, OBJ_B, "a2")
    doc = _sealed(sink)
    # swap so index order is broken
    e0, e1 = doc["entries"][0], doc["entries"][1]
    doc["entries"][0] = {**e1, "index": 0}
    doc["entries"][1] = {**e0, "index": 1}
    with pytest.raises(AuditSinkError):
        AuditSink.from_document(doc)


def test_missing_audit_envelope_rejected_on_replay() -> None:
    sink = _new_sink()
    _append(sink, OBJ_A, "a1")
    doc = _sealed(sink)
    del doc["entries"][0]["audit"]
    with pytest.raises(AuditSinkError):
        AuditSink.from_document(doc)


# --------------------------------------------------------------------------- #
# Partial-failure fail-closed (no silent acceptance)
# --------------------------------------------------------------------------- #
def test_invalid_correlation_field_refused() -> None:
    sink = _new_sink()
    bad = AuditContext(
        campaign_id="",  # invalid: empty
        run_id="run-1",
        step_id="step-1",
        attempt_id="a1",
        principal="gw",
        decision="allow",
        correlation_id="c",
    )
    with pytest.raises(AuditSinkError):
        sink.append(
            object_kind="evidence_record",
            object_ref="evidence://x/y.json",
            object_digest_sha256=OBJ_A,
            object_size_bytes=64,
            object_media_type="application/json",
            context=bad,
        )


def test_invalid_object_digest_refused_by_chain() -> None:
    sink = _new_sink()
    with pytest.raises(AuditSinkError):
        sink.append(
            object_kind="evidence_record",
            object_ref="evidence://x/y.json",
            object_digest_sha256="NOT_A_HASH",
            object_size_bytes=64,
            object_media_type="application/json",
            context=_ctx(),
        )


def test_object_ref_violation_refused() -> None:
    sink = _new_sink()
    with pytest.raises(AuditSinkError):
        sink.append(
            object_kind="evidence_record",
            object_ref="http://evil.example/x",  # not evidence:// or object://sha256/
            object_digest_sha256=OBJ_A,
            object_size_bytes=64,
            object_media_type="application/json",
            context=_ctx(),
        )


def test_from_document_rejects_external_delivery_claim() -> None:
    sink = _new_sink()
    _append(sink, OBJ_A, "a1")
    doc = _sealed(sink)
    doc["no_external_delivery"] = False
    with pytest.raises(AuditSinkError):
        AuditSink.from_document(doc)


def test_from_document_rejects_secrets_claim() -> None:
    sink = _new_sink()
    _append(sink, OBJ_A, "a1")
    doc = _sealed(sink)
    doc["no_secrets"] = False
    with pytest.raises(AuditSinkError):
        AuditSink.from_document(doc)


# --------------------------------------------------------------------------- #
# Round-trip / replay equals original
# --------------------------------------------------------------------------- #
def test_round_trip_preserves_events() -> None:
    sink = _new_sink()
    _append(sink, OBJ_A, "a1", decision="allow", outcome="observed")
    _append(sink, OBJ_B, "a2", decision="deny", outcome="denied")
    doc = _sealed(sink)
    restored = AuditSink.from_document(doc)
    assert restored.length == sink.length
    assert restored.events[0].entry.digest() == sink.events[0].entry.digest()
    assert restored.events[1].entry.digest() == sink.events[1].entry.digest()
    assert restored.events[1].context.decision == "deny"
    res = restored.verify()
    assert res["verified"] is True


# --------------------------------------------------------------------------- #
# Schema validation
# --------------------------------------------------------------------------- #
def test_sealed_document_matches_schema() -> None:
    schema = json.loads(SCHEMA_PATH.read_text())
    sink = _new_sink()
    _append(sink, OBJ_A, "a1")
    _append(sink, OBJ_B, "a2")
    doc = _sealed(sink)
    jsonschema.validate(doc, schema)


def test_schema_rejects_unknown_additional_property() -> None:
    schema = json.loads(SCHEMA_PATH.read_text())
    sink = _new_sink()
    _append(sink, OBJ_A, "a1")
    doc = _sealed(sink)
    doc["unexpected_field"] = 1
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(doc, schema)


# --------------------------------------------------------------------------- #
# AST guards: no runtime/secret/external-delivery effect in the module
# --------------------------------------------------------------------------- #
def test_module_has_no_runtime_or_secret_effects() -> None:
    src = (SINK_DIR / "audit_sink.py").read_text()
    tree = ast.parse(src)
    imported_modules = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imported_modules.add(alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                imported_modules.add(node.module.split(".")[0])
    forbidden_modules = {
        "socket",
        "subprocess",
        "requests",
        "httpx",
        "smtplib",
        "boto3",
        "cryptography",
        "secrets",
        "os",
    }
    overlap = forbidden_modules & imported_modules
    assert not overlap, f"module imports forbidden dependency: {overlap}"
    # No forbidden runtime symbols as *code* (not via scanning the guard list text)
    names = {node.id for node in ast.walk(tree) if isinstance(node, ast.Name)}
    attrs = {node.attr for node in ast.walk(tree) if isinstance(node, ast.Attribute)}
    forbidden_symbols = {"socket", "subprocess", "signer", "private_key"}
    bad = (forbidden_symbols & names) | (forbidden_symbols & attrs)
    assert not bad, f"module references forbidden symbol: {bad}"
    # No calls that would open a network/socket/subprocess or persist to disk.
    calls = {node.func.id for node in ast.walk(tree) if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)}
    calls |= {
        node.func.attr
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
    }
    forbidden_calls = {"socket", "subprocess", "Popen", "open", "write", "send", "connect"}
    assert not (forbidden_calls & calls), f"module performs forbidden call: {forbidden_calls & calls}"


def test_module_declares_no_runtime_change_contract() -> None:
    src = (SINK_DIR / "audit_sink.py").read_text()
    assert "NO_RUNTIME_CHANGE" in src
    assert "no_external_delivery" in src
    assert "no_secrets" in src
    assert "no_runtime_effect" in src
