"""Focused contract tests for the OPTIONAL readiness port override.

Scope: a legitimate loopback publication override (``WEBGOAT_HOST_PORT`` /
``WEBWOLF_HOST_PORT``) must be readiness-validatable without weakening any
invariant. Only the TCP port may change; scheme, host, path and query stay
exactly as committed in the adapter. No runtime, socket or container is used:
every assertion is on the parsed contract and on pure resolution helpers.
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
COMPOSE = ROOT / "environments" / "web-api" / "webgoat" / "compose.yaml"


def _load():
    spec = importlib.util.spec_from_file_location("port_override_lab_readiness", MODULE_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


readiness = _load()


def _webgoat():
    return readiness.load_adapter("webgoat", ADAPTERS)


def _check(check_id):
    for check in _webgoat().readiness:
        if check.id == check_id:
            return check
    raise AssertionError(f"unknown check id {check_id}")


# --------------------------------------------------------------------------- #
# Absent env => exact existing default behaviour
# --------------------------------------------------------------------------- #


def test_absent_env_keeps_committed_default_ports():
    assert readiness.resolve_port(_check("tcp-webgoat"), {}) == 8080
    assert readiness.resolve_port(_check("tcp-webwolf"), {}) == 9090
    assert readiness.effective_url(_check("http-webgoat"), {}) == "http://127.0.0.1:8080/WebGoat/"
    assert readiness.effective_url(_check("http-webwolf"), {}) == "http://127.0.0.1:9090/login"


def test_check_without_port_env_ignores_environment_entirely():
    check = readiness.Check(
        id="no-env",
        kind="tcp_connect",
        params={"host": "127.0.0.1", "port": 8080, "timeout_seconds": 5},
    )
    assert readiness.resolve_port(check, {"WEBGOAT_HOST_PORT": "18080"}) == 8080


# --------------------------------------------------------------------------- #
# Valid override
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("value,expected", [("18080", 18080), (" 18080 ", 18080), ("1", 1), ("65535", 65535)])
def test_tcp_port_substitution_accepts_valid_integer_ports(value, expected):
    assert readiness.resolve_port(_check("tcp-webgoat"), {"WEBGOAT_HOST_PORT": value}) == expected


def test_http_port_substitution_changes_only_the_port():
    env = {"WEBWOLF_HOST_PORT": "19090"}
    url = readiness.effective_url(_check("http-webwolf"), env)
    assert url == "http://127.0.0.1:19090/login"

    original = urlparse(_check("http-webwolf").params["url"])
    overridden = urlparse(url)
    assert overridden.scheme == original.scheme == "http"
    assert overridden.hostname == original.hostname == "127.0.0.1"
    assert overridden.path == original.path
    assert overridden.query == original.query == ""
    assert overridden.params == original.params
    assert overridden.fragment == original.fragment


def test_override_is_scoped_to_the_declared_variable_only():
    env = {"WEBWOLF_HOST_PORT": "19090"}
    assert readiness.resolve_port(_check("tcp-webgoat"), env) == 8080
    assert readiness.effective_url(_check("http-webgoat"), env) == "http://127.0.0.1:8080/WebGoat/"


# --------------------------------------------------------------------------- #
# Invalid env => fail closed, never a silent fallback
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    "value",
    ["", "0", "-1", "65536", "99999", "8080.0", "8080abc", "abc", "08080x", "0x1f90", "+8080", "80 80",
     "127.0.0.1:8080", "$(id)", "8080;rm -rf /", "８０８０"],
)
def test_invalid_env_values_fail_closed(value):
    with pytest.raises(readiness.ReadinessContractError) as excinfo:
        readiness.resolve_port(_check("tcp-webgoat"), {"WEBGOAT_HOST_PORT": value})
    assert readiness.REASON_PORT_ENV_INVALID in str(excinfo.value)


@pytest.mark.parametrize("value", ["", "abc", "0", "70000"])
def test_invalid_env_never_falls_back_to_default_for_http(value):
    with pytest.raises(readiness.ReadinessContractError):
        readiness.effective_url(_check("http-webgoat"), {"WEBGOAT_HOST_PORT": value})


def test_invalid_env_makes_the_executed_check_fail_not_pass(monkeypatch):
    monkeypatch.setenv("WEBGOAT_HOST_PORT", "not-a-port")
    executor = readiness.DefaultExecutor()
    tcp_result = executor.run("webgoat", _check("tcp-webgoat"))
    http_result = executor.run("webgoat", _check("http-webgoat"))
    assert tcp_result.passed is False
    assert http_result.passed is False
    assert readiness.REASON_PORT_ENV_INVALID in tcp_result.detail
    assert readiness.REASON_PORT_ENV_INVALID in http_result.detail


# --------------------------------------------------------------------------- #
# Adapter-level invariants: strict name validation, no generic substitution
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    "bad_name",
    ["", "webgoat_host_port", "WEBGOAT-HOST-PORT", "1PORT", "WEBGOAT HOST PORT", "PATH}", "A" * 65, 8080, True, ["X"]],
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
    with pytest.raises(readiness.ReadinessContractError) as excinfo:
        readiness.parse_adapter("sample", document, Path("sample.yaml"))
    assert readiness.REASON_ADAPTER_INVALID in str(excinfo.value)


def test_port_env_cannot_relax_the_non_loopback_invariant():
    document = {
        "schema_version": 1,
        "env_id": "sample",
        "readiness": [
            {
                "id": "tcp",
                "kind": "tcp_connect",
                "host": "10.0.0.5",
                "port": 8080,
                "port_env": "WEBGOAT_HOST_PORT",
                "timeout_seconds": 5,
            }
        ],
    }
    with pytest.raises(readiness.ReadinessContractError):
        readiness.parse_adapter("sample", document, Path("sample.yaml"))


def test_port_env_cannot_relax_the_http_loopback_and_scheme_invariants():
    for url in ("http://10.0.0.5:8080/x", "https://127.0.0.1:8080/x", "http://127.0.0.1:8080/x?a=1"):
        document = {
            "schema_version": 1,
            "env_id": "sample",
            "readiness": [
                {
                    "id": "http",
                    "kind": "http_get",
                    "url": url,
                    "port_env": "WEBGOAT_HOST_PORT",
                    "timeout_seconds": 5,
                }
            ],
        }
        with pytest.raises(readiness.ReadinessContractError):
            readiness.parse_adapter("sample", document, Path("sample.yaml"))


def test_overridden_host_remains_loopback_for_every_webgoat_check():
    env = {"WEBGOAT_HOST_PORT": "18080", "WEBWOLF_HOST_PORT": "19090"}
    for check in _webgoat().readiness:
        if check.kind == "tcp_connect":
            assert check.params["host"] in readiness.LOOPBACK_HOSTS
        else:
            assert urlparse(readiness.effective_url(check, env)).hostname in readiness.LOOPBACK_HOSTS


def test_no_generic_template_or_command_substitution_is_supported():
    document = {
        "schema_version": 1,
        "env_id": "sample",
        "readiness": [
            {
                "id": "http",
                "kind": "http_get",
                "url": "http://127.0.0.1:${WEBGOAT_HOST_PORT:-8080}/WebGoat/",
                "timeout_seconds": 5,
            }
        ],
    }
    with pytest.raises(readiness.ReadinessContractError):
        readiness.parse_adapter("sample", document, Path("sample.yaml"))

    # The only mutable field on a parsed check is the port; nothing else is templated.
    for check in _webgoat().readiness:
        for key, value in check.params.items():
            if isinstance(value, str) and key != readiness.PORT_ENV_KEY:
                assert "${" not in value


# --------------------------------------------------------------------------- #
# Parity with the WebGoat Compose publication variables
# --------------------------------------------------------------------------- #


def test_adapter_port_env_and_defaults_match_compose_publication():
    compose_text = COMPOSE.read_text(encoding="utf-8")
    published = dict(
        (match.group(1), int(match.group(2)))
        for match in re.finditer(
            r"127\.0\.0\.1:\$\{([A-Z][A-Z0-9_]*):-([0-9]+)\}:", compose_text
        )
    )
    assert published == {"WEBGOAT_HOST_PORT": 8080, "WEBWOLF_HOST_PORT": 9090}

    adapter = _webgoat()
    observed = {
        (check.params[readiness.PORT_ENV_KEY], check.params["port"])
        for check in adapter.readiness
    }
    assert observed == {("WEBGOAT_HOST_PORT", 8080), ("WEBWOLF_HOST_PORT", 9090)}

    raw = yaml.safe_load((ADAPTERS / "webgoat.yaml").read_text(encoding="utf-8"))
    for entry in raw["readiness"]:
        assert entry["port_env"] in published


def test_other_adapters_declare_no_port_override():
    for path in sorted(ADAPTERS.glob("*.yaml")):
        if path.stem == "webgoat":
            continue
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
        for entry in raw.get("readiness", []):
            assert readiness.PORT_ENV_KEY not in entry, path.name
