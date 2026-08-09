"""Validate the canonical Kali MCP connectivity profile and its invariants.

Pure standard library. Asserts the example profile never exposes the MCP
server off-loopback, prefers the STDIO/docker-exec transport, and that the
canonical Compose command binds 127.0.0.1 (cross-check). The example file is a
repository reference only and must not live under ~/.hermes.
"""

from __future__ import annotations

from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
PROFILE = ROOT / "kali-mcp" / "config" / "mcp-connectivity.example.yaml"
COMPOSE = ROOT / "kali-mcp" / "compose.yaml"


def _profile() -> dict:
    return yaml.safe_load(PROFILE.read_text(encoding="utf-8"))


def test_connectivity_profile_path_is_canonical_not_live() -> None:
    # The profile is a repo reference; it must not be wired into live ~/.hermes.
    assert PROFILE.is_relative_to(ROOT)
    assert ".hermes" not in PROFILE.parts


def test_profile_never_binds_off_loopback() -> None:
    profile = _profile()
    # The forbidden set documents the hard rule.
    forbidden = profile.get("forbidden_binds") or []
    assert "0.0.0.0" in forbidden
    # Every transport must bind/publish loopback only when enabled.
    for name, transport in (profile.get("transports") or {}).items():
        if transport.get("enabled") is not True:
            continue
        if "bind" in transport:
            assert transport["bind"] in ("127.0.0.1", "::1"), (
                f"{name} binds off-loopback: {transport['bind']}"
            )
        if "host_publish" in transport:
            assert str(transport["host_publish"]).startswith("127.0.0.1:"), (
                f"{name} publishes off-loopback: {transport['host_publish']}"
            )
    # The example must not contain a literal off-loopback bind token that the
    # YAML parser would accept as a host:port. We only reject '0.0.0.0:' as a
    # bind prefix; documenting the forbidden value by name is allowed.
    text = PROFILE.read_text(encoding="utf-8")
    assert 'bind: "0.0.0.0"' not in text
    assert 'host_publish: "0.0.0.0' not in text


def test_profile_prefers_stdio_docker_exec_transport() -> None:
    transports = _profile()["transports"]
    assert "stdio_docker_exec" in transports
    assert transports["stdio_docker_exec"]["enabled"] is True
    assert transports["stdio_docker_exec"]["host_exposure"] == "none"
    assert transports["stdio_docker_exec"]["command"][:3] == [
        "docker",
        "exec",
        "-i",
    ]


def test_loopback_http_transport_is_loopback_only() -> None:
    transports = _profile()["transports"]
    loopback = transports["loopback_http"]
    assert loopback["host_publish"].startswith("127.0.0.1:")
    assert loopback["bind"] == "127.0.0.1"


def test_canonical_compose_command_is_loopback_only() -> None:
    document = yaml.safe_load(COMPOSE.read_text(encoding="utf-8")) or {}
    service = (document.get("services") or {}).get("kali-mcp") or {}
    command = " ".join(str(c) for c in service.get("command") or [])
    assert "127.0.0.1" in command
    assert "0.0.0.0" not in command
    # No host port publication on the kali-mcp service.
    assert not service.get("ports")
