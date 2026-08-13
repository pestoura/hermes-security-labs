#!/usr/bin/env python3
"""Strictly-HOLD Runner dispatch listener (#354, phase A).

Repository-only boundary surface. Under systemd socket activation this listener
accepts an AF_UNIX connection inherited as a listening file descriptor (systemd
passes LISTEN_FDS starting at fd 3; this listener uses that fd exclusively),
derives the kernel SO_PEERCRED of the peer using the **canonical**
platform/runner-transport/unix_peer_identity.py module, records only safe
refusal metadata, and closes the connection immediately.

It performs no further work:
- it never reads the request payload (no recv/read/makefile);
- it never authorizes an execution;
- it never creates a TB1 receipt;
- it never calls the router, adapter or Evidence Plane;
- it never touches a target (WebGoat/Kali);
- it never reads, installs or synthesizes a trust store (phase B is external-only).

The committed transport policy stays DISABLED / NOT_RUN / deny / none, so even
SO_PEERCRED authentication is not performed as authorization -- the listener
simply proves the boundary can observe the peer identity and refuse.

Live serve accepts exclusively a systemd-inherited AF_UNIX listening fd; without
valid socket activation, a non-AF_UNIX fd, or missing SO_PEERCRED support the
listener fails closed. The HoldListener class and PeerRefusal result are pure and
importable for tests without performing any live bind.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import socket
import struct
import sys
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

# Reuse the canonical SO_PEERCRED module. No duplication of that implementation.
# In installed mode the exact copied module sits beside this file; that copy is
# preferred (and is byte-identical to the repository canonical). Otherwise the
# repository platform module is used. Path resolution walks upward so the layout
# is robust to repository/worktree nesting.
_HERE = Path(__file__).resolve().parent
_ADJACENT_PEER_MODULE = _HERE / "unix_peer_identity.py"
_REPO_PEER_RELATIVE = ("platform", "runner-transport", "unix_peer_identity.py")


def _find_repo_peer_module() -> Path | None:
    candidate = _HERE
    for _ in range(8):
        probe = candidate.joinpath(*_REPO_PEER_RELATIVE)
        if probe.exists():
            return probe
        parent = candidate.parent
        if parent == candidate:
            break
        candidate = parent
    return None


def _canonical_peer_module_path() -> Path:
    """Return the preferred canonical peer module path.

    Prefer the installed exact copy (installed mode); fall back to the repository
    platform module discovered by walking upward (repository mode). Both are the
    canonical SO_PEERCRED implementation.
    """

    if _ADJACENT_PEER_MODULE.exists():
        return _ADJACENT_PEER_MODULE
    found = _find_repo_peer_module()
    if found is None:
        raise RuntimeError("cannot locate canonical unix_peer_identity module")
    return found


def _load_canonical_peer_module() -> Any:
    name = "runner_runtime_unix_peer_identity"
    existing = sys.modules.get(name)
    if existing is not None:
        return existing
    target = _canonical_peer_module_path()
    spec = importlib.util.spec_from_file_location(name, target)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load canonical peer module: {target}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


peer_module = _load_canonical_peer_module()

_SYSTEMD_LISTEN_FDS_START = 3
_SYSTEMD_LISTEN_PID_ENV = "LISTEN_PID"
_SYSTEMD_LISTEN_FDS_ENV = "LISTEN_FDS"


# Prohibited downstream effects for the HOLD listener (phase A).
PROHIBITED_EFFECTS = (
    "read_request_payload",
    "authorize_execution",
    "create_receipt",
    "call_router",
    "call_adapter",
    "touch_evidence_plane",
    "touch_target",
    "enable_trust_store",
)

# Canonical declared identities (mirror the example descriptor).
HEXOR_GATEWAY_UID = 4100
HEXOR_GATEWAY_GID = 4100
HEXOR_RUNNER_UID = 4101
HEXOR_RUNNER_GID = 4101
HEXOR_DISPATCH_GID = 4110

SOCKET_PATH = "/run/hexor/runner-dispatch.sock"


class HoldListenerError(RuntimeError):
    """Stable HOLD listener error (fail-closed)."""


@dataclass(frozen=True)
class PeerRefusal:
    """Result of a HOLD decision: the peer was observed and refused, nothing else."""

    peer_pid: int
    peer_uid: int
    peer_gid: int
    decision: str  # always "REFUSE_HOLD"
    reason: str
    performed_effects: tuple[str, ...]  # always empty in HOLD

    def as_safe_dict(self) -> dict[str, Any]:
        return {
            "decision": self.decision,
            "reason": self.reason,
            "peer_pid": self.peer_pid,
            "peer_uid": self.peer_uid,
            "peer_gid": self.peer_gid,
            "performed_effects": list(self.performed_effects),
        }


class HoldListener:
    """Strictly-HOLD Runner dispatch listener.

    Observes the peer credential and refuses. It never reads the request
    payload and never wires to any downstream effect. The only identity action
    is deriving kernel SO_PEERCRED via the canonical module.
    """

    def __init__(
        self,
        socket_path: str = SOCKET_PATH,
        *,
        on_accept: Sequence[Any] | None = None,
        on_refuse: Sequence[Any] | None = None,
    ) -> None:
        self.socket_path = socket_path
        self.on_accept: list[Any] = list(on_accept or [])
        self.on_refuse: list[Any] = list(on_refuse or [])
        self.connections_seen = 0
        self.refusals = 0

    def observe_peer(self, peer_socket: socket.socket) -> PeerRefusal:
        """Derive kernel SO_PEERCRED via the canonical module, then refuse.

        This is the ONLY identity action. No payload is read; no downstream call
        is made; no effect is performed.
        """

        credentials = peer_module.read_kernel_peer_credentials(peer_socket)
        refusal = PeerRefusal(
            peer_pid=credentials.pid,
            peer_uid=credentials.uid,
            peer_gid=credentials.gid,
            decision="REFUSE_HOLD",
            reason="HOLD boundary: peer observed, no payload read, no downstream action",
            performed_effects=(),
        )
        self.connections_seen += 1
        self.refusals += 1
        for hook in self.on_accept:
            hook(credentials)
        for hook in self.on_refuse:
            hook(refusal)
        return refusal

    def refuse_peer(self, peer_socket: socket.socket) -> PeerRefusal:
        """Alias of observe_peer: the listener only ever refuses."""
        return self.observe_peer(peer_socket)

    def guarded_accept_loop_once(self, accepted_socket: socket.socket) -> PeerRefusal:
        """Process exactly one already-accepted socket in HOLD mode.

        The caller is responsible for the actual accept()/lifecycle, so this
        method is trivially testable without binding a real socket. Whatever the
        peer, the result is a refusal with no performed effects.
        """

        try:
            return self.observe_peer(accepted_socket)
        finally:
            try:
                accepted_socket.close()
            except OSError:
                pass

    def refuse_connection(self, accepted_socket: socket.socket) -> PeerRefusal:
        return self.guarded_accept_loop_once(accepted_socket)


def _assert_no_prohibited_effect() -> None:
    """Guard: the listener package never exposes a prohibited effect."""
    for effect in PROHIBITED_EFFECTS:
        if hasattr(sys.modules[__name__], effect):
            raise HoldListenerError(f"listener must not expose prohibited effect: {effect}")


def runtime_mode_is_hold(config: Mapping[str, Any]) -> bool:
    """Fail-closed check: the listener only runs when the contract is HOLD."""
    return bool(config.get("listener", {}).get("mode") == "HOLD")


def _assert_so_peercred_available() -> None:
    """Fail closed when the platform lacks Linux SO_PEERCRED support."""
    if not hasattr(socket, "SO_PEERCRED"):
        raise HoldListenerError(
            "SO_PEERCRED_UNAVAILABLE",
            "platform does not expose Linux SO_PEERCRED",
        )


def _validate_af_unix(listening_fd: int) -> socket.socket:
    """Wrap an inherited fd and fail closed unless it is an AF_UNIX listen socket.

    socket.fromfd trusts the family/type arguments, so the real domain is read
    back from the kernel via SO_DOMAIN before the fd is adopted as a listener.
    """

    try:
        sock = socket.fromfd(listening_fd, socket.AF_UNIX, socket.SOCK_STREAM)
    except OSError as exc:
        raise HoldListenerError(f"LISTENER_FD_INVALID: cannot adopt fd {listening_fd}: {exc}") from exc
    try:
        domain_buf = sock.getsockopt(socket.SOL_SOCKET, socket.SO_DOMAIN, 4)
        real_family = struct.unpack("i", domain_buf)[0]
    except OSError as exc:
        try:
            sock.close()
        except OSError:
            pass
        raise HoldListenerError(f"LISTENER_FD_DOMAIN_UNREADABLE: {exc}") from exc
    if real_family != socket.AF_UNIX:
        try:
            sock.close()
        except OSError:
            pass
        raise HoldListenerError(
            f"LISTENER_FD_NOT_UNIX: inherited fd family is {real_family}, expected AF_UNIX"
        )
    return sock


def _accept_one(accept_sock: socket.socket) -> tuple[PeerRefusal, dict[str, Any]] | None:
    """Accept a single connection, observe SO_PEERCRED, refuse, close.

    Returns the safe refusal record, or None if accept() returned no peer. Never
    reads the request payload; never calls recv/read/makefile.
    """

    try:
        peer, _peer_addr = accept_sock.accept()
    except OSError:
        return None
    try:
        refusal = HoldListener().observe_peer(peer)
        return refusal, refusal.as_safe_dict()
    except Exception as exc:  # noqa: BLE001 - refuse regardless, but record the failure
        sys.stderr.write(json.dumps({"decision": "REFUSE_HOLD", "error": str(exc)}) + "\n")
        return None
    finally:
        try:
            peer.close()
        except OSError:
            pass


def serve_systemd_socket(listening_fd: int = _SYSTEMD_LISTEN_FDS_START) -> int:
    """Serve exclusively an AF_UNIX listening fd inherited from systemd.

    Validates socket activation (LISTEN_PID/LISTEN_FDS), wraps the fd, accepts
    connections one at a time, and refuses each immediately. All connections are
    refused in HOLD. Fails closed on any invalid precondition (missing socket
    activation, non-AF_UNIX fd, or unavailable SO_PEERCRED).
    """

    _assert_so_peercred_available()

    listen_pid = os.environ.get(_SYSTEMD_LISTEN_PID_ENV)
    listen_fds = os.environ.get(_SYSTEMD_LISTEN_FDS_ENV)
    if listen_pid is None or listen_fds is None:
        raise HoldListenerError("SOCKET_ACTIVATION_MISSING: LISTEN_PID/LISTEN_FDS not set")
    try:
        fds_count = int(listen_fds)
    except ValueError as exc:
        raise HoldListenerError(f"SOCKET_ACTIVATION_BAD_FDS: {listen_fds!r}") from exc
    if fds_count < 1:
        raise HoldListenerError("SOCKET_ACTIVATION_NO_FD: no inherited listening fd")
    if listening_fd < _SYSTEMD_LISTEN_FDS_START or listening_fd >= _SYSTEMD_LISTEN_FDS_START + fds_count:
        raise HoldListenerError(
            f"SOCKET_ACTIVATION_FD_OUT_OF_RANGE: fd {listening_fd} not in "
            f"[{_SYSTEMD_LISTEN_FDS_START}, {_SYSTEMD_LISTEN_FDS_START + fds_count})"
        )

    accept_sock = _validate_af_unix(listening_fd)

    refusals = 0
    try:
        while True:
            result = _accept_one(accept_sock)
            if result is None:
                continue
            _refusal, safe_metadata = result
            # Record only safe refusal metadata; never forward a Runner outcome.
            sys.stderr.write(json.dumps(safe_metadata) + "\n")
            refusals += 1
    except KeyboardInterrupt:
        pass
    finally:
        try:
            accept_sock.close()
        except OSError:
            pass
    return refusals


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0] if __doc__ else "")
    parser.add_argument("--socket", default=SOCKET_PATH)
    parser.add_argument("--check", action="store_true", help="validate HOLD invariants and exit")
    parser.add_argument(
        "--fd",
        type=int,
        default=_SYSTEMD_LISTEN_FDS_START,
        help="systemd-inherited listening fd (default 3)",
    )
    args = parser.parse_args(list(argv) if argv is not None else None)

    _assert_no_prohibited_effect()

    if args.check:
        print(json.dumps({"mode": "HOLD", "prohibited_effects": list(PROHIBITED_EFFECTS)}, indent=2))
        return 0

    # Live serve: accept exclusively a systemd-inherited AF_UNIX listening fd.
    try:
        serve_systemd_socket(args.fd)
    except HoldListenerError as exc:
        print(f"HOLD listener refused to start: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
