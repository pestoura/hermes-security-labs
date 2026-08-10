from __future__ import annotations

import ast
import importlib.util
import json
import sys
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[2]
RUNNER_SDK_SRC = ROOT / "platform" / "runner-protocol" / "src"
if str(RUNNER_SDK_SRC) not in sys.path:
    sys.path.insert(0, str(RUNNER_SDK_SRC))

AUDIT_PATH = ROOT / "platform" / "runner-dispatch" / "audit.py"
CUSTODY_PATH = ROOT / "platform" / "evidence-plane" / "dispatch_audit_custody.py"
STORE_PATH = ROOT / "platform" / "evidence-plane" / "local_store.py"


def _load(name: str, path: Path) -> Any:
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


audit = _load("dispatch_audit_for_custody_test", AUDIT_PATH)
custody = _load("dispatch_audit_custody_test", CUSTODY_PATH)
local_store = _load("dispatch_audit_local_store_test", STORE_PATH)

AUTHORIZATION_REF = "tb1-authz:v1:" + ("4" * 64)


def _request() -> dict[str, Any]:
    return {
        "message_type": "runner.step.request",
        "protocol_version": "2.0.0",
        "correlation": {
            "campaign_id": "11111111-1111-4111-8111-111111111111",
            "run_id": "22222222-2222-4222-8222-222222222222",
            "step_id": "33333333-3333-4333-8333-333333333333",
            "attempt_id": "44444444-4444-4444-8444-444444444444",
        },
        "emitted_at": "2026-08-10T20:00:00Z",
        "authorization_ref": AUTHORIZATION_REF,
        "idempotency_key": "audit-custody-fixture-key",
        "operation": {
            "capability_id": "web.discovery.headers",
            "input": {
                "operation_id": "web.discovery.headers",
                "operation_version": "1.0.0",
                "intrusiveness_level": "L1",
                "target": {"type": "lab-asset", "value": "webgoat-web"},
                "parameters": {"follow_redirects": False},
            },
        },
        "timeout_budget": {"soft_timeout_ms": 1000, "hard_timeout_ms": 5000},
        "retry_policy": {"max_attempts": 1, "retryable_error_codes": []},
        "cancellation_policy": {"mode": "cooperative", "grace_period_ms": 0},
    }


def _event() -> dict[str, Any]:
    event = audit.build_dispatch_audit_event(
        principal_id="hexor.execution-gateway",
        transport="unix-peer",
        request=_request(),
        phase="pre-dispatch",
        decision="ALLOW",
        reason_code="ROUTING_BINDING_ACCEPTED",
        adapter_id="webgoat-l1",
    )
    # Stabilize the occurrence timestamp while preserving the logical fingerprint.
    event["recorded_at"] = "2026-08-10T20:05:00Z"
    return event


def _enabled_policy() -> dict[str, Any]:
    policy = custody.load_policy()
    policy["state"] = "ENABLED"
    return policy


def test_canonical_policy_is_disabled_and_fail_closed() -> None:
    policy = custody.load_policy()
    assert policy["state"] == "DISABLED"
    assert policy["default"] == "deny"
    assert policy["runtime_status"] == "NOT_RUN"
    assert policy["execution_authority"] == "none"
    assert custody.validate_policy(policy) == []

    bridge = custody.DispatchAuditCustody(policy)
    with pytest.raises(custody.DispatchAuditCustodyError) as exc:
        bridge.persist(_event(), evidence_store=object())
    assert exc.value.code == "CUSTODY_DISABLED"


def test_enabled_test_policy_projects_exact_event_to_existing_evidence_plane(tmp_path: Path) -> None:
    store = local_store.LocalEvidenceStore(tmp_path / "evidence")
    bridge = custody.DispatchAuditCustody(_enabled_policy())
    event = _event()

    result = bridge.persist(event, evidence_store=store)
    assert store.verify(result.evidence_id) is True
    assert result.event_fingerprint == event["event_fingerprint"]
    assert result.classification == "restricted"

    record = store.get_record(result.evidence_id)
    assert record["classification"] == "restricted"
    assert record["correlation"] == event["correlation"]
    assert record["origin"]["producer"] == "runner-dispatch-audit-custody-v1"
    assert record["origin"]["operation"] == "runner.dispatch.audit.pre-dispatch"
    assert record["content"]["storage_ref"].startswith("evidence://")
    assert event["event_fingerprint"] in record["content"]["storage_ref"]
    assert result.payload_sha256 in record["content"]["storage_ref"]
    assert record["retention"]["policy_id"] == "default-30d"
    assert record["retention"]["retain_until"] == "2026-09-09T20:05:00Z"


def test_exact_replay_is_idempotent_in_canonical_local_store(tmp_path: Path) -> None:
    store = local_store.LocalEvidenceStore(tmp_path / "evidence")
    bridge = custody.DispatchAuditCustody(_enabled_policy())
    event = _event()

    first = bridge.persist(event, evidence_store=store)
    second = bridge.persist(event, evidence_store=store)
    assert second.evidence_id == first.evidence_id
    assert second.payload_sha256 == first.payload_sha256
    records = list((store.root / "records").glob("ev_*.json"))
    assert len(records) == 1


def test_custodied_payload_contains_sanitized_event_not_raw_target_or_parameters(tmp_path: Path) -> None:
    store = local_store.LocalEvidenceStore(tmp_path / "evidence")
    result = custody.DispatchAuditCustody(_enabled_policy()).persist(
        _event(), evidence_store=store
    )
    record = store.get_record(result.evidence_id)
    digest = record["content"]["sha256"]
    payload = (store.objects / digest[:2] / digest).read_text(encoding="utf-8")
    decoded = json.loads(payload)

    assert decoded["principal_id"] == "hexor.execution-gateway"
    assert decoded["authorization_ref"] == AUTHORIZATION_REF
    assert "webgoat-web" not in payload
    assert "follow_redirects" not in payload
    assert "target" not in decoded
    assert "parameters" not in decoded


def test_fingerprint_tampering_is_refused_before_evidence_write(tmp_path: Path) -> None:
    store = local_store.LocalEvidenceStore(tmp_path / "evidence")
    event = _event()
    event["decision"] = "DENY"
    with pytest.raises(custody.DispatchAuditCustodyError) as exc:
        custody.DispatchAuditCustody(_enabled_policy()).persist(event, evidence_store=store)
    assert exc.value.code == "AUDIT_FINGERPRINT_MISMATCH"
    assert list((store.root / "records").glob("*.json")) == []


def test_schema_invalid_event_is_refused_before_evidence_write(tmp_path: Path) -> None:
    store = local_store.LocalEvidenceStore(tmp_path / "evidence")
    event = _event()
    event["raw_target"] = "forbidden"
    with pytest.raises(custody.DispatchAuditCustodyError) as exc:
        custody.DispatchAuditCustody(_enabled_policy()).persist(event, evidence_store=store)
    assert exc.value.code == "AUDIT_EVENT_INVALID"
    assert list((store.root / "records").glob("*.json")) == []


def test_store_contract_requires_put_and_verify() -> None:
    bridge = custody.DispatchAuditCustody(_enabled_policy())
    with pytest.raises(custody.DispatchAuditCustodyError) as exc:
        bridge.persist(_event(), evidence_store=None)
    assert exc.value.code == "EVIDENCE_STORE_UNAVAILABLE"

    class PutOnly:
        def put(self, record, payload):  # noqa: ANN001
            return "ev_" + ("a" * 32)

    with pytest.raises(custody.DispatchAuditCustodyError) as exc:
        bridge.persist(_event(), evidence_store=PutOnly())
    assert exc.value.code == "EVIDENCE_STORE_UNAVAILABLE"


def test_backend_failures_are_sanitized() -> None:
    class FailingStore:
        def put(self, record, payload):  # noqa: ANN001
            raise RuntimeError("sensitive-backend-path")

        def verify(self, evidence_id):  # noqa: ANN001
            return True

    with pytest.raises(custody.DispatchAuditCustodyError) as exc:
        custody.DispatchAuditCustody(_enabled_policy()).persist(
            _event(), evidence_store=FailingStore()
        )
    assert exc.value.code == "EVIDENCE_PROJECTION_FAILED"
    assert "sensitive-backend-path" not in str(exc.value)


def test_integrity_verification_failure_is_refused() -> None:
    class NonVerifyingStore:
        def put(self, record, payload):  # noqa: ANN001
            return record["evidence_id"]

        def verify(self, evidence_id):  # noqa: ANN001
            return False

    with pytest.raises(custody.DispatchAuditCustodyError) as exc:
        custody.DispatchAuditCustody(_enabled_policy()).persist(
            _event(), evidence_store=NonVerifyingStore()
        )
    assert exc.value.code == "EVIDENCE_VERIFICATION_FAILED"


@pytest.mark.parametrize(
    "mutator,expected",
    [
        (lambda p: p.update(state="BROKEN"), "state must be DISABLED or ENABLED"),
        (lambda p: p.update(default="allow"), "default must be deny"),
        (lambda p: p.update(runtime_status="READY"), "runtime_status must remain NOT_RUN"),
        (lambda p: p.update(execution_authority="runner"), "must never claim execution authority"),
        (lambda p: p["custody"].update(classification="sanitized"), "classification must be restricted"),
        (lambda p: p["custody"].update(retention_days=0), "retention_days"),
        (lambda p: p["custody"].update(include_raw_application_payloads=True), "raw application payload"),
    ],
)
def test_policy_mutations_fail_validation(mutator, expected: str) -> None:  # noqa: ANN001
    policy = custody.load_policy()
    mutator(policy)
    assert any(expected in finding for finding in custody.validate_policy(policy))


def test_custody_source_does_not_create_parallel_store_or_runtime_effect() -> None:
    source = CUSTODY_PATH.read_text(encoding="utf-8")
    tree = ast.parse(source)
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module.split(".")[0])
    assert not imported & {"socket", "subprocess", "requests", "urllib", "docker"}
    assert "LocalEvidenceStore(" not in source
    assert "evidence_store.put(" in source
    for forbidden in ("execute_command", "execute_runbook", "docker compose", "network connect"):
        assert forbidden not in source
