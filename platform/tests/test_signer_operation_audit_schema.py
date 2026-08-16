from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path

import jsonschema
import pytest

ROOT = Path(__file__).resolve().parents[2]
SCHEMA_PATH = ROOT / "platform/schemas/signer-operation-audit.schema.json"


def _event() -> dict:
    return {
        "schema_version": "signer-operation-audit/v1",
        "operation": "SIGN",
        "request_digest_sha256": "a" * 64,
        "purpose": "tb1-authorization",
        "domain": "hex0r.tb1.authorization.v1",
        "request_correlation_id": "corr-001",
        "signature_sha256": "b" * 64,
        "key_id": "key-001",
        "algorithm": "Ed25519",
        "public_key_spki_sha256": "c" * 64,
        "signer_class": "VAULT",
        "authority": "EXTERNAL_CUSTODY",
        "audit_ref": "evidence://signer/audit-001",
        "principal": "hermes-assurance",
        "provider_ref": "provider-ref-001",
        "test_only": False,
        "promotion_allowed": False,
        "runtime_status": "NOT_RUN",
        "execution_authority": "NONE",
    }


def _schema() -> dict:
    assert SCHEMA_PATH.exists(), "signer-operation-audit schema is not implemented yet"
    return json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))


def test_canonical_event_validates_against_closed_public_schema() -> None:
    jsonschema.validate(_event(), _schema())


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("schema_version", "signer-operation-audit/v2"),
        ("operation", "VERIFY"),
        ("request_digest_sha256", "A" * 64),
        ("purpose", "arbitrary-signing"),
        ("domain", "arbitrary.domain"),
        ("request_correlation_id", "corr\n001"),
        ("signature_sha256", "b" * 63),
        ("algorithm", "RSA"),
        ("public_key_spki_sha256", "C" * 64),
        ("signer_class", "PKCS11"),
        ("audit_ref", "file:///tmp/audit.json"),
        ("principal", ""),
        ("provider_ref", ""),
        ("promotion_allowed", True),
        ("runtime_status", "RUNNING"),
        ("execution_authority", "RUNNER"),
    ],
)
def test_schema_refuses_noncanonical_or_authority_elevating_values(
    field: str, value: object
) -> None:
    event = deepcopy(_event())
    event[field] = value
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(event, _schema())


def test_schema_requires_attribution_fields() -> None:
    for field in ("principal", "provider_ref", "request_correlation_id"):
        event = deepcopy(_event())
        event.pop(field)
        with pytest.raises(jsonschema.ValidationError):
            jsonschema.validate(event, _schema())


@pytest.mark.parametrize("forbidden", ["private_key", "secret", "token", "credential", "payload", "signature_b64"])
def test_schema_is_closed_to_secret_raw_or_unknown_fields(forbidden: str) -> None:
    event = deepcopy(_event())
    event[forbidden] = "forbidden"
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(event, _schema())
