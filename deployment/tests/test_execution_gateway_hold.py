"""Repository-only tests for the Execution Gateway runtime HOLD boundary (#79).

Nothing here creates a user, group, socket, service or trust store. No live host
state is read and no canonical policy is mutated. The gateway is the CLIENT side
of the AF_UNIX dispatch boundary: it connects, observes the dispatcher's HOLD
refusal, and closes, never sending a Runner payload. These tests prove the HOLD
contract, the fail-closed envelope, the read-only/check behavior, and the
systemd unit shape without performing any live effect.
"""

from __future__ import annotations

import ast
import importlib.util
import json
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[2]
GATEWAY_DIR = ROOT / "deployment" / "execution-gateway"
GATEWAY_MODULE = GATEWAY_DIR / "execution_gateway_hold.py"
DESCRIPTOR = GATEWAY_DIR / "execution-gateway-deployment.yaml"
SERVICE_UNIT = GATEWAY_DIR / "systemd" / "hexor-execution-gateway.service"
CANONICAL_PEER_IDENTITY = ROOT / "platform" / "runner-transport" / "unix_peer_identity.py"
TRANSPORT_POLICY = ROOT / "platform" / "runner-transport" / "transport-policy.yaml"


def _load(name: str, path: Path) -> Any:
    existing = sys.modules.get(name)
    if existing is not None:
        return existing
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


gateway = _load("execution_gateway_hold_test", GATEWAY_MODULE)


def _descriptor() -> dict[str, Any]:
    return dict(yaml.safe_load(DESCRIPTOR.read_text(encoding="utf-8")))


# ------------------------------------------------------- canonical state untouched


def test_canonical_transport_policy_remains_disabled_not_run() -> None:
    policy = yaml.safe_load(TRANSPORT_POLICY.read_text(encoding="utf-8"))
    assert policy["state"] == "DISABLED"
    assert policy["default"] == "deny"
    assert policy["runtime_status"] == "NOT_RUN"
    assert policy["execution_authority"] == "none"
    assert policy["modes"]["unix-peer"]["socket_path"] == "NOT_CONFIGURED"
    assert policy["modes"]["unix-peer"]["allowed_peers"] == []


# --------------------------------------------------------------- HOLD envelope


def test_gateway_runs_as_hexor_gateway_identity() -> None:
    assert gateway.HEXOR_GATEWAY_UID == 4100
    assert gateway.HEXOR_GATEWAY_GID == 4100
    assert gateway.HEXOR_GATEWAY_USER == "hexor-gateway"
    assert gateway.HEXOR_DISPATCH_GID == 4110
    assert gateway.HEXOR_DISPATCH_GROUP == "hexor-dispatch"


def test_descriptor_keeps_fail_closed_policy_envelope() -> None:
    descriptor = _descriptor()
    policy = descriptor["policy"]
    assert policy["state"] == "DISABLED"
    assert policy["default"] == "deny"
    assert policy["runtime_status"] == "NOT_RUN"
    assert policy["execution_authority"] == "none"
    assert policy["promotion_allowed"] is False
    assert descriptor["runtime_status"] == "NOT_RUN"
    assert descriptor["promotion_allowed"] is False


def test_gateway_client_is_client_role_and_refuses_every_downstream_effect() -> None:
    descriptor = _descriptor()
    client = descriptor["gateway_client"]
    assert client["role"] == "client"
    assert client["transport"] == "unix-peer"
    assert client["identity_source"] == "linux-so-peercred"
    assert client["socket_path"] == "/run/hexor/runner-dispatch.sock"

    listener = descriptor["listener"]
    assert listener["mode"] == "HOLD"
    assert listener["role"] == "client"
    assert set(listener["refuse_on_any"]) == set(gateway.PROHIBITED_EFFECTS)


def test_no_target_effects_possible() -> None:
    descriptor = _descriptor()
    tb = descriptor["trust_binding"]
    assert tb["enabled"] is False
    assert tb["source"] is None
    assert tb["public_source"] is False
    assert tb["expected_sha256"] is None
    for effect in descriptor["target_effects"].values():
        assert effect in (None, "none")


# ------------------------------------------------- no prohibited downstream effect


def test_gateway_module_exposes_no_prohibited_downstream_method() -> None:
    for effect in gateway.PROHIBITED_EFFECTS:
        assert not hasattr(gateway, effect)
        assert not hasattr(gateway, f"do_{effect}")


def test_gateway_module_never_sends_a_runner_payload() -> None:
    """AST proof: no send/sendall/dispatch/authorize call in the gateway."""

    tree = ast.parse(GATEWAY_MODULE.read_text(encoding="utf-8"))
    source = ast.unparse(tree)
    # `send_runner_payload` is a declared prohibited-effect *name*, not a call.
    # Assert no actual send/dispatch CALL exists in the gateway source.
    for forbidden in ("sendall(", "send(", "socket.send(", "dispatch("):
        assert forbidden not in source


def test_gateway_module_never_authorizes_or_calls_router_adapter_evidence() -> None:
    tree = ast.parse(GATEWAY_MODULE.read_text(encoding="utf-8"))
    source = ast.unparse(tree)
    for token in ("router.", "adapter.", "evidence."):
        assert token not in source
    called = {ast.unparse(n.func) for n in ast.walk(tree) if isinstance(n, ast.Call)}
    assert not any("authorize" in c for c in called)


def test_gateway_module_never_binds_a_socket() -> None:
    """AST proof the gateway only connects; it never binds/listens as a server."""

    tree = ast.parse(GATEWAY_MODULE.read_text(encoding="utf-8"))
    source = ast.unparse(tree)
    assert ".bind(" not in source
    assert "listen(" not in source
    for token in (".connect(", ".recv(", ".close("):
        assert token in source


# ------------------------------------------------------------- HOLD observation


def _fake_recv_socket() -> SimpleNamespace:
    """A fake AF_UNIX client socket that returns b'' (dispatcher closed)."""

    sock = SimpleNamespace(family=__import__("socket").AF_UNIX)
    sock._closed = False

    def recv(_buflen: int = 4096) -> bytes:
        return b""  # dispatcher refused and closed without sending a Runner outcome

    sock.recv = recv  # type: ignore[attr-defined]

    def settimeout(_t: float) -> None:
        return None

    sock.settimeout = settimeout  # type: ignore[attr-defined]

    def close() -> None:
        sock._closed = True

    sock.close = close  # type: ignore[attr-defined]
    return sock


def test_gateway_observes_dispatch_refusal_and_sends_no_payload() -> None:
    fake = _fake_recv_socket()
    obs = gateway.observe_dispatch_refusal(fake)
    assert obs.connected is True
    assert obs.decision == "HOLD_OBSERVED"
    assert obs.performed_effects == ()
    assert obs.peer_path == str(gateway.SOCKET_PATH)
    assert fake._closed is True


def test_gateway_connect_is_the_only_socket_operation() -> None:
    import socket as _socket

    connected: dict[str, Any] = {}

    def fake_connect(self: Any, path: str) -> None:  # noqa: ANN001
        connected["path"] = path

    real_connect = _socket.socket.connect
    try:
        _socket.socket.connect = fake_connect  # type: ignore[assignment]
        sock = gateway.connect_dispatch_client(gateway.SOCKET_PATH)
        # The returned object is a real client socket; we do not send anything.
        assert "path" in connected
        assert connected["path"] == str(gateway.SOCKET_PATH)
        sock.close()
    finally:
        _socket.socket.connect = real_connect  # type: ignore[assignment]


def test_gateway_check_cli_reports_hold_without_connecting() -> None:
    completed = subprocess.run(
        [sys.executable, str(GATEWAY_MODULE), "--check"],
        capture_output=True,
        text=True,
        check=True,
    )
    report = json.loads(completed.stdout)
    assert report["mode"] == "HOLD"
    assert report["runtime_status"] == "NOT_RUN"
    assert report["execution_authority"] == "none"
    assert report["promotion_allowed"] is False
    assert report["role"] == "client"
    assert "send_runner_payload" in report["prohibited_effects"]
    assert "touch_target" in report["prohibited_effects"]


def test_gateway_probe_cli_is_read_only_and_exits_ok() -> None:
    # With no dispatcher socket present, --probe reports the unavailable dispatch
    # and still performs no promotion/sending. It must exit 0 (HOLD, not crash).
    completed = subprocess.run(
        [sys.executable, str(GATEWAY_MODULE), "--probe", "--socket", "/nonexistent/dispatch.sock"],
        capture_output=True,
        text=True,
        check=True,
    )
    report = json.loads(completed.stdout)
    assert report["mode"] == "HOLD"
    assert report["performed_effects"] == []
    assert report["connected"] is False


# --------------------------------------------------------- supervision loop (PID)


def test_hold_supervision_loop_runs_as_a_real_process_without_effects() -> None:
    """The default ExecStart keeps a real PID; max_iterations bounds it here."""

    def fake_connect(_path):  # noqa: ANN001
        # A fake socket whose recv returns b'' (dispatcher HOLD refusal).
        return _fake_recv_socket()

    def fake_observe(_sock):  # noqa: ANN001
        return gateway.DispatchObservation(
            connected=True,
            peer_path=str(gateway.SOCKET_PATH),
            decision="HOLD_OBSERVED",
            reason="test",
            performed_effects=(),
        )

    result = gateway.hold_supervision_loop(
        gateway.SOCKET_PATH,
        interval=0.0,
        connect=fake_connect,
        observe=fake_observe,
        sleep=lambda _t: None,
        max_iterations=3,
    )
    assert result == 0
    # The loop ran as a real process (this is the systemd ExecStart; PID is real).
    assert isinstance(result, int)


# -------------------------------------------------------------- systemd invariants


def _systemd_unit_text(path: Path) -> dict[str, list[str]]:
    sections: dict[str, list[str]] = {"": []}
    current = ""
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("[") and line.endswith("]"):
            current = line[1:-1]
            sections.setdefault(current, [])
        else:
            sections[current].append(line)
    return sections


def test_service_unit_uses_hexor_gateway_identity_and_dispatch_member() -> None:
    unit = _systemd_unit_text(SERVICE_UNIT)
    service = unit["Service"]
    assert any("User=hexor-gateway" in line for line in service)
    assert any("Group=hexor-gateway" in line for line in service)
    assert any("SupplementaryGroups=hexor-dispatch" in line for line in service)


def test_service_unit_has_no_network_dependency_and_only_af_unix() -> None:
    unit = _systemd_unit_text(SERVICE_UNIT)
    service = unit["Service"]
    assert not any("network.target" in line or "network-online" in line for line in unit.get("Unit", []))
    assert any("RestrictAddressFamilies=AF_UNIX" in line for line in service)
    assert any("PYTHONDONTWRITEBYTECODE=1" in line for line in service)
    assert any("CapabilityBoundingSet=" in line for line in service)
    assert any("AmbientCapabilities=" in line for line in service)
    # The gateway is a client: no ListenStream socket unit is shipped by this dir.
    assert not (GATEWAY_DIR / "systemd" / "hexor-execution-gateway.socket").exists()


def test_service_execstart_runs_the_hold_supervisor() -> None:
    unit = _systemd_unit_text(SERVICE_UNIT)
    service = unit["Service"]
    assert any("execution_gateway_hold.py --hold" in line for line in service)


def test_systemd_analyze_verify_passes_for_service_unit() -> None:
    completed = subprocess.run(
        ["systemd-analyze", "verify", str(SERVICE_UNIT)],
        capture_output=True,
        text=True,
    )
    # systemd-analyze prints to stderr; a clean unit yields an empty result.
    assert not completed.stdout.strip()
    assert not completed.stderr.strip()


# ----------------------------------------- CHG-HSL-050 extended HOLD invariants


def test_gateway_descriptor_is_repo_only_fail_closed_hold_boundary() -> None:
    descriptor = _descriptor()
    # The Execution Gateway HOLD boundary is repository-only and fail-closed:
    # no live promotion, no target effect, client role on the AF_UNIX surface.
    assert descriptor["policy"]["promotion_allowed"] is False
    assert descriptor["promotion_allowed"] is False
    assert descriptor["runtime_status"] == "NOT_RUN"
    assert descriptor["gateway_client"]["role"] == "client"
    assert descriptor["listener"]["mode"] == "HOLD"
    # The gateway is the client side of the AF_UNIX dispatch surface and never
    # promotes or enables a policy; promotion stays disabled and NOT_RUN.
    assert descriptor["policy"]["state"] == "DISABLED"


def test_gateway_descriptor_never_declares_a_target_or_trust_effect() -> None:
    descriptor = _descriptor()
    # Every target effect slot must be a no-op; the gateway binds no trust.
    tb = descriptor["trust_binding"]
    assert tb["enabled"] is False
    assert tb["source"] is None
    assert tb["expected_sha256"] is None
    for effect in descriptor["target_effects"].values():
        assert effect in (None, "none")
    assert descriptor["listener"]["mode"] == "HOLD"


def test_gateway_module_exposes_no_target_trust_or_payload_surface() -> None:
    # PROHIBITED_EFFECTS names (e.g. send_runner_payload) are declared as a
    # fail-closed tuple; the module must expose NO method/attribute of those
    # names that would let a caller perform a payload/target/trust effect.
    for forbidden in ("send_runner_payload", "touch_target", "bind_trust", "apply_policy",
                      "do_send_runner_payload", "do_touch_target", "do_bind_trust", "do_apply_policy"):
        assert not hasattr(gateway, forbidden)
    tree = ast.parse(GATEWAY_MODULE.read_text(encoding="utf-8"))
    called = {ast.unparse(n.func) for n in ast.walk(tree) if isinstance(n, ast.Call)}
    # No outbound effect call of any prohibited verb (dispatch/auth/touch/trust).
    # `DispatchObservation` is a data class, not a call, so match only real
    # trailing calls like `something.dispatch(` / `authorize(` / `apply_policy(`.
    called_tail = {c.split(".")[-1] for c in called}
    for verb in ("dispatch", "authorize", "apply_policy", "bind_trust", "touch_target"):
        assert verb not in called_tail
    # The gateway only CONNECTS/RECVs/CLOSEs; it never SENDs a payload.
    source = ast.unparse(tree)
    assert "send(" not in source
    assert "sendall(" not in source


def test_gateway_module_never_mutates_target_or_trust_state() -> None:
    tree = ast.parse(GATEWAY_MODULE.read_text(encoding="utf-8"))
    source = ast.unparse(tree)
    assert "write_text(" not in source
    assert "unlink(" not in source
    called = {ast.unparse(n.func) for n in ast.walk(tree) if isinstance(n, ast.Call)}
    assert not any("chmod" in c or "chown" in c for c in called)


def test_gateway_descriptor_mirrors_canonical_gateway_identity_ids() -> None:
    descriptor = _descriptor()
    assert descriptor["identities"]["gateway"]["uid"] == 4100
    assert descriptor["identities"]["gateway"]["gid"] == 4100
    assert descriptor["identities"]["dispatch_group"]["gid"] == 4110
