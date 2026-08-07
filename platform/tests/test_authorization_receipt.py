"""TB1 control-plane authorization receipt contract tests.

Signing keys are generated in memory and only public verification material is
written to temporary trust stores. No runtime, target, network or runner is
used by this suite.
"""

from __future__ import annotations

import base64
import copy
import importlib.util
import json
import sys
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec, ed25519

ROOT = Path(__file__).resolve().parents[2]
AUTH_DIR = ROOT / "platform/authorization-contract"


def _load() -> Any:
    spec = importlib.util.spec_from_file_location(
        "authorization_receipt_under_test", AUTH_DIR / "authorization_receipt.py"
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


auth = _load()

CAMPAIGN_ID = "3f2a1c64-1e8b-4a2b-9c7d-1c2b3a4d5e6f"
RUN_ID = "5c9d7e2a-8b41-4f6d-9a03-2d4e6f8a1b2c"
STEP_ID = "7b1e4d3c-2a95-4c8e-8f10-3e5d7c9b1a24"
KEY_ID = "tb1-authorization-ed25519-test"
TARGET_DIGEST = "a" * 64
ROE_DIGEST = "b" * 64


def _iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat(timespec="seconds").replace(
        "+00:00", "Z"
    )


def _public_der(private_key: Any) -> str:
    der = private_key.public_key().public_bytes(
        encoding=serialization.Encoding.DER,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    return base64.b64encode(der).decode("ascii")


def _trust_store(
    tmp_path: Path,
    private_key: Any,
    *,
    state: str = "active",
    purpose: str = "tb1-authorization",
    domain: str = "hex0r.tb1.authorization.v1",
    not_before: datetime | None = None,
    not_after: datetime | None = None,
    algorithm: str = "Ed25519",
) -> Path:
    entry: dict[str, Any] = {
        "key_id": KEY_ID,
        "algorithm": algorithm,
        "state": state,
        "purpose": purpose,
        "public_key": _public_der(private_key),
    }
    if not_before is not None:
        entry["not_before"] = _iso(not_before)
    if not_after is not None:
        entry["not_after"] = _iso(not_after)
    path = tmp_path / "authorization-trust-store.json"
    path.write_text(
        json.dumps(
            {
                "schema_version": "1.0.0",
                "domain": domain,
                "purpose": purpose,
                "keys": [entry],
            }
        ),
        encoding="utf-8",
    )
    return path


def _receipt(private_key: Any, **overrides: Any) -> dict[str, Any]:
    now = datetime.now(timezone.utc)
    receipt: dict[str, Any] = {
        "schema_version": "1.0.0",
        "domain": "hex0r.tb1.authorization.v1",
        "issuer": "hermes-control-plane",
        "authorization_id": str(uuid.uuid4()),
        "issued_at": _iso(now - timedelta(seconds=30)),
        "expires_at": _iso(now + timedelta(minutes=5)),
        "campaign_id": CAMPAIGN_ID,
        "run_id": RUN_ID,
        "step_id": STEP_ID,
        "roe_contract_id": "roe-contract-test-001",
        "roe_contract_payload_sha256": ROE_DIGEST,
        "roe_step_request_id": "roe-step-test-001",
        "operation_id": "web.discovery.headers",
        "operation_version": "1.0.0",
        "capability_id": "web.discovery.headers",
        "target_sha256": TARGET_DIGEST,
        "intrusiveness_level": "L1",
    }
    receipt.update(overrides)
    receipt["authorization_ref"] = auth.build_authorization_ref(receipt)
    receipt["signature"] = {
        "algorithm": "Ed25519",
        "key_id": KEY_ID,
        "value": base64.b64encode(
            private_key.sign(auth.canonical_signed_payload(receipt))
        ).decode("ascii"),
    }
    return receipt


def _resign(receipt: dict[str, Any], private_key: Any) -> dict[str, Any]:
    updated = copy.deepcopy(receipt)
    updated.pop("signature", None)
    updated.pop("authorization_ref", None)
    updated["authorization_ref"] = auth.build_authorization_ref(updated)
    updated["signature"] = {
        "algorithm": "Ed25519",
        "key_id": KEY_ID,
        "value": base64.b64encode(
            private_key.sign(auth.canonical_signed_payload(updated))
        ).decode("ascii"),
    }
    return updated


def test_valid_receipt_verifies_and_returns_sanitized_metadata(tmp_path: Path) -> None:
    key = ed25519.Ed25519PrivateKey.generate()
    store = _trust_store(tmp_path, key)
    receipt = _receipt(key)

    verified = auth.verify_authorization_receipt(receipt, store)

    assert verified.authorization_ref == receipt["authorization_ref"]
    assert verified.campaign_id == CAMPAIGN_ID
    assert verified.target_sha256 == TARGET_DIGEST
    assert not hasattr(verified, "target")
    assert not hasattr(verified, "parameters")
    assert "signature" not in repr(verified).lower()


def test_reference_is_domain_separated_and_deterministic() -> None:
    key = ed25519.Ed25519PrivateKey.generate()
    receipt = _receipt(key)
    assert receipt["authorization_ref"].startswith("tb1-authz:v1:")
    assert auth.build_authorization_ref(receipt) == receipt["authorization_ref"]


def test_attempt_id_is_not_part_of_receipt_schema_or_reference() -> None:
    key = ed25519.Ed25519PrivateKey.generate()
    receipt = _receipt(key)
    assert "attempt_id" not in receipt
    assert "attempt_id" not in auth.authorization_body(receipt)


@pytest.mark.parametrize(
    "mutation, expected",
    [
        (lambda r: r.__setitem__("authorization_ref", "tb1-authz:v1:" + "0" * 64), "AUTHORIZATION_REF_MISMATCH"),
        (lambda r: r.__setitem__("target_sha256", "c" * 64), "AUTHORIZATION_REF_MISMATCH"),
        (lambda r: r.__setitem__("operation_id", "web.discovery.tls"), "AUTHORIZATION_REF_MISMATCH"),
    ],
)
def test_unsigned_body_or_reference_tampering_fails_closed(
    tmp_path: Path, mutation, expected: str
) -> None:
    key = ed25519.Ed25519PrivateKey.generate()
    store = _trust_store(tmp_path, key)
    receipt = _receipt(key)
    mutation(receipt)
    with pytest.raises(auth.AuthorizationReceiptError, match=expected):
        auth.verify_authorization_receipt(receipt, store)


def test_valid_ref_with_forged_signature_is_refused(tmp_path: Path) -> None:
    key = ed25519.Ed25519PrivateKey.generate()
    other = ed25519.Ed25519PrivateKey.generate()
    store = _trust_store(tmp_path, key)
    receipt = _receipt(key)
    receipt["signature"]["value"] = base64.b64encode(
        other.sign(auth.canonical_signed_payload(receipt))
    ).decode("ascii")
    with pytest.raises(auth.AuthorizationReceiptError, match="AUTH_SIGNATURE_INVALID"):
        auth.verify_authorization_receipt(receipt, store)


def test_missing_trust_store_fails_closed() -> None:
    key = ed25519.Ed25519PrivateKey.generate()
    with pytest.raises(auth.AuthorizationReceiptError, match="AUTH_TRUST_STORE_REQUIRED"):
        auth.verify_authorization_receipt(_receipt(key), None)


def test_unavailable_trust_store_fails_closed(tmp_path: Path) -> None:
    key = ed25519.Ed25519PrivateKey.generate()
    with pytest.raises(
        auth.AuthorizationReceiptError, match="AUTH_TRUST_STORE_UNAVAILABLE"
    ):
        auth.verify_authorization_receipt(_receipt(key), tmp_path / "missing.json")


@pytest.mark.parametrize(
    "state, expected",
    [
        ("revoked", "AUTH_SIGNATURE_KEY_REVOKED"),
        ("retired", "AUTH_SIGNATURE_KEY_NOT_ACTIVE"),
    ],
)
def test_non_active_authorization_keys_are_refused(
    tmp_path: Path, state: str, expected: str
) -> None:
    key = ed25519.Ed25519PrivateKey.generate()
    store = _trust_store(tmp_path, key, state=state)
    with pytest.raises(auth.AuthorizationReceiptError, match=expected):
        auth.verify_authorization_receipt(_receipt(key), store)


def test_not_yet_valid_authorization_key_is_refused(tmp_path: Path) -> None:
    key = ed25519.Ed25519PrivateKey.generate()
    now = datetime.now(timezone.utc)
    store = _trust_store(tmp_path, key, not_before=now + timedelta(hours=1))
    with pytest.raises(
        auth.AuthorizationReceiptError, match="AUTH_SIGNATURE_KEY_NOT_YET_VALID"
    ):
        auth.verify_authorization_receipt(_receipt(key), store)


def test_expired_authorization_key_is_refused(tmp_path: Path) -> None:
    key = ed25519.Ed25519PrivateKey.generate()
    now = datetime.now(timezone.utc)
    store = _trust_store(tmp_path, key, not_after=now - timedelta(seconds=1))
    with pytest.raises(
        auth.AuthorizationReceiptError, match="AUTH_SIGNATURE_KEY_EXPIRED"
    ):
        auth.verify_authorization_receipt(_receipt(key), store)


def test_unknown_authorization_key_is_refused(tmp_path: Path) -> None:
    key = ed25519.Ed25519PrivateKey.generate()
    other = ed25519.Ed25519PrivateKey.generate()
    store = _trust_store(tmp_path, other)
    receipt = _receipt(key)
    with pytest.raises(auth.AuthorizationReceiptError, match="AUTH_SIGNATURE_INVALID"):
        auth.verify_authorization_receipt(receipt, store)


def test_roe_style_trust_store_cannot_be_reused_for_tb1(tmp_path: Path) -> None:
    key = ed25519.Ed25519PrivateKey.generate()
    path = tmp_path / "roe-trust-store.json"
    path.write_text(
        json.dumps(
            {
                "schema_version": "1.0.0",
                "keys": [
                    {
                        "key_id": KEY_ID,
                        "algorithm": "Ed25519",
                        "state": "active",
                        "public_key": _public_der(key),
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(auth.AuthorizationReceiptError, match="AUTH_TRUST_STORE_INVALID"):
        auth.verify_authorization_receipt(_receipt(key), path)


def test_wrong_purpose_authorization_store_is_refused(tmp_path: Path) -> None:
    key = ed25519.Ed25519PrivateKey.generate()
    store = _trust_store(tmp_path, key, purpose="roe-signing")
    with pytest.raises(auth.AuthorizationReceiptError):
        auth.verify_authorization_receipt(_receipt(key), store)


def test_private_key_like_material_in_store_is_rejected(tmp_path: Path) -> None:
    key = ed25519.Ed25519PrivateKey.generate()
    path = _trust_store(tmp_path, key)
    doc = json.loads(path.read_text(encoding="utf-8"))
    doc["keys"][0]["private_key"] = "forbidden-test-marker"
    path.write_text(json.dumps(doc), encoding="utf-8")
    with pytest.raises(auth.AuthorizationReceiptError, match="AUTH_SECRET_MATERIAL"):
        auth.verify_authorization_receipt(_receipt(key), path)


def test_expired_receipt_is_refused(tmp_path: Path) -> None:
    key = ed25519.Ed25519PrivateKey.generate()
    store = _trust_store(tmp_path, key)
    now = datetime.now(timezone.utc)
    receipt = _receipt(
        key,
        issued_at=_iso(now - timedelta(minutes=5)),
        expires_at=_iso(now - timedelta(seconds=1)),
    )
    with pytest.raises(auth.AuthorizationReceiptError, match="AUTH_RECEIPT_EXPIRED"):
        auth.verify_authorization_receipt(receipt, store)


def test_not_yet_valid_receipt_is_refused(tmp_path: Path) -> None:
    key = ed25519.Ed25519PrivateKey.generate()
    store = _trust_store(tmp_path, key)
    now = datetime.now(timezone.utc)
    receipt = _receipt(
        key,
        issued_at=_iso(now + timedelta(minutes=1)),
        expires_at=_iso(now + timedelta(minutes=5)),
    )
    with pytest.raises(
        auth.AuthorizationReceiptError, match="AUTH_RECEIPT_NOT_YET_VALID"
    ):
        auth.verify_authorization_receipt(receipt, store)


def test_receipt_lifetime_over_fifteen_minutes_is_refused(tmp_path: Path) -> None:
    key = ed25519.Ed25519PrivateKey.generate()
    store = _trust_store(tmp_path, key)
    now = datetime.now(timezone.utc)
    receipt = _receipt(
        key,
        issued_at=_iso(now - timedelta(seconds=1)),
        expires_at=_iso(now + timedelta(minutes=16)),
    )
    with pytest.raises(
        auth.AuthorizationReceiptError, match="AUTH_RECEIPT_LIFETIME_EXCEEDED"
    ):
        auth.verify_authorization_receipt(receipt, store)


def test_ecdsa_p256_receipt_verifies(tmp_path: Path) -> None:
    key = ec.generate_private_key(ec.SECP256R1())
    store = _trust_store(tmp_path, key, algorithm="ECDSA-P256-SHA256")
    receipt = _receipt(ed25519.Ed25519PrivateKey.generate())
    receipt.pop("signature")
    receipt["authorization_ref"] = auth.build_authorization_ref(receipt)
    from cryptography.hazmat.primitives import hashes
    receipt["signature"] = {
        "algorithm": "ECDSA-P256-SHA256",
        "key_id": KEY_ID,
        "value": base64.b64encode(
            key.sign(auth.canonical_signed_payload(receipt), ec.ECDSA(hashes.SHA256()))
        ).decode("ascii"),
    }
    verified = auth.verify_authorization_receipt(receipt, store)
    assert verified.authorization_ref == receipt["authorization_ref"]


def test_resigned_change_produces_a_different_control_plane_reference() -> None:
    key = ed25519.Ed25519PrivateKey.generate()
    receipt = _receipt(key)
    changed = copy.deepcopy(receipt)
    changed["run_id"] = "2e5a7b93-6f84-4d3a-8b19-7c9d1e3f5a68"
    changed = _resign(changed, key)
    assert changed["authorization_ref"] != receipt["authorization_ref"]
