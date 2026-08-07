from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import jsonschema
import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
INTEROP_DIR = ROOT / "platform" / "interoperability"

spec = importlib.util.spec_from_file_location("interoperability", INTEROP_DIR / "interoperability.py")
assert spec and spec.loader
module = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = module
spec.loader.exec_module(module)

InteroperabilityError = module.InteroperabilityError
build_export = module.build_export
validate_target_schema = module.validate_target_schema

TARGET_SCHEMA = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "type": "object",
    "additionalProperties": False,
    "required": ["document_type", "results"],
    "properties": {
        "document_type": {"type": "string"},
        "results": {"type": "array"},
    },
}
PAYLOAD = {"document_type": "synthetic", "results": [{"finding": "synthetic"}]}
SIGNATURE_EVIDENCE = {"verified": True, "signer": "synthetic-signer", "algorithm": "synthetic-algorithm"}


@pytest.mark.parametrize("format_id", ["oscal-assessment-results", "oscal-poam", "cacao-2.0", "attack-flow"])
def test_each_supported_format_validates_against_explicit_target_schema(format_id: str) -> None:
    export = build_export(
        format_id=format_id,
        payload=PAYLOAD,
        target_schema=TARGET_SCHEMA,
        target_schema_id=f"schema:{format_id}",
        target_schema_version="synthetic-profile-1",
        data_markings=["TLP:CLEAR"],
        signature_evidence=SIGNATURE_EVIDENCE,
    )
    assert export["schema_validated"] is True
    assert export["format"] == format_id
    assert export["data_markings"] == ["TLP:CLEAR"]
    assert export["signature"]["verified"] is True
    envelope_schema = json.loads((INTEROP_DIR / "export-envelope.schema.json").read_text())
    jsonschema.Draft202012Validator(envelope_schema).validate(export)


def test_invalid_target_payload_fails_closed() -> None:
    with pytest.raises(InteroperabilityError):
        validate_target_schema(payload={"document_type": "synthetic"}, target_schema=TARGET_SCHEMA)


def test_invalid_target_schema_fails_closed() -> None:
    with pytest.raises(InteroperabilityError):
        validate_target_schema(payload=PAYLOAD, target_schema={"type": "not-a-valid-json-schema-type"})


def test_missing_data_markings_are_rejected() -> None:
    with pytest.raises(InteroperabilityError):
        build_export(
            format_id="oscal-assessment-results",
            payload=PAYLOAD,
            target_schema=TARGET_SCHEMA,
            target_schema_id="schema:synthetic",
            target_schema_version="1",
            data_markings=[],
            signature_evidence=SIGNATURE_EVIDENCE,
        )


def test_unverified_signature_evidence_is_rejected() -> None:
    with pytest.raises(InteroperabilityError):
        build_export(
            format_id="cacao-2.0",
            payload=PAYLOAD,
            target_schema=TARGET_SCHEMA,
            target_schema_id="schema:synthetic",
            target_schema_version="1",
            data_markings=["TLP:CLEAR"],
            signature_evidence={"verified": False, "signer": "synthetic-signer", "algorithm": "synthetic-algorithm"},
        )


def test_runtime_nonclaims_are_preserved() -> None:
    policy = yaml.safe_load((INTEROP_DIR / "interoperability-policy.yaml").read_text())
    assert policy["validation"]["explicit_target_schema_required"] is True
    assert policy["signature"]["verified_evidence_required"] is True
    assert policy["runtime_status"] == {
        "authoritative_schema_fetch": "NOT_IMPLEMENTED",
        "cryptographic_signing": "NOT_RUN",
        "external_transport": "NOT_RUN",
        "oscal_export_delivery": "NOT_RUN",
        "cacao_export_delivery": "NOT_RUN",
        "attack_flow_export_delivery": "NOT_RUN",
    }
