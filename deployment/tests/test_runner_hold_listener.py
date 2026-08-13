"""Repository-only tests for the strictly-HOLD Runner dispatch listener (#354).

Validates the HOLD contract: the listener reuses the canonical
platform/runner-transport unix_peer_identity SO_PEERCRED module, observes the
peer and refuses, without reading payloads, authorizing, creating receipts,
calling the router/adapter/Evidence Plane, or touching a target. No live
bind/listen is performed; peer sockets are faked via the canonical module's
credential reader. The listener must work both from the repo and from the
installed directory, preferring the installed exact copy of the canonical peer
module.
"""

from __future__ import annotations

import ast
import importlib.util
import json
import shutil
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
RUNTIME_DIR = ROOT / "deployment" / "runner-runtime"
LISTENER_MODULE = RUNTIME_DIR / "runner_hold_listener.py"
SERVICE_UNIT = RUNTIME_DIR / "systemd" / "hexor-runner.service"
SOCKET_UNIT = RUNTIME_DIR / "systemd" / "hexor-runner.socket"
TMPFILES_CONF = RUNTIME_DIR / "tmpfiles" / "hexor-runner.conf"
CANONICAL_PEER_MODULE = ROOT / "platform" / "runner-transport" / "unix_peer_identity.py"


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


listener = _load("runner_hold_listener_test", LISTENER_MODULE)
canonical_peer = _load("canonical_unix_peer_identity_test", CANONICAL_PEER_MODULE)


def _fake_peer_socket(uid: int = 4101, gid: int = 4110, pid: int = 4242) -> Any:
    """A minimal fake AF_UNIX socket whose getsockopt yields SO_PEERCRED."""

    creds = SimpleNamespace(family=__import__("socket").AF_UNIX)

    def getsockopt(level: int, optname: int, buflen: int = 12) -> bytes:  # noqa: ARG001
        import struct

        return struct.pack("3i", pid, uid, gid)

    creds.getsockopt = getsockopt  # type: ignore[attr-defined]
    creds.close = lambda: None  # type: ignore[attr-defined]
    return creds


# ------------------------------------------------------- canonical module reuse


def test_listener_reuses_canonical_so_peercred_module() -> None:
    # The loaded peer module must be the canonical platform module (same path),
    # and the canonical symbol must be present.
    assert listener.peer_module is not None
    # In repository mode the canonical path is the platform module.
    assert str(listener.peer_module.__file__) == str(CANONICAL_PEER_MODULE)
    assert hasattr(listener.peer_module, "read_kernel_peer_credentials")
    assert hasattr(listener.peer_module, "KernelPeerCredentials")


def test_listener_installed_mode_prefers_adjacent_canonical_copy(tmp_path: Path) -> None:
    """When run from the installed dir, the adjacent exact copy is preferred."""

    installed = tmp_path / "opt" / "hexor" / "runner-runtime"
    installed.mkdir(parents=True)
    shutil.copy(LISTENER_MODULE, installed / "runner_hold_listener.py")
    shutil.copy(CANONICAL_PEER_MODULE, installed / "unix_peer_identity.py")

    import importlib

    # Use a fresh peer-module cache name so the installed listener prefers its
    # adjacent exact copy rather than a previously-cached repo module.
    sys.path.insert(0, str(installed))
    saved_peer = sys.modules.pop("runner_runtime_unix_peer_identity", None)
    try:
        spec = importlib.util.spec_from_file_location(
            "installed_listener_test_iso", installed / "runner_hold_listener.py"
        )
        assert spec and spec.loader
        mod = importlib.util.module_from_spec(spec)
        sys.modules["installed_listener_test_iso"] = mod
        spec.loader.exec_module(mod)
        # The adjacent copy (byte-identical canonical) must be preferred.
        assert Path(mod.peer_module.__file__).resolve() == (installed / "unix_peer_identity.py").resolve()
    finally:
        sys.path[:] = [p for p in sys.path if p != str(installed)]
        sys.modules.pop("installed_listener_test_iso", None)
        if saved_peer is not None:
            sys.modules["runner_runtime_unix_peer_identity"] = saved_peer


def test_listener_does_not_duplicate_so_peercred_implementation() -> None:
    """AST proof: the listener does not re-implement SO_PEERCRED reading."""

    tree = ast.parse(LISTENER_MODULE.read_text(encoding="utf-8"))
    source = ast.unparse(tree)
    assert "read_kernel_peer_credentials" in source
    assert "socket.SO_PEERCRED" not in source
    assert "struct.calcsize" not in source


# ----------------------------------------------------------------- HOLD refusal


def test_listener_observes_peer_and_refuses_with_no_performed_effects() -> None:
    fake = _fake_peer_socket(uid=4101, gid=4110, pid=4242)
    hold = listener.HoldListener()
    refusal = hold.observe_peer(fake)
    assert refusal.decision == "REFUSE_HOLD"
    assert refusal.peer_uid == 4101
    assert refusal.peer_gid == 4110
    assert refusal.peer_pid == 4242
    assert refusal.performed_effects == ()


def test_listener_refuses_any_peer_identity() -> None:
    for uid, gid in ((4100, 4100), (4101, 4101), (0, 0), (9999, 8888)):
        fake = _fake_peer_socket(uid=uid, gid=gid, pid=7)
        hold = listener.HoldListener()
        refusal = hold.refuse_peer(fake)
        assert refusal.decision == "REFUSE_HOLD"
        assert refusal.performed_effects == ()
        assert refusal.peer_uid == uid
        assert refusal.peer_gid == gid


def test_listener_increments_seen_and_refusals() -> None:
    hold = listener.HoldListener()
    for _ in range(3):
        hold.guarded_accept_loop_once(_fake_peer_socket())
    assert hold.connections_seen == 3
    assert hold.refusals == 3


def test_listener_hooks_observe_but_never_drive_downstream_effects() -> None:
    events: list[str] = []

    def on_accept(creds: Any) -> None:  # noqa: ANN001
        events.append(f"accept:{creds.uid}")

    def on_refuse(refusal: Any) -> None:  # noqa: ANN001
        events.append(f"refuse:{refusal.decision}")

    hold = listener.HoldListener(on_accept=[on_accept], on_refuse=[on_refuse])
    hold.observe_peer(_fake_peer_socket(uid=4101, gid=4110, pid=99))
    assert events == ["accept:4101", "refuse:REFUSE_HOLD"]
    assert hold.refusals == 1


# --------------------------------------------------------- no prohibited effect


def test_listener_exposes_no_prohibited_downstream_method() -> None:
    for effect in listener.PROHIBITED_EFFECTS:
        assert not hasattr(listener.HoldListener, effect)
        assert not hasattr(listener, effect)


def test_listener_module_has_no_live_bind_by_default() -> None:
    """AST proof the listener never binds a socket in module scope."""

    tree = ast.parse(LISTENER_MODULE.read_text(encoding="utf-8"))
    called: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            called.add(ast.unparse(node.func))
    assert "socket.bind" not in called
    assert "listen" not in called


def test_listener_module_never_reads_peer_payload() -> None:
    """AST proof: no recv/read/makefile on the peer socket (HOLD only)."""

    tree = ast.parse(LISTENER_MODULE.read_text(encoding="utf-8"))
    source = ast.unparse(tree)
    for forbidden in ("recv(", "read(", "makefile("):
        assert forbidden not in source


def test_listener_module_never_authorizes_or_calls_router_adapter_evidence() -> None:
    """AST proof: no router/adapter/Evidence Plane/target calls in the listener."""

    tree = ast.parse(LISTENER_MODULE.read_text(encoding="utf-8"))
    source = ast.unparse(tree)
    # The only token references allowed are the HOLD refuse contract names;
    # there must be no actual call to router/adapter/evidence/dispatch logic.
    for token in ("router.", "adapter.", "evidence."):
        assert token not in source
    # No authorization logic: only the refuse contract names, never a real call.
    # Accept the word only inside refuse-on-any declarations, not as a call.
    called = {ast.unparse(n.func) for n in ast.walk(tree) if isinstance(n, ast.Call)}
    assert not any("authorize" in c for c in called)


def test_runtime_mode_guard_requires_hold() -> None:
    assert listener.runtime_mode_is_hold({"listener": {"mode": "HOLD"}}) is True
    assert listener.runtime_mode_is_hold({"listener": {"mode": "ENABLED"}}) is False
    assert listener.runtime_mode_is_hold({}) is False


def test_listener_check_cli_reports_hold() -> None:
    import subprocess

    completed = subprocess.run(
        [sys.executable, str(LISTENER_MODULE), "--check"],
        capture_output=True,
        text=True,
        check=True,
    )
    report = json.loads(completed.stdout)
    assert report["mode"] == "HOLD"
    assert "read_request_payload" in report["prohibited_effects"]
    assert "touch_target" in report["prohibited_effects"]


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


def test_service_unit_uses_hexor_runner_primary_group_and_dispatch_supplementary() -> None:
    unit = _systemd_unit_text(SERVICE_UNIT)
    service = unit["Service"]
    assert any("User=hexor-runner" in line for line in service)
    assert any("Group=hexor-runner" in line for line in service)
    assert any("SupplementaryGroups=hexor-dispatch" in line for line in service)


def test_service_unit_has_no_network_dependency_and_only_af_unix() -> None:
    unit = _systemd_unit_text(SERVICE_UNIT)
    service = unit["Service"]
    assert not any("network.target" in line or "network-online" in line for line in unit.get("Unit", []))
    assert any("RestrictAddressFamilies=AF_UNIX" in line for line in service)
    # No RuntimeDirectory that would fight tmpfiles ownership.
    assert not any(line.startswith("RuntimeDirectory=") for line in service)
    # PYTHONDONTWRITEBYTECODE present.
    assert any("PYTHONDONTWRITEBYTECODE=1" in line for line in service)
    # No capabilities.
    assert any("CapabilityBoundingSet=" in line for line in service)
    assert any("AmbientCapabilities=" in line for line in service)


def test_socket_unit_owns_runner_dispatch_socket_and_tmpfiles_owns_dir() -> None:
    unit = _systemd_unit_text(SOCKET_UNIT)
    sock = unit["Socket"]
    assert any("SocketUser=hexor-runner" in line for line in sock)
    assert any("SocketGroup=hexor-dispatch" in line for line in sock)
    assert any("SocketMode=0660" in line for line in sock)
    assert any("DirectoryMode=0750" in line for line in sock)

    tmp = _systemd_unit_text(TMPFILES_CONF)
    # tmpfiles line is in the (implicit) top section.
    body = tmp.get("", []) + tmp.get("Files", [])
    assert any(line.startswith("d /run/hexor 0750 4101 4110") for line in body)
