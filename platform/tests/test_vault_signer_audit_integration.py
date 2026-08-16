#!/usr/bin/env python3
"""Cross-contract proof for CHG-HSL-081 Vault signing and canonical signer audit."""

from __future__ import annotations

import base64
import importlib.util
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

ROOT = Path(__file__).resolve().parents[2]
ASSURANCE = ROOT / "platform" / "assurance"
VAULT_PATH = ASSURANCE / "vault_signer_adapter.py"
AUDIT_PATH = ASSURANCE / "signer_audit_adapter.py"
DECISION_PATH = ASSURANCE / "signer-human-decision.yaml"
CAMPAIGN_PATH = ROOT / "validation" / "VAL-HSL-RUNNER-L1-LIVE-PROMOTION.yaml"

# Scanner-safe runtime-only fixture markers. They are deliberately constructed rather
# than committed as credential-looking literals, while still proving that resolved
# credential material never enters public result/audit serialization.
_TOKEN_MARKER = "T" * 31
_ROLE_MARKER = "R" * 29
_SECRET_MARKER = "S" * 37


def _load(path: Path, name: str):
    existing = sys.modules.get(name)
    if existing is not None:
        return existing
    spec = importlib.util.spec_from_file_location(name, path)
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
        self.calls: list[tuple[str, str, dict[str, str], dict[str, object] | None]] = []

    def request(self, method, path, *, headers=None, json_body=None):
        self.calls.append(
            (
                str(method),
                str(path),
                dict(headers or {}),
                dict(json_body) if json_body is not None else None,
            )
        )
        assert self._outcomes, "unexpected Vault call"
        return self._outcomes.pop(0)


class _Secrets:
    def __init__(self) -> None:
        self.values = {
            "secretref://vault/lab-l1/role-id": _ROLE_MARKER,
            "secretref://vault/lab-l1/secret-id": _SECRET_MARKER,
        }

    def resolve(self, reference: str) -> str:
        return self.values[reference]


def _provider_private_key() -> Ed25519PrivateKey:
    return Ed25519PrivateKey.from_private_bytes(b"\x91" * 32)


def _public_key_pem() -> str:
    return _provider_private_key().public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    ).decode("ascii")


def _provider_responses(signing, request) -> list[_Response]:
    signature_bytes = _provider_private_key().sign(
        signing.canonical_signing_payload(request)
    )
    signature = base64.b64encode(signature_bytes).decode("ascii")
    return [
        _Response(200, {"auth": {"client_token": _TOKEN_MARKER}}),
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
                    "keys": {"7": {"public_key": _public_key_pem()}},
                }
            },
        ),
        _Response(200, {"data": {"signature": f"vault:v7:{signature}"}}),
    ]


def test_vault_result_enters_canonical_signer_audit_without_secret_or_authority_drift() -> None:
    # Load signer audit first so the request is created by the exact canonical
    # signing_service module instance that its strict isinstance guards expect.
    audit = _load(AUDIT_PATH, "chg_hsl_081_signer_audit_integration")
    vault = _load(VAULT_PATH, "chg_hsl_081_vault_audit_integration")

    request = audit.SigningRequest(
        digest_sha256="c" * 64,
        purpose="tb1-authorization",
        domain="hex0r.tb1.authorization.v1",
        correlation_id="corr-audit-081",
    )
    signing = vault._signing_module_for_request(request)
    transport = _Transport(_provider_responses(signing, request))
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

    result = adapter.sign(request)
    record = audit.build_signer_audit_record(
        request,
        result,
        audit.SignerAuditAttribution(
            principal="hermes-assurance",
            provider_ref="vault-transit/lab-l1",
            test_only=False,
        ),
    )

    assert result.signer_class == "VAULT"
    assert result.audit_ref.startswith("evidence://vault-sign-operation/")
    assert record["schema_version"] == "signer-operation-audit/v1"
    assert record["signer_class"] == "VAULT"
    assert record["test_only"] is False
    assert record["promotion_allowed"] is False
    assert record["runtime_status"] == "NOT_RUN"
    assert record["execution_authority"] == "NONE"
    assert record["request_digest_sha256"] == "c" * 64
    assert record["request_correlation_id"] == "corr-audit-081"

    serialized = json.dumps(
        {"result": result.__dict__, "audit": record},
        sort_keys=True,
        separators=(",", ":"),
    )
    for marker in (_TOKEN_MARKER, _ROLE_MARKER, _SECRET_MARKER):
        assert marker not in serialized

    assert [call[1] for call in transport.calls] == [
        "/v1/auth/approle/login",
        "/v1/transit/keys/hsl-lab-l1",
        "/v1/transit/sign/hsl-lab-l1",
    ]


def test_vault_repository_capability_does_not_mutate_human_or_campaign_authority() -> None:
    decision = yaml.safe_load(DECISION_PATH.read_text(encoding="utf-8"))
    campaign = yaml.safe_load(CAMPAIGN_PATH.read_text(encoding="utf-8"))

    assert decision["decision"]["state"] == "NO_DECISION"
    assert decision["decision"]["selected_class"] is None
    assert decision["decision"]["decision_id"] is None
    assert decision["decision"]["evidence_refs"] == []

    assert campaign["state"] == "BLOCKED"
    assert campaign["promotionRecommendation"] == "HOLD"


def test_vault_adapter_source_has_no_local_fallback_or_provider_admin_surface() -> None:
    source = VAULT_PATH.read_text(encoding="utf-8")

    assert "import subprocess" not in source
    assert "from subprocess" not in source
    assert "TestSignerAdapter" not in source
    assert "BEGIN PRIVATE KEY" not in source
    assert "VAULT_TOKEN" not in source

    # The adapter may authenticate, read exactly one key and sign. It must not expose
    # management endpoints capable of changing the Vault/key lifecycle.
    forbidden_endpoint_fragments = (
        "/rotate",
        "/config/keys",
        "/sys/mounts",
        "/sys/policies",
        "/sys/auth",
        "/keys/import",
        "/keys/config",
        "/backup/",
        "/restore/",
    )
    for fragment in forbidden_endpoint_fragments:
        assert fragment not in source
