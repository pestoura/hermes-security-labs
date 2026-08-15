from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path

import jsonschema
import pytest

ROOT = Path(__file__).resolve().parents[2]
SCHEMA_PATH = ROOT / "platform/schemas/signer-trust-manifest.schema.json"


def _manifest() -> dict:
    return {
        "manifest_id": "stm_" + "a" * 32,
        "schema_version": "signer-trust-manifest/v1",
        "provider_kind": "VAULT",
        "provider_ref": "vault://hermes/transit/tb1",
        "key_id": "vault-key-1",
        "algorithm": "Ed25519",
        "public_key_spki_sha256": "b" * 64,
        "attestation_id": "attestation-001",
        "observed_at": "2026-08-15T21:59:45Z",
        "source_evidence_ref": "evidence://signer/provider-observation.json",
        "source_evidence_sha256": "c" * 64,
        "generation_id": "tsg_" + "d" * 32,
        "generation_sequence": 1,
        "trust_store_sha256": "e" * 64,
        "lifecycle_decision": "ACCEPT_FOR_REVIEW",
        "trust_binding_allowed": False,
        "automatic_activation": False,
        "activation_effect": "NONE",
        "authorization_effect": "NONE",
        "execution_authority": "NONE",
        "promotion_allowed": False,
        "runtime_status": "NOT_RUN",
    }


def _schema() -> dict:
    assert SCHEMA_PATH.exists(), "signer-trust-manifest schema is not implemented yet"
    return json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))


def test_manifest_shape_validates_against_public_schema() -> None:
    jsonschema.validate(_manifest(), _schema())


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("provider_kind", "PKCS11"),
        ("algorithm", "RSA"),
        ("public_key_spki_sha256", "B" * 64),
        ("source_evidence_ref", "file:///tmp/evidence.json"),
        ("lifecycle_decision", "REFUSE"),
        ("trust_binding_allowed", True),
        ("automatic_activation", True),
        ("activation_effect", "ACTIVE"),
        ("authorization_effect", "GRANT"),
        ("execution_authority", "RUNNER"),
        ("promotion_allowed", True),
        ("runtime_status", "RUNNING"),
    ],
)
def test_schema_refuses_authority_or_noncanonical_identity(field: str, value: object) -> None:
    manifest = deepcopy(_manifest())
    manifest[field] = value
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(manifest, _schema())


def test_schema_is_closed_to_unknown_fields() -> None:
    manifest = _manifest()
    manifest["private_key"] = "forbidden"
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(manifest, _schema())
