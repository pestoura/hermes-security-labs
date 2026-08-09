from __future__ import annotations

import importlib.util
import json
import re
import sys
from pathlib import Path
from urllib.parse import urlparse

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "scripts" / "lab_readiness.py"
ADAPTERS = ROOT / "lab-readiness" / "adapters"
ENVIRONMENTS = ROOT / "environments" / "web-api"

LANE_L_ENVS = ("webgoat", "dvwa", "juice-shop")
ENV_PATHS = {
    "webgoat": ENVIRONMENTS / "webgoat" / "manifest.yaml",
    "dvwa": ENVIRONMENTS / "dvwa" / "manifest.yaml",
    "juice-shop": ENVIRONMENTS / "juice-shop" / "manifest.yaml",
}


def _load_readiness():
    spec = importlib.util.spec_from_file_location("lane_l_lab_readiness", MODULE_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


readiness = _load_readiness()


def _yaml(path: Path):
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def _default_port(raw) -> int:
    if isinstance(raw, int) and not isinstance(raw, bool):
        return raw
    if isinstance(raw, str) and raw.isdigit():
        return int(raw)
    if isinstance(raw, str):
        match = re.fullmatch(r"\$\{[A-Z0-9_]+:-([0-9]+)\}", raw)
        if match:
            return int(match.group(1))
    raise AssertionError(f"unsupported canonical host_port expression: {raw!r}")


def _expand_default_port(url: str) -> str:
    return re.sub(
        r"\$\{[A-Z0-9_]+:-([0-9]+)\}",
        lambda match: match.group(1),
        url,
    )


@pytest.mark.parametrize("env_id", LANE_L_ENVS)
def test_lane_l_adapter_exists_and_parses(env_id):
    adapter = readiness.load_adapter(env_id, ADAPTERS)
    assert adapter.env_id == env_id
    assert adapter.liveness
    assert adapter.readiness


@pytest.mark.parametrize("env_id", LANE_L_ENVS)
def test_lane_l_adapter_is_typed_loopback_only_and_has_no_generic_execution(env_id):
    adapter = readiness.load_adapter(env_id, ADAPTERS)
    raw = _yaml(ADAPTERS / f"{env_id}.yaml")
    serialized = json.dumps(raw)

    for forbidden in ("command", "cmd", "shell", "script", "exec", "args"):
        assert f'"{forbidden}"' not in serialized

    for check in adapter.liveness:
        assert check.kind in readiness.LIVENESS_KINDS
    for check in adapter.readiness:
        assert check.kind in readiness.READINESS_KINDS
        assert 0 < check.params["timeout_seconds"] <= readiness.MAX_TIMEOUT_SECONDS
        if check.kind == "http_get":
            parsed = urlparse(check.params["url"])
            assert parsed.scheme == "http"
            assert parsed.hostname in readiness.LOOPBACK_HOSTS
            assert check.params["expect_status"] == 200
        elif check.kind == "tcp_connect":
            assert check.params["host"] in readiness.LOOPBACK_HOSTS


@pytest.mark.parametrize("env_id", LANE_L_ENVS)
def test_lane_l_adapter_uses_canonical_default_publication_ports(env_id):
    adapter = readiness.load_adapter(env_id, ADAPTERS)
    manifest = _yaml(ENV_PATHS[env_id])
    bindings = manifest["network"]["ingress"]["bindings"]
    canonical_ports = {_default_port(binding["host_port"]) for binding in bindings}

    tcp_ports = {
        check.params["port"]
        for check in adapter.readiness
        if check.kind == "tcp_connect"
    }
    http_ports = {
        urlparse(check.params["url"]).port
        for check in adapter.readiness
        if check.kind == "http_get"
    }

    assert tcp_ports == canonical_ports
    assert http_ports == canonical_ports


@pytest.mark.parametrize("env_id", LANE_L_ENVS)
def test_lane_l_adapter_covers_manifest_primary_readiness_probe(env_id):
    adapter = readiness.load_adapter(env_id, ADAPTERS)
    manifest = _yaml(ENV_PATHS[env_id])
    manifest_probe = _expand_default_port(manifest["readiness"]["probe"])
    adapter_http_urls = {
        check.params["url"]
        for check in adapter.readiness
        if check.kind == "http_get"
    }

    assert manifest_probe in adapter_http_urls


def test_lane_l_webgoat_covers_webwolf_publication_too():
    adapter = readiness.load_adapter("webgoat", ADAPTERS)
    urls = {
        check.params["url"]
        for check in adapter.readiness
        if check.kind == "http_get"
    }
    assert "http://127.0.0.1:8080/WebGoat/" in urls
    assert "http://127.0.0.1:9090/login" in urls


def test_lane_l_adapters_are_discoverable_without_runtime():
    known = set(readiness.known_adapters(ADAPTERS))
    assert set(LANE_L_ENVS).issubset(known)
