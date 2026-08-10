from __future__ import annotations

import ast
import importlib.util
import json
import sys
from pathlib import Path
from typing import Any

import jsonschema
import pytest

ROOT = Path(__file__).resolve().parents[2]
AUDIT_PATH = ROOT / "platform" / "runner-dispatch" / "audit.py"
SCHEMA_PATH = ROOT / "platform" / "runner-dispatch" / "dispatch-audit-event.schema.json"
AUTHORIZATION_REF = "tb1-authz:v1:" + ("3" * 64)


def _load(name: str, path: Path) -> Any:
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


audit = _load("runner_dispatch_audit_test", AUDIT_PATH)


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
        "idempotency_key": "audit-fixture-key-one",
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


def _allow() -> dict[str, Any]:
    return audit.build_dispatch_audit_event(
        principal_id="hexor.execution-gateway",
        transport="unix-peer",
        request=_request(),
        phase="pre-dispatch",
        decision="ALLOW",
        reason_code="ROUTING_BINDING_ACCEPTED",
        adapter_id="webgoat-l1",
    )


def test_allow_event_binds_authenticated_principal_to_runner_correlation() -> None:
    event = _allow()
    assert event["principal_id"] == "hexor.execution-gateway"
    assert event["transport"] == "unix-peer"
    assert event["correlation"] == _request()["correlation"]
    assert event["authorization_ref"] == AUTHORIZATION_REF
    assert event["capability_id"] == "web.discovery.headers"
    assert event["adapter_id"] == "webgoat-l1"
    assert event["decision"] == "ALLOW"
    assert event["phase"] == "pre-dispatch"


def test_event_is_sanitized_no_raw_target_or_parameters() -> None:
    event = _allow()
    serialized = json.dumps(event, sort_keys=True)
    assert "webgoat-web" not in serialized
    assert "follow_redirects" not in serialized
    assert "parameters" not in event
    assert "target" not in event
    assert len(event["target_sha256"]) == 64


def test_schema_accepts_allow_deny_and_terminal_events() -> None:
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    validator = jsonschema.Draft202012Validator(
        schema, format_checker=jsonschema.FormatChecker()
    )
    validator.validate(_allow())

    denied = audit.build_dispatch_audit_event(
        principal_id="hexor.execution-gateway",
        transport="unix-peer",
        request=_request(),
        phase="pre-dispatch",
        decision="DENY",
        reason_code="ROUTING_BINDING_DENIED",
    )
    validator.validate(denied)

    terminal = audit.build_dispatch_audit_event(
        principal_id="hexor.execution-gateway",
        transport="unix-peer",
        request=_request(),
        phase="terminal",
        decision="OUTCOME",
        reason_code="RUNNER_OUTCOME_RECORDED",
        adapter_id="webgoat-l1",
        terminal_status="SUCCEEDED",
    )
    validator.validate(terminal)


def test_fingerprint_is_stable_when_only_recorded_at_changes(monkeypatch) -> None:
    monkeypatch.setattr(audit, "_iso_now", lambda: "2026-08-10T20:00:00Z")
    first = _allow()
    monkeypatch.setattr(audit, "_iso_now", lambda: "2026-08-10T20:00:05Z")
    second = _allow()
    assert first["recorded_at"] != second["recorded_at"]
    assert first["event_fingerprint"] == second["event_fingerprint"]


def test_logical_retry_attempt_changes_fingerprint() -> None:
    request = _request()
    first = audit.build_dispatch_audit_event(
        principal_id="hexor.execution-gateway",
        transport="unix-peer",
        request=request,
        phase="pre-dispatch",
        decision="ALLOW",
        reason_code="ROUTING_BINDING_ACCEPTED",
        adapter_id="webgoat-l1",
    )
    request["correlation"]["attempt_id"] = "55555555-5555-4555-8555-555555555555"
    second = audit.build_dispatch_audit_event(
        principal_id="hexor.execution-gateway",
        transport="unix-peer",
        request=request,
        phase="pre-dispatch",
        decision="ALLOW",
        reason_code="ROUTING_BINDING_ACCEPTED",
        adapter_id="webgoat-l1",
    )
    assert first["event_fingerprint"] != second["event_fingerprint"]


@pytest.mark.parametrize(
    "principal,transport,code",
    [
        ("", "unix-peer", "AUDIT_PRINCIPAL_INVALID"),
        ("*", "unix-peer", "AUDIT_PRINCIPAL_INVALID"),
        ("hexor.execution-gateway", "", "AUDIT_TRANSPORT_INVALID"),
        ("hexor.execution-gateway", "UNIX PEER", "AUDIT_TRANSPORT_INVALID"),
    ],
)
def test_untrusted_identity_values_fail_closed(principal: str, transport: str, code: str) -> None:
    with pytest.raises(audit.DispatchAuditError) as exc:
        audit.build_dispatch_audit_event(
            principal_id=principal,
            transport=transport,
            request=_request(),
            phase="pre-dispatch",
            decision="DENY",
            reason_code="ROUTING_BINDING_DENIED",
        )
    assert exc.value.code == code


def test_request_must_be_valid_runner_step_request() -> None:
    request = _request()
    request["operation"]["input"]["parameters"]["token"] = "must-not-pass"
    with pytest.raises(audit.DispatchAuditError) as exc:
        audit.build_dispatch_audit_event(
            principal_id="hexor.execution-gateway",
            transport="unix-peer",
            request=request,
            phase="pre-dispatch",
            decision="DENY",
            reason_code="RUNNER_REQUEST_INVALID",
        )
    assert exc.value.code == "AUDIT_REQUEST_INVALID"


def test_terminal_phase_is_strict() -> None:
    with pytest.raises(audit.DispatchAuditError, match="requires OUTCOME"):
        audit.build_dispatch_audit_event(
            principal_id="hexor.execution-gateway",
            transport="unix-peer",
            request=_request(),
            phase="terminal",
            decision="ALLOW",
            reason_code="RUNNER_OUTCOME_RECORDED",
            adapter_id="webgoat-l1",
            terminal_status="SUCCEEDED",
        )

    with pytest.raises(audit.DispatchAuditError) as exc:
        audit.build_dispatch_audit_event(
            principal_id="hexor.execution-gateway",
            transport="unix-peer",
            request=_request(),
            phase="terminal",
            decision="OUTCOME",
            reason_code="RUNNER_OUTCOME_RECORDED",
            terminal_status="SUCCEEDED",
        )
    assert exc.value.code == "AUDIT_ADAPTER_REQUIRED"


def test_schema_is_strict() -> None:
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    assert schema["additionalProperties"] is False
    assert schema["properties"]["correlation"]["additionalProperties"] is False


def test_audit_projection_has_no_logging_or_network_io() -> None:
    source = AUDIT_PATH.read_text(encoding="utf-8")
    tree = ast.parse(source)
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module.split(".")[0])
    assert not imported & {"logging", "socket", "subprocess", "requests", "urllib", "os"}
    for forbidden in ("open(", "syslog", "http.client", "execute_command", "execute_runbook"):
        assert forbidden not in source
