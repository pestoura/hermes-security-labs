"""RTA-002 Stage 2 least-privilege Kali MCP health contract."""

from __future__ import annotations

from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
OP_REGISTRY = ROOT / "platform" / "gateway-protocol" / "operation-registry.yaml"
TOOL_REGISTRY = ROOT / "platform" / "scenario-registry" / "tool-registry.yaml"


def _operation() -> dict:
    document = yaml.safe_load(OP_REGISTRY.read_text(encoding="utf-8"))
    return next(op for op in document["operations"] if op["id"] == "kali.mcp.health.read")


def _tool() -> dict:
    document = yaml.safe_load(TOOL_REGISTRY.read_text(encoding="utf-8"))
    return next(tool for tool in document["tools"] if tool["tool_id"] == "kali-mcp.server-health")


def test_kali_health_is_normal_profile_l0_and_parameterless() -> None:
    document = yaml.safe_load(OP_REGISTRY.read_text(encoding="utf-8"))
    operation = _operation()
    assert "kali.mcp.health.read" in document["profiles"]["normal"]["operations"]
    assert operation["intrusiveness_level"] == "L0"
    assert operation["side_effect"] == "none"
    assert operation["parameters_schema"] == {"type": "object", "additionalProperties": False}
    assert operation["required_capabilities"] == ["kali.mcp.health.read"]
    assert operation["production_status"] == "NOT_RUN"


def test_exact_server_health_tool_maps_to_typed_operation_only() -> None:
    tool = _tool()
    assert tool["mapped_operation"] == "kali.mcp.health.read"
    assert tool["health_check"] == "server_health"
    assert tool["risk"] == "L0"
    assert tool["availability"] == "PRESENT"
    assert tool["scenario_refs"] == []


def test_health_contract_does_not_enable_generic_or_offensive_tools() -> None:
    text = TOOL_REGISTRY.read_text(encoding="utf-8")
    tool = _tool()
    assert "generic_execution" not in tool
    assert "execute_command" not in tool.values()
    assert "nmap_scan" not in tool.values()
    assert "metasploit_run" not in tool.values()
    assert "hydra_attack" not in tool.values()
    assert "server_health" in text


def test_discovery_does_not_promote_kali_health_to_ready() -> None:
    tool = _tool()
    assert tool["availability"] != "READY"
    assert "Stage 2" in tool["availability_basis"]
