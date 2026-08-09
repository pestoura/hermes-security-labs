"""Validate the canonical Kali MCP connectivity profile and its invariants.

Pure standard library plus YAML. Asserts the example profile never exposes the
MCP service off-loopback, prefers the STDIO/docker-exec wrapper, and keeps that
wrapper distinct from the canonical container-local HTTP backend. The example
file is a repository reference only and must not live under ~/.hermes.
"""

from __future__ import annotations

from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
PROFILE = ROOT / "kali-mcp" / "config" / "mcp-connectivity.example.yaml"
COMPOSE = ROOT / "kali-mcp" / "compose.yaml"
SKILL = ROOT / "skills" / "kali-mcp-lab" / "SKILL.md"


def _profile() -> dict:
    return yaml.safe_load(PROFILE.read_text(encoding="utf-8"))


def _compose_service() -> dict:
    document = yaml.safe_load(COMPOSE.read_text(encoding="utf-8")) or {}
    return (document.get("services") or {}).get("kali-mcp") or {}


def test_connectivity_profile_path_is_canonical_not_live() -> None:
    # The profile is a repo reference; it must not be wired into live ~/.hermes.
    assert PROFILE.is_relative_to(ROOT)
    assert ".hermes" not in PROFILE.parts


def test_profile_never_binds_off_loopback() -> None:
    profile = _profile()
    forbidden = profile.get("forbidden_binds") or []
    assert "0.0.0.0" in forbidden
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
    text = PROFILE.read_text(encoding="utf-8")
    assert 'bind: "0.0.0.0"' not in text
    assert 'host_publish: "0.0.0.0' not in text


def test_profile_prefers_stdio_docker_exec_transport() -> None:
    transports = _profile()["transports"]
    assert "stdio_docker_exec" in transports
    assert transports["stdio_docker_exec"]["enabled"] is True
    assert transports["stdio_docker_exec"]["host_exposure"] == "none"
    assert transports["stdio_docker_exec"]["command"] == [
        "docker",
        "exec",
        "-i",
        "hermes-kali-mcp",
        "mcp-server",
    ]


def test_loopback_http_transport_is_disabled_and_loopback_only() -> None:
    transports = _profile()["transports"]
    loopback = transports["loopback_http"]
    assert loopback["enabled"] is False
    assert loopback["host_publish"].startswith("127.0.0.1:")
    assert loopback["bind"] == "127.0.0.1"


def test_canonical_compose_command_is_http_backend_and_loopback_only() -> None:
    service = _compose_service()
    command_parts = [str(c) for c in service.get("command") or []]
    command = " ".join(command_parts)
    assert command_parts[0] == "kali-server-mcp"
    assert "127.0.0.1" in command
    assert "0.0.0.0" not in command
    assert not service.get("ports")


def test_stdio_wrapper_is_distinct_from_http_backend() -> None:
    stdio_command = _profile()["transports"]["stdio_docker_exec"]["command"]
    compose_command = [str(c) for c in _compose_service().get("command") or []]
    assert stdio_command[-1] == "mcp-server"
    assert compose_command[0] == "kali-server-mcp"
    assert stdio_command[-1] != compose_command[0]


def test_skill_uses_connectivity_profile_as_authority() -> None:
    text = SKILL.read_text(encoding="utf-8")
    assert "kali-mcp/config/mcp-connectivity.example.yaml" in text
    assert "docker exec -i hermes-kali-mcp mcp-server" in text
    assert "kali-server-mcp` is the long-running HTTP backend" in text
    assert "`mcp-server` is the FastMCP STDIO wrapper" in text
    assert "Use exclusively `@url:" not in text
    assert "Do not use `tools.include`." not in text
    assert "Keep all 12 Kali MCP tools available." not in text


def test_skill_registration_is_fail_closed_before_tool_enablement() -> None:
    text = SKILL.read_text(encoding="utf-8")
    assert "enabled: false" in text
    assert "__hermes_rta002_no_tool__" in text
    assert "resources: false" in text
    assert "prompts: false" in text
    assert "Do not use `tools.include: []`" in text
    assert "exact literal tool names" in text
    assert "Do not enable all discovered Kali tools by default" in text
