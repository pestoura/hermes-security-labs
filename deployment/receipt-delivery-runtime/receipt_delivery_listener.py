#!/usr/bin/env python3
"""Authenticated AF_UNIX receipt-delivery runtime boundary.

Behavior is added incrementally under CHG-HSL-088. The committed runtime remains
fail-closed and carries no execution authority.
"""

from __future__ import annotations

SOCKET_PATH = "/run/hexor/runner-authz.sock"
HEXOR_GATEWAY_UID = 4100
HEXOR_GATEWAY_PRINCIPAL = "hexor.execution-gateway"
HEXOR_RUNNER_UID = 4101
HEXOR_DISPATCH_GID = 4110
MAX_FRAME_BYTES = 65536
READ_TIMEOUT_SECONDS = 2.0

import importlib.util
import sys
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
ADJACENT_PEER_MODULE = HERE / "unix_peer_identity.py"
REPO_PEER_RELATIVE = ("platform", "runner-transport", "unix_peer_identity.py")


class ReceiptDeliveryRuntimeError(RuntimeError):
    """Stable fail-closed runtime boundary error."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


def _canonical_peer_module_path() -> Path:
    if ADJACENT_PEER_MODULE.is_file():
        return ADJACENT_PEER_MODULE
    candidate = HERE
    for _ in range(8):
        probe = candidate.joinpath(*REPO_PEER_RELATIVE)
        if probe.is_file():
            return probe
        if candidate.parent == candidate:
            break
        candidate = candidate.parent
    raise ReceiptDeliveryRuntimeError("PEER_MODULE_MISSING", "canonical peer module unavailable")

def _load_peer_module() -> Any:
    name = "receipt_delivery_runtime_unix_peer_identity"
    existing = sys.modules.get(name)
    if existing is not None:
        return existing
    target = _canonical_peer_module_path()
    spec = importlib.util.spec_from_file_location(name, target)
    if spec is None or spec.loader is None:
        raise ReceiptDeliveryRuntimeError("PEER_MODULE_INVALID", "cannot load canonical peer module")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


peer_module = _load_peer_module()


def authenticate_gateway_peer(peer_socket: Any) -> dict[str, Any]:
    """Derive the canonical control-plane peer exclusively from kernel credentials."""

    try:
        credentials = peer_module.read_kernel_peer_credentials(peer_socket)
    except Exception as exc:  # noqa: BLE001 - transport detail stays internal
        raise ReceiptDeliveryRuntimeError(
            "PEER_CREDENTIALS_UNAVAILABLE", "kernel peer credentials unavailable"
        ) from exc
    if credentials.uid != HEXOR_GATEWAY_UID:
        raise ReceiptDeliveryRuntimeError("PEER_UID_UNAUTHORIZED", "peer uid is not the execution gateway")
    return {"uid": HEXOR_GATEWAY_UID, "principal": HEXOR_GATEWAY_PRINCIPAL}

from dataclasses import dataclass


@dataclass(frozen=True)
class RuntimeOutcome:
    status: str
    code: str
    authorization_ref: str | None = None
    sequence: int | None = None
    duplicate: bool | None = None

    def as_safe_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "code": self.code,
            "authorization_ref": self.authorization_ref,
            "sequence": self.sequence,
            "duplicate": self.duplicate,
        }


import json
from collections.abc import Mapping


def _read_frame(peer_socket: Any) -> dict[str, Any]:
    peer_socket.settimeout(READ_TIMEOUT_SECONDS)
    data = bytearray()
    while True:
        try:
            chunk = peer_socket.recv(4096)
        except TimeoutError as exc:
            raise ReceiptDeliveryRuntimeError("FRAME_TIMEOUT", "frame read timed out") from exc
        if not chunk:
            raise ReceiptDeliveryRuntimeError("FRAME_INCOMPLETE", "frame ended before newline")
        data.extend(chunk)
        if len(data) > MAX_FRAME_BYTES + 1:
            raise ReceiptDeliveryRuntimeError("FRAME_TOO_LARGE", "frame exceeds maximum size")
        newline = data.find(b"\n")
        if newline < 0:
            continue
        if newline > MAX_FRAME_BYTES:
            raise ReceiptDeliveryRuntimeError("FRAME_TOO_LARGE", "frame exceeds maximum size")
        if data[newline + 1 :]:
            raise ReceiptDeliveryRuntimeError("FRAME_TRAILING_DATA", "extra data after frame")
        payload = bytes(data[:newline])
        try:
            decoded = payload.decode("utf-8")
            document = json.loads(decoded)
        except UnicodeDecodeError as exc:
            raise ReceiptDeliveryRuntimeError("FRAME_INVALID_UTF8", "frame is not UTF-8") from exc
        except json.JSONDecodeError as exc:
            raise ReceiptDeliveryRuntimeError("FRAME_INVALID_JSON", "frame is not valid JSON") from exc
        if not isinstance(document, Mapping):
            raise ReceiptDeliveryRuntimeError("FRAME_NOT_OBJECT", "frame root must be an object")
        return dict(document)

def handle_connection(
    peer_socket: Any,
    *,
    delivery: Any | None = None,
    audit_context: Any = None,
) -> RuntimeOutcome:
    """Authenticate, optionally consume one frame, then delegate canonically."""

    peer = authenticate_gateway_peer(peer_socket)
    if delivery is None or getattr(delivery, "enabled", False) is not True:
        return RuntimeOutcome(status="REFUSED", code="DELIVERY_DISABLED")

    try:
        envelope = _read_frame(peer_socket)
    except ReceiptDeliveryRuntimeError as exc:
        return RuntimeOutcome(status="REFUSED", code=exc.code)
    try:
        delivered = delivery.deliver(
            envelope,
            peer=peer,
            audit_context=audit_context,
        )
    except Exception:  # noqa: BLE001 - backend detail must not escape
        return RuntimeOutcome(status="REFUSED", code="DELIVERY_FAILED")

    authorization_ref = getattr(delivered, "authorization_ref", None)
    sequence = getattr(delivered, "sequence", None)
    accepted = getattr(delivered, "accepted", None)
    duplicate = getattr(delivered, "duplicate", None)
    if (
        not isinstance(authorization_ref, str)
        or not authorization_ref
        or len(authorization_ref) > 256
        or isinstance(sequence, bool)
        or not isinstance(sequence, int)
        or sequence < 0
        or accepted is not True
        or not isinstance(duplicate, bool)
    ):
        return RuntimeOutcome(status="REFUSED", code="DELIVERY_RESULT_INVALID")
    return RuntimeOutcome(
        status="ACCEPTED",
        code="RECEIPT_VERIFIED",
        authorization_ref=authorization_ref,
        sequence=sequence,
        duplicate=duplicate,
    )

import argparse
import os
import socket
from collections.abc import Sequence

SYSTEMD_LISTEN_FD = 3


def _systemd_listening_socket(listening_fd: int = SYSTEMD_LISTEN_FD) -> socket.socket:
    listen_pid = os.environ.get("LISTEN_PID")
    listen_fds = os.environ.get("LISTEN_FDS")
    if listen_pid is None or listen_fds is None:
        raise ReceiptDeliveryRuntimeError("SOCKET_ACTIVATION_MISSING", "systemd socket activation missing")
    try:
        pid = int(listen_pid)
        count = int(listen_fds)
    except ValueError as exc:
        raise ReceiptDeliveryRuntimeError("SOCKET_ACTIVATION_INVALID", "invalid systemd socket metadata") from exc
    if pid != os.getpid() or count != 1 or listening_fd != SYSTEMD_LISTEN_FD:
        raise ReceiptDeliveryRuntimeError("SOCKET_ACTIVATION_INVALID", "unexpected systemd socket metadata")
    try:
        accepted = socket.socket(fileno=os.dup(listening_fd))
    except OSError as exc:
        raise ReceiptDeliveryRuntimeError("LISTENER_FD_INVALID", "cannot adopt systemd socket") from exc
    if accepted.family != socket.AF_UNIX or not accepted.getsockopt(socket.SOL_SOCKET, socket.SO_ACCEPTCONN):
        accepted.close()
        raise ReceiptDeliveryRuntimeError("LISTENER_FD_INVALID", "systemd socket is not AF_UNIX listening")
    return accepted

def _serve_peer(peer_socket: socket.socket, *, delivery: Any | None = None) -> RuntimeOutcome:
    try:
        outcome = handle_connection(peer_socket, delivery=delivery)
    except ReceiptDeliveryRuntimeError as exc:
        outcome = RuntimeOutcome(status="REFUSED", code=exc.code)
    payload = json.dumps(outcome.as_safe_dict(), sort_keys=True, separators=(",", ":")).encode("utf-8") + b"\n"
    try:
        peer_socket.sendall(payload)
    except OSError:
        pass
    finally:
        try:
            peer_socket.close()
        except OSError:
            pass
    return outcome


def serve_systemd_socket(
    listening_fd: int = SYSTEMD_LISTEN_FD,
    *,
    delivery: Any | None = None,
    max_connections: int | None = None,
) -> int:
    """Serve the dedicated systemd AF_UNIX socket; default is authenticated HOLD."""

    listener = _systemd_listening_socket(listening_fd)
    handled = 0
    try:
        while max_connections is None or handled < max_connections:
            peer, _ = listener.accept()
            _serve_peer(peer, delivery=delivery)
            handled += 1
    except KeyboardInterrupt:
        pass
    finally:
        listener.close()
    return handled

def safe_check_state() -> dict[str, Any]:
    return {
        "socket_path": SOCKET_PATH,
        "peer_uid": HEXOR_GATEWAY_UID,
        "peer_principal": HEXOR_GATEWAY_PRINCIPAL,
        "mode": "AUTHENTICATED_HOLD",
        "receipt_delivery": "DISABLED",
        "execution_authority": "NONE",
        "promotion_allowed": False,
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0] if __doc__ else "")
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--fd", type=int, default=SYSTEMD_LISTEN_FD)
    args = parser.parse_args(list(argv) if argv is not None else None)
    if args.check:
        print(json.dumps(safe_check_state(), sort_keys=True))
        return 0
    try:
        serve_systemd_socket(args.fd)
    except ReceiptDeliveryRuntimeError as exc:
        print(json.dumps({"status": "REFUSED", "code": exc.code}), file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
