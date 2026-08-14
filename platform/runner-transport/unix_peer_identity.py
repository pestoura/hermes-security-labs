#!/usr/bin/env python3
"""Fail-closed local Runner transport identity using Linux ``SO_PEERCRED``.

This module authenticates a peer connection. It does not authorize a pentest
operation, parse Runner payload authority, dispatch an adapter or create a TB1
receipt. The only identity input is the kernel-reported peer credential tuple
from an already accepted AF_UNIX socket.

The committed policy is DISABLED and deny-all. Runtime enablement requires an
explicit socket path and exact UID/GID-to-principal mappings.
"""

from __future__ import annotations

import argparse
import re
import socket
import struct
import sys
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol, runtime_checkable

import yaml


@runtime_checkable
class AuditSinkProtocol(Protocol):
    """Minimal audit sink contract for authentication decisions.

    Any sink (the in-memory ``AuthenticatorAuditSink`` test double, the canonical
    evidence-plane adapter, or a future durable backend) implements only
    ``record_decision``. The authenticator depends on THIS protocol, not on a
    concrete sink -- so it does not own a second production audit sink. It emits
    ALLOW/DENY through the injected contract only on the ENABLED path and
    otherwise produces no authorization-admission audit.
    """

    def record_decision(
        self, *, decision: str, reason_code: str, detail: Mapping[str, Any]
    ) -> None:
        ...


class AuthenticatorAuditSink:
    """Repository-only in-memory test double for ``AuditSinkProtocol``.

    This is NOT a production audit sink. It implements the minimal protocol purely
    for repository tests and local inspection: it records exactly the
    authentication decisions made by ``authenticate_unix_peer``. No filesystem,
    network or process I/O occurs here. It is fail-closed relative to the
    transport policy -- consulted only when ENABLED, and a DISABLED policy fails
    closed without producing any authorization-admission audit record. Callers
    cannot influence the emitted identity (principal/uid/gid) because those
    values are derived exclusively from the kernel ``SO_PEERCRED`` tuple inside
    the authenticator.
    """

    def __init__(self) -> None:
        self._records: list[dict[str, Any]] = []

    @property
    def records(self) -> list[dict[str, Any]]:
        # Defensive copy of every stored record so a tampered caller cannot
        # mutate internal audit state through the returned reference.
        return [dict(record) for record in self._records]

    def record_decision(self, *, decision: str, reason_code: str, detail: Mapping[str, Any]) -> None:
        if decision not in {"ALLOW", "DENY"}:
            raise TransportIdentityError(
                "AUDIT_DECISION_INVALID",
                "authenticator audit sink received an unsupported decision",
            )
        if not isinstance(reason_code, str) or not reason_code:
            raise TransportIdentityError(
                "AUDIT_REASON_INVALID",
                "authenticator audit sink requires a non-empty reason code",
            )
        entry = {
            "decision": decision,
            "reason_code": reason_code,
            "evidence_source": detail.get("evidence_source"),
            "peer_uid": detail.get("peer_uid"),
            "peer_gid": detail.get("peer_gid"),
            "principal_id": detail.get("principal_id"),
        }
        # Store a fresh copy so later mutation of the caller's detail mapping
        # cannot alter the persisted audit record.
        self._records.append(dict(entry))


def _emit_decision(
    sink: AuditSinkProtocol | None,
    *,
    decision: str,
    reason_code: str,
    detail: Mapping[str, Any],
) -> None:
    if sink is None:
        return
    sink.record_decision(decision=decision, reason_code=reason_code, detail=detail)

POLICY_PATH = Path(__file__).resolve().parent / "transport-policy.yaml"
PRINCIPAL_RE = re.compile(r"^[a-z0-9][a-z0-9._:-]{2,127}$")
PURPOSE = "runner-dispatch"


class TransportIdentityError(ValueError):
    """Stable fail-closed transport identity error."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class KernelPeerCredentials:
    pid: int
    uid: int
    gid: int


@dataclass(frozen=True)
class AuthenticatedPeer:
    """Identity derived from the accepted transport, not the Runner message."""

    principal_id: str
    purpose: str
    transport: str
    peer_pid: int
    peer_uid: int
    peer_gid: int
    evidence_source: str

    def as_safe_dict(self) -> dict[str, Any]:
        return {
            "principal_id": self.principal_id,
            "purpose": self.purpose,
            "transport": self.transport,
            "peer_uid": self.peer_uid,
            "peer_gid": self.peer_gid,
            "evidence_source": self.evidence_source,
        }


def load_policy(path: Path | str = POLICY_PATH) -> dict[str, Any]:
    policy_path = Path(path)
    try:
        document = yaml.safe_load(policy_path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise TransportIdentityError("POLICY_UNREADABLE", str(exc)) from exc
    except yaml.YAMLError as exc:
        raise TransportIdentityError("POLICY_INVALID", str(exc)) from exc
    if not isinstance(document, dict):
        raise TransportIdentityError("POLICY_INVALID", "policy must be a mapping")
    problems = validate_policy(document)
    if problems:
        raise TransportIdentityError("POLICY_INVALID", "; ".join(problems))
    return document


def validate_policy(document: Any) -> list[str]:
    if not isinstance(document, Mapping):
        return ["transport policy must be an object"]

    problems: list[str] = []
    if document.get("schema_version") != "1.0":
        problems.append("schema_version must be '1.0'")
    if document.get("policy_id") != "hexor.runner.transport.identity":
        problems.append("policy_id must be hexor.runner.transport.identity")
    if document.get("state") not in {"DISABLED", "ENABLED"}:
        problems.append("state must be DISABLED or ENABLED")
    if document.get("default") != "deny":
        problems.append("default must be deny")
    if document.get("execution_authority") != "none":
        problems.append("transport identity must never claim execution authority")
    if document.get("runtime_status") != "NOT_RUN":
        problems.append("runtime_status must remain NOT_RUN before live acceptance")

    modes = document.get("modes")
    if not isinstance(modes, Mapping):
        return problems + ["modes must be an object"]

    unix_peer = modes.get("unix-peer")
    if not isinstance(unix_peer, Mapping):
        return problems + ["modes.unix-peer must be an object"]
    if unix_peer.get("status") != "CANDIDATE":
        problems.append("unix-peer status must remain CANDIDATE")
    if unix_peer.get("identity_source") != "linux-so-peercred":
        problems.append("unix-peer identity_source must be linux-so-peercred")

    socket_path = unix_peer.get("socket_path")
    allowed = unix_peer.get("allowed_peers")
    if not isinstance(allowed, list):
        problems.append("unix-peer allowed_peers must be an array")
        allowed = []

    state = document.get("state")
    if state == "DISABLED":
        if socket_path != "NOT_CONFIGURED":
            problems.append("disabled policy socket_path must be NOT_CONFIGURED")
        if allowed:
            problems.append("disabled policy must not retain allowed peers")
    elif state == "ENABLED":
        if not isinstance(socket_path, str) or not socket_path.startswith("/"):
            problems.append("enabled unix-peer socket_path must be absolute")
        if not allowed:
            problems.append("enabled unix-peer policy requires at least one exact peer mapping")

    seen_principals: set[str] = set()
    seen_credentials: set[tuple[int, int]] = set()
    for position, peer in enumerate(allowed):
        label = f"allowed_peers[{position}]"
        if not isinstance(peer, Mapping):
            problems.append(f"{label}: peer must be an object")
            continue
        if set(peer) != {"principal_id", "uid", "gid", "purpose"}:
            problems.append(f"{label}: exact fields principal_id, uid, gid, purpose are required")
            continue
        principal_id = peer.get("principal_id")
        uid = peer.get("uid")
        gid = peer.get("gid")
        purpose = peer.get("purpose")
        if not isinstance(principal_id, str) or PRINCIPAL_RE.fullmatch(principal_id) is None:
            problems.append(f"{label}: principal_id is invalid")
        elif principal_id in seen_principals:
            problems.append(f"{label}: duplicate principal_id")
        else:
            seen_principals.add(principal_id)
        if isinstance(uid, bool) or not isinstance(uid, int) or uid < 0:
            problems.append(f"{label}: uid must be a non-negative integer")
        if isinstance(gid, bool) or not isinstance(gid, int) or gid < 0:
            problems.append(f"{label}: gid must be a non-negative integer")
        if isinstance(uid, int) and not isinstance(uid, bool) and isinstance(gid, int) and not isinstance(gid, bool):
            credentials = (uid, gid)
            if credentials in seen_credentials:
                problems.append(f"{label}: duplicate UID/GID mapping")
            seen_credentials.add(credentials)
        if purpose != PURPOSE:
            problems.append(f"{label}: purpose must be {PURPOSE}")

    mtls = modes.get("mtls")
    if not isinstance(mtls, Mapping):
        problems.append("modes.mtls must be an object")
    else:
        if mtls.get("status") != "FUTURE":
            problems.append("mTLS transport must remain FUTURE in this lane")
        if mtls.get("identity_source") != "x509-client-certificate":
            problems.append("mTLS identity_source must be x509-client-certificate")
        if mtls.get("trust_store") != "NOT_CONFIGURED":
            problems.append("mTLS trust_store must remain NOT_CONFIGURED")
    return problems


def read_kernel_peer_credentials(peer_socket: socket.socket) -> KernelPeerCredentials:
    """Read PID/UID/GID directly from the Linux kernel for an AF_UNIX peer."""

    if peer_socket.family != socket.AF_UNIX:
        raise TransportIdentityError("TRANSPORT_NOT_UNIX", "peer socket is not AF_UNIX")
    if not hasattr(socket, "SO_PEERCRED"):
        raise TransportIdentityError(
            "SO_PEERCRED_UNAVAILABLE",
            "platform does not expose Linux SO_PEERCRED",
        )
    try:
        raw = peer_socket.getsockopt(
            socket.SOL_SOCKET,
            socket.SO_PEERCRED,
            struct.calcsize("3i"),
        )
        pid, uid, gid = struct.unpack("3i", raw)
    except OSError as exc:
        raise TransportIdentityError("PEER_CREDENTIAL_READ_FAILED", str(exc)) from exc
    if pid <= 0 or uid < 0 or gid < 0:
        raise TransportIdentityError(
            "PEER_CREDENTIAL_INVALID",
            "kernel returned invalid peer credentials",
        )
    return KernelPeerCredentials(pid=pid, uid=uid, gid=gid)


def authenticate_unix_peer(
    peer_socket: socket.socket,
    policy: Mapping[str, Any],
    *,
    audit_sink: AuditSinkProtocol | None = None,
) -> AuthenticatedPeer:
    """Authenticate one accepted Unix peer using exact kernel UID/GID mapping.

    An optional ``audit_sink`` records the authentication decision (allowed or
    denied) but never changes it. The sink is only consulted when the transport
    policy is ENABLED, because a DISABLED policy must fail closed without
    producing any authorization-admission audit record. The authenticated
    identity is derived exclusively from the kernel ``SO_PEERCRED`` tuple; it is
    never taken from the socket object, caller-supplied values or the policy
    principal metadata beyond exact UID/GID equality.
    """

    problems = validate_policy(policy)
    if problems:
        raise TransportIdentityError("POLICY_INVALID", "; ".join(problems))
    if policy.get("state") != "ENABLED":
        # Fail closed first. No authorization-admission audit is emitted for a
        # disabled transport: audit only observes an ENABLED decision path.
        raise TransportIdentityError("TRANSPORT_DISABLED", "transport policy is disabled")

    credentials = read_kernel_peer_credentials(peer_socket)
    unix_peer = policy["modes"]["unix-peer"]
    matches = [
        peer
        for peer in unix_peer["allowed_peers"]
        if peer["uid"] == credentials.uid and peer["gid"] == credentials.gid
    ]
    if not matches:
        _emit_decision(
            audit_sink,
            decision="DENY",
            reason_code="PEER_NOT_AUTHORIZED",
            detail={
                "evidence_source": "kernel-so-peercred",
                "peer_uid": credentials.uid,
                "peer_gid": credentials.gid,
                "principal_id": None,
            },
        )
        raise TransportIdentityError(
            "PEER_NOT_AUTHORIZED",
            "kernel peer UID/GID is not allowlisted",
        )
    if len(matches) != 1:
        _emit_decision(
            audit_sink,
            decision="DENY",
            reason_code="PEER_IDENTITY_AMBIGUOUS",
            detail={
                "evidence_source": "kernel-so-peercred",
                "peer_uid": credentials.uid,
                "peer_gid": credentials.gid,
                "principal_id": None,
            },
        )
        raise TransportIdentityError(
            "PEER_IDENTITY_AMBIGUOUS",
            "kernel peer UID/GID resolves to multiple principals",
        )
    peer = matches[0]
    authenticated = AuthenticatedPeer(
        principal_id=peer["principal_id"],
        purpose=peer["purpose"],
        transport="unix-peer",
        peer_pid=credentials.pid,
        peer_uid=credentials.uid,
        peer_gid=credentials.gid,
        evidence_source="kernel-so-peercred",
    )
    _emit_decision(
        audit_sink,
        decision="ALLOW",
        reason_code="PEER_AUTHORIZED",
        detail={
            "evidence_source": authenticated.evidence_source,
            "peer_uid": authenticated.peer_uid,
            "peer_gid": authenticated.peer_gid,
            "principal_id": authenticated.principal_id,
        },
    )
    return authenticated


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--policy", default=str(POLICY_PATH))
    parser.add_argument("command", choices=("validate",))
    args = parser.parse_args(list(argv) if argv is not None else None)
    try:
        load_policy(args.policy)
    except TransportIdentityError as exc:
        print(f"FAIL {exc.code}: {exc}", file=sys.stderr)
        return 1
    print("OK runner transport identity policy is fail-closed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
