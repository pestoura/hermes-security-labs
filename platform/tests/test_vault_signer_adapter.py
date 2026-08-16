#!/usr/bin/env python3
"""CHG-HSL-081 tests for the LAB_L1 Vault Transit signer adapter."""

from __future__ import annotations

import base64
import importlib.util
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

ROOT = Path(__file__).resolve().parents[2]
ASSURANCE = ROOT / "platform" / "assurance"
SIGNING_PATH = ASSURANCE / "signing_service.py"
VAULT_ADAPTER_PATH = ASSURANCE / "vault_signer_adapter.py"
VAULT_TRANSPORT_PATH = ASSURANCE / "vault_transport.py"


def _load(path: Path, name: str):
    assert path.exists(), f"{path.name} is not implemented yet"
    existing = sys.modules.get(name)
    if existing is not None:
        return existing
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def _signing():
    return _load(SIGNING_PATH, "chg_hsl_081_signing_service")


def _vault():
    return _load(VAULT_ADAPTER_PATH, "chg_hsl_081_vault_signer")


def _transport_module():
    return _load(VAULT_TRANSPORT_PATH, "chg_hsl_081_vault_transport")


@dataclass(frozen=True)
class _Response:
    status_code: int
    body: dict[str, Any]
    request_id: str | None = None


@dataclass(frozen=True)
class _Call:
    method: str
    path: str
    headers: dict[str, str]
    json_body: dict[str, object] | None


class FakeTransport:
    def __init__(self, *outcomes: object):
        self.outcomes = list(outcomes)
        self.calls: list[_Call] = []

    def request(self, method, path, *, headers=None, json_body=None):
        self.calls.append(
            _Call(
                method=str(method),
                path=str(path),
                headers=dict(headers or {}),
                json_body=dict(json_body) if json_body is not None else None,
            )
        )
        if not self.outcomes:
            raise AssertionError("unexpected Vault transport call")
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, BaseException):
            raise outcome
        return outcome


class SecretResolver:
    def __init__(self, values: dict[str, str]):
        self.values = dict(values)
        self.calls: list[str] = []

    def resolve(self, reference: str) -> str:
        self.calls.append(reference)
        return self.values[reference]


def _provider_private_key() -> Ed25519PrivateKey:
    return Ed25519PrivateKey.from_private_bytes(b"\x81" * 32)


def _public_key_pem() -> str:
    return _provider_private_key().public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    ).decode("ascii")


def _login(token: str = "vault-token-redacted") -> _Response:
    return _Response(200, {"auth": {"client_token": token}}, "req-login")


def _key_metadata(
    *,
    version: int = 3,
    name: str = "hsl-lab-l1",
    vault_type: str = "ed25519",
    supports_signing: bool = True,
    derived: bool = False,
    exportable: bool = False,
    backup: bool = False,
    public_key: str | None = None,
) -> _Response:
    return _Response(
        200,
        {
            "data": {
                "name": name,
                "type": vault_type,
                "supports_signing": supports_signing,
                "derived": derived,
                "exportable": exportable,
                "allow_plaintext_backup": backup,
                "keys": {
                    str(version): {
                        "public_key": public_key if public_key is not None else _public_key_pem()
                    }
                },
            }
        },
        "req-key",
    )


def _config(vault):
    return vault.VaultSignerConfig(
        vault_addr="https://vault.internal:8200",
        transit_mount="transit",
        key_name="hsl-lab-l1",
        approle_mount="approle",
        role_id_ref="secretref://vault/lab-l1/role-id",
        secret_id_ref="secretref://vault/lab-l1/secret-id",
        expected_algorithm="Ed25519",
        namespace=None,
        timeout_seconds=3.0,
    )


def _resolver() -> SecretResolver:
    return SecretResolver(
        {
            "secretref://vault/lab-l1/role-id": "role-id-081",
            "secretref://vault/lab-l1/secret-id": "secret-id-081",
        }
    )


def _request(signing, *, digest: str = "a" * 64):
    return signing.SigningRequest(
        digest_sha256=digest,
        purpose="tb1-authorization",
        domain="hex0r.tb1.authorization.v1",
        correlation_id="corr-081",
    )


def _signature(*, version: int = 3, raw: bytes | None = None) -> _Response:
    if raw is None:
        signing = _signing()
        raw = _provider_private_key().sign(
            signing.canonical_signing_payload(_request(signing))
        )
    return _Response(
        200,
        {
            "data": {
                "signature": f"vault:v{version}:{base64.b64encode(raw).decode('ascii')}"
            }
        },
        "req-sign",
    )


def _adapter(transport: FakeTransport):
    vault = _vault()
    return vault.VaultSignerAdapter(
        _config(vault), transport=transport, secret_resolver=_resolver()
    )


def test_config_contains_secret_references_not_credentials() -> None:
    vault = _vault()
    config = _config(vault)
    text = repr(config).lower()
    assert "role-id-081" not in text
    assert "secret-id-081" not in text
    assert "vault-token-redacted" not in text
    assert config.role_id_ref.startswith("secretref://")
    assert config.secret_id_ref.startswith("secretref://")


@pytest.mark.parametrize(
    "field,value",
    [
        ("vault_addr", "http://vault.internal:8200"),
        ("transit_mount", "../transit"),
        ("key_name", "bad/key"),
        ("approle_mount", "bad/auth"),
        ("role_id_ref", ""),
        ("secret_id_ref", "x\nsecret"),
        ("expected_algorithm", "ECDSA-P256-SHA256"),
        ("timeout_seconds", 0.1),
        ("timeout_seconds", True),
    ],
)
def test_config_rejects_unsafe_or_out_of_scope_values(field: str, value: object) -> None:
    vault = _vault()
    values = {
        "vault_addr": "https://vault.internal:8200",
        "transit_mount": "transit",
        "key_name": "hsl-lab-l1",
        "approle_mount": "approle",
        "role_id_ref": "secretref://vault/lab-l1/role-id",
        "secret_id_ref": "secretref://vault/lab-l1/secret-id",
        "expected_algorithm": "Ed25519",
        "namespace": None,
        "timeout_seconds": 3.0,
    }
    values[field] = value
    with pytest.raises(vault.VaultSignerError) as exc:
        vault.VaultSignerConfig(**values)
    assert exc.value.code == "VAULT_CONFIG_INVALID"


def test_invalid_signing_request_is_rejected_before_any_transport_call() -> None:
    signing = _signing()
    transport = FakeTransport()
    adapter = _adapter(transport)
    with pytest.raises(signing.SigningServiceError) as exc:
        adapter.sign(_request(signing, digest="A" * 64))
    assert exc.value.code == "SIGNING_REQUEST_INVALID"
    assert transport.calls == []


def test_adapter_uses_approle_observes_key_and_pins_exact_version() -> None:
    signing = _signing()
    transport = FakeTransport(_login(), _key_metadata(version=3), _signature(version=3))
    result = _adapter(transport).sign(_request(signing))

    assert [call.path for call in transport.calls] == [
        "/v1/auth/approle/login",
        "/v1/transit/keys/hsl-lab-l1",
        "/v1/transit/sign/hsl-lab-l1",
    ]
    login = transport.calls[0]
    assert login.json_body == {"role_id": "role-id-081", "secret_id": "secret-id-081"}
    key_read = transport.calls[1]
    assert key_read.headers["X-Vault-Token"] == "vault-token-redacted"
    sign_call = transport.calls[2]
    assert sign_call.json_body is not None
    assert sign_call.json_body["key_version"] == 3
    assert set(sign_call.json_body) == {"input", "key_version"}
    payload = signing.canonical_signing_payload(_request(signing))
    assert base64.b64decode(str(sign_call.json_body["input"]), validate=True) == payload

    assert result.signer_class == "VAULT"
    assert result.algorithm == "Ed25519"
    assert result.key_id == "vault:transit:hsl-lab-l1:v3"
    assert result.admissible_for_lab_l1 is True
    assert result.authority == "EXTERNAL_CUSTODY"
    assert result.audit_ref.startswith("evidence://vault-sign-operation/")
    assert len(result.public_key_spki_sha256) == 64
    signature = base64.b64decode(result.signature_b64, validate=True)
    _provider_private_key().public_key().verify(signature, payload)
    assert "vault-token-redacted" not in repr(result)
    assert "role-id-081" not in repr(result)
    assert "secret-id-081" not in repr(result)


@pytest.mark.parametrize(
    "response",
    [
        _key_metadata(exportable=True),
        _key_metadata(backup=True),
        _key_metadata(derived=True),
        _key_metadata(supports_signing=False),
        _key_metadata(name="other-key"),
        _key_metadata(vault_type="ecdsa-p256"),
        _key_metadata(public_key="not-a-public-key"),
    ],
)
def test_inadmissible_or_malformed_key_state_fails_closed(response: _Response) -> None:
    vault = _vault()
    signing = _signing()
    transport = FakeTransport(_login(), response)
    with pytest.raises(vault.VaultSignerError) as exc:
        _adapter(transport).sign(_request(signing))
    assert exc.value.code in {"VAULT_KEY_NOT_ADMISSIBLE", "VAULT_KEY_IDENTITY_INVALID"}
    assert all("/sign/" not in call.path for call in transport.calls)


def test_returned_signature_version_must_match_observed_key_version() -> None:
    vault = _vault()
    signing = _signing()
    transport = FakeTransport(_login(), _key_metadata(version=3), _signature(version=4))
    with pytest.raises(vault.VaultSignerError) as exc:
        _adapter(transport).sign(_request(signing))
    assert exc.value.code == "VAULT_SIGN_RESPONSE_INVALID"


@pytest.mark.parametrize(
    "provider_signature",
    [
        "not-vault-format",
        "vault:v3:not base64!",
        "vault:v0:" + base64.b64encode(b"x" * 64).decode("ascii"),
        "vault:v3:" + base64.b64encode(b"short").decode("ascii"),
    ],
)
def test_malformed_provider_signature_fails_closed(provider_signature: str) -> None:
    vault = _vault()
    signing = _signing()
    transport = FakeTransport(
        _login(),
        _key_metadata(version=3),
        _Response(200, {"data": {"signature": provider_signature}}),
    )
    with pytest.raises(vault.VaultSignerError) as exc:
        _adapter(transport).sign(_request(signing))
    assert exc.value.code == "VAULT_SIGN_RESPONSE_INVALID"


def test_one_auth_failure_can_reauthenticate_once_then_replay_sign() -> None:
    vault_transport = _transport_module()
    signing = _signing()
    transport = FakeTransport(
        _login("token-1"),
        _key_metadata(version=3),
        vault_transport.VaultTransportError(
            "VAULT_TRANSPORT_HTTP_ERROR", status_code=403
        ),
        _login("token-2"),
        _signature(version=3),
    )
    result = _adapter(transport).sign(_request(signing))
    assert result.signer_class == "VAULT"
    assert [c.path for c in transport.calls].count("/v1/auth/approle/login") == 2
    assert transport.calls[-1].headers["X-Vault-Token"] == "token-2"


def test_second_auth_failure_is_terminal_and_never_loops() -> None:
    vault = _vault()
    vault_transport = _transport_module()
    signing = _signing()
    transport = FakeTransport(
        _login("token-1"),
        _key_metadata(version=3),
        vault_transport.VaultTransportError(
            "VAULT_TRANSPORT_HTTP_ERROR", status_code=403
        ),
        _login("token-2"),
        vault_transport.VaultTransportError(
            "VAULT_TRANSPORT_HTTP_ERROR", status_code=403
        ),
    )
    with pytest.raises(vault.VaultSignerError) as exc:
        _adapter(transport).sign(_request(signing))
    assert exc.value.code in {"VAULT_AUTH_FAILED", "VAULT_ACCESS_DENIED"}
    assert [c.path for c in transport.calls].count("/v1/auth/approle/login") == 2
    assert len(transport.calls) == 5


def test_provider_and_secret_errors_are_sanitized() -> None:
    vault = _vault()
    vault_transport = _transport_module()
    signing = _signing()
    transport = FakeTransport(
        _login(),
        vault_transport.VaultTransportError(
            "VAULT_TRANSPORT_HTTP_ERROR", status_code=500
        ),
    )
    with pytest.raises(vault.VaultSignerError) as exc:
        _adapter(transport).sign(_request(signing))
    message = str(exc.value).lower()
    assert "vault-token-redacted" not in message
    assert "role-id-081" not in message
    assert "secret-id-081" not in message
