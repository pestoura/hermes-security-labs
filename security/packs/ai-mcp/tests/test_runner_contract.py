"""Runner JSON contract tests: CLI boundary, validation, modes, sanitisation."""

from __future__ import annotations

import base64
import json
import subprocess
import sys
from pathlib import Path

import pytest

PACK_ROOT = Path(__file__).resolve().parents[1]
RUNNER = PACK_ROOT / "runner" / "ai_mcp_runner.py"

sys.path.insert(0, str(PACK_ROOT / "runner"))
sys.path.insert(0, str(Path(__file__).resolve().parent / "fixtures"))

import ai_mcp_runner  # noqa: E402
from legacy_runner_stub import legacy_execute  # noqa: E402

#: Allowlisted host/port that is closed on the validation host, so the
#: calibrated path exercises real dispatch without reaching any service.
CLOSED_LOCAL_URL = "http://127.0.0.1:8216"

VALID = {
    "schema_version": 1,
    "provider": "agent",
    "action": "conversation-test",
    "profile": "promptme-direct-injection",
    "target_ref": "promptme",
    "scope": "laboratory",
    "control_id": "AIMCP-DIRECTPROMPTINJECTION-001",
    "arguments": {"base_url": CLOSED_LOCAL_URL},
}

REQUIRED_KEYS = {
    "schema_version",
    "status",
    "decision",
    "provider",
    "action",
    "profile",
    "target_ref",
    "scope",
    "control_id",
    "reason",
    "vulnerable_signals",
    "secure_signals",
    "inconclusive_signals",
    "evidence",
    "meta",
}


def encode(payload) -> str:
    return base64.urlsafe_b64encode(json.dumps(payload).encode()).decode()


def run_cli(payload, *extra):
    return subprocess.run(
        [sys.executable, str(RUNNER), "execute", "--payload-b64", encode(payload), *extra],
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )


def test_runner_file_is_standard_library_only():
    text = RUNNER.read_text(encoding="utf-8")
    assert "import yaml" not in text
    assert "import requests" not in text
    assert "shell=True" not in text


def test_dry_run_is_the_default_mode():
    document = ai_mcp_runner.execute(VALID)
    assert document["status"] == "dry-run"
    assert document["decision"] == "not-applicable"
    assert REQUIRED_KEYS.issubset(document)


def test_forced_execution_produces_a_functional_decision():
    document = ai_mcp_runner.execute(VALID, force=True)
    assert document["status"] in {"ok", "error"}
    assert document["decision"] in {"vulnerable", "secure", "inconclusive"}
    assert document["status"] != "not-implemented"


def test_differential_stub_versus_calibrated_dispatch():
    """The pre-calibration stub returned not-implemented for this exact payload."""

    legacy = legacy_execute(VALID, mode="enabled")
    assert legacy["status"] == "not-implemented"
    assert legacy["reason"] == "real adapter execution pending calibration"

    current = ai_mcp_runner.execute(VALID, force=True)
    assert current["status"] != "not-implemented"
    assert "handler.not_calibrated" not in current["inconclusive_signals"]
    assert current["reason"] != legacy["reason"]


def test_declared_but_uncalibrated_handler_is_still_explicit():
    payload = dict(VALID, provider="mcp", action="security-test")
    legacy = legacy_execute(payload, mode="enabled")
    document = ai_mcp_runner.execute(payload, force=True)
    assert legacy["status"] == "not-implemented"
    assert document["status"] == "not-implemented"
    assert "handler.not_calibrated" in document["inconclusive_signals"]


def test_unknown_handler_is_refused_by_policy():
    payload = dict(VALID, provider="shell", action="exec")
    document = ai_mcp_runner.execute(payload, force=True)
    assert document["status"] == "error"
    assert "policy violation" in document["reason"]


@pytest.mark.parametrize(
    "payload",
    [
        dict(VALID, target_ref="evil.example.com"),
        dict(VALID, scope="production"),
    ],
)
def test_invalid_target_or_scope_is_rejected(payload):
    document = ai_mcp_runner.execute(payload, force=True)
    assert document["status"] == "error"
    assert document["decision"] == "inconclusive"


def test_base_url_outside_the_transport_allowlist_is_refused():
    payload = dict(VALID, arguments={"base_url": "http://attacker.example.com:8080"})
    document = ai_mcp_runner.execute(payload, force=True)
    assert document["status"] == "error"
    assert "base_url" in document["reason"]


def test_malformed_payload_returns_structured_error():
    document = ai_mcp_runner.execute({"provider": "agent"}, force=True)
    assert document["status"] == "error"
    assert "invalid request" in document["reason"]


def test_cli_emits_single_line_stable_json():
    completed = run_cli(VALID)
    assert completed.returncode == 0
    assert len(completed.stdout.strip().splitlines()) == 1
    document = json.loads(completed.stdout)
    assert REQUIRED_KEYS.issubset(document)


def test_cli_output_is_deterministic():
    first = run_cli(VALID)
    second = run_cli(VALID)
    assert first.stdout == second.stdout


def test_cli_rejects_undecodable_payload():
    completed = subprocess.run(
        [sys.executable, str(RUNNER), "execute", "--payload-b64", "!!!not-base64!!!"],
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    assert completed.returncode == 2
    assert json.loads(completed.stdout)["status"] == "error"


def test_cli_handlers_subcommand_lists_capabilities():
    completed = subprocess.run(
        [sys.executable, str(RUNNER), "handlers"],
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    assert completed.returncode == 0
    handlers = json.loads(completed.stdout)["handlers"]
    assert {"provider": "agent", "action": "conversation-test", "implemented": True} in handlers
    assert [item for item in handlers if not item["implemented"]]


def test_result_never_contains_raw_sensitive_material():
    payload = dict(
        VALID,
        arguments={"base_url": CLOSED_LOCAL_URL, "password": "SuperSecret123", "prompt": "leak-me"},
    )
    document = ai_mcp_runner.execute(payload, force=True)
    serialised = json.dumps(document)
    assert "SuperSecret123" not in serialised
    assert "leak-me" not in serialised
