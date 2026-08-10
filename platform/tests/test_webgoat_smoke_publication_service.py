"""Contract tests: WebGoat compose publication ownership vs. smoke.sh lookups.

Scope is repository-only. No container, no Docker daemon and no network is used:
the behavioural test drives ``smoke.sh`` against recording stubs for ``docker``
and ``curl`` placed first on ``PATH``, so every assertion is about which compose
service the script interrogates, not about a live lab.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
ENV_DIR = ROOT / "platform" / "environments" / "web-api" / "webgoat"
COMPOSE = ENV_DIR / "compose.yaml"
SMOKE = ENV_DIR / "scripts" / "smoke.sh"

APP_SERVICE = "webgoat"
PUBLISH_SERVICE = "webgoat-proxy"
PUBLISHED_CONTAINER_PORTS = ("8080", "9090")
IMAGE_DIGEST = "sha256:2775102b8186df1656f8a69cfb7a6bf6c77b43a25fa0accd6d44e6ae04c8d3b7"


def _compose() -> dict:
    value = yaml.safe_load(COMPOSE.read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value


def _smoke_text() -> str:
    return SMOKE.read_text(encoding="utf-8")


def _assignment(name: str) -> str:
    match = re.search(rf'^{name}="([^"]+)"$', _smoke_text(), re.MULTILINE)
    assert match, f"{name} assignment not found in smoke.sh"
    return match.group(1)


# --------------------------------------------------------------------------- #
# Static: compose publication ownership
# --------------------------------------------------------------------------- #


def test_exactly_one_service_publishes_host_ports() -> None:
    services = _compose()["services"]
    publishers = sorted(name for name, spec in services.items() if spec.get("ports"))
    assert publishers == [PUBLISH_SERVICE]


def test_application_service_declares_no_host_ports() -> None:
    assert "ports" not in _compose()["services"][APP_SERVICE]


def test_publisher_publishes_both_container_ports_on_loopback_only() -> None:
    ports = [str(port) for port in _compose()["services"][PUBLISH_SERVICE]["ports"]]
    assert len(ports) == len(PUBLISHED_CONTAINER_PORTS)
    for container_port, mapping in zip(PUBLISHED_CONTAINER_PORTS, ports, strict=True):
        assert mapping.startswith("127.0.0.1:")
        assert mapping.endswith(f":{container_port}")


def test_publisher_host_ports_are_env_overridable_with_committed_defaults() -> None:
    ports = [str(port) for port in _compose()["services"][PUBLISH_SERVICE]["ports"]]
    assert ports[0] == "127.0.0.1:${WEBGOAT_HOST_PORT:-8080}:8080"
    assert ports[1] == "127.0.0.1:${WEBWOLF_HOST_PORT:-9090}:9090"


# --------------------------------------------------------------------------- #
# Static: smoke.sh uses the publishing service for port lookups
# --------------------------------------------------------------------------- #


def test_smoke_declares_both_application_and_publication_services() -> None:
    assert _assignment("SERVICE_NAME") == APP_SERVICE
    assert _assignment("PUBLISH_SERVICE_NAME") == PUBLISH_SERVICE


def test_smoke_port_lookups_target_the_publishing_service_only() -> None:
    lookups = re.findall(r'port "\$\{(\w+)\}" (\d+)', _smoke_text())
    assert lookups == [("PUBLISH_SERVICE_NAME", "8080"), ("PUBLISH_SERVICE_NAME", "9090")]


def test_smoke_port_lookup_service_is_the_compose_publisher() -> None:
    publishers = [
        name for name, spec in _compose()["services"].items() if spec.get("ports")
    ]
    assert _assignment("PUBLISH_SERVICE_NAME") in publishers


def test_smoke_keeps_digest_and_health_on_the_application_container() -> None:
    text = _smoke_text()
    assert 'CONTAINER_ID=$("${COMPOSE[@]}" ps -q "${SERVICE_NAME}"' in text
    assert 'docker inspect "${CONTAINER_ID}" --format \'{{.Config.Image}}\'' in text
    assert IMAGE_DIGEST in text


def test_smoke_preserves_loopback_binding_and_network_checks() -> None:
    text = _smoke_text()
    assert text.count("grep -q '^127\\.0\\.0\\.1:'") == 2
    assert "docker network inspect webgoat-lab" in text
    assert "http://127.0.0.1:${WEBGOAT_PORT}/WebGoat/" in text
    assert "http://127.0.0.1:${WEBWOLF_PORT}/login" in text


def test_smoke_has_no_offensive_or_target_behaviour() -> None:
    text = _smoke_text().lower()
    for token in ("nmap", "sqlmap", "nikto", "hydra", "msfconsole", "exploit"):
        assert token not in text


# --------------------------------------------------------------------------- #
# Behavioural: run smoke.sh against recording stubs (no Docker, no network)
# --------------------------------------------------------------------------- #


DOCKER_STUB = r"""#!/usr/bin/env bash
echo "$@" >> "${STUB_LOG}"
if [ "$1" = "compose" ]; then
  shift
  while [ "$1" = "-p" ] || [ "$1" = "-f" ]; do shift 2; done
  case "$1" in
    ps)
      if [ "$2" = "-q" ]; then echo "cid-$3"; else echo "NAME STATE"; fi
      ;;
    port)
      case "$3" in
        8080) echo "127.0.0.1:${WEBGOAT_HOST_PORT:-8080}" ;;
        9090) echo "127.0.0.1:${WEBWOLF_HOST_PORT:-9090}" ;;
      esac
      ;;
  esac
  exit 0
fi
if [ "$1" = "inspect" ]; then
  case "$*" in
    *Config.Image*) echo "webgoat/webgoat@__DIGEST__" ;;
    *) echo "healthy" ;;
  esac
  exit 0
fi
if [ "$1" = "network" ]; then
  echo "webgoat-lab bridge"
  exit 0
fi
exit 0
"""

CURL_STUB = """#!/usr/bin/env bash
echo "curl $@" >> "${STUB_LOG}"
exit 0
"""


def _stub_env(tmp_path: Path, extra: dict[str, str] | None = None):
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    log = tmp_path / "calls.log"
    (bin_dir / "docker").write_text(
        DOCKER_STUB.replace("__DIGEST__", IMAGE_DIGEST), encoding="utf-8"
    )
    (bin_dir / "curl").write_text(CURL_STUB, encoding="utf-8")
    for name in ("docker", "curl"):
        (bin_dir / name).chmod(0o755)
    env = dict(os.environ)
    env["PATH"] = f"{bin_dir}:{env['PATH']}"
    env["STUB_LOG"] = str(log)
    env.pop("WEBGOAT_HOST_PORT", None)
    env.pop("WEBWOLF_HOST_PORT", None)
    if extra:
        env.update(extra)
    return env, log


@pytest.mark.skipif(shutil.which("bash") is None, reason="bash unavailable")
def test_smoke_run_queries_publisher_for_ports_and_app_for_digest(tmp_path: Path) -> None:
    env, log = _stub_env(tmp_path)
    proc = subprocess.run(
        ["bash", str(SMOKE)], env=env, capture_output=True, text=True, timeout=60
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    calls = log.read_text(encoding="utf-8").splitlines()
    assert any(f"port {PUBLISH_SERVICE} 8080" in call for call in calls)
    assert any(f"port {PUBLISH_SERVICE} 9090" in call for call in calls)
    assert not any(f"port {APP_SERVICE} " in call for call in calls)
    assert any(f"ps -q {APP_SERVICE}" in call for call in calls)
    assert any(f"ps -q {PUBLISH_SERVICE}" in call for call in calls)
    assert "WebGoat mapping: 127.0.0.1:8080" in proc.stdout
    assert "WebWolf mapping: 127.0.0.1:9090" in proc.stdout
    assert "All checks passed" in proc.stdout


@pytest.mark.skipif(shutil.which("bash") is None, reason="bash unavailable")
def test_smoke_run_follows_env_port_overrides(tmp_path: Path) -> None:
    env, log = _stub_env(
        tmp_path, {"WEBGOAT_HOST_PORT": "18080", "WEBWOLF_HOST_PORT": "19090"}
    )
    proc = subprocess.run(
        ["bash", str(SMOKE)], env=env, capture_output=True, text=True, timeout=60
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "WebGoat mapping: 127.0.0.1:18080" in proc.stdout
    assert "WebWolf mapping: 127.0.0.1:19090" in proc.stdout
    calls = log.read_text(encoding="utf-8")
    assert "curl" in calls
    assert "http://127.0.0.1:18080/WebGoat/" in calls
    assert "http://127.0.0.1:19090/login" in calls


@pytest.mark.skipif(shutil.which("bash") is None, reason="bash unavailable")
def test_smoke_fails_closed_when_publisher_container_is_missing(tmp_path: Path) -> None:
    env, _ = _stub_env(tmp_path)
    bin_dir = Path(env["PATH"].split(":")[0])
    (bin_dir / "docker").write_text(
        DOCKER_STUB.replace("__DIGEST__", IMAGE_DIGEST).replace(
            'if [ "$2" = "-q" ]; then echo "cid-$3"',
            'if [ "$2" = "-q" ]; then [ "$3" = "webgoat-proxy" ] || echo "cid-$3"',
        ),
        encoding="utf-8",
    )
    (bin_dir / "docker").chmod(0o755)
    proc = subprocess.run(
        ["bash", str(SMOKE)], env=env, capture_output=True, text=True, timeout=60
    )
    assert proc.returncode == 1
    assert "Publication container not found" in proc.stdout
