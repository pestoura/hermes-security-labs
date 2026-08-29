#!/usr/bin/env python3
"""Tests for sanitized shared-Vault signer provider observations."""

from __future__ import annotations

import base64
import io
import json
import hashlib
import importlib.util
import sys
from pathlib import Path

import pytest
import yaml
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

ROOT = Path(__file__).resolve().parents[2]
MODULE = ROOT / "deployment/shared-vault-hsl/signer-evidence/vault_provider_observation.py"
SCHEMA = ROOT / "deployment/shared-vault-hsl/signer-evidence/provider-observation.schema.json"
TEMPLATE = ROOT / "deployment/shared-vault-hsl/signer-evidence/templates/provider-observation.example.yaml"


def _load_module():
    spec = importlib.util.spec_from_file_location("hsl_vault_provider_observation_test", MODULE)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _public_key_pem() -> str:
    key = Ed25519PrivateKey.from_private_bytes(b"\x91" * 32).public_key()
    return key.public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    ).decode("ascii")


def _raw_key_response(**overrides):
    data = {
        "name": "hsl-signing",
        "type": "ed25519",
        "supports_signing": True,
        "derived": False,
        "exportable": False,
        "allow_plaintext_backup": False,
        "keys": {"3": {"public_key": _public_key_pem()}},
    }
    data.update(overrides)
    return {"data": data}


def _checks(**overrides):
    value = {
        "key_read_passed": True,
        "sign_verify_passed": True,
        "negative_sys_passed": True,
        "negative_auth_passed": True,
        "audit_attribution_passed": True,
        "no_secret_material_persisted": True,
    }
    value.update(overrides)
    return value


def _evidence(ref: str, fill: str) -> dict[str, str]:
    return {"ref": ref, "sha256": fill * 64}


def _normalize(module, raw=None, checks=None):
    return module.normalize_provider_observation(
        _raw_key_response() if raw is None else raw,
        observed_at="2026-08-29T22:45:00Z",
        capability_checks=_checks() if checks is None else checks,
        bootstrap_evidence=_evidence("evidence://signer/secret-zero-20260829.yaml", "a"),
        audit_evidence=_evidence("evidence://signer/vault-audit-20260829.json", "b"),
    )


def test_valid_observation_derives_exact_public_identity() -> None:
    module = _load_module()
    result = _normalize(module)
    public_key = serialization.load_pem_public_key(_public_key_pem().encode("ascii"))
    der = public_key.public_bytes(
        encoding=serialization.Encoding.DER,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    assert result["state"] == "OBSERVED"
    assert result["provider_kind"] == "VAULT"
    assert result["provider_ref"] == "https://hermes-vault:8200/hsl-transit/hsl-signing"
    assert result["key_id"] == "vault:hsl-transit:hsl-signing:v3"
    assert result["algorithm"] == "Ed25519"
    assert result["public_key_spki_b64"] == base64.b64encode(der).decode("ascii")
    assert result["public_key_spki_sha256"] == hashlib.sha256(der).hexdigest()
    assert result["key_state"] == "active"
    assert result["signing_enabled"] is True
    assert result["private_key_exportable"] is False
    assert result["allow_plaintext_backup"] is False
    assert result["capability_checks"] == _checks()
    assert result["trust_binding_allowed"] is False
    assert result["promotion_allowed"] is False
    assert result["execution_authority"] == "NONE"
    assert result["runtime_status"] == "NOT_RUN"


def test_observation_schema_accepts_normalized_result() -> None:
    module = _load_module()
    result = _normalize(module)
    module.validate_provider_observation(result, schema_path=SCHEMA)


@pytest.mark.parametrize(
    "field,value,code",
    [
        ("exportable", True, "VAULT_KEY_NOT_ADMISSIBLE"),
        ("allow_plaintext_backup", True, "VAULT_KEY_NOT_ADMISSIBLE"),
        ("supports_signing", False, "VAULT_KEY_NOT_ADMISSIBLE"),
        ("derived", True, "VAULT_KEY_NOT_ADMISSIBLE"),
        ("type", "ecdsa-p256", "VAULT_KEY_NOT_ADMISSIBLE"),
        ("name", "other-key", "VAULT_KEY_NOT_ADMISSIBLE"),
    ],
)
def test_non_admissible_key_metadata_fails_closed(field, value, code) -> None:
    module = _load_module()
    with pytest.raises(module.ProviderObservationError) as exc:
        _normalize(module, raw=_raw_key_response(**{field: value}))
    assert exc.value.code == code


def test_secret_like_material_anywhere_in_raw_response_is_refused() -> None:
    module = _load_module()
    raw = _raw_key_response()
    raw["auth"] = {"client_token": "must-never-cross-boundary"}
    with pytest.raises(module.ProviderObservationError) as exc:
        _normalize(module, raw=raw)
    assert exc.value.code == "PROVIDER_OBSERVATION_SECRET_MATERIAL_REFUSED"


def test_all_capability_checks_must_pass() -> None:
    module = _load_module()
    with pytest.raises(module.ProviderObservationError) as exc:
        _normalize(module, checks=_checks(audit_attribution_passed=False))
    assert exc.value.code == "PROVIDER_CAPABILITY_CHECKS_FAILED"


def test_evidence_refs_and_digests_fail_closed() -> None:
    module = _load_module()
    with pytest.raises(module.ProviderObservationError) as exc:
        module.normalize_provider_observation(
            _raw_key_response(),
            observed_at="2026-08-29T22:45:00Z",
            capability_checks=_checks(),
            bootstrap_evidence={"ref": "/tmp/raw", "sha256": "a" * 64},
            audit_evidence=_evidence("evidence://signer/audit.json", "b"),
        )
    assert exc.value.code == "PROVIDER_EVIDENCE_INVALID"


def test_module_has_no_secret_persistence_surface() -> None:
    source = MODULE.read_text(encoding="utf-8")
    for banned in ("VAULT_TOKEN", "SecretID", "RoleID", "wrapping_token", "write_text(", "write_bytes("):
        assert banned not in source


def test_not_run_example_is_schema_valid_and_non_authoritative() -> None:
    module = _load_module()
    document = yaml.safe_load(TEMPLATE.read_text(encoding="utf-8"))
    module.validate_provider_observation(document, schema_path=SCHEMA)
    assert document["state"] == "NOT_RUN"
    assert document["promotion_allowed"] is False
    assert document["execution_authority"] == "NONE"


def test_cli_normalizes_public_stdin_without_provider_credentials() -> None:
    module = _load_module()
    stdout = io.StringIO()
    stderr = io.StringIO()
    args = [
        "normalize", "--observed-at", "2026-08-29T22:45:00Z",
        "--bootstrap-ref", "evidence://signer/bootstrap.json", "--bootstrap-sha256", "a" * 64,
        "--audit-ref", "evidence://signer/audit.json", "--audit-sha256", "b" * 64,
        "--key-read-passed", "--sign-verify-passed", "--negative-sys-passed",
        "--negative-auth-passed", "--audit-attribution-passed", "--no-secret-material-persisted",
    ]
    rc = module.main(args, stdin=io.StringIO(json.dumps(_raw_key_response())), stdout=stdout, stderr=stderr)
    assert rc == 0
    document = json.loads(stdout.getvalue())
    assert document["state"] == "OBSERVED"
    assert document["key_id"] == "vault:hsl-transit:hsl-signing:v3"
    assert stderr.getvalue() == ""
