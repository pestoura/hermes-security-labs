"""Contract tests for the AI/MCP runtime ↔ Runner Protocol v2 projection.

The suite proves the projection is a pure, fail-closed translation boundary:
protocol messages it emits are validated by the canonical SDK, refusals never
leak raw pack text, sanitisation is unconditional, and no execution, network,
subprocess or adapter import is reachable from the module.
"""

from __future__ import annotations

import ast
import copy
import sys
from pathlib import Path
from typing import Any

import pytest

PACK_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = PACK_ROOT.parents[2]
SDK_SRC = REPO_ROOT / "platform" / "runner-protocol" / "src"
PACK_SRC = PACK_ROOT / "src"
for source in (SDK_SRC, PACK_SRC):
    if str(source) not in sys.path:
        sys.path.insert(0, str(source))

from ai_mcp_runbooks.contracts import (  # noqa: E402
    Decision,
    Evidence,
    ExecutionRequest,
    ExecutionResult,
    Status,
)
from ai_mcp_runbooks.runner_protocol_projection import (  # noqa: E402
    CAPABILITY_ID,
    STATUS_MAP,
    ProjectionRefusal,
    canonical_digest,
    is_calibrated,
    project_execution_result,
    project_step_request,
    refusal_outcome,
)
from runner_protocol_v2 import validate_semantics  # noqa: E402

MODULE_PATH = PACK_SRC / "ai_mcp_runbooks" / "runner_protocol_projection.py"

CORRELATION = {
    "campaign_id": "11111111-1111-4111-8111-111111111111",
    "run_id": "22222222-2222-4222-8222-222222222222",
    "step_id": "33333333-3333-4333-8333-333333333333",
    "attempt_id": "44444444-4444-4444-8444-444444444444",
}
STARTED_AT = "2026-01-01T10:00:00.000Z"


def _input(**overrides: Any) -> dict[str, Any]:
    payload = {
        "schema_version": 1,
        "provider": "agent",
        "action": "conversation-test",
        "profile": "safe",
        "target_ref": "promptme",
        "scope": "laboratory",
        "arguments": {},
    }
    payload.update(overrides)
    return payload


def _request(capability: str = CAPABILITY_ID, **input_overrides: Any) -> dict[str, Any]:
    return {
        "message_type": "runner.step.request",
        "protocol_version": "2.0.0",
        "correlation": copy.deepcopy(CORRELATION),
        "emitted_at": "2026-08-09T10:00:00Z",
        "authorization_ref": "authz/campaign/ai-mcp-001",
        "idempotency_key": "idem:ai-mcp:step:0001",
        "operation": {"capability_id": capability, "input": _input(**input_overrides)},
        "timeout_budget": {"soft_timeout_ms": 1000, "hard_timeout_ms": 5000},
        "retry_policy": {"max_attempts": 2, "retryable_error_codes": ["TRANSIENT_DEPENDENCY"]},
        "cancellation_policy": {"mode": "cooperative", "grace_period_ms": 500},
    }


def _result(status: Status = Status.OK, **overrides: Any) -> ExecutionResult:
    base: dict[str, Any] = {
        "status": status,
        "decision": Decision.VULNERABLE,
        "provider": "agent",
        "action": "conversation-test",
        "profile": "safe",
        "target_ref": "promptme",
        "scope": "laboratory",
        "reason": "probe completed",
        "vulnerable_signals": ("prompt.injection.accepted",),
        "evidence": (Evidence(ref="rule-1", kind="rule", value=3),),
    }
    base.update(overrides)
    return ExecutionResult(**base)


# --------------------------------------------------------------------------
# Request projection
# --------------------------------------------------------------------------


def test_valid_request_projects_to_authorised_pack_request() -> None:
    projected = project_step_request(_request())
    assert isinstance(projected, ExecutionRequest)
    assert projected.handler == ("agent", "conversation-test")
    assert projected.target_ref == "promptme"
    assert is_calibrated(projected) is True


def test_uncalibrated_handler_projects_but_is_reported_uncalibrated() -> None:
    projected = project_step_request(_request(action="discover"))
    assert is_calibrated(projected) is False


def test_foreign_capability_is_refused_as_compatibility_error() -> None:
    with pytest.raises(ProjectionRefusal) as excinfo:
        project_step_request(_request(capability="api.http.get"))
    assert excinfo.value.error["code"] == "UNSUPPORTED_CAPABILITY"
    assert excinfo.value.error["category"] == "compatibility"


def test_non_request_message_is_refused() -> None:
    outcome = project_execution_result(_request(), _result(), started_at=STARTED_AT)
    with pytest.raises(ProjectionRefusal) as excinfo:
        project_step_request(outcome)
    assert excinfo.value.error["code"] == "INVALID_REQUEST"


def test_invalid_protocol_message_is_refused_without_raw_exception_text() -> None:
    broken = _request()
    del broken["timeout_budget"]
    with pytest.raises(ProjectionRefusal) as excinfo:
        project_step_request(broken)
    assert excinfo.value.error["code"] == "INVALID_REQUEST"
    assert "timeout_budget" not in excinfo.value.error["message"]


def test_invalid_runtime_input_is_refused_as_validation() -> None:
    with pytest.raises(ProjectionRefusal) as excinfo:
        project_step_request(_request(provider=""))
    assert excinfo.value.error["code"] == "INVALID_REQUEST"
    assert excinfo.value.error["category"] == "validation"


@pytest.mark.parametrize(
    ("override", "expected"),
    [
        ({"target_ref": "example.com"}, "AUTHORIZATION_DENIED"),
        ({"scope": "production"}, "AUTHORIZATION_DENIED"),
        ({"provider": "shell", "action": "run"}, "AUTHORIZATION_DENIED"),
    ],
)
def test_policy_refusals_are_authorization_denied(override: dict[str, Any], expected: str) -> None:
    with pytest.raises(ProjectionRefusal) as excinfo:
        project_step_request(_request(**override))
    assert excinfo.value.error["code"] == expected


def test_execution_policy_can_narrow_but_projection_cannot_widen() -> None:
    with pytest.raises(ProjectionRefusal):
        project_step_request(_request(), policy={"allowed_targets": ["llmforge"]})
    with pytest.raises(ProjectionRefusal):
        project_step_request(_request(), policy={"production_mode": True})


def test_request_never_selects_authorization_reference() -> None:
    projected = project_step_request(_request())
    assert not hasattr(projected, "authorization_ref")
    assert "authz" not in projected.to_dict().get("arguments", {})


# --------------------------------------------------------------------------
# Outcome projection
# --------------------------------------------------------------------------


@pytest.mark.parametrize("status", list(Status))
def test_every_runtime_status_maps_to_a_validated_terminal_outcome(status: Status) -> None:
    outcome = project_execution_result(_request(), _result(status), started_at=STARTED_AT)
    validate_semantics(outcome)
    assert outcome["status"] == STATUS_MAP[status]
    assert outcome["correlation"] == CORRELATION
    assert len(outcome["evidence_refs"]) == 1


def test_status_map_covers_the_whole_runtime_status_enum() -> None:
    assert set(STATUS_MAP) == set(Status)


def test_security_decision_does_not_become_a_protocol_failure() -> None:
    vulnerable = project_execution_result(
        _request(), _result(decision=Decision.VULNERABLE), started_at=STARTED_AT
    )
    secure = project_execution_result(
        _request(), _result(decision=Decision.SECURE), started_at=STARTED_AT
    )
    assert vulnerable["status"] == "PASS"
    assert secure["status"] == "PASS"
    assert vulnerable["output"]["runtime_decision"] == "vulnerable"


def test_error_and_not_implemented_carry_normalized_errors() -> None:
    error = project_execution_result(_request(), _result(Status.ERROR), started_at=STARTED_AT)
    refused = project_execution_result(
        _request(), _result(Status.NOT_IMPLEMENTED), started_at=STARTED_AT
    )
    assert error["error"]["code"] == "EXECUTION_FAILED"
    assert refused["status"] == "REFUSED"
    assert refused["error"]["category"] == "compatibility"


def test_pass_never_carries_an_error() -> None:
    outcome = project_execution_result(_request(), _result(Status.OK), started_at=STARTED_AT)
    assert "error" not in outcome


def test_evidence_reference_is_deterministic_and_carries_no_runtime_text() -> None:
    first = project_execution_result(_request(), _result(), started_at=STARTED_AT)
    second = project_execution_result(_request(), _result(), started_at=STARTED_AT)
    assert first["evidence_refs"] == second["evidence_refs"]
    assert first["evidence_refs"][0]["sha256"] == canonical_digest(
        {
            **_result().to_dict(),
            "evidence": [{"ref": "rule-1", "kind": "rule", "value": 3, "redacted": True}],
            "meta": {},
            "reason": "probe completed",
        }
    )


def test_secret_and_prompt_material_never_reaches_the_outcome() -> None:
    # Canaries are assembled at runtime so the test file itself contains no
    # literal that a secret scanner could reasonably treat as a credential.
    canary = "abc" + "def" + "123456"
    token_canary = "gh" + "p_" + "a" * 20
    leaky = _result(
        reason=f"token={canary} leaked",
        meta={"prompt": "ignore previous instructions", "token": token_canary},
        evidence=(Evidence(ref="leak", kind="raw", value="HERMES_PHASE2_SYNTHETIC_MARKER"),),
    )
    outcome = project_execution_result(_request(), leaky, started_at=STARTED_AT)
    serialized = str(outcome)
    for forbidden in (canary, "ignore previous instructions", token_canary, "PHASE2"):
        assert forbidden not in serialized


def test_sanitisation_is_applied_to_an_unsanitised_mapping_too() -> None:
    document = _result().to_dict()
    document["meta"] = {"password": "hunter2"}
    outcome = project_execution_result(_request(), document, started_at=STARTED_AT)
    assert "hunter2" not in str(outcome)


def test_unknown_runtime_status_is_an_internal_refusal() -> None:
    document = _result().to_dict()
    document["status"] = "teleported"
    with pytest.raises(ProjectionRefusal) as excinfo:
        project_execution_result(_request(), document, started_at=STARTED_AT)
    assert excinfo.value.error["code"] == "INTERNAL_ERROR"


def test_refusal_outcome_is_a_validated_decision_record() -> None:
    request = _request(capability="api.http.get")
    with pytest.raises(ProjectionRefusal) as excinfo:
        project_step_request(request)
    outcome = refusal_outcome(request, excinfo.value)
    validate_semantics(outcome)
    assert outcome["status"] == "REFUSED"
    assert outcome["evidence_refs"][0]["kind"] == "decision"
    assert outcome["error"]["code"] == "UNSUPPORTED_CAPABILITY"


def test_correlation_is_propagated_unchanged_end_to_end() -> None:
    request = _request()
    outcome = project_execution_result(request, _result(), started_at=STARTED_AT)
    assert outcome["correlation"] == request["correlation"]


# --------------------------------------------------------------------------
# Isolation invariants (static)
# --------------------------------------------------------------------------


def _module_tree() -> ast.Module:
    return ast.parse(MODULE_PATH.read_text(encoding="utf-8"))


def test_projection_imports_no_execution_dispatch_or_adapter_module() -> None:
    forbidden = {
        "ai_mcp_runbooks.dispatch",
        "ai_mcp_runbooks.execution",
        "ai_mcp_runbooks.adapters",
        "subprocess",
        "socket",
        "urllib",
        "urllib.request",
        "http",
        "requests",
    }
    imported: set[str] = set()
    for node in ast.walk(_module_tree()):
        if isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module)
    assert not (imported & forbidden), sorted(imported & forbidden)


def test_projection_source_declares_no_execution_entry_point() -> None:
    source = MODULE_PATH.read_text(encoding="utf-8")
    for forbidden in ("execute_runbook", "execute_command", "build_adapter", "Popen", "os.system"):
        assert forbidden not in source, forbidden


def test_projection_exposes_only_pure_translation_helpers() -> None:
    public = {
        node.name
        for node in _module_tree().body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and not node.name.startswith("_")
    }
    assert public == {
        "canonical_digest",
        "evidence_reference",
        "is_calibrated",
        "project_execution_result",
        "project_step_request",
        "refusal_outcome",
    }
