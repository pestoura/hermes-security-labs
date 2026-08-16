#!/usr/bin/env python3
"""CHG-HSL-081 tests for the bounded HTTPS Vault transport."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from urllib.error import HTTPError, URLError

import pytest

ROOT = Path(__file__).resolve().parents[2]
ASSURANCE = ROOT / "platform" / "assurance"
MODULE_PATH = ASSURANCE / "vault_transport.py"


def _load():
    assert MODULE_PATH.exists(), "vault_transport.py is not implemented yet"
    existing = sys.modules.get("chg_hsl_081_vault_transport_test")
    if existing is not None:
        return existing
    spec = importlib.util.spec_from_file_location(
        "chg_hsl_081_vault_transport_test", MODULE_PATH
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class _Response:
    def __init__(self, payload: bytes, *, status: int = 200, request_id: str | None = None):
        self._payload = payload
        self.status = status
        self.headers = {"X-Vault-Request": request_id} if request_id else {}

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self, amount: int = -1) -> bytes:
        if amount < 0:
            return self._payload
        return self._payload[:amount]


def test_transport_rejects_non_https_or_ambiguous_base_urls() -> None:
    module = _load()
    invalid = [
        "http://vault.internal:8200",
        "https://user:pass@vault.internal:8200",
        "https://vault.internal:8200/?x=1",
        "https://vault.internal:8200/#fragment",
        "https:///missing-host",
    ]
    for address in invalid:
        with pytest.raises(module.VaultTransportError) as exc:
            module.UrllibVaultTransport(address)
        assert exc.value.code == "VAULT_TRANSPORT_REQUEST_INVALID"


def test_transport_rejects_unsafe_method_path_and_headers(monkeypatch) -> None:
    module = _load()
    transport = module.UrllibVaultTransport("https://vault.internal:8200")
    for method in ("PUT", "DELETE", "PATCH"):
        with pytest.raises(module.VaultTransportError):
            transport.request(method, "/v1/transit/keys/key")
    for path in ("transit/keys/key", "/v1/../sys", "/v1/transit/key?x=1", "/v1/a#b"):
        with pytest.raises(module.VaultTransportError):
            transport.request("GET", path)
    with pytest.raises(module.VaultTransportError):
        transport.request("GET", "/v1/transit/keys/key", headers={"Authorization": "x"})
    with pytest.raises(module.VaultTransportError):
        transport.request("GET", "/v1/transit/keys/key", headers={"X-Vault-Token": "bad\nvalue"})


def test_transport_serializes_canonical_json_and_uses_tls_verified_context(monkeypatch) -> None:
    module = _load()
    captured: dict[str, object] = {}

    class _Context:
        pass

    context = _Context()

    def fake_context(*, cafile=None):
        captured["cafile"] = cafile
        return context

    def fake_urlopen(request, *, timeout, context):
        captured["request"] = request
        captured["timeout"] = timeout
        captured["context"] = context
        return _Response(json.dumps({"data": {"ok": True}}).encode("utf-8"), request_id="req-081")

    monkeypatch.setattr(module.ssl, "create_default_context", fake_context)
    monkeypatch.setattr(module.urllib.request, "urlopen", fake_urlopen)

    transport = module.UrllibVaultTransport(
        "https://vault.internal:8200/", timeout_seconds=2.5, ca_bundle_path="/etc/ssl/hsl-ca.pem"
    )
    response = transport.request(
        "POST",
        "/v1/auth/approle/login",
        headers={"X-Vault-Namespace": "lab"},
        json_body={"secret_id": "s", "role_id": "r"},
    )

    request = captured["request"]
    assert request.full_url == "https://vault.internal:8200/v1/auth/approle/login"
    assert request.data == b'{"role_id":"r","secret_id":"s"}'
    assert captured["timeout"] == 2.5
    assert captured["context"] is context
    assert captured["cafile"] == "/etc/ssl/hsl-ca.pem"
    assert response.status_code == 200
    assert response.body == {"data": {"ok": True}}
    assert response.request_id == "req-081"


def test_transport_rejects_response_larger_than_256_kib(monkeypatch) -> None:
    module = _load()
    payload = b"{" + (b"x" * 262_144) + b"}"
    monkeypatch.setattr(
        module.urllib.request,
        "urlopen",
        lambda *_args, **_kwargs: _Response(payload),
    )
    transport = module.UrllibVaultTransport("https://vault.internal:8200")
    with pytest.raises(module.VaultTransportError) as exc:
        transport.request("GET", "/v1/transit/keys/key")
    assert exc.value.code == "VAULT_TRANSPORT_RESPONSE_TOO_LARGE"


def test_transport_maps_invalid_json_without_exposing_body(monkeypatch) -> None:
    module = _load()
    secret_body = b'not-json-vault-token-secret-id-role-id'
    monkeypatch.setattr(
        module.urllib.request,
        "urlopen",
        lambda *_args, **_kwargs: _Response(secret_body),
    )
    transport = module.UrllibVaultTransport("https://vault.internal:8200")
    with pytest.raises(module.VaultTransportError) as exc:
        transport.request("GET", "/v1/transit/keys/key")
    assert exc.value.code == "VAULT_TRANSPORT_RESPONSE_INVALID"
    assert "vault-token" not in str(exc.value).lower()
    assert "secret-id" not in str(exc.value).lower()
    assert secret_body.decode("ascii") not in str(exc.value)


def test_transport_maps_http_and_network_errors_without_response_content(monkeypatch) -> None:
    module = _load()
    transport = module.UrllibVaultTransport("https://vault.internal:8200")

    def http_error(*_args, **_kwargs):
        raise HTTPError(
            "https://vault.internal:8200/v1/x",
            403,
            "forbidden-secret-body",
            {},
            None,
        )

    monkeypatch.setattr(module.urllib.request, "urlopen", http_error)
    with pytest.raises(module.VaultTransportError) as exc:
        transport.request("GET", "/v1/transit/keys/key", headers={"X-Vault-Token": "token-081"})
    assert exc.value.code == "VAULT_TRANSPORT_HTTP_ERROR"
    assert exc.value.status_code == 403
    assert "forbidden-secret-body" not in str(exc.value)
    assert "token-081" not in str(exc.value)

    monkeypatch.setattr(
        module.urllib.request,
        "urlopen",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(URLError("credential-like-detail")),
    )
    with pytest.raises(module.VaultTransportError) as exc:
        transport.request("GET", "/v1/transit/keys/key")
    assert exc.value.code == "VAULT_TRANSPORT_UNREACHABLE"
    assert "credential-like-detail" not in str(exc.value)
