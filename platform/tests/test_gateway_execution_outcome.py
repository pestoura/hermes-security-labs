"""Repository-only tests for the sanitized gateway execution outcome boundary.

No runner, process, network, laboratory, scanner or target is executed here.
"""

from __future__ import annotations

import copy
import importlib.util
import json
import sys
from pathlib import Path
from typing import Any

import jsonschema

ROOT = Path(__file__).resolve().parents[2]
GATEWAY_DIR = ROOT / "platform/gateway-protocol"
RUNNER_SDK_SRC = ROOT / "platform/runner-protocol/src"

if str(RUNNER_SDK_SRC) not in sys.path:
    sys.path.insert(0, str(RUNNER_SDK_SRC))

from runner_protocol_v2 import request_fingerprint, validate_semantics  # noqa: E402

CAMPAIGN = "3f2a1c64-1e8b-4a2b-9c7d-1c2b3a4d5e6f"
RUN = "5c9d7e2a-8b41-4f6d-9a03-2d4e6f8a1b2c"
STEP = "7b1e4d3c-2a95-4c8e-8f10-3e5d7c9b1a24"
ATTEMPT = "9a3c5e71-4d62-4b18-8e27-5f7a9c1d3b46"
OTHER_ATTEMPT = "1d4f6a82-5e73-4c29-9f38-6a8b0d2e4c57"
EVIDENCE = "6b8e2d41-3f75-4c29-9a10-7d1e5f3b8c62"
AUTH_REF = "tb1-authz:v1:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
IDEMPOTENCY = "rp2-step-bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"


def _load(module_name: str, path: Path) -> Any:
    spec = importlib.util.spec_from_file_location(module_name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


outcome = _load("gateway_execution_outcome_under_test", GATEWAY_DIR / "outcome.py")
handoff_module = outcome.runner_handoff


def _correlation() -> dict[str, str]:
    return {
        "campaign_id": CAMPAIGN,
        "run_id": RUN,
        "step_id": STEP,
        "attempt_id": ATTEMPT,
    }


def _runner_request() -> dict[str, Any]:
    return {
        "message_type": "runner.step.request",
        "protocol_version": "2.0.0",
        "correlation": _correlation(),
        "emitted_at": "2026-08-07T17:00:00Z",
        "authorization_ref": AUTH_REF,
        "idempotency_key": IDEMPOTENCY,
        "operation": {
            "capability_id": "web.discovery.headers",
            "input": {
                "operation_id": "web.discovery.headers",
                "operation_version": "1.0.0",
                "intrusiveness_level": "L1",
                "target": {"type": "lab-asset", "value": "juice-shop-demo"},
                "parameters": {"follow_redirects": False},
            },
        },
        "timeout_budget": {"soft_timeout_ms": 30000, "hard_timeout_ms": 120000},
        "retry_policy": {
            "max_attempts": 2,
            "retryable_error_codes": ["TRANSIENT_DEPENDENCY", "RUNNER_UNAVAILABLE"],
        },
        "cancellation_policy": {"mode": "cooperative", "grace_period_ms": 5000},
        "progress_mode": "optional",
    }


def _handoff_result() -> Any:
    request = _runner_request()
    fingerprint = request_fingerprint(request)
    return handoff_module.RunnerHandoffResult(
        request_built=True,
        codes=("HANDOFF_STEP_REQUEST_BUILT",),
        admission_codes=("ADMIT_TYPED_OPERATION",),
        request_id="gateway-outcome-test",
        campaign_id=CAMPAIGN,
        operation_id="web.discovery.headers",
        operation_version="1.0.0",
        authorization_ref=AUTH_REF,
        idempotency_key=IDEMPOTENCY,
        request_fingerprint=fingerprint,
        runner_request=request,
    )


def _evidence() -> dict[str, Any]:
    return {
        "evidence_id": EVIDENCE,
        "kind": "execution",
        "classification": "RESTRICTED",
        "sha256": "c" * 64,
        "uri": "file:///restricted/raw/runner-output.json",
    }


def _pass_outcome() -> dict[str, Any]:
    return {
        "message_type": "runner.outcome",
        "protocol_version": "2.0.0",
        "correlation": _correlation(),
        "emitted_at": "2026-08-07T17:00:03Z",
        "status": "PASS",
        "started_at": "2026-08-07T17:00:01Z",
        "finished_at": "2026-08-07T17:00:03Z",
        "evidence_refs": [_evidence()],
        "output": {
            "result": "credential-like-value-must-not-cross-the-boundary",
            "nested": {"raw": "target-specific-output"},
        },
    }


def _error_outcome() -> dict[str, Any]:
    value = _pass_outcome()
    value["status"] = "ERROR"
    value["error"] = {
        "code": "EXECUTION_FAILED",
        "category": "execution",
        "retryable": False,
        "message": "backend returned credential-like-sensitive-value",
        "safe_context": {"detail": "raw internal context must not cross"},
    }
    return value


def test_valid_runner_outcome_builds_sanitized_typed_outcome() -> None:
    result = outcome.build_execution_outcome(_handoff_result(), _pass_outcome())

    assert result.outcome_built is True
    assert result.codes == ("GATEWAY_OUTCOME_BUILT",)
    assert result.runner_status == "PASS"
    assert result.evidence_count == 1
    assert result.output_present is True
    assert result.error_code is None

    typed = result.typed_outcome
    assert typed is not None
    assert typed["message_type"] == "gateway.execution.outcome"
    assert typed["correlation"] == _correlation()
    assert typed["authorization_ref"] == AUTH_REF
    assert typed["idempotency_key"] == IDEMPOTENCY
    assert typed["operation_id"] == "web.discovery.headers"
    assert typed["capability_id"] == "web.discovery.headers"
    assert typed["output_present"] is True
    assert "output" not in typed
    assert "uri" not in typed["evidence_refs"][0]
    assert "error" not in typed


def test_typed_outcome_validates_against_strict_gateway_schema() -> None:
    result = outcome.build_execution_outcome(_handoff_result(), _pass_outcome())
    assert result.typed_outcome is not None

    schema = json.loads(
        (GATEWAY_DIR / "gateway-execution-outcome.schema.json").read_text(
            encoding="utf-8"
        )
    )
    jsonschema.Draft202012Validator(
        schema, format_checker=jsonschema.FormatChecker()
    ).validate(result.typed_outcome)


def test_error_message_and_safe_context_are_not_forwarded() -> None:
    runner = _error_outcome()
    validate_semantics(runner)

    result = outcome.build_execution_outcome(_handoff_result(), runner)

    assert result.outcome_built is True
    assert result.error_code == "EXECUTION_FAILED"
    assert result.typed_outcome is not None
    assert result.typed_outcome["error"] == {
        "code": "EXECUTION_FAILED",
        "category": "execution",
        "retryable": False,
    }
    rendered = json.dumps(result.typed_outcome, sort_keys=True)
    assert runner["error"]["message"] not in rendered
    assert "raw internal context must not cross" not in rendered


def test_raw_output_and_restricted_evidence_uri_do_not_cross_boundary() -> None:
    runner = _pass_outcome()
    result = outcome.build_execution_outcome(_handoff_result(), runner)

    assert result.typed_outcome is not None
    rendered = json.dumps(result.typed_outcome, sort_keys=True)
    assert "credential-like-value-must-not-cross-the-boundary" not in rendered
    assert "target-specific-output" not in rendered
    assert "file:///restricted/raw/runner-output.json" not in rendered


def test_mismatched_correlation_is_refused_without_derivative() -> None:
    runner = _pass_outcome()
    runner["correlation"]["attempt_id"] = OTHER_ATTEMPT

    result = outcome.build_execution_outcome(_handoff_result(), runner)

    assert result.outcome_built is False
    assert result.codes == ("RUNNER_OUTCOME_CORRELATION_MISMATCH",)
    assert result.typed_outcome is None


def test_malformed_runner_outcome_is_refused() -> None:
    runner = _pass_outcome()
    del runner["evidence_refs"]

    result = outcome.build_execution_outcome(_handoff_result(), runner)

    assert result.outcome_built is False
    assert result.codes == ("RUNNER_OUTCOME_INVALID",)
    assert result.typed_outcome is None


def test_non_outcome_runner_message_is_refused() -> None:
    runner = _pass_outcome()
    runner["message_type"] = "runner.progress"

    result = outcome.build_execution_outcome(_handoff_result(), runner)

    assert result.outcome_built is False
    assert result.typed_outcome is None
    assert "RUNNER_OUTCOME" in result.codes[0]


def test_unbuilt_handoff_is_refused_before_outcome_processing() -> None:
    handoff = _handoff_result()
    handoff = handoff_module.RunnerHandoffResult(
        request_built=False,
        codes=("ADMISSION_REFUSED",),
        admission_codes=("ROE_REFUSED",),
        request_id=handoff.request_id,
        campaign_id=handoff.campaign_id,
        operation_id=handoff.operation_id,
        operation_version=handoff.operation_version,
        authorization_ref=None,
        idempotency_key=None,
        request_fingerprint=None,
        runner_request=None,
    )

    result = outcome.build_execution_outcome(handoff, _pass_outcome())

    assert result.outcome_built is False
    assert result.codes == ("OUTCOME_HANDOFF_NOT_BUILT",)
    assert result.typed_outcome is None


def test_tampered_built_request_fingerprint_is_refused() -> None:
    handoff = _handoff_result()
    assert handoff.runner_request is not None
    handoff.runner_request["operation"]["input"]["parameters"]["follow_redirects"] = True

    result = outcome.build_execution_outcome(handoff, _pass_outcome())

    assert result.outcome_built is False
    assert result.codes == ("OUTCOME_HANDOFF_FINGERPRINT_MISMATCH",)
    assert result.typed_outcome is None


def test_handoff_authorization_ref_mismatch_is_refused() -> None:
    handoff = _handoff_result()
    assert handoff.runner_request is not None
    handoff.runner_request["authorization_ref"] = "tb1-authz:v1:" + "d" * 64
    handoff.request_fingerprint = handoff.request_fingerprint  # type: ignore[misc]

    # The request fingerprint also changes, so construct a consistent forged result
    # to prove the separate authorization binding is checked.
    forged = handoff_module.RunnerHandoffResult(
        request_built=True,
        codes=handoff.codes,
        admission_codes=handoff.admission_codes,
        request_id=handoff.request_id,
        campaign_id=handoff.campaign_id,
        operation_id=handoff.operation_id,
        operation_version=handoff.operation_version,
        authorization_ref=AUTH_REF,
        idempotency_key=handoff.idempotency_key,
        request_fingerprint=request_fingerprint(handoff.runner_request),
        runner_request=handoff.runner_request,
    )

    result = outcome.build_execution_outcome(forged, _pass_outcome())

    assert result.outcome_built is False
    assert result.codes == ("OUTCOME_HANDOFF_AUTHORIZATION_MISMATCH",)


def test_handoff_idempotency_mismatch_is_refused() -> None:
    handoff = _handoff_result()
    forged = handoff_module.RunnerHandoffResult(
        request_built=True,
        codes=handoff.codes,
        admission_codes=handoff.admission_codes,
        request_id=handoff.request_id,
        campaign_id=handoff.campaign_id,
        operation_id=handoff.operation_id,
        operation_version=handoff.operation_version,
        authorization_ref=handoff.authorization_ref,
        idempotency_key="rp2-step-" + "e" * 64,
        request_fingerprint=handoff.request_fingerprint,
        runner_request=handoff.runner_request,
    )

    result = outcome.build_execution_outcome(forged, _pass_outcome())

    assert result.outcome_built is False
    assert result.codes == ("OUTCOME_HANDOFF_IDEMPOTENCY_MISMATCH",)


def test_result_repr_and_summary_do_not_expose_raw_payloads() -> None:
    runner = _error_outcome()
    result = outcome.build_execution_outcome(_handoff_result(), runner)

    rendered = repr(result)
    summary = json.dumps(result.sanitized_summary(), sort_keys=True)
    for sensitive in (
        "credential-like-value-must-not-cross-the-boundary",
        "target-specific-output",
        runner["error"]["message"],
        "raw internal context must not cross",
        "file:///restricted/raw/runner-output.json",
    ):
        assert sensitive not in rendered
        assert sensitive not in summary
    assert "typed_outcome=" not in rendered


def test_gateway_outcome_is_descriptive_not_authorizing() -> None:
    schema = json.loads(
        (GATEWAY_DIR / "gateway-execution-outcome.schema.json").read_text(
            encoding="utf-8"
        )
    )
    properties = schema["properties"]

    for forbidden in ("authorized", "allow", "approval", "authorization_receipt"):
        assert forbidden not in properties
    assert "authorization_ref" in properties
