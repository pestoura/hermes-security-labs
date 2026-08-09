from __future__ import annotations

import base64
import copy
import importlib.util
import json
import sys
import uuid
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ed25519

ROOT = Path(__file__).resolve().parents[2]
RESOLVER_PATH = ROOT / "platform" / "runner-authorization" / "verified_authorization_resolver.py"
POLICY_PATH = ROOT / "platform" / "runner-authorization" / "resolver-policy.yaml"


def _load():
    spec = importlib.util.spec_from_file_location(
        "verified_authorization_resolver_test",
        RESOLVER_PATH,
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


resolver_module = _load()
auth = resolver_module.authorization_contract

CAMPAIGN_ID = "3f2a1c64-1e8b-4a2b-9c7d-1c2b3a4d5e6f"
RUN_ID = "5c9d7e2a-8b41-4f6d-9a03-2d4e6f8a1b2c"
STEP_ID = "7b1e4d3c-2a95-4c8e-8f10-3e5d7c9b1a24"
KEY_ID = "tb1-resolver-ed25519-fixture"
TARGET_DIGEST = "a" * 64
ROE_DIGEST = "b" * 64
PARAMETERS_DIGEST = auth.canonical_parameters_sha256({"follow_redirects": False})


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


def _trust_store(tmp_path: Path, private_key: Any, *, name: str = "trust-store.json") -> Path:
    path = tmp_path / name
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
    operation: str | None = None,
    campaign_id: str = CAMPAIGN_ID,
    run_id: str = RUN_ID,
    step_id: str = STEP_ID,
    issued_at: datetime | None = None,
    expires_at: datetime | None = None,
) -> dict[str, Any]:
    now = datetime.now(timezone.utc)
    receipt: dict[str, Any] = {
        "schema_version": "1.0.0",
        "domain": "hex0r.tb1.authorization.v1",
        "issuer": "hermes-control-plane",
        "authorization_id": str(uuid.uuid4()),
        "issued_at": _iso(issued_at or (now - timedelta(seconds=30))),
        "expires_at": _iso(expires_at or (now + timedelta(minutes=5))),
        "campaign_id": campaign_id,
        "run_id": run_id,
        "step_id": step_id,
        "roe_contract_id": "roe-contract-resolver-fixture",
        "roe_contract_payload_sha256": ROE_DIGEST,
        "roe_step_request_id": "roe-step-resolver-fixture",
        "operation_id": operation or capability,
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


def _enabled_policy(trust_store: Path, *, max_entries: int = 256) -> dict[str, Any]:
    return {
        "schema_version": "1.0",
        "policy_id": "hexor.runner.authorization.resolver",
        "state": "ENABLED",
        "default": "deny",
        "runtime_status": "NOT_RUN",
        "execution_authority": "none",
        "verification_source": "platform/authorization-contract/authorization_receipt.py",
        "trust_store_path": str(trust_store.resolve()),
        "cache": {
            "mode": "memory-only",
            "max_entries": max_entries,
            "persistence": "none",
        },
    }


def test_committed_policy_is_disabled_and_deny_all() -> None:
    policy = resolver_module.load_policy()
    assert resolver_module.validate_policy(policy) == []
    assert policy["state"] == "DISABLED"
    assert policy["default"] == "deny"
    assert policy["runtime_status"] == "NOT_RUN"
    assert policy["execution_authority"] == "none"
    assert policy["trust_store_path"] == "NOT_CONFIGURED"
    assert policy["cache"]["mode"] == "memory-only"
    assert policy["cache"]["persistence"] == "none"


def test_cli_validates_committed_policy() -> None:
    assert resolver_module.main(["validate"]) == 0


def test_disabled_resolver_cannot_register_and_resolves_nothing() -> None:
    policy = resolver_module.load_policy(POLICY_PATH)
    resolver = resolver_module.VerifiedAuthorizationResolver(policy)
    key = ed25519.Ed25519PrivateKey.generate()
    with pytest.raises(resolver_module.AuthorizationResolverError) as exc:
        resolver.register_receipt(_receipt(key))
    assert exc.value.code == "RESOLVER_DISABLED"
    assert resolver.resolve("tb1-authz:v1:" + "0" * 64) is None
    assert resolver.size == 0


def test_naked_reference_without_verified_ingest_resolves_nothing(tmp_path: Path) -> None:
    key = ed25519.Ed25519PrivateKey.generate()
    resolver = resolver_module.VerifiedAuthorizationResolver(
        _enabled_policy(_trust_store(tmp_path, key))
    )
    receipt = _receipt(key)
    assert resolver.resolve(receipt["authorization_ref"]) is None
    assert resolver.size == 0


def test_valid_signed_receipt_registers_only_sanitized_verified_metadata(tmp_path: Path) -> None:
    key = ed25519.Ed25519PrivateKey.generate()
    store = _trust_store(tmp_path, key)
    resolver = resolver_module.VerifiedAuthorizationResolver(_enabled_policy(store))
    receipt = _receipt(key)

    verified = resolver.register_receipt(receipt)
    resolved = resolver.resolve(receipt["authorization_ref"])

    assert resolved == verified
    assert resolved.authorization_ref == receipt["authorization_ref"]
    assert resolved.campaign_id == CAMPAIGN_ID
    assert resolved.run_id == RUN_ID
    assert resolved.step_id == STEP_ID
    assert resolved.capability_id == "web.discovery.headers"
    assert resolved.target_sha256 == TARGET_DIGEST
    assert resolved.operation_parameters_sha256 == PARAMETERS_DIGEST
    assert not hasattr(resolved, "signature")
    assert not hasattr(resolved, "target")
    assert not hasattr(resolved, "parameters")
    assert resolver.size == 1

    inventory = resolver.safe_inventory()
    serialized = json.dumps(inventory, sort_keys=True)
    assert receipt["authorization_ref"] in serialized
    assert "signature" not in serialized.lower()
    assert TARGET_DIGEST not in serialized
    assert PARAMETERS_DIGEST not in serialized
    assert "public_key" not in serialized


def test_same_verified_receipt_registration_is_idempotent(tmp_path: Path) -> None:
    key = ed25519.Ed25519PrivateKey.generate()
    resolver = resolver_module.VerifiedAuthorizationResolver(
        _enabled_policy(_trust_store(tmp_path, key))
    )
    receipt = _receipt(key)
    first = resolver.register_receipt(receipt)
    second = resolver.register_receipt(copy.deepcopy(receipt))
    assert first == second
    assert resolver.size == 1


def test_forged_signature_is_not_cached(tmp_path: Path) -> None:
    trusted = ed25519.Ed25519PrivateKey.generate()
    attacker = ed25519.Ed25519PrivateKey.generate()
    resolver = resolver_module.VerifiedAuthorizationResolver(
        _enabled_policy(_trust_store(tmp_path, trusted))
    )
    receipt = _receipt(attacker)
    with pytest.raises(resolver_module.AuthorizationResolverError) as exc:
        resolver.register_receipt(receipt)
    assert exc.value.code.startswith("TB1_AUTH_SIGNATURE_")
    assert resolver.size == 0
    assert resolver.resolve(receipt["authorization_ref"]) is None


def test_wrong_trust_store_key_is_not_cached(tmp_path: Path) -> None:
    signer = ed25519.Ed25519PrivateKey.generate()
    other = ed25519.Ed25519PrivateKey.generate()
    resolver = resolver_module.VerifiedAuthorizationResolver(
        _enabled_policy(_trust_store(tmp_path, other))
    )
    receipt = _receipt(signer)
    with pytest.raises(resolver_module.AuthorizationResolverError):
        resolver.register_receipt(receipt)
    assert resolver.size == 0


def test_restart_semantics_are_fail_closed_memory_only(tmp_path: Path) -> None:
    key = ed25519.Ed25519PrivateKey.generate()
    policy = _enabled_policy(_trust_store(tmp_path, key))
    receipt = _receipt(key)

    first_process = resolver_module.VerifiedAuthorizationResolver(policy)
    first_process.register_receipt(receipt)
    assert first_process.resolve(receipt["authorization_ref"]) is not None

    restarted_process = resolver_module.VerifiedAuthorizationResolver(policy)
    assert restarted_process.size == 0
    assert restarted_process.resolve(receipt["authorization_ref"]) is None


def test_expired_cached_metadata_is_removed_and_denied(tmp_path: Path) -> None:
    key = ed25519.Ed25519PrivateKey.generate()
    resolver = resolver_module.VerifiedAuthorizationResolver(
        _enabled_policy(_trust_store(tmp_path, key))
    )
    receipt = _receipt(key)
    verified = resolver.register_receipt(receipt)
    stale = replace(
        verified,
        issued_at=_iso(datetime.now(timezone.utc) - timedelta(minutes=2)),
        expires_at=_iso(datetime.now(timezone.utc) - timedelta(seconds=1)),
    )
    resolver._entries[verified.authorization_ref] = stale

    assert resolver.resolve(verified.authorization_ref) is None
    assert resolver.size == 0


def test_future_cached_metadata_is_removed_and_denied(tmp_path: Path) -> None:
    key = ed25519.Ed25519PrivateKey.generate()
    resolver = resolver_module.VerifiedAuthorizationResolver(
        _enabled_policy(_trust_store(tmp_path, key))
    )
    verified = resolver.register_receipt(_receipt(key))
    future = replace(
        verified,
        issued_at=_iso(datetime.now(timezone.utc) + timedelta(minutes=1)),
        expires_at=_iso(datetime.now(timezone.utc) + timedelta(minutes=5)),
    )
    resolver._entries[verified.authorization_ref] = future
    assert resolver.resolve(verified.authorization_ref) is None
    assert resolver.size == 0


def test_cache_capacity_evicts_oldest_verified_reference(tmp_path: Path) -> None:
    key = ed25519.Ed25519PrivateKey.generate()
    resolver = resolver_module.VerifiedAuthorizationResolver(
        _enabled_policy(_trust_store(tmp_path, key), max_entries=2)
    )
    first = _receipt(key, step_id=str(uuid.uuid4()))
    second = _receipt(key, step_id=str(uuid.uuid4()))
    third = _receipt(key, step_id=str(uuid.uuid4()))

    resolver.register_receipt(first)
    resolver.register_receipt(second)
    resolver.register_receipt(third)

    assert resolver.size == 2
    assert resolver.resolve(first["authorization_ref"]) is None
    assert resolver.resolve(second["authorization_ref"]) is not None
    assert resolver.resolve(third["authorization_ref"]) is not None


def test_forget_removes_only_local_resolvability(tmp_path: Path) -> None:
    key = ed25519.Ed25519PrivateKey.generate()
    resolver = resolver_module.VerifiedAuthorizationResolver(
        _enabled_policy(_trust_store(tmp_path, key))
    )
    receipt = _receipt(key)
    resolver.register_receipt(receipt)
    assert resolver.forget(receipt["authorization_ref"]) is True
    assert resolver.resolve(receipt["authorization_ref"]) is None
    assert resolver.forget(receipt["authorization_ref"]) is False


def test_enabled_policy_requires_absolute_trust_store_path() -> None:
    policy = _enabled_policy(Path("relative-trust-store.json"))
    policy["trust_store_path"] = "relative-trust-store.json"
    findings = resolver_module.validate_policy(policy)
    assert any("trust_store_path must be absolute" in item for item in findings)


def test_persistent_cache_cannot_be_silently_enabled() -> None:
    policy = resolver_module.load_policy(POLICY_PATH)
    policy["cache"]["persistence"] = "sqlite"
    findings = resolver_module.validate_policy(policy)
    assert any("persistence must remain none" in item for item in findings)


def test_resolver_never_claims_execution_authority() -> None:
    policy = resolver_module.load_policy(POLICY_PATH)
    policy["execution_authority"] = "runner"
    findings = resolver_module.validate_policy(policy)
    assert any("never claim execution authority" in item for item in findings)
