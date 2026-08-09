from __future__ import annotations

import copy
import importlib.util
import os
import socket
import sys
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
COMPOSITION_PATH = ROOT / "platform" / "runner-dispatch" / "custodial_dispatch.py"
ADAPTER_PATH = ROOT / "platform" / "runner-adapters" / "webgoat_l1_adapter.py"
ADAPTER_REGISTRY_PATH = ROOT / "platform" / "runner-adapters" / "adapter-registry.yaml"
CUSTODY_PATH = ROOT / "platform" / "evidence-plane" / "runner_outcome_custody.py"
CUSTODY_POLICY_PATH = ROOT / "platform" / "evidence-plane" / "runner-outcome-policy.yaml"
STORE_PATH = ROOT / "platform" / "evidence-plane" / "local_store.py"

CAMPAIGN_ID = "11111111-1111-4111-8111-111111111111"
RUN_ID = "22222222-2222-4222-8222-222222222222"
STEP_ID = "33333333-3333-4333-8333-333333333333"
FIRST_ATTEMPT = "44444444-4444-4444-8444-444444444444"
RETRY_ATTEMPT = "55555555-5555-4555-8555-555555555555"
AUTHORIZATION_REF = "tb1-authz:v1:" + ("4" * 64)


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


composition = _load("runner_custodial_dispatch_test", COMPOSITION_PATH)
webgoat = _load("runner_custodial_webgoat_test", ADAPTER_PATH)
custody_module = _load("runner_custodial_evidence_test", CUSTODY_PATH)
store_module = _load("runner_custodial_store_test", STORE_PATH)


def _iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


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


@dataclass
class StaticResolver:
    binding: VerifiedBinding

    def resolve(self, authorization_ref: str):
        assert authorization_ref == AUTHORIZATION_REF
        return self.binding


class FakeProbe:
    def __init__(self) -> None:
        self.calls = 0

    def get(self, *, timeout_seconds: float):
        assert 0 < timeout_seconds <= 10.0
        self.calls += 1
        return webgoat.ProbeResponse(status=200, headers=(("Server", "WebGoat"),))


class FailingStore:
    def __init__(self) -> None:
        self.calls = 0

    def put(self, record: dict[str, Any], payload: bytes) -> str:
        del record, payload
        self.calls += 1
        raise OSError("simulated Evidence Plane outage")


def _request(attempt_id: str = FIRST_ATTEMPT) -> dict[str, Any]:
    return {
        "message_type": "runner.step.request",
        "protocol_version": "2.0.0",
        "correlation": {
            "campaign_id": CAMPAIGN_ID,
            "run_id": RUN_ID,
            "step_id": STEP_ID,
            "attempt_id": attempt_id,
        },
        "emitted_at": "2026-08-09T19:00:00Z",
        "authorization_ref": AUTHORIZATION_REF,
        "idempotency_key": "fixture-custodial-dispatch-key",
        "operation": {
            "capability_id": "web.discovery.headers",
            "input": {
                "operation_id": "web.discovery.headers",
                "operation_version": "1.0.0",
                "intrusiveness_level": "L1",
                "target": {"type": "lab-asset", "value": "webgoat-web"},
                "parameters": {},
            },
        },
        "timeout_budget": {"soft_timeout_ms": 1000, "hard_timeout_ms": 5000},
        "retry_policy": {"max_attempts": 1, "retryable_error_codes": []},
        "cancellation_policy": {"mode": "cooperative", "grace_period_ms": 0},
    }


def _verified(request: dict[str, Any]) -> VerifiedBinding:
    payload = request["operation"]["input"]
    now = datetime.now(timezone.utc)
    return VerifiedBinding(
        authorization_ref=AUTHORIZATION_REF,
        issued_at=_iso(now - timedelta(seconds=30)),
        expires_at=_iso(now + timedelta(minutes=5)),
        campaign_id=CAMPAIGN_ID,
        run_id=RUN_ID,
        step_id=STEP_ID,
        operation_id=payload["operation_id"],
        operation_version=payload["operation_version"],
        operation_parameters_sha256=webgoat.authorization_contract.canonical_parameters_sha256(
            payload["parameters"]
        ),
        capability_id=request["operation"]["capability_id"],
        target_sha256=webgoat.gateway_contract.canonical_target_digest(payload["target"]),
        intrusiveness_level=payload["intrusiveness_level"],
    )


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
                "allowed_peers": [{
                    "principal_id": "hexor.execution-gateway",
                    "uid": os.getuid(),
                    "gid": os.getgid(),
                    "purpose": "runner-dispatch",
                }],
            },
            "mtls": {
                "status": "FUTURE",
                "identity_source": "x509-client-certificate",
                "trust_store": "NOT_CONFIGURED",
            },
        },
    }


def _routing_policy() -> dict[str, Any]:
    return {
        "schema_version": "1.0",
        "policy_id": "hexor.runner.dispatch.routing",
        "state": "ENABLED",
        "default": "deny",
        "runtime_status": "NOT_RUN",
        "execution_authority": "none",
        "bindings": [{
            "principal_id": "hexor.execution-gateway",
            "adapter_id": "webgoat-l1",
            "target_id": "webgoat-web",
            "capabilities": ["web.discovery.headers"],
        }],
    }


def _adapter_registry() -> dict[str, Any]:
    registry = yaml.safe_load(ADAPTER_REGISTRY_PATH.read_text(encoding="utf-8"))
    registry = copy.deepcopy(registry)
    registry["adapters"][0]["status"] = "AS_BUILT"
    registry["adapters"][0]["runtime_status"] = "READY"
    return registry


def _custody(*, enabled: bool = True):
    policy = custody_module.load_policy(CUSTODY_POLICY_PATH)
    if enabled:
        policy["state"] = "ENABLED"
    return custody_module.RunnerOutcomeCustody(policy)


def _adapter(tmp_path: Path, probe: FakeProbe):
    request = _request()
    return webgoat.build_adapter(
        ledger_path=tmp_path / "adapter-ledger.sqlite3",
        authorization_resolver=StaticResolver(_verified(request)),
        probe=probe,
    )


def _dispatch(tmp_path: Path, *, request, adapter, custody, store):
    left, right = socket.socketpair(socket.AF_UNIX, socket.SOCK_STREAM)
    try:
        return composition.dispatch_with_custody_from_unix_peer(
            peer_socket=left,
            request=request,
            transport_policy=_transport_policy(),
            routing_policy=_routing_policy(),
            adapter_registry=_adapter_registry(),
            adapters={"webgoat-l1": adapter},
            evidence_custody=custody,
            evidence_store=store,
            results_root=tmp_path / "results",
        )
    finally:
        left.close()
        right.close()


def test_missing_custody_blocks_before_target_effect(tmp_path: Path) -> None:
    probe = FakeProbe()
    adapter = _adapter(tmp_path, probe)
    store = store_module.LocalEvidenceStore(tmp_path / "store")
    with pytest.raises(composition.CustodialDispatchError) as exc:
        _dispatch(tmp_path, request=_request(), adapter=adapter, custody=None, store=store)
    assert exc.value.code == "EVIDENCE_CUSTODY_UNAVAILABLE"
    assert probe.calls == 0


def test_disabled_custody_blocks_before_target_effect(tmp_path: Path) -> None:
    probe = FakeProbe()
    adapter = _adapter(tmp_path, probe)
    store = store_module.LocalEvidenceStore(tmp_path / "store")
    with pytest.raises(composition.CustodialDispatchError) as exc:
        _dispatch(
            tmp_path,
            request=_request(),
            adapter=adapter,
            custody=_custody(enabled=False),
            store=store,
        )
    assert exc.value.code == "EVIDENCE_CUSTODY_DISABLED"
    assert probe.calls == 0


def test_missing_evidence_store_blocks_before_target_effect(tmp_path: Path) -> None:
    probe = FakeProbe()
    adapter = _adapter(tmp_path, probe)
    with pytest.raises(composition.CustodialDispatchError) as exc:
        _dispatch(
            tmp_path,
            request=_request(),
            adapter=adapter,
            custody=_custody(),
            store=None,
        )
    assert exc.value.code == "EVIDENCE_STORE_UNAVAILABLE"
    assert probe.calls == 0


def test_authenticated_dispatch_returns_success_only_after_custody(tmp_path: Path) -> None:
    probe = FakeProbe()
    adapter = _adapter(tmp_path, probe)
    store = store_module.LocalEvidenceStore(tmp_path / "store")
    result = _dispatch(
        tmp_path,
        request=_request(),
        adapter=adapter,
        custody=_custody(),
        store=store,
    )
    assert result.messages[-1]["status"] == "PASS"
    assert probe.calls == 1
    assert result.custody["execution_id"].startswith("runner-")
    assert store.verify(result.custody["manifest_evidence_id"])
    assert store.verify(result.custody["summary_evidence_id"])
    safe = result.as_safe_dict()
    assert safe["terminal_status"] == "PASS"
    assert "output" not in safe


def test_projection_failure_then_exact_retry_completes_custody_without_second_effect(
    tmp_path: Path,
) -> None:
    probe = FakeProbe()
    adapter = _adapter(tmp_path, probe)
    custody = _custody()
    failing = FailingStore()

    with pytest.raises(composition.CustodialDispatchError) as exc:
        _dispatch(
            tmp_path,
            request=_request(FIRST_ATTEMPT),
            adapter=adapter,
            custody=custody,
            store=failing,
        )
    assert exc.value.code == "EVIDENCE_CUSTODY_FAILED"
    assert probe.calls == 1

    healthy = store_module.LocalEvidenceStore(tmp_path / "healthy-store")
    recovered = _dispatch(
        tmp_path,
        request=_request(RETRY_ATTEMPT),
        adapter=adapter,
        custody=custody,
        store=healthy,
    )
    assert recovered.messages[-1]["status"] == "PASS"
    assert recovered.messages[-1]["correlation"]["attempt_id"] == FIRST_ATTEMPT
    assert recovered.custody["replayed_custody"] is True
    assert probe.calls == 1
    assert healthy.verify(recovered.custody["manifest_evidence_id"])
    assert healthy.verify(recovered.custody["summary_evidence_id"])


def test_custody_error_does_not_leak_store_exception_text(tmp_path: Path) -> None:
    probe = FakeProbe()
    adapter = _adapter(tmp_path, probe)
    with pytest.raises(composition.CustodialDispatchError) as exc:
        _dispatch(
            tmp_path,
            request=_request(),
            adapter=adapter,
            custody=_custody(),
            store=FailingStore(),
        )
    assert exc.value.code == "EVIDENCE_CUSTODY_FAILED"
    assert "simulated Evidence Plane outage" not in str(exc.value)
    assert probe.calls == 1
