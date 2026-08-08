from __future__ import annotations

import base64
import hashlib
import json
import shutil
import subprocess
import tempfile
from copy import deepcopy
from pathlib import Path
from typing import Any, Mapping

import jsonschema

FORMATS = {"oscal-assessment-results", "oscal-poam", "cacao-2.0", "attack-flow"}


class SignedExportError(ValueError):
    """Fail-closed controlled interoperability signing violation."""


def _canonical(value: Mapping[str, Any]) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")


def _validate_target(payload: Mapping[str, Any], target_schema: Mapping[str, Any]) -> None:
    if not isinstance(target_schema, Mapping) or not target_schema:
        raise SignedExportError("explicit target schema is required")
    try:
        jsonschema.Draft202012Validator.check_schema(target_schema)
        jsonschema.Draft202012Validator(target_schema).validate(dict(payload))
    except (jsonschema.SchemaError, jsonschema.ValidationError) as exc:
        raise SignedExportError("payload or target schema validation failed") from exc


def _unsigned_envelope(
    *,
    format_id: str,
    payload: Mapping[str, Any],
    target_schema_id: str,
    target_schema_version: str,
    data_markings: list[str],
) -> dict[str, Any]:
    if format_id not in FORMATS:
        raise SignedExportError("unsupported interoperability format")
    if not target_schema_id or not target_schema_version:
        raise SignedExportError("target schema id and version are required")
    if not data_markings or any(not isinstance(item, str) or not item for item in data_markings):
        raise SignedExportError("non-empty data markings are required")
    payload_value = deepcopy(dict(payload))
    return {
        "schema_version": "1.0",
        "format": format_id,
        "target_schema_id": target_schema_id,
        "target_schema_version": target_schema_version,
        "schema_validated": True,
        "data_markings": sorted(set(data_markings)),
        "payload_sha256": hashlib.sha256(_canonical(payload_value)).hexdigest(),
        "payload": payload_value,
    }


def signing_message(
    *,
    format_id: str,
    payload: Mapping[str, Any],
    target_schema: Mapping[str, Any],
    target_schema_id: str,
    target_schema_version: str,
    data_markings: list[str],
) -> bytes:
    _validate_target(payload, target_schema)
    return _canonical(
        _unsigned_envelope(
            format_id=format_id,
            payload=payload,
            target_schema_id=target_schema_id,
            target_schema_version=target_schema_version,
            data_markings=data_markings,
        )
    )


def _verify_ed25519(*, public_key_pem: bytes, message: bytes, signature: bytes) -> None:
    openssl = shutil.which("openssl")
    if not openssl:
        raise SignedExportError("openssl verifier is unavailable")
    if not public_key_pem.startswith(b"-----BEGIN PUBLIC KEY-----"):
        raise SignedExportError("PEM public key is required")
    if len(signature) != 64:
        raise SignedExportError("invalid Ed25519 signature length")
    with tempfile.TemporaryDirectory(prefix="hex0r-j02-") as temp:
        root = Path(temp)
        key_path = root / "public.pem"
        message_path = root / "message.bin"
        signature_path = root / "signature.bin"
        key_path.write_bytes(public_key_pem)
        message_path.write_bytes(message)
        signature_path.write_bytes(signature)
        result = subprocess.run(
            [
                openssl,
                "pkeyutl",
                "-verify",
                "-pubin",
                "-inkey",
                str(key_path),
                "-rawin",
                "-in",
                str(message_path),
                "-sigfile",
                str(signature_path),
            ],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=5,
            check=False,
            env={"PATH": str(Path(openssl).parent)},
        )
    if result.returncode != 0:
        raise SignedExportError("cryptographic signature verification failed")


def build_verified_signed_export(
    *,
    format_id: str,
    payload: Mapping[str, Any],
    target_schema: Mapping[str, Any],
    target_schema_id: str,
    target_schema_version: str,
    data_markings: list[str],
    signer: str,
    public_key_pem: bytes,
    signature_b64: str,
) -> dict[str, Any]:
    if not isinstance(signer, str) or not signer or len(signer) > 128:
        raise SignedExportError("bounded signer identity is required")
    message = signing_message(
        format_id=format_id,
        payload=payload,
        target_schema=target_schema,
        target_schema_id=target_schema_id,
        target_schema_version=target_schema_version,
        data_markings=data_markings,
    )
    try:
        signature = base64.b64decode(signature_b64, validate=True)
    except Exception as exc:
        raise SignedExportError("signature must be canonical base64") from exc
    _verify_ed25519(public_key_pem=public_key_pem, message=message, signature=signature)
    envelope = json.loads(message)
    envelope["signature"] = {
        "verified": True,
        "algorithm": "Ed25519",
        "signer": signer,
        "public_key_sha256": hashlib.sha256(public_key_pem).hexdigest(),
        "value_b64": base64.b64encode(signature).decode("ascii"),
    }
    envelope["execution_authority"] = "NONE"
    envelope["external_transport"] = "NOT_PERFORMED"
    return envelope


def verify_signed_export(
    envelope: Mapping[str, Any], *, target_schema: Mapping[str, Any], public_key_pem: bytes
) -> bool:
    try:
        if not isinstance(envelope, Mapping):
            return False
        if envelope.get("execution_authority") != "NONE" or envelope.get("external_transport") != "NOT_PERFORMED":
            return False
        signature = envelope.get("signature")
        if not isinstance(signature, Mapping):
            return False
        if signature.get("verified") is not True or signature.get("algorithm") != "Ed25519":
            return False
        if signature.get("public_key_sha256") != hashlib.sha256(public_key_pem).hexdigest():
            return False
        payload = envelope.get("payload")
        if not isinstance(payload, Mapping):
            return False
        _validate_target(payload, target_schema)
        unsigned = {
            key: deepcopy(envelope[key])
            for key in (
                "schema_version",
                "format",
                "target_schema_id",
                "target_schema_version",
                "schema_validated",
                "data_markings",
                "payload_sha256",
                "payload",
            )
        }
        if unsigned["payload_sha256"] != hashlib.sha256(_canonical(payload)).hexdigest():
            return False
        signature_bytes = base64.b64decode(str(signature.get("value_b64", "")), validate=True)
        _verify_ed25519(public_key_pem=public_key_pem, message=_canonical(unsigned), signature=signature_bytes)
        return True
    except (SignedExportError, ValueError, TypeError, KeyError):
        return False
