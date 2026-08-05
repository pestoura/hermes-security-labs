"""End-to-end propagation tests for the bridge -> normalize -> evaluate path (#63).

Second-order root cause: ``ProcessBridgeAdapter`` could return an envelope-only
payload (``{}`` plus ``meta``) after a failed runner invocation. ``meta`` made the
payload non-empty, so ``_is_degraded_output`` considered it functional and the
normalizer emitted ``target_reachable=True`` / ``prerequisites_missing=False``,
producing a false ``secure`` on runbooks whose ``secure_when`` matches on absent
evidence.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
import yaml

from api_pentest_runbooks.adapter import build_bridge_result, sanitize_stderr
from evaluation import evaluate_signals, normalize_execution_output

PACK_ROOT = Path(__file__).resolve().parents[1]

AFFECTED_RUNBOOKS = (
    "API-CONFIG-DEBUG-MODE-008",
    "API-DATA-DIRECTORY-LIST-008",
    "API-DATA-SECRET-RESPONSE-006",
)


def _criteria(runbook_id: str) -> dict[str, list[str]]:
    for path in (PACK_ROOT / "runbooks").rglob("*.yaml"):
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        if isinstance(data, dict) and (data.get("metadata") or {}).get("id") == runbook_id:
            return dict(data.get("evaluation") or {})
    raise AssertionError(f"runbook not found: {runbook_id}")


class TestBuildBridgeResult:
    def test_empty_stdout_nonzero_exit_is_structured_error(self) -> None:
        result = build_bridge_result("", "boom", 1)
        assert result["status"] == "error"
        assert result["error_code"] == "runner.no_output"
        assert result["prerequisites_missing"] is True
        assert result["target_reachable"] is False
        assert result["meta"]["runner_exit_code"] == 1
        assert result["meta"]["runner_status"] == "error"

    def test_invalid_json_is_structured_error(self) -> None:
        result = build_bridge_result("not json at all", "", 0)
        assert result["error_code"] == "bridge.invalid_output"
        assert result["prerequisites_missing"] is True

    def test_envelope_only_stdout_is_not_functional(self) -> None:
        result = build_bridge_result(json.dumps({"meta": {"runner_status": "ok"}}), "", 0)
        assert result["error_code"] == "bridge.invalid_output"
        assert result["status"] == "error"

    def test_valid_payload_with_nonzero_exit_is_nonzero_exit_error(self) -> None:
        result = build_bridge_result(json.dumps({"status": "completed", "status_code": 200}), "", 3)
        assert result["error_code"] == "runner.nonzero_exit"
        assert result["prerequisites_missing"] is True
        assert result["meta"]["runner_exit_code"] == 3

    def test_success_payload_is_preserved(self) -> None:
        result = build_bridge_result(
            json.dumps({"status": "completed", "status_code": 200, "contains_sensitive_data": False}),
            "",
            0,
        )
        assert result["status"] == "completed"
        assert result["status_code"] == 200
        assert result["meta"]["runner_status"] == "ok"

    def test_raw_stdout_is_never_echoed_into_result(self) -> None:
        raw = "SUPERSECRETRAWSTDOUT"
        result = build_bridge_result(raw, "", 1)
        assert raw not in json.dumps(result)


class TestStderrSanitization:
    def test_traceback_paths_and_tokens_are_redacted(self) -> None:
        stderr = (
            "Traceback (most recent call last):\n"
            '  File "/opt/hex0r-api-runner/kali_runner.py", line 10\n'
            "Authorization: Bearer abcdef123456\n"
        )
        cleaned = sanitize_stderr(stderr)
        assert "Traceback" not in cleaned
        assert "abcdef123456" not in cleaned
        assert "/opt/hex0r-api-runner/kali_runner.py" not in cleaned

    def test_sanitized_stderr_in_bridge_result(self) -> None:
        result = build_bridge_result(
            "",
            'Traceback (most recent call last): token=deadbeef /opt/secret/path/file.py',
            1,
        )
        serialized = json.dumps(result)
        assert "Traceback" not in serialized
        assert "deadbeef" not in serialized
        assert "/opt/secret/path" not in serialized


class TestEndToEndPropagation:
    @pytest.mark.parametrize("runbook_id", AFFECTED_RUNBOOKS)
    def test_empty_stdout_exit_1_is_inconclusive(self, runbook_id: str) -> None:
        bridge_result = build_bridge_result("", "tool not found", 1)
        signals = normalize_execution_output("nuclei", bridge_result)
        result = evaluate_signals(signals, _criteria(runbook_id))
        assert result.decision == "inconclusive", result

    @pytest.mark.parametrize("runbook_id", AFFECTED_RUNBOOKS)
    def test_envelope_only_meta_payload_is_inconclusive(self, runbook_id: str) -> None:
        """Exact regression of the observed acceptance failure."""
        payload: dict[str, Any] = {"meta": {"runner_status": "error", "runner_exit_code": 1}}
        signals = normalize_execution_output("nuclei", payload)
        assert signals["target_reachable"] is False
        assert signals["prerequisites_missing"] is True
        result = evaluate_signals(signals, _criteria(runbook_id))
        assert result.decision == "inconclusive", result

    @pytest.mark.parametrize("runbook_id", AFFECTED_RUNBOOKS)
    def test_error_status_with_exit_zero_is_inconclusive(self, runbook_id: str) -> None:
        payload = {
            "status": "error",
            "error_code": "handler.tool_unavailable",
            "meta": {"runner_status": "ok", "runner_exit_code": 0},
        }
        signals = normalize_execution_output("nuclei", payload, runner_status="ok", exit_code=0)
        result = evaluate_signals(signals, _criteria(runbook_id))
        assert result.decision == "inconclusive", result

    def test_kwargs_force_degradation_on_functional_looking_payload(self) -> None:
        payload = {"status": "completed", "status_code": 200, "contains_sensitive_data": False}
        signals = normalize_execution_output("http", payload, runner_status="error", exit_code=1)
        assert signals["target_reachable"] is False
        assert signals["prerequisites_missing"] is True
        result = evaluate_signals(signals, _criteria("API-DATA-SECRET-RESPONSE-006"))
        assert result.decision == "inconclusive", result

    def test_success_path_still_decides_secure(self) -> None:
        bridge_result = build_bridge_result(
            json.dumps({"status": "completed", "status_code": 200, "contains_sensitive_data": False}),
            "",
            0,
        )
        signals = normalize_execution_output("http", bridge_result)
        assert signals["target_reachable"] is True
        assert signals["prerequisites_missing"] is False
        result = evaluate_signals(signals, _criteria("API-DATA-SECRET-RESPONSE-006"))
        assert result.decision == "secure", result

    def test_runner_metadata_never_becomes_a_signal(self) -> None:
        bridge_result = build_bridge_result("", "err", 1)
        signals = normalize_execution_output("nuclei", bridge_result)
        assert "meta" not in signals
        for key in ("runner_exit_code", "runner_status", "runner_stdout", "runner_stderr"):
            assert key not in signals
