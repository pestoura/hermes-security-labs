from __future__ import annotations

import base64
import importlib.util
import json
import sys
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ed25519
from runner_protocol_v2 import validate_semantics

ROOT = Path(__file__).resolve().parents[2]
ADAPTER_PATH = ROOT / "platform" / "runner-adapters" / "webgoat_l1_adapter.py"
RESOLVER_PATH = (
    ROOT / "platform" / "runner-authorization" / "verified_authorization_resolver.py"
)
HANDOFF_PATH = ROOT / "platform" / "gateway-protocol" / "runner_handoff.py"

CAMPAIGN_ID = "11111111-1111-4111-8111-111111111111"
RUN_ID = "22222222-2222-4222-8222-222222222222"
STEP_ID = "33333333-3333-4333-8333-333333333333"
ATTEMPT_ID = "44444444-4444-4444-8444-444444444444"
KEY_ID = "tb1-webgoat-integration-fixture"


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


webgoat = _load("webgoat_verified_tb1_adapter_test", ADAPTER_PATH)
resolver_module = _load("webgoat_verified_tb1_resolver_test", RESOLVER_PATH)
handoff = _load("webgoat_verified_tb1_handoff_test", HANDOFF_PATH)
auth = resolver_module.authorization_contract


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


def _trust_store(tmp_path: Path, private_key: Any) -> Path:
    path = tmp_path / "webgoat-tb1-trust-store.json"
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


def _resolver_policy(trust_store: Path) -> dict[str, Any]:
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
            "max_entries": 16,
            "persistence": "none",
        },
    }


def _control_plane_request(
    capability: str = "web.discovery.headers",
    *,
    parameters: dict[str, Any] | None = None,
    attempt_id: str = ATTEMPT_ID,
) -> tuple[dict[str, Any], dict[str, Any]]:
    request = {
        "campaign_id": CAMPAIGN_ID,
        "run_id": RUN_ID,
        "step_id": STEP_ID,
        "attempt_id": attempt_id,
        "operation": {
            "id": capability,
            "version": "1.0.0",
            "parameters": {} if parameters is None else parameters,
        },
        "target": {"type": "lab-asset", "value": "webgoat-web"},
    }
    roe_step_request = {
        "capability": capability,
        "intrusiveness_level": "L1",
    }
    return request, roe_step_request


def _receipt(private_key: Any, request: dict[str, Any]) -> dict[str, Any]:
    now = datetime.now(timezone.utc)
    target_digest = webgoat.gateway_contract.canonical_target_digest(request["target"])
    parameter_digest = auth.canonical_parameters_sha256(request["operation"]["parameters"])
    receipt: dict[str, Any] = {
        "schema_version": "1.0.0",
        "domain": "hex0r.tb1.authorization.v1",
        "issuer": "hermes-control-plane",
        "authorization_id": str(uuid.uuid4()),
        "issued_at": _iso(now - timedelta(seconds=30)),
        "expires_at": _iso(now + timedelta(minutes=5)),
        "campaign_id": request["campaign_id"],
        "run_id": request["run_id"],
        "step_id": request["step_id"],
        "roe_contract_id": "roe-contract-webgoat-integration",
        "roe_contract_payload_sha256": "b" * 64,
        "roe_step_request_id": "roe-step-webgoat-integration",
        "operation_id": request["operation"]["id"],
        "operation_version": request["operation"]["version"],
        "operation_parameters_sha256": parameter_digest,
        "capability_id": request["operation"]["id"],
        "target_sha256": target_digest,
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


@dataclass(frozen=True)
class VerifiedHandoff:
    authorization_ref: str


class FakeProbe:
    def __init__(self) -> None:
        self.calls = 0

    def get(self, *, timeout_seconds: float):
        assert 0 < timeout_seconds <= 10.0
        self.calls += 1
        return webgoat.ProbeResponse(
            status=200,
            headers=(("Server", "WebGoat"),),
        )


def _runner_message(
    request: dict[str, Any],
    roe_step_request: dict[str, Any],
    authorization_ref: str,
) -> dict[str, Any]:
    message = handoff._assemble_message(
        request,
        roe_step_request,
        object(),
        VerifiedHandoff(authorization_ref=authorization_ref),
        handoff.RunnerHandoffConfig(),
    )
    validate_semantics(message)
    return message


def test_signed_tb1_receipt_resolves_and_binds_exact_webgoat_effect(tmp_path: Path) -> None:
    key = ed25519.Ed25519PrivateKey.generate()
    request, roe_step_request = _control_plane_request(
        parameters={"follow_redirects": False}
    )
    receipt = _receipt(key, request)

    resolver = resolver_module.VerifiedAuthorizationResolver(
        _resolver_policy(_trust_store(tmp_path, key))
    )
    verified = resolver.register_receipt(receipt)
    assert verified.authorization_ref == receipt["authorization_ref"]

    runner_message = _runner_message(
        request,
        roe_step_request,
        receipt["authorization_ref"],
    )
    probe = FakeProbe()
    runner = webgoat.build_adapter(
        ledger_path=tmp_path / "integration-ledger.sqlite3",
        authorization_resolver=resolver,
        probe=probe,
    )

    outcome = runner.dispatch(runner_message)["messages"][0]
    validate_semantics(outcome)
    assert outcome["status"] == "PASS"
    assert outcome["output"]["target_id"] == "webgoat-web"
    assert outcome["output"]["capability_id"] == "web.discovery.headers"
    assert probe.calls == 1


def test_same_tb1_authorization_allows_new_attempt_for_exact_logical_retry(
    tmp_path: Path,
) -> None:
    key = ed25519.Ed25519PrivateKey.generate()
    request, roe_step_request = _control_plane_request()
    receipt = _receipt(key, request)
    resolver = resolver_module.VerifiedAuthorizationResolver(
        _resolver_policy(_trust_store(tmp_path, key))
    )
    resolver.register_receipt(receipt)

    first_message = _runner_message(
        request,
        roe_step_request,
        receipt["authorization_ref"],
    )
    retry_request, retry_roe = _control_plane_request(
        attempt_id="55555555-5555-4555-8555-555555555555"
    )
    retry_message = _runner_message(
        retry_request,
        retry_roe,
        receipt["authorization_ref"],
    )
    retry_message["idempotency_key"] = "fixture-logical-retry-key-two"
    validate_semantics(retry_message)

    probe = FakeProbe()
    runner = webgoat.build_adapter(
        ledger_path=tmp_path / "retry-ledger.sqlite3",
        authorization_resolver=resolver,
        probe=probe,
    )

    first = runner.dispatch(first_message)["messages"][0]
    retry = runner.dispatch(retry_message)["messages"][0]
    assert first["status"] == "PASS"
    assert retry["status"] == "PASS"
    assert first_message["correlation"]["attempt_id"] != retry_message["correlation"]["attempt_id"]
    assert first_message["correlation"]["run_id"] == retry_message["correlation"]["run_id"]
    assert first_message["correlation"]["step_id"] == retry_message["correlation"]["step_id"]
    assert probe.calls == 2


def test_verified_receipt_cannot_authorize_different_runner_correlation(tmp_path: Path) -> None:
    key = ed25519.Ed25519PrivateKey.generate()
    request, roe_step_request = _control_plane_request()
    receipt = _receipt(key, request)
    resolver = resolver_module.VerifiedAuthorizationResolver(
        _resolver_policy(_trust_store(tmp_path, key))
    )
    resolver.register_receipt(receipt)

    runner_message = _runner_message(
        request,
        roe_step_request,
        receipt["authorization_ref"],
    )
    runner_message["correlation"]["run_id"] = "66666666-6666-4666-8666-666666666666"
    validate_semantics(runner_message)

    probe = FakeProbe()
    runner = webgoat.build_adapter(
        ledger_path=tmp_path / "mismatch-ledger.sqlite3",
        authorization_resolver=resolver,
        probe=probe,
    )
    outcome = runner.dispatch(runner_message)["messages"][0]
    assert outcome["status"] == "REFUSED"
    assert outcome["error"]["code"] == "AUTHORIZATION_DENIED"
    assert probe.calls == 0


def test_unknown_reference_cannot_borrow_cached_verified_authorization(tmp_path: Path) -> None:
    key = ed25519.Ed25519PrivateKey.generate()
    request, roe_step_request = _control_plane_request()
    receipt = _receipt(key, request)
    resolver = resolver_module.VerifiedAuthorizationResolver(
        _resolver_policy(_trust_store(tmp_path, key))
    )
    resolver.register_receipt(receipt)

    runner_message = _runner_message(
        request,
        roe_step_request,
        "tb1-authz:v1:" + ("9" * 64),
    )
    probe = FakeProbe()
    runner = webgoat.build_adapter(
        ledger_path=tmp_path / "unknown-ref-ledger.sqlite3",
        authorization_resolver=resolver,
        probe=probe,
    )
    outcome = runner.dispatch(runner_message)["messages"][0]
    assert outcome["status"] == "REFUSED"
    assert probe.calls == 0
