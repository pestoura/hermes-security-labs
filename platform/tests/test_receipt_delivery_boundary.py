"""Repository-only tests for the trusted TB1 receipt delivery boundary.

No socket is opened, no process is started, no target is contacted and no
authorization is issued. Signature material is generated locally per test.
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
from cryptography.hazmat.primitives.asymmetric import ed25519

ROOT = Path(__file__).resolve().parents[2]
DELIVERY_PATH = ROOT / "platform" / "runner-authorization" / "receipt_delivery.py"
DELIVERY_POLICY_PATH = ROOT / "platform" / "runner-authorization" / "receipt-delivery-policy.yaml"


def _load(name: str, path: Path) -> Any:
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


delivery_module = _load("receipt_delivery_test", DELIVERY_PATH)
resolver_module = delivery_module.resolver_module
auth = delivery_module.authorization_contract

CAMPAIGN_ID = "3f2a1c64-1e8b-4a2b-9c7d-1c2b3a4d5e6f"
RUN_ID = "5c9d7e2a-8b41-4f6d-9a03-2d4e6f8a1b2c"
STEP_ID = "7b1e4d3c-2a95-4c8e-8f10-3e5d7c9b1a24"
KEY_ID = "tb1-delivery-ed25519-fixture"
TARGET_DIGEST = "a" * 64
ROE_DIGEST = "b" * 64
PARAMETERS_DIGEST = auth.canonical_parameters_sha256({"follow_redirects": False})

PEER_PRINCIPAL = "hexor.control-plane"
PEER_UID = 4242
PEER = {"uid": PEER_UID, "principal": PEER_PRINCIPAL}


def _iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _public_der(private_key: Any) -> str:
    der = private_key.public_key().public_bytes(
        encoding=serialization.Encoding.DER,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    return base64.b64encode(der).decode("ascii")


def _trust_store(tmp_path: Path, private_key: Any) -> Path:
    path = tmp_path / "trust-store.json"
    path.write_text(
        json.dumps(
            {
                "schema_version": "1.0.0",
                "domain": "hex0r.tb1.authorization.v1",
                "purpose": "tb1-authorization",
                "keys": [
                    {
                        "key_id": KEY_ID,
                        "algorithm": "Ed25519",
                        "state": "active",
                        "purpose": "tb1-authorization",
                        "public_key": _public_der(private_key),
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    return path


def _receipt(
    private_key: Any,
    *,
    capability: str = "web.discovery.headers",
    expires_at: datetime | None = None,
) -> dict[str, Any]:
    now = datetime.now(timezone.utc)
    receipt: dict[str, Any] = {
        "schema_version": "1.0.0",
        "domain": "hex0r.tb1.authorization.v1",
        "issuer": "hermes-control-plane",
        "authorization_id": str(uuid.uuid4()),
        "issued_at": _iso(now - timedelta(seconds=30)),
        "expires_at": _iso(expires_at or (now + timedelta(minutes=5))),
        "campaign_id": CAMPAIGN_ID,
        "run_id": RUN_ID,
        "step_id": STEP_ID,
        "roe_contract_id": "roe-contract-delivery-fixture",
        "roe_contract_payload_sha256": ROE_DIGEST,
        "roe_step_request_id": "roe-step-delivery-fixture",
        "operation_id": capability,
        "operation_version": "1.0.0",
        "operation_parameters_sha256": PARAMETERS_DIGEST,
        "capability_id": capability,
        "target_sha256": TARGET_DIGEST,
        "intrusiveness_level": "L1",
    }
    receipt["authorization_ref"] = auth.build_authorization_ref(receipt)
    receipt["signature"] = {
        "algorithm": "Ed25519",
        "key_id": KEY_ID,
        "value": base64.b64encode(
            private_key.sign(auth.canonical_signed_payload(receipt))
        ).decode("ascii"),
    }
    return receipt


def _enabled_resolver_policy(trust_store: Path) -> dict[str, Any]:
    return {
        "schema_version": "1.0",
        "policy_id": "hexor.runner.authorization.resolver",
        "state": "ENABLED",
        "default": "deny",
        "runtime_status": "NOT_RUN",
        "execution_authority": "none",
        "verification_source": "platform/authorization-contract/authorization_receipt.py",
        "trust_store_path": str(trust_store.resolve()),
        "cache": {"mode": "memory-only", "max_entries": 256, "persistence": "none"},
    }


def _enabled_delivery_policy() -> dict[str, Any]:
    return {
        "schema_version": "1.0",
        "policy_id": "hexor.runner.authorization.receipt-delivery",
        "state": "ENABLED",
        "default": "deny",
        "runtime_status": "NOT_RUN",
        "execution_authority": "none",
        "issuer": "hermes-control-plane",
        "channel": {
            "kind": "local-authenticated",
            "transport": "af_unix-peercred",
            "socket_path": "/run/hexor/runner-authz.sock",
            "allowed_peer_principal": PEER_PRINCIPAL,
            "allowed_peer_uid": PEER_UID,
            "require_monotonic_sequence": True,
        },
        "runner_private_key": "forbidden",
        "persistence": "none",
        "restart_behaviour": "fail-closed-empty",
    }


def _envelope(receipt: dict[str, Any], *, sequence: int = 1) -> dict[str, Any]:
    return {
        "schema_version": "1.0",
        "issuer": "hermes-control-plane",
        "sequence": sequence,
        "receipt": receipt,
    }


def _wired(tmp_path: Path) -> tuple[Any, Any, Any]:
    key = ed25519.Ed25519PrivateKey.generate()
    store = _trust_store(tmp_path, key)
    resolver = resolver_module.VerifiedAuthorizationResolver(_enabled_resolver_policy(store))
    delivery = delivery_module.TrustedReceiptDelivery(_enabled_delivery_policy(), resolver)
    return key, resolver, delivery


# --------------------------------------------------------------- canonical state


def test_committed_delivery_policy_is_disabled_and_not_run() -> None:
    policy = delivery_module.load_policy()
    assert delivery_module.validate_policy(policy) == []
    assert policy["state"] == "DISABLED"
    assert policy["default"] == "deny"
    assert policy["runtime_status"] == "NOT_RUN"
    assert policy["execution_authority"] == "none"
    assert policy["issuer"] == auth.ISSUER
    assert policy["runner_private_key"] == "forbidden"
    assert policy["persistence"] == "none"
    assert policy["restart_behaviour"] == "fail-closed-empty"
    assert policy["channel"]["socket_path"] == "NOT_CONFIGURED"
    assert policy["channel"]["allowed_peer_principal"] == "NOT_CONFIGURED"
    assert policy["channel"]["allowed_peer_uid"] == -1


def test_cli_validates_committed_delivery_policy() -> None:
    assert delivery_module.main(["validate"]) == 0


def test_disabled_delivery_refuses_every_receipt(tmp_path: Path) -> None:
    key = ed25519.Ed25519PrivateKey.generate()
    store = _trust_store(tmp_path, key)
    resolver = resolver_module.VerifiedAuthorizationResolver(_enabled_resolver_policy(store))
    delivery = delivery_module.TrustedReceiptDelivery(delivery_module.load_policy(), resolver)
    with pytest.raises(delivery_module.ReceiptDeliveryError) as exc:
        delivery.deliver(_envelope(_receipt(key)), peer=PEER)
    assert exc.value.code == "DELIVERY_DISABLED"
    assert resolver.size == 0


# --------------------------------------------------------------- authenticated path


def test_authenticated_local_delivery_populates_resolver(tmp_path: Path) -> None:
    key, resolver, delivery = _wired(tmp_path)
    receipt = _receipt(key)
    outcome = delivery.deliver(_envelope(receipt), peer=PEER)
    assert outcome.accepted is True
    assert outcome.duplicate is False
    assert outcome.authorization_ref == receipt["authorization_ref"]
    verified = resolver.resolve(receipt["authorization_ref"])
    assert verified is not None
    assert verified.capability_id == "web.discovery.headers"
    assert verified.target_sha256 == TARGET_DIGEST


def test_unauthenticated_peer_cannot_deliver(tmp_path: Path) -> None:
    key, resolver, delivery = _wired(tmp_path)
    with pytest.raises(delivery_module.ReceiptDeliveryError) as uid_exc:
        delivery.deliver(_envelope(_receipt(key)), peer={"uid": 1, "principal": PEER_PRINCIPAL})
    assert uid_exc.value.code == "PEER_UID_UNAUTHORIZED"
    with pytest.raises(delivery_module.ReceiptDeliveryError) as principal_exc:
        delivery.deliver(_envelope(_receipt(key)), peer={"uid": PEER_UID, "principal": "attacker"})
    assert principal_exc.value.code == "PEER_PRINCIPAL_UNAUTHORIZED"
    with pytest.raises(delivery_module.ReceiptDeliveryError) as missing_exc:
        delivery.deliver(_envelope(_receipt(key)), peer=None)
    assert missing_exc.value.code == "PEER_CREDENTIALS_REQUIRED"
    assert resolver.size == 0


# --------------------------------------------------------------- sole issuer


def test_non_hermes_issuer_is_refused(tmp_path: Path) -> None:
    key, resolver, delivery = _wired(tmp_path)
    envelope = _envelope(_receipt(key))
    envelope["issuer"] = "rogue-control-plane"
    with pytest.raises(delivery_module.ReceiptDeliveryError) as exc:
        delivery.deliver(envelope, peer=PEER)
    assert exc.value.code == "DELIVERY_ISSUER_UNAUTHORIZED"
    assert resolver.size == 0


def test_forged_receipt_issuer_fails_closed_in_the_verifier(tmp_path: Path) -> None:
    key, resolver, delivery = _wired(tmp_path)
    receipt = _receipt(key)
    receipt["issuer"] = "rogue-control-plane"
    with pytest.raises(resolver_module.AuthorizationResolverError):
        delivery.deliver(_envelope(receipt), peer=PEER)
    assert resolver.size == 0


def test_receipt_signed_by_unknown_key_is_refused(tmp_path: Path) -> None:
    _key, resolver, delivery = _wired(tmp_path)
    rogue = ed25519.Ed25519PrivateKey.generate()
    with pytest.raises(resolver_module.AuthorizationResolverError) as exc:
        delivery.deliver(_envelope(_receipt(rogue)), peer=PEER)
    assert exc.value.code.startswith("TB1_")
    assert resolver.size == 0


# --------------------------------------------------------------- no caller-controlled trust


@pytest.mark.parametrize(
    "field",
    ["verified", "trusted", "trust_level", "execution_authority", "bypass", "verification_source"],
)
def test_caller_cannot_assert_trust_fields(tmp_path: Path, field: str) -> None:
    key, resolver, delivery = _wired(tmp_path)
    envelope = _envelope(_receipt(key))
    envelope["receipt"] = copy.deepcopy(envelope["receipt"])
    envelope["receipt"][field] = True
    with pytest.raises(delivery_module.ReceiptDeliveryError) as exc:
        delivery.deliver(envelope, peer=PEER)
    assert exc.value.code == "DELIVERY_TRUST_FIELD_REFUSED"
    assert resolver.size == 0


def test_envelope_rejects_unknown_top_level_fields(tmp_path: Path) -> None:
    key, resolver, delivery = _wired(tmp_path)
    envelope = _envelope(_receipt(key))
    envelope["priority"] = "high"
    with pytest.raises(delivery_module.ReceiptDeliveryError) as exc:
        delivery.deliver(envelope, peer=PEER)
    assert exc.value.code == "DELIVERY_ENVELOPE_INVALID"
    assert resolver.size == 0


# --------------------------------------------------------------- no private key in Runner


@pytest.mark.parametrize("field", ["private_key", "signing_key", "token", "passphrase"])
def test_secret_material_is_refused_before_verification(tmp_path: Path, field: str) -> None:
    key, resolver, delivery = _wired(tmp_path)
    envelope = _envelope(_receipt(key))
    envelope["receipt"] = copy.deepcopy(envelope["receipt"])
    envelope["receipt"][field] = "AAAA"
    with pytest.raises(delivery_module.ReceiptDeliveryError) as exc:
        delivery.deliver(envelope, peer=PEER)
    assert exc.value.code == "DELIVERY_SECRET_MATERIAL_REFUSED"
    assert resolver.size == 0


def test_delivery_module_never_signs_or_loads_private_keys() -> None:
    source = DELIVERY_PATH.read_text(encoding="utf-8")
    for forbidden in ("private_key_from", "load_pem_private_key", ".sign(", "Ed25519PrivateKey"):
        assert forbidden not in source


# --------------------------------------------------------------- replay / sequence


def test_exact_duplicate_sequence_is_idempotent_not_a_second_registration(
    tmp_path: Path,
) -> None:
    key, resolver, delivery = _wired(tmp_path)
    receipt = _receipt(key)
    first = delivery.deliver(_envelope(receipt, sequence=7), peer=PEER)
    second = delivery.deliver(_envelope(receipt, sequence=7), peer=PEER)
    assert first.authorization_ref == second.authorization_ref
    assert second.duplicate is True
    assert resolver.size == 1


def test_out_of_order_sequence_is_refused(tmp_path: Path) -> None:
    key, resolver, delivery = _wired(tmp_path)
    delivery.deliver(_envelope(_receipt(key), sequence=9), peer=PEER)
    with pytest.raises(delivery_module.ReceiptDeliveryError) as exc:
        delivery.deliver(_envelope(_receipt(key), sequence=4), peer=PEER)
    assert exc.value.code == "DELIVERY_SEQUENCE_REPLAY"
    assert resolver.size == 1


# --------------------------------------------------------------- restart semantics


def test_restart_is_fail_closed_and_resolves_nothing(tmp_path: Path) -> None:
    key, resolver, delivery = _wired(tmp_path)
    receipt = _receipt(key)
    delivery.deliver(_envelope(receipt), peer=PEER)
    assert resolver.resolve(receipt["authorization_ref"]) is not None

    # Simulated restart: brand new resolver + delivery, no persistence anywhere.
    store = _trust_store(tmp_path, key)
    restarted_resolver = resolver_module.VerifiedAuthorizationResolver(
        _enabled_resolver_policy(store)
    )
    restarted_delivery = delivery_module.TrustedReceiptDelivery(
        _enabled_delivery_policy(), restarted_resolver
    )
    assert restarted_resolver.resolve(receipt["authorization_ref"]) is None
    assert restarted_delivery.last_sequence is None
    assert restarted_delivery.safe_state()["delivered_count"] == 0


def test_safe_state_exposes_no_receipt_or_key_material(tmp_path: Path) -> None:
    key, _resolver, delivery = _wired(tmp_path)
    receipt = _receipt(key)
    delivery.deliver(_envelope(receipt), peer=PEER)
    state = delivery.safe_state()
    assert set(state) == {
        "enabled",
        "issuer",
        "transport",
        "last_sequence",
        "delivered_count",
        "persistence",
        "restart_behaviour",
    }
    serialized = json.dumps(state)
    assert receipt["signature"]["value"] not in serialized
    assert TARGET_DIGEST not in serialized


# --------------------------------------------------------------- policy guards


def test_enabled_policy_requires_real_peer_identity() -> None:
    policy = _enabled_delivery_policy()
    policy["channel"]["allowed_peer_principal"] = "NOT_CONFIGURED"
    policy["channel"]["allowed_peer_uid"] = -1
    findings = delivery_module.validate_policy(policy)
    assert any("allowed_peer_principal" in finding for finding in findings)
    assert any("allowed_peer_uid" in finding for finding in findings)


def test_policy_cannot_disable_monotonic_sequence_or_allow_persistence() -> None:
    policy = _enabled_delivery_policy()
    policy["channel"]["require_monotonic_sequence"] = False
    policy["persistence"] = "disk"
    findings = delivery_module.validate_policy(policy)
    assert any("monotonic" in finding for finding in findings)
    assert any("persistence" in finding for finding in findings)


def test_policy_cannot_permit_runner_private_key() -> None:
    policy = _enabled_delivery_policy()
    policy["runner_private_key"] = "allowed"
    assert any("runner_private_key" in f for f in delivery_module.validate_policy(policy))
