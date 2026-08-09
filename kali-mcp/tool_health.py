"""Deterministic Kali MCP tool-health classification (canonical, repo-only).

Pure standard library. No Docker, no network, no runtime mutation.

Classifies every tracked Kali tool into exactly one observable state:

* ``ABSENT``  - the tool is not installed in the canonical image (so it is out
                of the operational tool set; e.g. Nuclei, which stays deferred).
* ``PRESENT`` - the tool is installed but no runtime precondition was supplied
                (static-only view; the tool exists but readiness is unverified).
* ``READY``   - installed AND every runtime precondition is satisfied: the
                service binds loopback only, is never published off-host, and any
                required writable state (tmpfs/volume) is mounted when the rootfs
                is read-only.
* ``DEGRADED`` - installed but a runtime precondition is known-broken: the
                service is exposed off-loopback, or the rootfs is read-only yet a
                required writable path is not mounted (exactly the live WPScan
                failure where ``/root/.wpscan`` is not writable).

The function is side-effect free so the same inputs always yield the same state.
Operators can run it as a CLI:

    python kali-mcp/tool_health.py \
        --compose kali-mcp/compose.yaml \
        --dockerfile kali-mcp/Dockerfile
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

import yaml

# Tool -> canonical Debian package that installs it.
TOOL_PACKAGES: dict[str, str] = {
    "wpscan": "wpscan",
    "john": "john",
    "msfconsole": "metasploit-framework",
    "metasploit": "metasploit-framework",
    "sqlmap": "sqlmap",
    "hydra": "hydra",
    "nmap": "nmap",
    "gobuster": "gobuster",
    "nikto": "nikto",
    "ffuf": "ffuf",
    "enum4linux": "enum4linux-ng",
    "enum4linux-ng": "enum4linux-ng",
    "dirb": "dirb",
}

# Tools that require a writable state beyond /tmp when the rootfs is read-only.
REQUIRED_WRITABLE: dict[str, str] = {
    "wpscan": "/root/.wpscan",
    "john": "/root/.john",
    "msfconsole": "/root/.msf4",
    "metasploit": "/root/.msf4",
}

# Tools tracked by the canonical health validator (image-installed set).
CANONICAL_TOOLS: tuple[str, ...] = (
    "wpscan",
    "john",
    "msfconsole",
    "sqlmap",
    "hydra",
    "nmap",
    "gobuster",
    "nikto",
    "ffuf",
    "enum4linux-ng",
    "dirb",
)

VALID_STATES = ("ABSENT", "PRESENT", "READY", "DEGRADED")


def parse_dockerfile_packages(dockerfile: Path) -> set[str]:
    """Return the set of apt packages declared in the canonical Dockerfile."""
    text = dockerfile.read_text(encoding="utf-8")
    packages: set[str] = set()
    # Match the apt-get install block (single or multi-line up to the '\' chain).
    match = re.search(r"apt-get install[^&]*?\\\s*(.*?)(?:&&|$)", text, re.DOTALL)
    block = match.group(0) if match else text
    for token in re.findall(r"[A-Za-z0-9][A-Za-z0-9.+_-]*", block):
        if token in {
            "apt-get", "install", "update", "clean", "rm", "rf",
            "DEBIAN_FRONTEND", "noninteractive", "LANG", "C.UTF-8",
            "LC_ALL", "no-install-recommends", "var", "lib", "apt", "lists",
        }:
            continue
        packages.add(token)
    return packages


def _mounts_path(service: dict, path: str) -> bool:
    for entry in service.get("tmpfs") or []:
        if isinstance(entry, str) and entry.split(":", 1)[0] == path:
            return True
    for volume in service.get("volumes") or []:
        if isinstance(volume, str):
            if volume.rsplit(":", 1)[-1] == path:
                return True
        elif isinstance(volume, dict):
            if volume.get("target") == path:
                return True
    return False


def _externally_published(service: dict) -> bool:
    for port in service.get("ports") or []:
        if isinstance(port, str):
            if not port.startswith("127.0.0.1:"):
                return True
        elif isinstance(port, dict):
            if not str(port.get("published", "")).startswith("127.0.0.1:"):
                return True
    for token in service.get("command") or []:
        if "0.0.0.0" in str(token):
            return True
    return False


def classify_tool(tool: str, *, installed: bool, service: dict | None = None) -> str:
    """Classify one tool into ABSENT / PRESENT / READY / DEGRADED."""
    if not installed:
        return "ABSENT"
    if service is None:
        return "PRESENT"
    if _externally_published(service):
        return "DEGRADED"
    required = REQUIRED_WRITABLE.get(tool)
    if service.get("read_only") is True and required and not _mounts_path(service, required):
        return "DEGRADED"
    return "READY"


def classify_service(service: dict, packages: set[str]) -> dict[str, str]:
    """Return {tool: state} for every canonical tool against one compose service."""
    result: dict[str, str] = {}
    for tool in CANONICAL_TOOLS:
        package = TOOL_PACKAGES[tool]
        installed = package in packages
        result[tool] = classify_tool(tool, installed=installed, service=service)
    return result


def _service_from_compose(compose: Path, name: str = "kali-mcp") -> dict:
    document = yaml.safe_load(compose.read_text(encoding="utf-8")) or {}
    return (document.get("services") or {}).get(name) or {}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Classify Kali MCP tool health.")
    parser.add_argument("--compose", type=Path, default=Path("kali-mcp/compose.yaml"))
    parser.add_argument("--dockerfile", type=Path, default=Path("kali-mcp/Dockerfile"))
    args = parser.parse_args(argv)

    service = _service_from_compose(args.compose)
    packages = parse_dockerfile_packages(args.dockerfile)
    states = classify_service(service, packages)

    print(f"{'TOOL':<16}{'STATE':<12}{'INSTALLED'}")
    print("-" * 40)
    for tool, state in states.items():
        installed = TOOL_PACKAGES[tool] in packages
        print(f"{tool:<16}{state:<12}{'yes' if installed else 'no'}")
    degraded = [t for t, s in states.items() if s == "DEGRADED"]
    if degraded:
        print(f"\nDEGRADED: {', '.join(degraded)}")
        return 1
    print("\nALL TRACKED TOOLS READY")
    return 0


if __name__ == "__main__":
    sys.exit(main())
