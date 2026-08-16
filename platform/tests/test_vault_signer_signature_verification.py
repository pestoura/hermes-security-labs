#!/usr/bin/env python3
"""Hardening TDD: Vault signatures must verify against the observed Ed25519 key."""

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
MODULE_PATH = ROOT / "platform" / "assurance" / "vault_signer_adapter.py"


def _load():
    name = "chg_hsl_081_vault_signature_hardening"
    existing = sys.modules.get(name)
    if existing is not None:
        return existing
    spec = importlib.util.spec_from_file_location(name, MODULE_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


@dataclass(frozen=True)
class _Response:
    status_code: int
    body: dict[str, Any]
    request_id: str | None = None


class _Transport:
    def __init__(self, outcomes: list[_Response]) -> None:
        self._outcomes = list(outcomes)

    def request(self, _method, _path, *, headers=None, json_body=None):
        assert self._outcomes, "unexpected provider call"
        return self._outcomes.pop(0)


class _Secrets:
    def resolve(self, reference: str) -> str:
        return "R" * 24 if reference.endswith("role-id") else "S" * 24


def test_invalid_provider_signature_is_rejected_against_observed_ed25519_key() -> None:
    vault = _load()
    private_key = Ed25519PrivateKey.from_private_bytes(b"\xa1" * 32)
    public_pem = private_key.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    ).decode("ascii")

    provider_signature = base64.b64encode(b"\x00" * 64).decode("ascii")
    transport = _Transport(
        [
            _Response(200, {"auth": {"client_token": "T" * 24}}),
            _Response(
                200,
                {
                    "data": {
                        "name": "hsl-lab-l1",
                        "type": "ed25519",
                        "supports_signing": True,
                        "derived": False,
                        "exportable": False,
                        "allow_plaintext_backup": False,
                        "keys": {"3": {"public_key": public_pem}},
                    }
                },
            ),
            _Response(200, {"data": {"signature": f"vault:v3:{provider_signature}"}}),
        ]
    )

    adapter = vault.VaultSignerAdapter(
        vault.VaultSignerConfig(
            vault_addr="https://vault.internal:8200",
            transit_mount="transit",
            key_name="hsl-lab-l1",
            approle_mount="approle",
            role_id_ref="secretref://vault/lab-l1/role-id",
            secret_id_ref="secretref://vault/lab-l1/secret-id",
            expected_algorithm="Ed25519",
            namespace=None,
            timeout_seconds=3.0,
        ),
        transport=transport,
        secret_resolver=_Secrets(),
    )
    signing = vault._signing
    request = signing.SigningRequest(
        digest_sha256="d" * 64,
        purpose="tb1-authorization",
        domain="hex0r.tb1.authorization.v1",
        correlation_id="corr-signature-verify-081",
    )

    with pytest.raises(vault.VaultSignerError) as exc:
        adapter.sign(request)
    assert exc.value.code == "VAULT_SIGN_RESPONSE_INVALID"
