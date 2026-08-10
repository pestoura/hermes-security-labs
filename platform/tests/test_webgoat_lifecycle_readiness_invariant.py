"""Lifecycle readiness invariant for the WebGoat environment (repo-only).

Live observation (SHA a91a325, WebGoat lab): ``start.sh``, the readiness probes
and ``smoke.sh`` all passed, but ``reset.sh --yes`` recreated the services,
waited **only** for the ``webgoat`` application healthcheck and then invoked
``smoke.sh`` while ``webgoat-proxy`` was still ``starting`` (proxy
``start_period: 60s``). Smoke failed closed with
``[smoke] Publication container not healthy: starting``. ``start.sh`` had the
same single-service wait but hid the defect because no smoke follows it.

These tests are repository-only: no Docker daemon, no container and no network.
``start.sh`` and ``reset.sh`` are driven against recording stubs for ``docker``
and ``ss`` placed first on ``PATH``, so every assertion is about which services
the lifecycle gates on and whether it fails closed.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
ENV_DIR = ROOT / "platform" / "environments" / "web-api" / "webgoat"
COMPOSE = ENV_DIR / "compose.yaml"
SCRIPTS = ENV_DIR / "scripts"
START = SCRIPTS / "start.sh"
RESET = SCRIPTS / "reset.sh"
HEALTH_LIB = SCRIPTS / "lib-health.sh"

APP_SERVICE = "webgoat"
PUBLISH_SERVICE = "webgoat-proxy"
IMAGE_DIGEST = "sha256:2775102b8186df1656f8a69cfb7a6bf6c77b43a25fa0accd6d44e6ae04c8d3b7"

# Health of a service is driven by STUB_HEALTH_<service with - replaced by _>.
# The literal "absent" means `docker compose ps -q <service>` returns nothing.
DOCKER_STUB = r"""#!/usr/bin/env bash
echo "$@" >> "${STUB_LOG}"

health_for() {
  local var="STUB_HEALTH_${1//-/_}"
  echo "${!var:-healthy}"
}

if [ "$1" = "compose" ]; then
  shift
  while [ "$1" = "-p" ] || [ "$1" = "-f" ]; do shift 2; done
  case "$1" in
    ps)
      if [ "$2" = "-q" ]; then
        [ "$(health_for "$3")" = "absent" ] || echo "cid-$3"
      else
        echo "NAME STATE"
      fi
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
    *State.Health.Status*)
      cid="${@: -1}"
      health_for "${cid#cid-}"
      ;;
    *) echo "healthy" ;;
  esac
  exit 0
fi

if [ "$1" = "image" ]; then
  exit 0
fi

if [ "$1" = "network" ]; then
  echo "webgoat-lab bridge"
  exit 0
fi
exit 0
"""

SS_STUB = """#!/usr/bin/env bash
echo "ss $@" >> "${STUB_LOG}"
exit 0
"""

CURL_STUB = """#!/usr/bin/env bash
echo "curl $@" >> "${STUB_LOG}"
exit 0
"""


def _stub_env(tmp_path: Path, extra: dict[str, str] | None = None):
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir(parents=True)
    log = tmp_path / "calls.log"
    (bin_dir / "docker").write_text(
        DOCKER_STUB.replace("__DIGEST__", IMAGE_DIGEST), encoding="utf-8"
    )
    (bin_dir / "ss").write_text(SS_STUB, encoding="utf-8")
    (bin_dir / "curl").write_text(CURL_STUB, encoding="utf-8")
    for name in ("docker", "ss", "curl"):
        (bin_dir / name).chmod(0o755)
    env = dict(os.environ)
    env["PATH"] = f"{bin_dir}:{env['PATH']}"
    env["STUB_LOG"] = str(log)
    env["HEALTH_POLL_INTERVAL"] = "1"
    env["WEBGOAT_HEALTH_TIMEOUT_SECONDS"] = "4"
    for name in ("WEBGOAT_HOST_PORT", "WEBWOLF_HOST_PORT"):
        env.pop(name, None)
    if extra:
        env.update(extra)
    return env, log


def _run(script: Path, env: dict[str, str]) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["bash", str(script)], env=env, capture_output=True, text=True, timeout=120
    )


requires_bash = pytest.mark.skipif(shutil.which("bash") is None, reason="bash unavailable")


# --------------------------------------------------------------------------- #
# Static: both entrypoints share one two-service readiness invariant
# --------------------------------------------------------------------------- #


def test_publication_service_is_the_only_compose_publisher() -> None:
    services = yaml.safe_load(COMPOSE.read_text(encoding="utf-8"))["services"]
    publishers = sorted(name for name, spec in services.items() if spec.get("ports"))
    assert publishers == [PUBLISH_SERVICE]


def test_compose_healthchecks_are_preserved_for_both_services() -> None:
    services = yaml.safe_load(COMPOSE.read_text(encoding="utf-8"))["services"]
    for name in (APP_SERVICE, PUBLISH_SERVICE):
        healthcheck = services[name]["healthcheck"]
        assert healthcheck["test"]
        assert healthcheck["retries"] == 12
        assert healthcheck["start_period"] == "60s"


@pytest.mark.parametrize("script", [START, RESET], ids=["start", "reset"])
def test_lifecycle_scripts_declare_both_services(script: Path) -> None:
    text = script.read_text(encoding="utf-8")
    assert f'SERVICE_NAME="{APP_SERVICE}"' in text
    assert f'PUBLISH_SERVICE_NAME="{PUBLISH_SERVICE}"' in text


@pytest.mark.parametrize("script", [START, RESET], ids=["start", "reset"])
def test_lifecycle_scripts_gate_on_the_shared_bounded_helper(script: Path) -> None:
    text = script.read_text(encoding="utf-8")
    assert 'source "${SCRIPT_DIR}/lib-health.sh"' in text
    assert (
        'wait_for_services_healthy "'
        in text
    )
    assert '"${SERVICE_NAME}" "${PUBLISH_SERVICE_NAME}"' in text
    assert 'HEALTH_TIMEOUT_SECONDS="${WEBGOAT_HEALTH_TIMEOUT_SECONDS:-300}"' in text


def test_health_gate_is_not_replaced_by_a_sleep_only_wait() -> None:
    text = HEALTH_LIB.read_text(encoding="utf-8")
    assert "docker inspect -f \"{{.State.Health.Status}}\"" in text
    assert "healthy" in text
    for script in (START, RESET):
        body = script.read_text(encoding="utf-8")
        assert "sleep " not in body


def test_env_port_overrides_are_preserved_in_start() -> None:
    text = START.read_text(encoding="utf-8")
    assert 'WEBGOAT_HOST_PORT="${WEBGOAT_HOST_PORT:-8080}"' in text
    assert 'WEBWOLF_HOST_PORT="${WEBWOLF_HOST_PORT:-9090}"' in text


def test_existing_log_diagnostics_are_preserved() -> None:
    for script, label in ((START, "start"), (RESET, "reset")):
        text = script.read_text(encoding="utf-8")
        assert f'echo "[{label}] Timeout or failure waiting for healthy"' in text
        assert '"${COMPOSE[@]}" logs --tail 50' in text


def test_helper_introduces_no_generic_command_execution() -> None:
    text = HEALTH_LIB.read_text(encoding="utf-8")
    for token in ("eval", "$(\"$", "bash -c", "sh -c", "nmap", "curl"):
        assert token not in text


# --------------------------------------------------------------------------- #
# Behavioural: the observed race and the fail-closed envelope
# --------------------------------------------------------------------------- #


@requires_bash
def test_reset_does_not_reach_smoke_while_publication_is_starting(tmp_path: Path) -> None:
    """Reproduces the live observation: app healthy + proxy starting."""
    env, _ = _stub_env(
        tmp_path,
        {"STUB_HEALTH_webgoat": "healthy", "STUB_HEALTH_webgoat_proxy": "starting"},
    )
    proc = _run(RESET, env)
    assert proc.returncode != 0
    combined = proc.stdout + proc.stderr
    assert "[smoke]" not in combined
    assert "Running smoke" not in combined
    assert "webgoat-proxy=starting" in combined
    assert "[reset] Timeout or failure waiting for healthy" in combined


@requires_bash
def test_start_does_not_return_success_while_publication_is_starting(tmp_path: Path) -> None:
    env, _ = _stub_env(
        tmp_path,
        {"STUB_HEALTH_webgoat": "healthy", "STUB_HEALTH_webgoat_proxy": "starting"},
    )
    proc = _run(START, env)
    assert proc.returncode != 0
    combined = proc.stdout + proc.stderr
    assert "WebGoat is healthy" not in combined
    assert "webgoat-proxy=starting" in combined


@requires_bash
def test_reset_proceeds_to_smoke_when_both_services_are_healthy(tmp_path: Path) -> None:
    env, log = _stub_env(tmp_path)
    proc = _run(RESET, env)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "[reset] Running smoke..." in proc.stdout
    assert "[smoke] All checks passed" in proc.stdout
    assert "[reset] Lab reset complete (Kali remains disconnected)" in proc.stdout
    calls = log.read_text(encoding="utf-8")
    assert f"ps -q {APP_SERVICE}" in calls
    assert f"ps -q {PUBLISH_SERVICE}" in calls


@requires_bash
def test_start_succeeds_when_both_services_are_healthy(tmp_path: Path) -> None:
    env, log = _stub_env(tmp_path)
    proc = _run(START, env)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "[start] WebGoat is healthy" in proc.stdout
    calls = log.read_text(encoding="utf-8")
    assert f"ps -q {PUBLISH_SERVICE}" in calls


@requires_bash
@pytest.mark.parametrize("script,label", [(START, "start"), (RESET, "reset")], ids=["start", "reset"])
@pytest.mark.parametrize(
    "health",
    ["unhealthy", "absent", "none", "starting"],
    ids=["unhealthy", "missing", "nohealth", "timeout"],
)
def test_publication_failure_modes_fail_closed(
    tmp_path: Path, script: Path, label: str, health: str
) -> None:
    env, _ = _stub_env(
        tmp_path,
        {"STUB_HEALTH_webgoat": "healthy", "STUB_HEALTH_webgoat_proxy": health},
    )
    proc = _run(script, env)
    assert proc.returncode != 0
    combined = proc.stdout + proc.stderr
    assert f"[{label}] Timeout or failure waiting for healthy" in combined
    assert "[smoke]" not in combined


@requires_bash
@pytest.mark.parametrize("script,label", [(START, "start"), (RESET, "reset")], ids=["start", "reset"])
@pytest.mark.parametrize(
    "health", ["unhealthy", "absent", "starting"], ids=["unhealthy", "missing", "timeout"]
)
def test_application_failure_modes_fail_closed(
    tmp_path: Path, script: Path, label: str, health: str
) -> None:
    env, _ = _stub_env(
        tmp_path,
        {"STUB_HEALTH_webgoat": health, "STUB_HEALTH_webgoat_proxy": "healthy"},
    )
    proc = _run(script, env)
    assert proc.returncode != 0
    assert f"[{label}] Timeout or failure waiting for healthy" in proc.stdout + proc.stderr


@requires_bash
def test_health_gate_is_bounded_and_returns_before_the_test_timeout(tmp_path: Path) -> None:
    env, _ = _stub_env(
        tmp_path,
        {
            "STUB_HEALTH_webgoat_proxy": "starting",
            "WEBGOAT_HEALTH_TIMEOUT_SECONDS": "3",
        },
    )
    proc = subprocess.run(
        ["bash", str(START)], env=env, capture_output=True, text=True, timeout=60
    )
    assert proc.returncode != 0
    assert "Timeout after 3s waiting for healthy" in proc.stdout + proc.stderr


@requires_bash
def test_invalid_timeout_fails_closed(tmp_path: Path) -> None:
    env, _ = _stub_env(tmp_path, {"WEBGOAT_HEALTH_TIMEOUT_SECONDS": "0"})
    proc = _run(START, env)
    assert proc.returncode != 0
    assert "Invalid health timeout: 0" in proc.stdout + proc.stderr


@requires_bash
def test_start_follows_env_port_overrides_for_the_availability_check(tmp_path: Path) -> None:
    env, log = _stub_env(
        tmp_path, {"WEBGOAT_HOST_PORT": "18080", "WEBWOLF_HOST_PORT": "19090"}
    )
    proc = _run(START, env)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    calls = log.read_text(encoding="utf-8")
    assert "sport = :18080" in calls
    assert "sport = :19090" in calls


@requires_bash
def test_start_and_reset_share_the_same_readiness_invariant(tmp_path: Path) -> None:
    """Both entrypoints must gate on exactly the same service set."""
    observed = {}
    for name, script in (("start", START), ("reset", RESET)):
        env, log = _stub_env(tmp_path / name)
        proc = _run(script, env)
        assert proc.returncode == 0, proc.stdout + proc.stderr
        gated = {
            line.split("ps -q ")[1].strip()
            for line in log.read_text(encoding="utf-8").splitlines()
            if "ps -q " in line
        }
        observed[name] = gated
    assert {APP_SERVICE, PUBLISH_SERVICE} <= observed["start"]
    assert {APP_SERVICE, PUBLISH_SERVICE} <= observed["reset"]
