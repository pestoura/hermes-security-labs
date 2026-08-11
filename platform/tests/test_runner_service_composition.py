from __future__ import annotations

import copy
import hashlib
import importlib.util
import os
import socket
import sys
import uuid
from pathlib import Path
from typing import Any

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
RUNNER_SDK_SRC = ROOT / "platform" / "runner-protocol" / "src"
if str(RUNNER_SDK_SRC) not in sys.path:
    sys.path.insert(0, str(RUNNER_SDK_SRC))


def _load(name: str, path: Path) -> Any:
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


service = _load(
    "runner_service_composition_test",
    ROOT / "platform" / "runner-service" / "service_composition.py",
)
audit_custody_module = _load(
    "runner_service_audit_custody_test",
    ROOT / "platform" / "evidence-plane" / "dispatch_audit_custody.py",
)
outcome_custody_module = _load(
    "runner_service_outcome_custody_test",
    ROOT / "platform" / "evidence-plane" / "runner_outcome_custody.py",
)
local_store = _load(
    "runner_service_local_store_test",
    ROOT / "platform" / "evidence-plane" / "local_store.py",
)

TRANSPORT_POLICY_PATH = ROOT / "platform" / "runner-transport" / "transport-policy.yaml"
ROUTING_POLICY_PATH = ROOT / "platform" / "runner-dispatch" / "routing-policy.yaml"
ADAPTER_REGISTRY_PATH = ROOT / "platform" / "runner-adapters" / "adapter-registry.yaml"
AUTHORIZATION_REF = "tb1-authz:v1:" + ("7" * 64)
PRINCIPAL = "hexor.execution-gateway"
CAMPAIGN_ID = "11111111-1111-4111-8111-111111111111"
RUN_ID = "22222222-2222-4222-8222-222222222222"
STEP_ID = "33333333-3333-4333-8333-333333333333"
ATTEMPT_ID = "44444444-4444-4444-8444-444444444444"


def _request() -> dict[str, Any]:
    return {
        "message_type": "runner.step.request",
        "protocol_version": "2.0.0",
        "correlation": {
            "campaign_id": CAMPAIGN_ID,
            "run_id": RUN_ID,
            "step_id": STEP_ID,
            "attempt_id": ATTEMPT_ID,
        },
        "emitted_at": "2026-08-10T20:00:00Z",
        "authorization_ref": AUTHORIZATION_REF,
        "idempotency_key": "service-composition-fixture",
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
                        "principal_id": PRINCIPAL,
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
                "principal_id": PRINCIPAL,
                "adapter_id": "webgoat-l1",
                "target_id": "webgoat-web",
                "capabilities": capabilities or ["web.discovery.headers"],
            }
        ],
    }


def _registry() -> dict[str, Any]:
    registry = yaml.safe_load(ADAPTER_REGISTRY_PATH.read_text(encoding="utf-8"))
    registry = copy.deepcopy(registry)
    registry["adapters"][0]["status"] = "AS_BUILT"
    registry["adapters"][0]["runtime_status"] = "READY"
    return registry


def _enabled_service_policy() -> dict[str, Any]:
    policy = service.load_policy()
    policy["state"] = "ENABLED"
    return policy


def _enabled_audit_custody():
    policy = audit_custody_module.load_policy()
    policy["state"] = "ENABLED"
    return audit_custody_module.DispatchAuditCustody(policy)


def _enabled_outcome_custody():
    policy = outcome_custody_module.load_policy()
    policy["state"] = "ENABLED"
    return outcome_custody_module.RunnerOutcomeCustody(policy)


class FakeAdapter:
    def __init__(self) -> None:
        self.calls = 0

    def dispatch(self, request: dict[str, Any]) -> dict[str, Any]:
        self.calls += 1
        output = {
            "adapter_id": "webgoat-l1",
            "target_id": "webgoat-web",
            "environment_id": "webgoat",
            "capability_id": "web.discovery.headers",
            "http_status": 200,
            "headers": [{"name": "server", "value": "fixture"}],
            "redirects_followed": False,
        }
        digest = hashlib.sha256(
            outcome_custody_module.execution_bridge.canonical_bytes(output)
        ).hexdigest()
        outcome = {
            "message_type": "runner.outcome",
            "protocol_version": request["protocol_version"],
            "correlation": dict(request["correlation"]),
            "emitted_at": "2026-08-10T20:00:01Z",
            "status": "PASS",
            "started_at": "2026-08-10T20:00:00Z",
            "finished_at": "2026-08-10T20:00:01Z",
            "output": output,
            "evidence_refs": [
                {
                    "evidence_id": str(
                        uuid.UUID("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa")
                    ),
                    "kind": "execution",
                    "classification": "INTERNAL",
                    "sha256": digest,
                }
            ],
        }
        return {"messages": [outcome]}


class BrokenAdapter:
    def __init__(self) -> None:
        self.calls = 0

    def dispatch(self, request: dict[str, Any]) -> dict[str, Any]:
        del request
        self.calls += 1
        return {"messages": [{"not": "runner-protocol"}]}


def _socket_pair():
    return socket.socketpair(socket.AF_UNIX, socket.SOCK_STREAM)


def _handle(
    tmp_path: Path,
    *,
    adapter: Any,
    service_policy: dict[str, Any] | None = None,
    routing_policy: dict[str, Any] | None = None,
    audit_custody: Any | None = None,
    outcome_custody: Any | None = None,
    evidence_store: Any | None = None,
):
    evidence = evidence_store or local_store.LocalEvidenceStore(tmp_path / "evidence")
    left, right = _socket_pair()
    try:
        return service.RunnerServiceComposition(
            service_policy or _enabled_service_policy()
        ).handle_accepted_peer(
            peer_socket=left,
            request=_request(),
            transport_policy=_transport_policy(),
            routing_policy=routing_policy or _routing_policy(),
            adapter_registry=_registry(),
            adapters={"webgoat-l1": adapter},
            audit_custody=audit_custody or _enabled_audit_custody(),
            outcome_custody=outcome_custody or _enabled_outcome_custody(),
            evidence_store=evidence,
            results_root=tmp_path / "results",
        )
    finally:
        left.close()
        right.close()


def test_canonical_service_policy_is_disabled_and_deny_all() -> None:
    policy = service.load_policy()
    assert service.validate_policy(policy) == []
    assert policy["state"] == "DISABLED"
    assert policy["default"] == "deny"
    assert policy["runtime_status"] == "NOT_RUN"
    assert policy["execution_authority"] == "none"


def test_committed_transport_and_routing_policies_remain_disabled() -> None:
    transport = yaml.safe_load(TRANSPORT_POLICY_PATH.read_text(encoding="utf-8"))
    routing = yaml.safe_load(ROUTING_POLICY_PATH.read_text(encoding="utf-8"))
    assert transport["state"] == "DISABLED"
    assert routing["state"] == "DISABLED"
    assert routing["bindings"] == []


def test_disabled_service_refuses_before_adapter(tmp_path: Path) -> None:
    adapter = FakeAdapter()
    with pytest.raises(service.RunnerServiceError) as exc:
        _handle(
            tmp_path,
            adapter=adapter,
            service_policy=service.load_policy(),
        )
    assert exc.value.code == "SERVICE_DISABLED"
    assert adapter.calls == 0


def test_full_composition_uses_real_peer_router_and_both_custodies(
    tmp_path: Path,
) -> None:
    adapter = FakeAdapter()
    evidence = local_store.LocalEvidenceStore(tmp_path / "evidence")
    result = _handle(
        tmp_path,
        adapter=adapter,
        evidence_store=evidence,
    )

    assert adapter.calls == 1
    assert result.principal_id == PRINCIPAL
    assert result.adapter_id == "webgoat-l1"
    assert result.terminal_status == "SUCCEEDED"
    assert result.message_count == 1
    assert len(result.audit_evidence_ids) == 2
    assert all(evidence.verify(item) for item in result.audit_evidence_ids)
    assert evidence.verify(result.outcome_manifest_evidence_id) is True
    assert evidence.verify(result.outcome_summary_evidence_id) is True
    assert outcome_custody_module.execution_bridge.verify_execution(
        tmp_path / "results", result.execution_id
    )["verified"] is True
    assert result.messages[-1]["message_type"] == "runner.outcome"


def test_pre_dispatch_audit_failure_blocks_router_and_adapter(tmp_path: Path) -> None:
    adapter = FakeAdapter()
    disabled_audit = audit_custody_module.DispatchAuditCustody(
        audit_custody_module.load_policy()
    )
    with pytest.raises(service.RunnerServiceError) as exc:
        _handle(
            tmp_path,
            adapter=adapter,
            audit_custody=disabled_audit,
        )
    assert exc.value.code == "AUDIT_CUSTODY_FAILED"
    assert adapter.calls == 0


def test_pre_effect_router_refusal_is_audited_without_adapter_invocation(
    tmp_path: Path,
) -> None:
    adapter = FakeAdapter()
    evidence = local_store.LocalEvidenceStore(tmp_path / "evidence")
    with pytest.raises(service.RunnerServiceError) as exc:
        _handle(
            tmp_path,
            adapter=adapter,
            routing_policy=_routing_policy(capabilities=["web.discovery.tls"]),
            evidence_store=evidence,
        )
    assert exc.value.code == "ROUTER_PRE_EFFECT_REFUSED"
    assert adapter.calls == 0
    assert len(list(evidence.records.glob("ev_*.json"))) == 2


def test_post_dispatch_router_failure_is_not_mislabeled_as_pre_effect_denial(
    tmp_path: Path,
) -> None:
    adapter = BrokenAdapter()
    evidence = local_store.LocalEvidenceStore(tmp_path / "evidence")
    with pytest.raises(service.RunnerServiceError) as exc:
        _handle(tmp_path, adapter=adapter, evidence_store=evidence)
    assert exc.value.code == "ROUTER_POST_DISPATCH_FAILED"
    assert adapter.calls == 1
    assert len(list(evidence.records.glob("ev_*.json"))) == 1


def test_post_effect_attempts_outcome_custody_when_terminal_audit_fails(
    tmp_path: Path,
) -> None:
    adapter = FakeAdapter()
    evidence = local_store.LocalEvidenceStore(tmp_path / "evidence")
    real_audit = _enabled_audit_custody()
    real_outcome = _enabled_outcome_custody()

    class FailSecondAudit:
        def __init__(self) -> None:
            self.calls = 0

        def persist(self, event, *, evidence_store):  # noqa: ANN001
            self.calls += 1
            if self.calls == 2:
                raise RuntimeError("terminal-audit-failure")
            return real_audit.persist(event, evidence_store=evidence_store)

    class RecordingOutcome:
        def __init__(self) -> None:
            self.called = False

        def persist(self, **kwargs):  # noqa: ANN003
            self.called = True
            return real_outcome.persist(**kwargs)

    audit = FailSecondAudit()
    outcome = RecordingOutcome()
    with pytest.raises(service.RunnerServiceError) as exc:
        _handle(
            tmp_path,
            adapter=adapter,
            audit_custody=audit,
            outcome_custody=outcome,
            evidence_store=evidence,
        )
    assert exc.value.code == "POST_EFFECT_CUSTODY_FAILED"
    assert outcome.called is True
    assert adapter.calls == 1
    assert len(list(evidence.records.glob("ev_*.json"))) >= 3


def test_service_source_has_no_listener_daemon_target_client_or_generic_execution() -> None:
    source = (
        ROOT / "platform" / "runner-service" / "service_composition.py"
    ).read_text(encoding="utf-8")
    for forbidden in (
        "socket.socket(",
        ".bind(",
        ".listen(",
        ".accept(",
        "subprocess",
        "requests",
        "http.client",
        "execute_command",
        "execute_runbook",
        "docker",
    ):
        assert forbidden not in source


def test_service_policy_never_claims_execution_authority() -> None:
    policy = _enabled_service_policy()
    policy["execution_authority"] = "runner-service"
    assert any(
        "never claim execution authority" in item
        for item in service.validate_policy(policy)
    )
