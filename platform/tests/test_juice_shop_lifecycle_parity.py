"""Static fail-closed parity tests for Juice Shop lifecycle publication.

No Docker daemon, network or target is used. These tests prevent drift between
the Compose publication contract, readiness adapter and lifecycle scripts.
"""

from __future__ import annotations

import re
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
ENV = ROOT / "environments" / "web-api" / "juice-shop"
ADAPTER = ROOT / "lab-readiness" / "adapters" / "juice-shop.yaml"
COMPOSE = ENV / "compose.yaml"
SMOKE = ENV / "scripts" / "smoke.sh"
RESET = ENV / "scripts" / "reset.sh"


def test_compose_publication_and_readiness_share_host_port_contract() -> None:
    compose = COMPOSE.read_text(encoding="utf-8")
    assert '127.0.0.1:${JUICE_SHOP_HOST_PORT:-3000}:3000' in compose

    adapter = yaml.safe_load(ADAPTER.read_text(encoding="utf-8"))
    readiness = adapter["readiness"]
    assert {item["port_env"] for item in readiness} == {"JUICE_SHOP_HOST_PORT"}
    assert {item.get("port", 3000) for item in readiness if item["kind"] == "tcp_connect"} == {3000}
    http = next(item for item in readiness if item["kind"] == "http_get")
    assert http["url"] == "http://127.0.0.1:3000/"


def test_smoke_resolves_compose_mapping_instead_of_hardcoded_host_port() -> None:
    smoke = SMOKE.read_text(encoding="utf-8")
    assert 'port "${APP_SERVICE}" 3000' in smoke
    assert '127\\.0\\.0\\.1:([0-9]+)' in smoke
    assert 'python3 - "${host_port}"' in smoke
    assert "http://127.0.0.1:3000" not in smoke
    assert "http.get('http://127.0.0.1:3000" not in smoke


def test_smoke_uses_same_compose_project_identity_as_lifecycle() -> None:
    smoke = SMOKE.read_text(encoding="utf-8")
    assert 'PROJECT_NAME="juice-shop"' in smoke
    assert 'COMPOSE=(docker compose -p "${PROJECT_NAME}" -f "${COMPOSE_FILE}")' in smoke
    assert re.search(r'container_id="\$\("\$\{COMPOSE\[@\]\}" ps -q "\$\{APP_SERVICE\}"', smoke)


def test_reset_disconnects_kali_from_explicit_compose_network_name() -> None:
    compose = yaml.safe_load(COMPOSE.read_text(encoding="utf-8"))
    network = compose["networks"]["juice-shop-lab"]
    assert network["name"] == "juice-shop-lab"

    reset = RESET.read_text(encoding="utf-8")
    assert 'APP_NETWORK="juice-shop-lab"' in reset
    assert 'docker network disconnect "${APP_NETWORK}" "${KALI_CONTAINER}"' in reset
    assert "juice-shop_juice-shop-lab" not in reset


def test_reset_keeps_smoke_after_health_gate() -> None:
    reset = RESET.read_text(encoding="utf-8")
    health_gate = reset.index('if [ "$health" = "healthy" ]')
    smoke = reset.index('"${SCRIPT_DIR}/smoke.sh"')
    assert health_gate < smoke
