#!/usr/bin/env python3
"""Strictly-HOLD Hexor Execution Gateway runtime boundary (repository-only).

The Execution Gateway is the CLIENT side of the AF_UNIX dispatch boundary. It
runs as the dedicated ``hexor-gateway`` identity (uid/gid 4100), is a member of
the shared ``hexor-dispatch`` group (4110), and connects to the dispatcher
socket at ``/run/hexor/runner-dispatch.sock``.

In HOLD the gateway NEVER sends a Runner payload. It connects to the dispatcher,
observes the (server-side) HOLD refusal read-only, and closes. It never
authorizes an execution, never dispatches a Runner, never creates a receipt,
never calls the router/adapter/Evidence Plane, and never touches a target
(WebGoat/Kali). It simply HOLDS: the default ``ExecStart`` runs a supervision
loop that keeps a real process alive so userns evidence can record its PID.

This is the smallest deployable gateway runtime artifact consistent with the
existing design:

- runs as ``hexor-gateway`` uid/gid 4100; member of ``hexor-dispatch``;
- AF_UNIX client side for ``/run/hexor/runner-dispatch.sock``;
- default HOLD / DISABLED / NOT_RUN / execution_authority none / promotion_allowed false;
- must not send a Runner payload in HOLD;
- no target/network effect;
- suitable for systemd lifecycle and future explicit policy promotion;
- a read-only ``--check`` and a HOLD supervision loop give real process evidence
  without fabricating a helper.

No live deployment, socket bind, user/group creation, trust-store write or
target effect is performed by this module.
"""

from __future__ import annotations

import argparse
import json
import socket
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

# Canonical declared identities (mirror the example descriptor and the runner
# runtime boundary module). These are re-declared locally on purpose: the runtime
# listener must not pull the YAML/trust-binding stack at import time. They must
# stay byte-consistent with runner-identity-descriptor.example.yaml.
HEXOR_GATEWAY_UID = 4100
HEXOR_GATEWAY_GID = 4100
HEXOR_DISPATCH_GID = 4110

HEXOR_GATEWAY_USER = "hexor-gateway"
HEXOR_DISPATCH_GROUP = "hexor-dispatch"

# AF_UNIX dispatcher socket (owned by the runner side: hexor-runner:hexor-dispatch,
# 0660). The gateway is the client connecting to it.
SOCKET_PATH = "/run/hexor/runner-dispatch.sock"

# Canonical installed runtime layout (repository-only; not created here).
INSTALL_DIR = Path("/opt/hexor/execution-gateway")

# Fail-closed policy envelope (never promoted by this boundary).
RUNTIME_STATUS = "NOT_RUN"
EXECUTION_AUTHORITY = "none"
PROMOTION_ALLOWED = False
LISTENER_MODE = "HOLD"

# Prohibited downstream effects for the gateway HOLD boundary.
PROHIBITED_EFFECTS = (
    "send_runner_payload",
    "authorize_execution",
    "create_receipt",
    "call_router",
    "call_adapter",
    "touch_evidence_plane",
    "touch_target",
    "enable_trust_store",
)


class GatewayHoldError(RuntimeError):
    """Stable HOLD gateway error (fail-closed)."""


@dataclass(frozen=True)
class DispatchObservation:
    """Result of a HOLD client observation: connected, refused, nothing sent."""

    connected: bool
    peer_path: str
    decision: str  # always "HOLD_OBSERVED"
    reason: str
    performed_effects: tuple[str, ...]  # always empty in HOLD

    def as_safe_dict(self) -> dict[str, Any]:
        return {
            "connected": self.connected,
            "peer_path": self.peer_path,
            "decision": self.decision,
            "reason": self.reason,
            "performed_effects": list(self.performed_effects),
        }


def gateway_hold_decision() -> dict[str, Any]:
    """Fail-closed HOLD contract summary for the gateway runtime boundary."""

    return {
        "mode": LISTENER_MODE,
        "runtime_status": RUNTIME_STATUS,
        "execution_authority": EXECUTION_AUTHORITY,
        "promotion_allowed": PROMOTION_ALLOWED,
        "role": "client",
        "transport": "unix-peer",
        "identity_source": "linux-so-peercred",
        "socket_path": SOCKET_PATH,
        "identity": {
            "user": HEXOR_GATEWAY_USER,
            "uid": HEXOR_GATEWAY_UID,
            "gid": HEXOR_GATEWAY_GID,
            "dispatch_group": HEXOR_DISPATCH_GROUP,
        },
        "prohibited_effects": list(PROHIBITED_EFFECTS),
    }


def _assert_no_prohibited_effect() -> None:
    """Guard: the gateway module never exposes a prohibited downstream effect."""

    for effect in PROHIBITED_EFFECTS:
        if hasattr(sys.modules[__name__], effect):
            raise GatewayHoldError(f"gateway must not expose prohibited effect: {effect}")


def connect_dispatch_client(
    path: str | Path = SOCKET_PATH,
    *,
    _socket_module: Any = socket,
) -> Any:
    """Open the AF_UNIX client connection to the dispatcher socket.

    This is the ONLY socket operation the gateway performs in HOLD. It connects
    and returns the connected socket. It never sends a Runner payload.
    """

    sock = _socket_module.socket(_socket_module.AF_UNIX, _socket_module.SOCK_STREAM)
    sock.connect(str(path))
    return sock


def observe_dispatch_refusal(
    sock: Any,
    *,
    timeout: float = 2.0,
    peer_path: str = SOCKET_PATH,
) -> DispatchObservation:
    """Read-only observation of the dispatcher's HOLD refusal. Never sends.

    The dispatcher (runner HOLD listener) accepts the connection, observes the
    peer and closes without sending a Runner outcome. The gateway reads only,
    never transmits a payload, and closes. A missing/unavailable dispatcher is
    reported as a non-connected HOLD observation; the gateway still holds.
    """

    connected = True
    try:
        try:
            sock.settimeout(timeout)
        except OSError:
            pass
        # Read-only: observe the dispatcher's HOLD response. recv returns b'' when
        # the dispatcher closes the connection without sending a Runner outcome.
        data = sock.recv(4096)
        _ = data  # observed only; never acted upon, never a Runner payload sent
    except OSError:
        connected = True  # the connect succeeded; the read/close is still HOLD
    finally:
        try:
            sock.close()
        except OSError:
            pass

    return DispatchObservation(
        connected=connected,
        peer_path=peer_path,
        decision="HOLD_OBSERVED",
        reason=(
            "gateway HOLD: connected as client, observed dispatcher refusal, "
            "sent no Runner payload"
        ),
        performed_effects=(),
    )


def hold_supervision_loop(
    path: str | Path = SOCKET_PATH,
    interval: float = 30.0,
    *,
    connect: Callable[[Any], Any] = connect_dispatch_client,
    observe: Callable[[Any], DispatchObservation] = observe_dispatch_refusal,
    sleep: Callable[[float], None] = time.sleep,
    is_stopped: Callable[[], bool] | None = None,
    max_iterations: int | None = None,
) -> int:
    """Hold supervision loop: keeps a real gateway process alive (PID evidence).

    Each iteration attempts a read-only client connection to the dispatcher and
    observes the HOLD refusal. No Runner payload is ever sent. A missing
    dispatcher does not promote the gateway: it is logged and the loop continues
    to hold. The loop is the systemd ``ExecStart``; it provides a real PID for
    userns evidence without fabricating a helper process.
    """

    iterations = 0
    while True:
        if is_stopped is not None and is_stopped():
            break
        try:
            sock = connect(path)
            observe(sock)
        except OSError as exc:
            sys.stderr.write(
                json.dumps({"mode": LISTENER_MODE, "dispatch_connect": "unavailable",
                            "error": str(exc)}) + "\n"
            )
        if max_iterations is not None:
            iterations += 1
            if iterations >= max_iterations:
                break
        try:
            sleep(interval)
        except (KeyboardInterrupt, InterruptedError):
            break
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0] if __doc__ else "")
    parser.add_argument("--socket", default=SOCKET_PATH)
    parser.add_argument("--check", action="store_true", help="validate HOLD invariants and exit (read-only)")
    parser.add_argument("--probe", action="store_true", help="one-shot read-only client connect and observe")
    parser.add_argument("--hold", action="store_true", help="run the HOLD supervision loop (default ExecStart)")
    parser.add_argument("--interval", type=float, default=30.0)
    args = parser.parse_args(list(argv) if argv is not None else None)

    _assert_no_prohibited_effect()

    if args.check:
        print(json.dumps(gateway_hold_decision(), indent=2, sort_keys=True))
        return 0

    if args.probe:
        try:
            obs = observe_dispatch_refusal(connect_dispatch_client(args.socket))
        except OSError as exc:
            print(json.dumps({
                "mode": LISTENER_MODE, "connected": False, "error": str(exc),
                "performed_effects": [],
            }, indent=2, sort_keys=True))
            return 0
        print(json.dumps(obs.as_safe_dict(), indent=2, sort_keys=True))
        return 0

    # Default ExecStart: hold supervision loop (real PID for userns evidence).
    try:
        return hold_supervision_loop(args.socket, args.interval)
    except KeyboardInterrupt:
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
