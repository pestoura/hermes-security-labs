"""Deterministic Kali MCP tool-health states (PRESENT / READY / DEGRADED).

Pure standard library. Parses the canonical Compose and Dockerfile and asserts
the classifier yields READY for the tracked tools, and would yield DEGRADED for
the exact live drift where the read-only rootfs lacks the ``/root/.wpscan``
tmpfs (the WPScan write failure). It also proves the classifier can distinguish
all three observable states and that deferred tools (Nuclei) are ABSENT.
"""

from __future__ import annotations

import importlib.util
import types
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
KALI_DIR = ROOT / "kali-mcp"
COMPOSE = KALI_DIR / "compose.yaml"
DOCKERFILE = KALI_DIR / "Dockerfile"


def _load_module(name: str, path: Path) -> types.ModuleType:
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None, f"cannot load {path}"
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


kali_tool_health = _load_module("kali_tool_health", KALI_DIR / "tool_health.py")


def _canonical_service() -> dict:
    document = yaml.safe_load(COMPOSE.read_text(encoding="utf-8")) or {}
    return (document.get("services") or {}).get("kali-mcp") or {}


def _packages() -> set[str]:
    return kali_tool_health.parse_dockerfile_packages(DOCKERFILE)


def test_core_tools_present_in_canonical_dockerfile() -> None:
    packages = _packages()
    for tool in ("wpscan", "john", "msfconsole", "sqlmap", "hydra"):
        assert kali_tool_health.TOOL_PACKAGES[tool] in packages, (
            f"{tool} package missing from canonical Dockerfile"
        )


def test_canonical_service_classifies_ready() -> None:
    service = _canonical_service()
    packages = _packages()
    states = kali_tool_health.classify_service(service, packages)
    # Every tracked tool that is installed must be READY in the canonical def.
    for tool, state in states.items():
        assert state == "READY", f"{tool} expected READY, got {state}"
    # WPScan specifically must be READY because /root/.wpscan tmpfs is mounted.
    assert states["wpscan"] == "READY"


def test_deferred_nuclei_is_absent() -> None:
    # Nuclei is not installed in the canonical image and no Wave 1 Lane E2
    # scenario/runbook maps Nuclei execution, so it stays deferred (ABSENT).
    service = _canonical_service()
    packages = _packages()
    assert "nuclei" not in packages
    assert kali_tool_health.classify_tool("nuclei", installed=False, service=service) == "ABSENT"


def test_present_state_when_service_absent() -> None:
    # Static-only view (no compose service) yields PRESENT for installed tools.
    assert kali_tool_health.classify_tool("wpscan", installed=True, service=None) == "PRESENT"


def test_live_drift_fixture_classifies_degraded() -> None:
    # Reproduce the observed live drift: read-only rootfs, all tmpfs present
    # EXCEPT /root/.wpscan (and /root/.cache). WPScan must be DEGRADED; tools
    # whose required writable path is still mounted stay READY.
    live_like = {
        "read_only": True,
        "cap_drop": ["all"],
        "security_opt": ["no-new-privileges"],
        "command": ["kali-server-mcp", "--ip", "127.0.0.1", "--port", "5000"],
        "tmpfs": [
            "/run:size=64m,mode=0755",
            "/tmp:size=512m,mode=1777",
            "/root/.msf4:size=256m,mode=0700",
            "/root/.john:size=64m,mode=0700",
            "/data/tmp:size=256m,mode=1777",
        ],
        "volumes": ["./data/results:/data/results", "./data/cache:/data/cache"],
    }
    packages = _packages()
    states = kali_tool_health.classify_service(live_like, packages)
    assert states["wpscan"] == "DEGRADED"
    # john/msfconsole retain their writable tmpfs -> still READY.
    assert states["john"] == "READY"
    assert states["msfconsole"] == "READY"


def test_canonical_service_is_loopback_only_and_not_exposed() -> None:
    service = _canonical_service()
    assert not kali_tool_health._externally_published(service)
    command = " ".join(str(c) for c in service.get("command") or [])
    assert "127.0.0.1" in command
    assert "0.0.0.0" not in command
