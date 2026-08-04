"""Runner JSON contract tests: CLI boundary, validation and sanitisation."""

from __future__ import annotations

import base64
import json
import subprocess
import sys
from pathlib import Path

import pytest

PACK_ROOT = Path(__file__).resolve().parents[1]
RUNNER = PACK_ROOT / "runner" / "devsecops_runner.py"

sys.path.insert(0, str(PACK_ROOT / "runner"))

import devsecops_runner  # noqa: E402

VALID = {
    "schema_version": 1,
    "provider": "secrets",
    "action": "scan",
    "profile": "wrongsecrets-exposure",
    "target_ref": "wrongsecrets",
    "scope": "laboratory",
    "control_id": "DEVSEC-SECRETS-002",
    "arguments": {"base_url": "http://127.0.0.1:1"},
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


def run_cli(payload, *extra, env=None):
    completed = subprocess.run(
        [sys.executable, str(RUNNER), "execute", "--payload-b64", encode(payload), *extra],
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
        env=env,
    )
    return completed


def test_runner_file_is_standard_library_only():
    text = RUNNER.read_text(encoding="utf-8")
    assert "import yaml" not in text
    assert "import requests" not in text
    assert "shell=True" not in text


def test_dry_run_is_the_default_mode():
    document = devsecops_runner.execute(VALID)
    assert document["status"] == "dry-run"
    assert document["decision"] == "not-applicable"
    assert REQUIRED_KEYS.issubset(document)


def test_forced_execution_produces_a_functional_decision():
    document = devsecops_runner.execute(VALID, force=True)
    assert document["status"] in {"ok", "error"}
    assert document["decision"] in {"vulnerable", "secure", "inconclusive"}
    assert document["status"] != "not-implemented"


def test_unknown_handler_is_refused_by_policy():
    payload = dict(VALID, provider="shell", action="exec")
    document = devsecops_runner.execute(payload, force=True)
    assert document["status"] == "error"
    assert "policy violation" in document["reason"]


def test_declared_but_uncalibrated_handler_is_explicit():
    payload = dict(VALID, provider="iac", action="scan")
    document = devsecops_runner.execute(payload, force=True)
    assert document["status"] == "not-implemented"
    assert "handler.not_calibrated" in document["inconclusive_signals"]


@pytest.mark.parametrize(
    "payload",
    [
        dict(VALID, target_ref="evil.example.com"),
        dict(VALID, scope="production"),
    ],
)
def test_invalid_target_or_scope_is_rejected(payload):
    document = devsecops_runner.execute(payload, force=True)
    assert document["status"] == "error"
    assert document["decision"] == "inconclusive"


def test_malformed_payload_returns_structured_error():
    document = devsecops_runner.execute({"provider": "secrets"}, force=True)
    assert document["status"] == "error"
    assert "invalid request" in document["reason"]


def test_cli_emits_single_line_stable_json():
    completed = run_cli(VALID)
    assert completed.returncode == 0
    assert len(completed.stdout.strip().splitlines()) == 1
    document = json.loads(completed.stdout)
    assert REQUIRED_KEYS.issubset(document)
    assert json.dumps(document, sort_keys=True) == json.dumps(
        json.loads(completed.stdout), sort_keys=True
    )


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


def test_cli_handlers_subcommand_lists_catalogue():
    completed = subprocess.run(
        [sys.executable, str(RUNNER), "handlers"],
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    assert completed.returncode == 0
    handlers = json.loads(completed.stdout)["handlers"]
    calibrated = [item for item in handlers if item["implemented"]]
    assert {"provider": "secrets", "action": "scan", "implemented": True} in handlers
    assert len(calibrated) >= 1


def test_result_never_contains_raw_secret_material():
    payload = dict(
        VALID,
        arguments={"base_url": "http://127.0.0.1:1", "password": "SuperSecret123"},
    )
    document = devsecops_runner.execute(payload, force=True)
    assert "SuperSecret123" not in json.dumps(document)
