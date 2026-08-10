"""Contract tests for typed, port-only readiness publication overrides.

A legitimate loopback host-port override must be readiness-validatable without
weakening scheme, host, path, query or no-generic-execution invariants. The
same generic mechanism is used by WebGoat/WebWolf, DVWA and Juice Shop.
No runtime socket, container or target is used by this suite.
"""

from __future__ import annotations

import importlib.util
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

PUBLICATIONS = {
    "webgoat": {
        "compose": ENVIRONMENTS / "webgoat" / "compose.yaml",
        "ports": {"WEBGOAT_HOST_PORT": 8080, "WEBWOLF_HOST_PORT": 9090},
    },
    "dvwa": {
        "compose": ENVIRONMENTS / "dvwa" / "compose.yaml",
        "ports": {"DVWA_HOST_PORT": 4280},
    },
    "juice-shop": {
        "compose": ENVIRONMENTS / "juice-shop" / "compose.yaml",
        "ports": {"JUICE_SHOP_HOST_PORT": 3000},
    },
}


def _load():
    spec = importlib.util.spec_from_file_location(
        "port_override_lab_readiness", MODULE_PATH
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


readiness = _load()


def _adapter(env_id):
    return readiness.load_adapter(env_id, ADAPTERS)


def _check(env_id, check_id):
    for check in _adapter(env_id).readiness:
        if check.id == check_id:
            return check
    raise AssertionError(f"unknown check id {env_id}/{check_id}")


def _declared_default_port(check):
    if check.kind == "tcp_connect":
        return int(check.params["port"])
    return int(urlparse(check.params["url"]).port)


# --------------------------------------------------------------------------- #
# Absent env => exact committed behaviour
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("env_id", sorted(PUBLICATIONS))
def test_absent_env_keeps_committed_default_ports(env_id):
    for check in _adapter(env_id).readiness:
        default_port = _declared_default_port(check)
        if check.kind == "tcp_connect":
            assert readiness.resolve_port(check, {}) == default_port
        else:
            effective = urlparse(readiness.effective_url(check, {}))
            assert effective.port == default_port
            assert effective == urlparse(check.params["url"])


def test_check_without_port_env_ignores_environment_entirely():
    check = readiness.Check(
        id="no-env",
        kind="tcp_connect",
        params={"host": "127.0.0.1", "port": 8080, "timeout_seconds": 5},
    )
    assert readiness.resolve_port(check, {"WEBGOAT_HOST_PORT": "18080"}) == 8080


# --------------------------------------------------------------------------- #
# Valid override => port changes, locator does not
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("env_id", sorted(PUBLICATIONS))
def test_valid_override_changes_only_declared_port(env_id):
    for check in _adapter(env_id).readiness:
        env_name = check.params[readiness.PORT_ENV_KEY]
        default_port = _declared_default_port(check)
        override = min(default_port + 10000, 65535)
        env = {env_name: str(override)}

        if check.kind == "tcp_connect":
            assert readiness.resolve_port(check, env) == override
            assert check.params["host"] in readiness.LOOPBACK_HOSTS
            continue

        original = urlparse(check.params["url"])
        changed = urlparse(readiness.effective_url(check, env))
        assert changed.port == override
        assert changed.scheme == original.scheme == "http"
        assert changed.hostname == original.hostname == "127.0.0.1"
        assert changed.path == original.path
        assert changed.params == original.params
        assert changed.query == original.query == ""
        assert changed.fragment == original.fragment


def test_override_is_scoped_to_the_declared_variable_only():
    webgoat = _check("webgoat", "tcp-webgoat")
    assert readiness.resolve_port(
        webgoat, {"WEBWOLF_HOST_PORT": "19090"}
    ) == 8080


# --------------------------------------------------------------------------- #
# Invalid env => fail closed, never silent fallback
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    "value",
    [
        "",
        "0",
        "-1",
        "65536",
        "99999",
        "8080.0",
        "8080abc",
        "abc",
        "08080x",
        "0x1f90",
        "+8080",
        "80 80",
        "127.0.0.1:8080",
        "$(id)",
        "8080;rm -rf /",
        "８０８０",
    ],
)
def test_invalid_env_values_fail_closed(value):
    check = _check("webgoat", "tcp-webgoat")
    with pytest.raises(readiness.ReadinessContractError) as exc_info:
        readiness.resolve_port(check, {"WEBGOAT_HOST_PORT": value})
    assert readiness.REASON_PORT_ENV_INVALID in str(exc_info.value)


@pytest.mark.parametrize("value", ["", "abc", "0", "70000"])
def test_invalid_env_never_falls_back_to_default_for_http(value):
    check = _check("dvwa", "http-dvwa-login")
    with pytest.raises(readiness.ReadinessContractError):
        readiness.effective_url(check, {"DVWA_HOST_PORT": value})


def test_invalid_env_makes_executed_check_fail_not_pass(monkeypatch):
    monkeypatch.setenv("JUICE_SHOP_HOST_PORT", "not-a-port")
    executor = readiness.DefaultExecutor()
    tcp = executor.run("juice-shop", _check("juice-shop", "tcp-juice-shop"))
    http = executor.run("juice-shop", _check("juice-shop", "http-juice-shop"))
    assert tcp.passed is False
    assert http.passed is False
    assert readiness.REASON_PORT_ENV_INVALID in tcp.detail
    assert readiness.REASON_PORT_ENV_INVALID in http.detail


# --------------------------------------------------------------------------- #
# Adapter-level invariants
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    "bad_name",
    [
        "",
        "webgoat_host_port",
        "WEBGOAT-HOST-PORT",
        "1PORT",
        "WEBGOAT HOST PORT",
        "PATH}",
        "A" * 65,
        8080,
        True,
        ["X"],
    ],
)
def test_port_env_name_is_strictly_validated(bad_name):
    document = {
        "schema_version": 1,
        "env_id": "sample",
        "readiness": [
            {
                "id": "tcp",
                "kind": "tcp_connect",
                "host": "127.0.0.1",
                "port": 8080,
                "port_env": bad_name,
                "timeout_seconds": 5,
            }
        ],
    }
    with pytest.raises(readiness.ReadinessContractError) as exc_info:
        readiness.parse_adapter("sample", document, Path("sample.yaml"))
    assert readiness.REASON_ADAPTER_INVALID in str(exc_info.value)


def test_port_env_cannot_relax_non_loopback_invariant():
    document = {
        "schema_version": 1,
        "env_id": "sample",
        "readiness": [
            {
                "id": "tcp",
                "kind": "tcp_connect",
                "host": "10.0.0.5",
                "port": 8080,
                "port_env": "SAMPLE_HOST_PORT",
                "timeout_seconds": 5,
            }
        ],
    }
    with pytest.raises(readiness.ReadinessContractError):
        readiness.parse_adapter("sample", document, Path("sample.yaml"))


def test_port_env_cannot_relax_http_locator_invariants():
    for url in (
        "http://10.0.0.5:8080/x",
        "https://127.0.0.1:8080/x",
        "http://127.0.0.1:8080/x?a=1",
    ):
        document = {
            "schema_version": 1,
            "env_id": "sample",
            "readiness": [
                {
                    "id": "http",
                    "kind": "http_get",
                    "url": url,
                    "port_env": "SAMPLE_HOST_PORT",
                    "timeout_seconds": 5,
                }
            ],
        }
        with pytest.raises(readiness.ReadinessContractError):
            readiness.parse_adapter("sample", document, Path("sample.yaml"))


def test_no_generic_template_or_command_substitution_is_supported():
    document = {
        "schema_version": 1,
        "env_id": "sample",
        "readiness": [
            {
                "id": "http",
                "kind": "http_get",
                "url": "http://127.0.0.1:${SAMPLE_HOST_PORT:-8080}/x",
                "timeout_seconds": 5,
            }
        ],
    }
    with pytest.raises(readiness.ReadinessContractError):
        readiness.parse_adapter("sample", document, Path("sample.yaml"))

    for env_id in PUBLICATIONS:
        for check in _adapter(env_id).readiness:
            for key, value in check.params.items():
                if isinstance(value, str) and key != readiness.PORT_ENV_KEY:
                    assert "${" not in value


# --------------------------------------------------------------------------- #
# Parity with Compose publication variables
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("env_id", sorted(PUBLICATIONS))
def test_adapter_port_env_and_defaults_match_compose_publication(env_id):
    contract = PUBLICATIONS[env_id]
    compose_text = contract["compose"].read_text(encoding="utf-8")
    published = dict(
        (match.group(1), int(match.group(2)))
        for match in re.finditer(
            r"127\.0\.0\.1:\$\{([A-Z][A-Z0-9_]*):-([0-9]+)\}:", compose_text
        )
    )
    assert published == contract["ports"]

    adapter = _adapter(env_id)
    observed = {
        (check.params[readiness.PORT_ENV_KEY], _declared_default_port(check))
        for check in adapter.readiness
    }
    assert observed == set(published.items())

    raw = yaml.safe_load(
        (ADAPTERS / f"{env_id}.yaml").read_text(encoding="utf-8")
    )
    for entry in raw["readiness"]:
        assert entry[readiness.PORT_ENV_KEY] in published


def test_unrelated_adapters_declare_no_port_override():
    allowed = set(PUBLICATIONS)
    for path in sorted(ADAPTERS.glob("*.yaml")):
        if path.stem in allowed:
            continue
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
        for entry in raw.get("readiness", []):
            assert readiness.PORT_ENV_KEY not in entry, path.name
