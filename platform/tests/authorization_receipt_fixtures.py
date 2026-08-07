"""Shared TB1 authorization receipt test helpers.

All signing key material is generated in memory at test time. The repository
stores no private key material; trust-store fixtures carry public verification
material only, inside temporary directories, and no private key value is ever
written to a repository path or printed.
"""

from __future__ import annotations

import base64
import importlib.util
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec, ed25519

ROOT = Path(__file__).resolve().parents[2]
CONTRACT_DIR = ROOT / "platform/roe-contract"

AUTHORIZATION_KEY_ID = "hermes-control-plane-tb1-ed25519"
AUTHORIZATION_KEY_ID_P256 = "hermes-control-plane-tb1-p256"
KEY_NOT_BEFORE = "2000-01-01T00:00:00Z"
KEY_NOT_AFTER = "2100-01-01T00:00:00Z"


def _stamp(offset_seconds: int) -> str:
    """Return a UTC timestamp relative to the test-session clock.

    The receipt validity window is deliberately short, so fixtures anchor on
    the real clock instead of a frozen literal date.
    """

    moment = _SESSION_NOW + timedelta(seconds=offset_seconds)
    return moment.isoformat(timespec="seconds").replace("+00:00", "Z")


_SESSION_NOW = datetime.now(timezone.utc).replace(microsecond=0)
DEFAULT_ISSUED_AT_OFFSET = -60
DEFAULT_EXPIRES_AT_OFFSET = 1500


def load_module(module_name: str, path: Path) -> Any:
    existing = sys.modules.get(module_name)
    if existing is not None:
        return existing
    spec = importlib.util.spec_from_file_location(module_name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


authorization_receipt = load_module(
    "authorization_receipt_under_test", CONTRACT_DIR / "authorization_receipt.py"
)


def public_der(private_key: Any) -> bytes:
    return private_key.public_key().public_bytes(
        encoding=serialization.Encoding.DER,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )


def authorization_trust_store(
    path: Path,
    private_key: Any,
    *,
    key_id: str = AUTHORIZATION_KEY_ID,
    algorithm: str = "Ed25519",
    state: str = "active",
    purpose: str = authorization_receipt.KEY_PURPOSE,
    document_purpose: str | None = None,
    not_before: str = KEY_NOT_BEFORE,
    not_after: str = KEY_NOT_AFTER,
) -> Path:
    """Write a purpose-bound authorization trust store (public keys only)."""

    document = {
        "schema_version": "1.0.0",
        "purpose": document_purpose if document_purpose is not None else purpose,
        "keys": [
            {
                "key_id": key_id,
                "algorithm": algorithm,
                "state": state,
                "purpose": purpose,
                "public_key": base64.b64encode(public_der(private_key)).decode("ascii"),
                "not_before": not_before,
                "not_after": not_after,
            }
        ],
    }
    path.write_text(json.dumps(document), encoding="utf-8")
    return path


def new_key(algorithm: str = "Ed25519") -> Any:
    if algorithm == "Ed25519":
        return ed25519.Ed25519PrivateKey.generate()
    return ec.generate_private_key(ec.SECP256R1())


def receipt_body(
    *,
    campaign_id: str,
    run_id: str,
    step_id: str,
    roe_contract_id: str,
    roe_contract_payload_sha256: str,
    roe_step_request_id: str,
    operation_id: str,
    operation_version: str,
    capability_id: str,
    target_sha256: str,
    intrusiveness_level: str,
    receipt_id: str = "hermes-authz-receipt-0001",
    authorization_id: str = "hermes-authz-0001",
    issuer_id: str = "hermes-control-plane",
    issued_at: str | None = None,
    expires_at: str | None = None,
) -> dict[str, Any]:
    """Return an unsigned receipt body without its ``authorization_ref``."""

    issued_at = issued_at or _stamp(DEFAULT_ISSUED_AT_OFFSET)
    expires_at = expires_at or _stamp(DEFAULT_EXPIRES_AT_OFFSET)
    return {
        "schema_version": authorization_receipt.SCHEMA_VERSION,
        "domain": authorization_receipt.AUTHORIZATION_DOMAIN,
        "receipt_id": receipt_id,
        "issuer": {
            "plane": "control-plane",
            "domain": authorization_receipt.CONTROL_PLANE_DOMAIN,
            "issuer_id": issuer_id,
        },
        "issued_at": issued_at,
        "expires_at": expires_at,
        "authorization": {
            "authorization_id": authorization_id,
            "campaign_id": campaign_id,
            "run_id": run_id,
            "step_id": step_id,
            "roe_contract_id": roe_contract_id,
            "roe_contract_payload_sha256": roe_contract_payload_sha256,
            "roe_step_request_id": roe_step_request_id,
            "operation_id": operation_id,
            "operation_version": operation_version,
            "capability_id": capability_id,
            "target_sha256": target_sha256,
            "intrusiveness_level": intrusiveness_level,
        },
    }


def issue_receipt(
    body: dict[str, Any],
    private_key: Any,
    *,
    key_id: str = AUTHORIZATION_KEY_ID,
    algorithm: str = "Ed25519",
    authorization_ref: str | None = None,
) -> dict[str, Any]:
    """Simulate control-plane issuance: compute the ref, then sign.

    This is a TEST issuer only. The repository ships no operational issuer and
    no private key: Hermes issuance runtime is ``NOT_IMPLEMENTED`` / ``NOT_RUN``.
    """

    receipt = {key: value for key, value in body.items() if key != "signature"}
    receipt.pop("authorization_ref", None)
    receipt["authorization_ref"] = (
        authorization_ref
        if authorization_ref is not None
        else authorization_receipt.compute_authorization_ref(receipt)
    )
    receipt.pop("signature", None)
    payload = authorization_receipt.canonical_payload(receipt)
    if algorithm == "Ed25519":
        raw = private_key.sign(payload)
    else:
        from cryptography.hazmat.primitives import hashes

        raw = private_key.sign(payload, ec.ECDSA(hashes.SHA256()))
    receipt["signature"] = {
        "algorithm": algorithm,
        "key_id": key_id,
        "payload_sha256": authorization_receipt.payload_sha256(receipt),
        "value": base64.b64encode(raw).decode("ascii"),
    }
    return receipt
