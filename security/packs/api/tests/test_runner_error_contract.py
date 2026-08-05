"""Regression tests for the runner error contract and fail-safe normalization (#63).

Root cause covered: a missing allowlisted tool (e.g. nuclei) produced an empty or
unstructured runner result, which the normalizer turned into
``target_reachable=True`` / ``prerequisites_missing=False``. Runbooks whose
``secure_when`` matches on absent evidence then reported a false ``secure``.
"""
from __future__ import annotations

import base64
import importlib.util
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest
import yaml

from evaluation import evaluate_signals, normalize_execution_output

PACK_ROOT = Path(__file__).resolve().parents[1]
RUNNER_PATH = PACK_ROOT / "runner" / "kali_runner.py"


def _load_runner():
    spec = importlib.util.spec_from_file_location("kali_runner_under_test", RUNNER_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


runner = _load_runner()


def _criteria(runbook_id: str) -> dict[str, list[str]]:
    for path in (PACK_ROOT / "runbooks").rglob("*.yaml"):
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        if isinstance(data, dict) and (data.get("metadata") or {}).get("id") == runbook_id:
            return dict(data.get("evaluation") or {})
    raise AssertionError(f"runbook not found: {runbook_id}")


class TestRunnerToolUnavailable:
    def test_missing_tool_returns_structured_error(self) -> None:
        result = runner.run_argv(["definitely-not-installed-tool-x"], 5, "nuclei")
        assert result["status"] == "error"
        assert result["error_code"] == "handler.tool_unavailable"
        assert result["handler"] == "nuclei"
        assert result["tool"] == "definitely-not-installed-tool-x"
        assert result["exit_code"] == 127
        assert result["target_reachable"] is False
        assert result["prerequisites_missing"] is True

    def test_missing_tool_does_not_leak_paths_or_traceback(self) -> None:
        result = runner.run_argv(["/opt/secret-dir/nuclei"], 5, "nuclei")
        serialized = json.dumps(result)
        assert "Traceback" not in serialized
        assert "/opt/secret-dir" not in serialized
        assert result["tool"] == "nuclei"

    def test_not_implemented_handler_is_structured_not_fatal(self) -> None:
        result = runner.external_action(
            {
                "handler": "graphqlx",
                "profile": "whatever",
                "arguments": {},
                "limits": {"timeout_seconds": 5},
            }
        )
        assert result["status"] == "not-implemented"
        assert result["prerequisites_missing"] is True
        assert result["target_reachable"] is False

    def test_cli_prints_valid_json_and_exits_deterministically(self, monkeypatch) -> None:
        payload = {
            "handler": "nuclei",
            "profile": "debug-mode",
            "arguments": {"url": "http://target.local/api"},
            "limits": {"timeout_seconds": 5, "max_response_bytes": 1024},
        }
        encoded = base64.urlsafe_b64encode(json.dumps(payload).encode()).decode()
        completed = subprocess.run(
            [sys.executable, str(RUNNER_PATH), "execute", "--payload-b64", encoded],
            text=True,
            capture_output=True,
            timeout=60,
            env={"HEX0R_ALLOWED_HOSTS": "target.local", "PATH": "/nonexistent-path-for-test"},
            check=False,
        )
        assert completed.returncode == 0, completed.stderr
        assert "Traceback" not in completed.stderr
        parsed = json.loads(completed.stdout)
        assert parsed["status"] == "error"
        assert parsed["error_code"] == "handler.tool_unavailable"
        assert parsed["exit_code"] == 127


class TestFailSafeNormalization:
    @pytest.mark.parametrize(
        "output",
        [
            None,
            {},
            {"status": "error", "error_code": "handler.tool_unavailable"},
            {"status": "not-implemented"},
        ],
    )
    def test_degraded_output_never_yields_positive_signals(self, output: Any) -> None:
        signals = normalize_execution_output("nuclei", output)
        assert signals["target_reachable"] is False
        assert signals["prerequisites_missing"] is True

    def test_claimed_reachable_is_overridden_on_error(self) -> None:
        signals = normalize_execution_output(
            "nuclei",
            {"status": "error", "target_reachable": True, "prerequisites_missing": False},
        )
        assert signals["target_reachable"] is False
        assert signals["prerequisites_missing"] is True

    def test_successful_output_is_unchanged(self) -> None:
        signals = normalize_execution_output(
            "http",
            {"status": "completed", "status_code": 200, "response_headers": {}},
        )
        assert signals["target_reachable"] is True
        assert signals["prerequisites_missing"] is False
        assert signals["response_status"] == 200

    def test_runner_metadata_is_not_leaked_as_signal(self) -> None:
        signals = normalize_execution_output(
            "nuclei",
            {
                "status": "error",
                "runner_exit_code": 127,
                "runner_status": "error",
                "runner_stdout": "raw",
            },
        )
        assert "runner_exit_code" not in signals
        assert "runner_status" not in signals
        assert "runner_stdout" not in signals


class TestNoFalseSecureOnHandlerFailure:
    AFFECTED = (
        "API-CONFIG-DEBUG-MODE-008",
        "API-DATA-DIRECTORY-LIST-008",
        "API-DATA-SECRET-RESPONSE-006",
    )

    @pytest.mark.parametrize("runbook_id", AFFECTED)
    @pytest.mark.parametrize(
        "output",
        [
            {},
            {"status": "error", "error_code": "handler.tool_unavailable", "exit_code": 127},
            {"status": "not-implemented"},
        ],
    )
    def test_handler_failure_is_inconclusive_never_secure(
        self, runbook_id: str, output: dict[str, Any]
    ) -> None:
        signals = normalize_execution_output("nuclei", output)
        result = evaluate_signals(signals, _criteria(runbook_id))
        assert result.decision == "inconclusive", result
        assert result.decision != "secure"

    def test_successful_secure_path_still_decides_secure(self) -> None:
        signals = normalize_execution_output(
            "http",
            {
                "status": "completed",
                "status_code": 200,
                "contains_sensitive_data": False,
            },
        )
        result = evaluate_signals(signals, _criteria("API-DATA-SECRET-RESPONSE-006"))
        assert result.decision == "secure", result
