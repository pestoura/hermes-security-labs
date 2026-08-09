from __future__ import annotations

import copy
import importlib.util
import os
import socket
import sys
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
ROUTER_PATH = ROOT / "platform" / "runner-dispatch" / "router.py"
ROUTING_POLICY_PATH = ROOT / "platform" / "runner-dispatch" / "routing-policy.yaml"
TRANSPORT_POLICY_PATH = ROOT / "platform" / "runner-transport" / "transport-policy.yaml"
ADAPTER_REGISTRY_PATH = ROOT / "platform" / "runner-adapters" / "adapter-registry.yaml"
WEBGOAT_ADAPTER_PATH = ROOT / "platform" / "runner-adapters" / "webgoat_l1_adapter.py"
AUTHORIZATION_REF = "tb1-authz:v1:" + ("3" * 64)
CAMPAIGN_ID = str(uuid.UUID("11111111-1111-4111-8111-111111111111"))
RUN_ID = "22222222-2222-4222-8222-222222222222"
STEP_ID = "33333333-3333-4333-8333-333333333333"
ATTEMPT_ID = "44444444-4444-4444-8444-444444444444"


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


router = _load("runner_dispatch_router_test", ROUTER_PATH)
webgoat = _load("runner_dispatch_webgoat_adapter_test", WEBGOAT_ADAPTER_PATH)


def _iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat(timespec="seconds").replace(
        "+00:00", "Z"
    )


@dataclass
class StaticResolver:
    binding: Any

    def resolve(self, authorization_ref: str):
        assert authorization_ref == AUTHORIZATION_REF
        return self.binding


@dataclass(frozen=True)
class VerifiedBinding:
    authorization_ref: str
    issued_at: str
    expires_at: str
    campaign_id: str
    run_id: str
    step_id: str
    operation_id: str
    operation_version: str
    operation_parameters_sha256: str
    capability_id: str
    target_sha256: str
    intrusiveness_level: str


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


class BrokenAdapter:
    def dispatch(self, request: dict[str, Any]) -> dict[str, Any]:
        del request
        return {"messages": [{"not": "runner-protocol"}]}


class ExplodingAdapter:
    def dispatch(self, request: dict[str, Any]) -> dict[str, Any]:
        del request
        raise RuntimeError("sensitive internal text must not cross router boundary")


def _transport_policy() -> dict[str, Any]:
    return {
        "schema_version": "1.0",
        "policy_id": "hexor.runner.transport.identity",
        "state": "ENABLED",
        "default": "deny",
        "runtime_status": "NOT_RUN",
        "execution_authority": "none",
        "modes": {
            "unix-peer": {
                "status": "CANDIDATE",
                "identity_source": "linux-so-peercred",
                "socket_path": "/run/hex0r-test/runner.sock",
                "allowed_peers": [
                    {
                        "principal_id": "hexor.execution-gateway",
                        "uid": os.getuid(),
                        "gid": os.getgid(),
                        "purpose": "runner-dispatch",
                    }
                ],
            },
            "mtls": {
                "status": "FUTURE",
                "identity_source": "x509-client-certificate",
                "trust_store": "NOT_CONFIGURED",
            },
        },
    }


def _routing_policy(*, capabilities: list[str] | None = None) -> dict[str, Any]:
    return {
        "schema_version": "1.0",
        "policy_id": "hexor.runner.dispatch.routing",
        "state": "ENABLED",
        "default": "deny",
        "runtime_status": "NOT_RUN",
        "execution_authority": "none",
        "bindings": [
            {
                "principal_id": "hexor.execution-gateway",
                "adapter_id": "webgoat-l1",
                "target_id": "webgoat-web",
                "capabilities": capabilities
                or ["web.discovery.headers", "web.discovery.tls"],
            }
        ],
    }


def _adapter_registry(*, promoted: bool) -> dict[str, Any]:
    registry = yaml.safe_load(ADAPTER_REGISTRY_PATH.read_text(encoding="utf-8"))
    if promoted:
        registry = copy.deepcopy(registry)
        registry["adapters"][0]["status"] = "AS_BUILT"
        registry["adapters"][0]["runtime_status"] = "READY"
    return registry


def _request(capability: str = "web.discovery.headers") -> dict[str, Any]:
    return {
        "message_type": "runner.step.request",
        "protocol_version": "2.0.0",
        "correlation": {
            "campaign_id": CAMPAIGN_ID,
            "run_id": RUN_ID,
            "step_id": STEP_ID,
            "attempt_id": ATTEMPT_ID,
        },
        "emitted_at": "2026-08-09T19:00:00Z",
        "authorization_ref": AUTHORIZATION_REF,
        "idempotency_key": "fixture-router-key-one",
        "operation": {
            "capability_id": capability,
            "input": {
                "operation_id": capability,
                "operation_version": "1.0.0",
                "intrusiveness_level": "L1",
                "target": {"type": "lab-asset", "value": "webgoat-web"},
                "parameters": {},
            },
        },
        "timeout_budget": {
            "soft_timeout_ms": 1000,
            "hard_timeout_ms": 5000,
        },
        "retry_policy": {
            "max_attempts": 1,
            "retryable_error_codes": [],
        },
        "cancellation_policy": {
            "mode": "cooperative",
            "grace_period_ms": 0,
        },
    }


def _verified_for(request: dict[str, Any]) -> VerifiedBinding:
    payload = request["operation"]["input"]
    now = datetime.now(timezone.utc)
    return VerifiedBinding(
        authorization_ref=request["authorization_ref"],
        issued_at=_iso(now - timedelta(seconds=30)),
        expires_at=_iso(now + timedelta(minutes=5)),
        campaign_id=request["correlation"]["campaign_id"],
        run_id=request["correlation"]["run_id"],
        step_id=request["correlation"]["step_id"],
        operation_id=payload["operation_id"],
        operation_version=payload["operation_version"],
        operation_parameters_sha256=webgoat.authorization_contract.canonical_parameters_sha256(
            payload["parameters"]
        ),
        capability_id=request["operation"]["capability_id"],
        target_sha256=webgoat.gateway_contract.canonical_target_digest(payload["target"]),
        intrusiveness_level=payload["intrusiveness_level"],
    )


def _real_adapter(tmp_path: Path, request: dict[str, Any], probe: FakeProbe):
    return webgoat.build_adapter(
        ledger_path=tmp_path / "router-ledger.sqlite3",
        authorization_resolver=StaticResolver(_verified_for(request)),
        probe=probe,
    )


def _dispatch(
    *,
    request: dict[str, Any],
    adapter_registry: dict[str, Any],
    adapter: Any,
    routing_policy: dict[str, Any] | None = None,
    transport_policy: dict[str, Any] | None = None,
):
    left, right = socket.socketpair(socket.AF_UNIX, socket.SOCK_STREAM)
    try:
        return router.dispatch_from_unix_peer(
            peer_socket=left,
            request=request,
            transport_policy=transport_policy or _transport_policy(),
            routing_policy=routing_policy or _routing_policy(),
            adapter_registry=adapter_registry,
            adapters={"webgoat-l1": adapter},
        )
    finally:
        left.close()
        right.close()


def test_committed_routing_policy_is_disabled_deny_all() -> None:
    policy = yaml.safe_load(ROUTING_POLICY_PATH.read_text(encoding="utf-8"))
    assert router.validate_routing_policy(policy) == []
    assert policy["state"] == "DISABLED"
    assert policy["default"] == "deny"
    assert policy["runtime_status"] == "NOT_RUN"
    assert policy["execution_authority"] == "none"
    assert policy["bindings"] == []


def test_committed_transport_policy_and_adapter_registry_prevent_dispatch(
    tmp_path: Path,
) -> None:
    request = _request()
    probe = FakeProbe()
    adapter = _real_adapter(tmp_path, request, probe)
    with pytest.raises(router.DispatchRouterError) as exc:
        _dispatch(
            request=request,
            adapter_registry=_adapter_registry(promoted=False),
            adapter=adapter,
        )
    assert exc.value.code == "ADAPTER_NOT_RUNTIME_READY"
    assert probe.calls == 0


def test_authenticated_peer_routes_to_promoted_adapter_with_fake_effect(
    tmp_path: Path,
) -> None:
    request = _request()
    probe = FakeProbe()
    adapter = _real_adapter(tmp_path, request, probe)
    result = _dispatch(
        request=request,
        adapter_registry=_adapter_registry(promoted=True),
        adapter=adapter,
    )
    assert result.principal_id == "hexor.execution-gateway"
    assert result.adapter_id == "webgoat-l1"
    assert result.transport == "unix-peer"
    assert result.messages[-1]["status"] == "PASS"
    assert result.messages[-1]["output"]["target_id"] == "webgoat-web"
    assert probe.calls == 1
    assert result.as_safe_dict()["message_count"] == 1


def test_disabled_transport_refuses_before_adapter(tmp_path: Path) -> None:
    request = _request()
    probe = FakeProbe()
    adapter = _real_adapter(tmp_path, request, probe)
    disabled = yaml.safe_load(TRANSPORT_POLICY_PATH.read_text(encoding="utf-8"))
    with pytest.raises(router.DispatchRouterError) as exc:
        _dispatch(
            request=request,
            adapter_registry=_adapter_registry(promoted=True),
            adapter=adapter,
            transport_policy=disabled,
        )
    assert "TRANSPORT_DISABLED" in exc.value.code
    assert probe.calls == 0


def test_disabled_routing_policy_refuses_before_adapter(tmp_path: Path) -> None:
    request = _request()
    probe = FakeProbe()
    adapter = _real_adapter(tmp_path, request, probe)
    disabled = yaml.safe_load(ROUTING_POLICY_PATH.read_text(encoding="utf-8"))
    with pytest.raises(router.DispatchRouterError) as exc:
        _dispatch(
            request=request,
            adapter_registry=_adapter_registry(promoted=True),
            adapter=adapter,
            routing_policy=disabled,
        )
    assert exc.value.code == "ROUTING_DISABLED"
    assert probe.calls == 0


def test_missing_exact_binding_refuses_before_adapter(tmp_path: Path) -> None:
    request = _request()
    probe = FakeProbe()
    adapter = _real_adapter(tmp_path, request, probe)
    policy = _routing_policy(capabilities=["web.discovery.tls"])
    with pytest.raises(router.DispatchRouterError) as exc:
        _dispatch(
            request=request,
            adapter_registry=_adapter_registry(promoted=True),
            adapter=adapter,
            routing_policy=policy,
        )
    assert exc.value.code == "ROUTING_BINDING_DENIED"
    assert probe.calls == 0


def test_unknown_capability_has_no_route(tmp_path: Path) -> None:
    request = _request("runtime.inventory.read")
    probe = FakeProbe()
    adapter = _real_adapter(tmp_path, request, probe)
    with pytest.raises(router.DispatchRouterError) as exc:
        _dispatch(
            request=request,
            adapter_registry=_adapter_registry(promoted=True),
            adapter=adapter,
        )
    assert exc.value.code == "ROUTE_NOT_FOUND"
    assert probe.calls == 0


def test_ambiguous_adapter_match_is_refused(tmp_path: Path) -> None:
    request = _request()
    probe = FakeProbe()
    adapter = _real_adapter(tmp_path, request, probe)
    registry = _adapter_registry(promoted=True)
    duplicate = copy.deepcopy(registry["adapters"][0])
    duplicate["adapter_id"] = "webgoat-l1-copy"
    registry["adapters"].append(duplicate)
    with pytest.raises(router.DispatchRouterError) as exc:
        _dispatch(
            request=request,
            adapter_registry=registry,
            adapter=adapter,
        )
    assert exc.value.code == "ROUTE_AMBIGUOUS"
    assert probe.calls == 0


def test_missing_composed_adapter_is_refused() -> None:
    left, right = socket.socketpair(socket.AF_UNIX, socket.SOCK_STREAM)
    try:
        with pytest.raises(router.DispatchRouterError) as exc:
            router.dispatch_from_unix_peer(
                peer_socket=left,
                request=_request(),
                transport_policy=_transport_policy(),
                routing_policy=_routing_policy(),
                adapter_registry=_adapter_registry(promoted=True),
                adapters={},
            )
        assert exc.value.code == "ADAPTER_NOT_COMPOSED"
    finally:
        left.close()
        right.close()


def test_malformed_adapter_result_is_rejected() -> None:
    with pytest.raises(router.DispatchRouterError) as exc:
        _dispatch(
            request=_request(),
            adapter_registry=_adapter_registry(promoted=True),
            adapter=BrokenAdapter(),
        )
    assert exc.value.code == "ADAPTER_RESULT_INVALID"


def test_adapter_exception_is_sanitized() -> None:
    with pytest.raises(router.DispatchRouterError) as exc:
        _dispatch(
            request=_request(),
            adapter_registry=_adapter_registry(promoted=True),
            adapter=ExplodingAdapter(),
        )
    assert exc.value.code == "ADAPTER_DISPATCH_FAILED"
    assert "sensitive internal text" not in str(exc.value)
    assert "RuntimeError" in str(exc.value)


def test_wildcard_routing_binding_is_invalid() -> None:
    policy = _routing_policy()
    policy["bindings"][0]["target_id"] = "*"
    findings = router.validate_routing_policy(policy)
    assert any("non-wildcard" in item for item in findings)


def test_routing_policy_never_claims_execution_authority() -> None:
    policy = _routing_policy()
    policy["execution_authority"] = "router"
    findings = router.validate_routing_policy(policy)
    assert any("never claim execution authority" in item for item in findings)
