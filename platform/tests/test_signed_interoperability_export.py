from __future__ import annotations

import base64
import importlib.util
import json
import shutil
import subprocess
import sys
from pathlib import Path

import jsonschema
import pytest

ROOT = Path(__file__).resolve().parents[2]
INTEROP_DIR = ROOT / "platform" / "interoperability"

spec = importlib.util.spec_from_file_location("j02_signed_export_test", INTEROP_DIR / "signed_export.py")
assert spec and spec.loader
module = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = module
spec.loader.exec_module(module)

SignedExportError = module.SignedExportError
build_verified_signed_export = module.build_verified_signed_export
signing_message = module.signing_message
verify_signed_export = module.verify_signed_export

TARGET_SCHEMA = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "type": "object",
    "additionalProperties": False,
    "required": ["document_type", "results"],
    "properties": {"document_type": {"type": "string"}, "results": {"type": "array"}},
}
PAYLOAD = {"document_type": "synthetic", "results": [{"finding": "synthetic"}]}


def _keys_and_signature(tmp_path: Path, message: bytes) -> tuple[bytes, str]:
    openssl = shutil.which("openssl")
    if not openssl:
        pytest.skip("openssl is required for controlled Ed25519 verification")
    tmp_path.mkdir(parents=True, exist_ok=True)
    private_key = tmp_path / "private.pem"
    public_key = tmp_path / "public.pem"
    message_path = tmp_path / "message.bin"
    signature_path = tmp_path / "signature.bin"
    subprocess.run([openssl, "genpkey", "-algorithm", "ED25519", "-out", str(private_key)], check=True, capture_output=True)
    subprocess.run([openssl, "pkey", "-in", str(private_key), "-pubout", "-out", str(public_key)], check=True, capture_output=True)
    message_path.write_bytes(message)
    subprocess.run(
        [openssl, "pkeyutl", "-sign", "-inkey", str(private_key), "-rawin", "-in", str(message_path), "-out", str(signature_path)],
        check=True,
        capture_output=True,
    )
    return public_key.read_bytes(), base64.b64encode(signature_path.read_bytes()).decode("ascii")


def _signed(tmp_path: Path, format_id: str = "oscal-assessment-results"):
    kwargs = {
        "format_id": format_id,
        "payload": PAYLOAD,
        "target_schema": TARGET_SCHEMA,
        "target_schema_id": f"schema:{format_id}",
        "target_schema_version": "synthetic-profile-1",
        "data_markings": ["TLP:CLEAR"],
    }
    message = signing_message(**kwargs)
    public_key, signature_b64 = _keys_and_signature(tmp_path, message)
    envelope = build_verified_signed_export(
        **kwargs,
        signer="controlled-ci-signer",
        public_key_pem=public_key,
        signature_b64=signature_b64,
    )
    return envelope, public_key


@pytest.mark.parametrize("format_id", ["oscal-assessment-results", "oscal-poam", "cacao-2.0", "attack-flow"])
def test_all_formats_carry_verified_ed25519_signature_and_markings(tmp_path: Path, format_id: str) -> None:
    envelope, public_key = _signed(tmp_path / format_id, format_id)
    assert envelope["signature"]["algorithm"] == "Ed25519"
    assert envelope["signature"]["verified"] is True
    assert envelope["signature"]["value_b64"]
    assert envelope["data_markings"] == ["TLP:CLEAR"]
    assert envelope["execution_authority"] == "NONE"
    assert envelope["external_transport"] == "NOT_PERFORMED"
    assert verify_signed_export(envelope, target_schema=TARGET_SCHEMA, public_key_pem=public_key) is True
    schema = json.loads((INTEROP_DIR / "signed-export-envelope.schema.json").read_text())
    jsonschema.Draft202012Validator(schema).validate(envelope)


def test_json_round_trip_preserves_verifiable_signature(tmp_path: Path) -> None:
    envelope, public_key = _signed(tmp_path)
    reopened = json.loads(json.dumps(envelope, sort_keys=True))
    assert verify_signed_export(reopened, target_schema=TARGET_SCHEMA, public_key_pem=public_key) is True


def test_payload_tamper_invalidates_signature_and_digest(tmp_path: Path) -> None:
    envelope, public_key = _signed(tmp_path)
    envelope["payload"]["results"].append({"finding": "tampered"})
    assert verify_signed_export(envelope, target_schema=TARGET_SCHEMA, public_key_pem=public_key) is False


def test_data_marking_tamper_invalidates_signature(tmp_path: Path) -> None:
    envelope, public_key = _signed(tmp_path)
    envelope["data_markings"] = ["TLP:GREEN"]
    assert verify_signed_export(envelope, target_schema=TARGET_SCHEMA, public_key_pem=public_key) is False


def test_wrong_public_key_fails_closed(tmp_path: Path) -> None:
    envelope, _ = _signed(tmp_path / "first")
    kwargs = {
        "format_id": "oscal-assessment-results",
        "payload": PAYLOAD,
        "target_schema": TARGET_SCHEMA,
        "target_schema_id": "schema:oscal-assessment-results",
        "target_schema_version": "synthetic-profile-1",
        "data_markings": ["TLP:CLEAR"],
    }
    wrong_public_key, _ = _keys_and_signature(tmp_path / "second", signing_message(**kwargs))
    assert verify_signed_export(envelope, target_schema=TARGET_SCHEMA, public_key_pem=wrong_public_key) is False


def test_invalid_signature_is_refused_before_envelope_creation(tmp_path: Path) -> None:
    kwargs = {
        "format_id": "attack-flow",
        "payload": PAYLOAD,
        "target_schema": TARGET_SCHEMA,
        "target_schema_id": "schema:attack-flow",
        "target_schema_version": "synthetic-profile-1",
        "data_markings": ["TLP:CLEAR"],
    }
    public_key, _ = _keys_and_signature(tmp_path, signing_message(**kwargs))
    invalid = base64.b64encode(b"x" * 64).decode("ascii")
    with pytest.raises(SignedExportError):
        build_verified_signed_export(
            **kwargs,
            signer="controlled-ci-signer",
            public_key_pem=public_key,
            signature_b64=invalid,
        )
