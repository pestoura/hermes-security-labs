from __future__ import annotations

import importlib.util
import os
import socket
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
MODULE_PATH = ROOT / "platform" / "runner-transport" / "unix_peer_identity.py"
ADAPTER_PATH = ROOT / "platform" / "runner-transport" / "audit_adapter.py"
POLICY_PATH = ROOT / "platform" / "runner-transport" / "transport-policy.yaml"
CHAIN_ID = "chain_" + "0" * 64
CORRELATION = {
    "campaign_id": "CHG-HSL-045",
    "run_id": "repo-only",
    "step_id": "unix-peer-authn",
    "attempt_id": "attempt-0",
}


def _load_identity():
    spec = importlib.util.spec_from_file_location("runner_unix_peer_identity_adapter_test", MODULE_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _load_adapter():
    spec = importlib.util.spec_from_file_location("runner_transport_audit_adapter_test", ADAPTER_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


identity = _load_identity()
adapter = _load_adapter()


def _enabled_policy(*, uid: int | None = None, gid: int | None = None):
    return {
        "schema_version": "1.0",
        "policy_id": "hexor.runner.transport.identity",
        "state": "ENABLED",
        "default": "deny",
        "runtime_status": "NOT_RUN",
        "execution_authority": "none",
        "modes": {
            "unix-peer": {
                "status": "CANDIDATE",
                "identity_source": "linux-so-peercred",
                "socket_path": "/run/hex0r-test/runner.sock",
                "allowed_peers": [
                    {
                        "principal_id": "hexor.execution-gateway",
                        "uid": os.getuid() if uid is None else uid,
                        "gid": os.getgid() if gid is None else gid,
                        "purpose": "runner-dispatch",
                    }
                ],
            },
            "mtls": {
                "status": "FUTURE",
                "identity_source": "x509-client-certificate",
                "trust_store": "NOT_CONFIGURED",
            },
        },
    }


def _make_adapter():
    return adapter.CanonicalAuditSinkAdapter(chain_id=CHAIN_ID, correlation=CORRELATION)


def test_adapter_satisfies_minimal_audit_sink_protocol() -> None:
    # The authenticator depends only on the minimal AuditSinkProtocol; the
    # canonical adapter must be a valid drop-in audit_sink (duck-typed via
    # record_decision).
    sink = _make_adapter()
    assert hasattr(sink, "record_decision")


def test_authorized_peer_emits_allow_into_canonical_sink_and_verifies() -> None:
    sink = _make_adapter()
    policy = _enabled_policy()
    left, right = socket.socketpair(socket.AF_UNIX, socket.SOCK_STREAM)
    try:
        peer = identity.authenticate_unix_peer(left, policy, audit_sink=sink)
    finally:
        left.close()
        right.close()

    assert sink.length == 1
    document = sink.seal(sealed_at="2026-08-14T00:00:00Z")
    result = adapter.AuditSink.verify_document(document)
    assert result.get("verified") is True
    assert result.get("entry_count") == 1
    entry = document["entries"][0]
    assert entry["object_kind"] == "evidence_record"
    assert entry["object_ref"].startswith("evidence://")
    assert entry["audit"]["decision"] == "ALLOW"
    assert entry["audit"]["principal"] == peer.principal_id == "hexor.execution-gateway"
    # Identity recorded in the canonical sink is exclusively kernel-derived.
    assert entry["audit"]["principal"] == peer.principal_id


def test_unauthorized_peer_emits_deny_into_canonical_sink_and_verifies() -> None:
    sink = _make_adapter()
    policy = _enabled_policy(uid=os.getuid() + 100000)
    left, right = socket.socketpair(socket.AF_UNIX, socket.SOCK_STREAM)
    try:
        with pytest.raises(identity.TransportIdentityError) as exc:
            identity.authenticate_unix_peer(left, policy, audit_sink=sink)
        assert exc.value.code == "PEER_NOT_AUTHORIZED"
    finally:
        left.close()
        right.close()

    assert sink.length == 1
    document = sink.seal(sealed_at="2026-08-14T00:00:00Z")
    result = adapter.AuditSink.verify_document(document)
    assert result.get("verified") is True
    entry = document["entries"][0]
    assert entry["audit"]["decision"] == "DENY"
    assert entry["audit"]["principal"] == "unauthenticated-peer"


def test_disabled_policy_emits_no_authorization_admission_audit_to_canonical_sink() -> None:
    sink = _make_adapter()
    policy = identity.load_policy(str(POLICY_PATH))
    assert policy["state"] == "DISABLED"
    left, right = socket.socketpair(socket.AF_UNIX, socket.SOCK_STREAM)
    try:
        with pytest.raises(identity.TransportIdentityError) as exc:
            identity.authenticate_unix_peer(left, policy, audit_sink=sink)
        assert exc.value.code == "TRANSPORT_DISABLED"
    finally:
        left.close()
        right.close()

    # Fail-closed: a disabled transport produces no authorization-admission audit,
    # so the canonical sink stays empty.
    assert sink.length == 0


def test_caller_cannot_inject_principal_or_uid_gid_through_canonical_adapter() -> None:
    # The authenticator exposes no positional/keyword path for principal/uid/gid;
    # any such injection attempt fails closed, and the kernel-derived identity is
    # the only one that reaches the canonical sink.
    sink = _make_adapter()
    policy = _enabled_policy()
    left, right = socket.socketpair(socket.AF_UNIX, socket.SOCK_STREAM)
    try:
        with pytest.raises(TypeError):
            identity.authenticate_unix_peer(  # type: ignore[call-arg]
                left, policy, audit_sink=sink, uid=os.getuid(), gid=os.getgid()
            )
        with pytest.raises(TypeError):
            identity.authenticate_unix_peer(  # type: ignore[call-arg]
                left, policy, audit_sink=sink, principal_id="hexor.attacker"
            )
    finally:
        left.close()
        right.close()

    # The blocked calls emitted nothing.
    assert sink.length == 0

    # A real (kernel-derived) authorization records only the kernel mapping.
    left2, right2 = socket.socketpair(socket.AF_UNIX, socket.SOCK_STREAM)
    try:
        peer = identity.authenticate_unix_peer(left2, policy, audit_sink=sink)
    finally:
        left2.close()
        right2.close()
    assert peer.peer_uid == os.getuid()
    assert peer.peer_gid == os.getgid()
    document = sink.seal(sealed_at="2026-08-14T00:00:00Z")
    assert document["entries"][0]["audit"]["principal"] == peer.principal_id


def test_tampered_canonical_document_fails_verification() -> None:
    sink = _make_adapter()
    policy = _enabled_policy()
    left, right = socket.socketpair(socket.AF_UNIX, socket.SOCK_STREAM)
    try:
        identity.authenticate_unix_peer(left, policy, audit_sink=sink)
    finally:
        left.close()
        right.close()

    document = sink.seal(sealed_at="2026-08-14T00:00:00Z")
    assert adapter.AuditSink.verify_document(document).get("verified") is True

    # Tamper with the audit envelope's bound payload: break the seal.
    tampered = dict(document)
    tampered["entries"] = [dict(e) for e in document["entries"]]
    tampered["entries"][0] = dict(tampered["entries"][0])
    tampered["entries"][0]["audit"] = dict(tampered["entries"][0]["audit"])
    tampered["entries"][0]["audit"]["decision"] = "DENY"
    result = adapter.AuditSink.verify_document(tampered)
    assert result.get("verified") is False
    assert result.get("reason_code") == "AUDIT_ENVELOPE_TAMPERED"


def test_default_none_behavior_unchanged_without_sink() -> None:
    # With no injected sink the authenticator behaves exactly as before.
    policy = _enabled_policy()
    left, right = socket.socketpair(socket.AF_UNIX, socket.SOCK_STREAM)
    try:
        peer = identity.authenticate_unix_peer(left, policy)
    finally:
        left.close()
        right.close()
    assert peer.principal_id == "hexor.execution-gateway"
    assert peer.evidence_source == "kernel-so-peercred"
