"""Lane C contract tests: liveness != readiness, fail-closed, no runtime touched.

Pure standard library plus PyYAML/pytest. Every probe is executed through an
injected fake executor, so no container, socket or subprocess is ever used.
Negative controls assert that missing, invalid or offensive adapter contracts
never produce a READY verdict.
"""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "platform" / "scripts"
MODULE_PATH = SCRIPTS / "lab_readiness.py"
ADAPTERS = ROOT / "platform" / "lab-readiness" / "adapters"

REFERENCE_ENVS = ("wrongsecrets", "vampi")


def _load():
    spec = importlib.util.spec_from_file_location("lab_readiness_test", MODULE_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


readiness = _load()


class FakeExecutor:
    """Deterministic executor: check id -> pass/fail. Records the call order."""

    def __init__(self, outcomes: dict[str, bool], default: bool = True) -> None:
        self.outcomes = outcomes
        self.default = default
        self.calls: list[str] = []

    def run(self, env_id, check):
        self.calls.append(check.id)
        passed = self.outcomes.get(check.id, self.default)
        return readiness.CheckResult(check.id, check.kind, passed, "fake ok" if passed else "fake fail")


# --------------------------------------------------------------------------- #
# Adapter contract
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("env_id", REFERENCE_ENVS)
def test_reference_adapters_exist_and_parse(env_id):
    adapter = readiness.load_adapter(env_id, ADAPTERS)
    assert adapter.env_id == env_id
    assert adapter.liveness, "liveness must never be empty"
    assert adapter.readiness, "readiness must never be empty"


@pytest.mark.parametrize("env_id", REFERENCE_ENVS)
def test_reference_adapters_use_only_allowlisted_kinds(env_id):
    adapter = readiness.load_adapter(env_id, ADAPTERS)
    for check in adapter.liveness:
        assert check.kind in readiness.LIVENESS_KINDS
    for check in adapter.readiness:
        assert check.kind in readiness.READINESS_KINDS


@pytest.mark.parametrize("env_id", REFERENCE_ENVS)
def test_reference_adapters_have_no_command_or_shell_field(env_id):
    raw = yaml.safe_load((ADAPTERS / f"{env_id}.yaml").read_text(encoding="utf-8"))
    serialized = json.dumps(raw)
    for forbidden in ("command", "cmd", "shell", "script", "exec", "args"):
        assert f'"{forbidden}"' not in serialized, f"{env_id}: generic execution field '{forbidden}' present"


@pytest.mark.parametrize("env_id", REFERENCE_ENVS)
def test_reference_readiness_probes_are_loopback_only(env_id):
    adapter = readiness.load_adapter(env_id, ADAPTERS)
    for check in adapter.readiness:
        if check.kind == "http_get":
            assert check.params["url"].startswith(("http://127.0.0.1:", "http://localhost:"))
        if check.kind == "tcp_connect":
            assert check.params["host"] in readiness.LOOPBACK_HOSTS


# --------------------------------------------------------------------------- #
# Negative controls on adapter parsing
# --------------------------------------------------------------------------- #


def _write(tmp_path: Path, env_id: str, doc: dict) -> Path:
    path = tmp_path / f"{env_id}.yaml"
    path.write_text(yaml.safe_dump(doc), encoding="utf-8")
    return path


def test_missing_adapter_is_fail_closed(tmp_path):
    with pytest.raises(readiness.ReadinessContractError) as exc:
        readiness.load_adapter("nope", tmp_path)
    assert readiness.REASON_ADAPTER_MISSING in str(exc.value)


def test_adapter_without_readiness_checks_is_rejected(tmp_path):
    _write(tmp_path, "x", {"schema_version": 1, "liveness": [{"id": "l", "kind": "lifecycle_status"}]})
    with pytest.raises(readiness.ReadinessContractError) as exc:
        readiness.load_adapter("x", tmp_path)
    assert readiness.REASON_NO_READINESS_CHECKS in str(exc.value)


def test_adapter_with_unknown_kind_is_rejected(tmp_path):
    _write(tmp_path, "x", {"schema_version": 1, "readiness": [{"id": "r", "kind": "run_shell"}]})
    with pytest.raises(readiness.ReadinessContractError) as exc:
        readiness.load_adapter("x", tmp_path)
    assert readiness.REASON_ADAPTER_INVALID in str(exc.value)


def test_adapter_with_non_loopback_probe_is_rejected(tmp_path):
    _write(
        tmp_path,
        "x",
        {"schema_version": 1, "readiness": [{"id": "r", "kind": "http_get", "url": "http://example.com/"}]},
    )
    with pytest.raises(readiness.ReadinessContractError) as exc:
        readiness.load_adapter("x", tmp_path)
    assert "loopback" in str(exc.value)


def test_adapter_with_https_probe_is_rejected(tmp_path):
    _write(
        tmp_path,
        "x",
        {"schema_version": 1, "readiness": [{"id": "r", "kind": "http_get", "url": "https://127.0.0.1/"}]},
    )
    with pytest.raises(readiness.ReadinessContractError):
        readiness.load_adapter("x", tmp_path)


def test_adapter_with_unbounded_timeout_is_rejected(tmp_path):
    _write(
        tmp_path,
        "x",
        {
            "schema_version": 1,
            "readiness": [
                {"id": "r", "kind": "http_get", "url": "http://127.0.0.1:1/", "timeout_seconds": 10_000}
            ],
        },
    )
    with pytest.raises(readiness.ReadinessContractError):
        readiness.load_adapter("x", tmp_path)


def test_adapter_env_id_mismatch_is_rejected(tmp_path):
    _write(
        tmp_path,
        "x",
        {
            "schema_version": 1,
            "env_id": "other",
            "readiness": [{"id": "r", "kind": "tcp_connect", "port": 5000}],
        },
    )
    with pytest.raises(readiness.ReadinessContractError):
        readiness.load_adapter("x", tmp_path)


def test_unsupported_schema_version_is_rejected(tmp_path):
    _write(tmp_path, "x", {"schema_version": 99, "readiness": [{"id": "r", "kind": "tcp_connect", "port": 1}]})
    with pytest.raises(readiness.ReadinessContractError):
        readiness.load_adapter("x", tmp_path)


def test_unknown_top_level_keys_are_tolerated_for_lane_a(tmp_path):
    _write(
        tmp_path,
        "x",
        {
            "schema_version": 1,
            "lane_a_future_field": {"anything": True},
            "readiness": [{"id": "r", "kind": "tcp_connect", "port": 5000}],
        },
    )
    adapter = readiness.load_adapter("x", tmp_path)
    assert adapter.readiness[0].id == "r"


# --------------------------------------------------------------------------- #
# Evaluation semantics: alive != ready
# --------------------------------------------------------------------------- #


NOW = datetime(2026, 1, 1, tzinfo=timezone.utc)


def test_live_but_probe_failing_is_live_not_ready():
    executor = FakeExecutor({"http-root": False})
    result = readiness.evaluate("vampi", executor=executor, adapter_root=ADAPTERS, now=NOW)
    assert result["lifecycle_state"] == readiness.STATE_LIVE_NOT_READY
    assert result["live"] is True
    assert result["ready"] is False
    assert any(r.startswith(readiness.REASON_READINESS_FAILED) for r in result["failure_reasons"])
    assert readiness.exit_code_for(result) == readiness.EXIT_NOT_READY


def test_all_checks_passing_is_ready():
    executor = FakeExecutor({})
    result = readiness.evaluate("vampi", executor=executor, adapter_root=ADAPTERS, now=NOW)
    assert result["lifecycle_state"] == readiness.STATE_READY
    assert result["ready"] is True
    assert result["failure_reasons"] == []
    assert readiness.exit_code_for(result) == readiness.EXIT_READY


def test_liveness_failure_short_circuits_readiness():
    executor = FakeExecutor({"lifecycle-status": False})
    result = readiness.evaluate("vampi", executor=executor, adapter_root=ADAPTERS, now=NOW)
    assert result["lifecycle_state"] == readiness.STATE_DOWN
    assert result["readiness"]["checks"] == []
    assert readiness.REASON_READINESS_NOT_EVALUATED in result["failure_reasons"]
    # readiness probes must not have been executed at all
    assert executor.calls == ["lifecycle-status"]


def test_missing_adapter_on_executable_lab_is_unknown_and_fail_closed(tmp_path):
    result = readiness.evaluate("vampi", executor=FakeExecutor({}), adapter_root=tmp_path, executable=True, now=NOW)
    assert result["lifecycle_state"] == readiness.STATE_UNKNOWN
    assert result["ready"] is False
    assert result["failure_reasons"]
    assert readiness.exit_code_for(result) == readiness.EXIT_FAIL_CLOSED


def test_missing_adapter_on_non_executable_lab_is_unknown_not_ready(tmp_path):
    result = readiness.evaluate("catalog-only", executor=FakeExecutor({}), adapter_root=tmp_path, executable=False, now=NOW)
    assert result["lifecycle_state"] == readiness.STATE_UNKNOWN
    assert result["ready"] is False


def test_invalid_adapter_never_reports_ready(tmp_path):
    (tmp_path / "vampi.yaml").write_text("readiness: [{id: r, kind: run_shell}]\n", encoding="utf-8")
    result = readiness.evaluate("vampi", executor=FakeExecutor({}), adapter_root=tmp_path, now=NOW)
    assert result["lifecycle_state"] == readiness.STATE_UNKNOWN
    assert result["ready"] is False


def test_result_document_shape_is_stable():
    result = readiness.evaluate("wrongsecrets", executor=FakeExecutor({}), adapter_root=ADAPTERS, now=NOW)
    expected = {
        "schema_version",
        "lab_id",
        "environment_id",
        "lifecycle_state",
        "ready",
        "live",
        "liveness",
        "readiness",
        "failure_reasons",
        "adapter",
        "observed_at",
    }
    assert set(result) == expected
    assert result["lifecycle_state"] in readiness.LIFECYCLE_STATES
    assert result["observed_at"] == "2026-01-01T00:00:00Z"
    json.dumps(result)  # must be serialisable as-is


def test_lab_id_uses_lane_a_tolerant_lookup():
    result = readiness.evaluate(
        "vampi",
        executor=FakeExecutor({}),
        adapter_root=ADAPTERS,
        manifest={"lab_id": "lane-a-vampi", "id": "vampi"},
        now=NOW,
    )
    assert result["lab_id"] == "lane-a-vampi"
    assert result["environment_id"] == "vampi"


def test_lab_id_falls_back_to_env_id_without_manifest():
    result = readiness.evaluate("vampi", executor=FakeExecutor({}), adapter_root=ADAPTERS, now=NOW)
    assert result["lab_id"] == "vampi"


# --------------------------------------------------------------------------- #
# Source-level safety properties
# --------------------------------------------------------------------------- #


def test_module_never_uses_a_shell():
    """Inspect executable code only: docstrings mention the forbidden constructs."""
    import ast

    tree = ast.parse(MODULE_PATH.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            for keyword in node.keywords:
                assert keyword.arg != "shell", "subprocess call uses shell="
            target = node.func
            name = getattr(target, "attr", None) or getattr(target, "id", None)
            assert name not in {"system", "eval", "exec", "popen"}, f"forbidden call: {name}"


def test_executable_manifest_detection():
    assert readiness.is_executable_manifest({"lifecycle": ["start", "status"]}) is True
    assert readiness.is_executable_manifest({"lifecycle": ["status"]}) is False
    assert readiness.is_executable_manifest({}) is False


# --------------------------------------------------------------------------- #
# CLI contract (read-only paths only)
# --------------------------------------------------------------------------- #


def _cli(*args):
    return subprocess.run(
        [sys.executable, str(MODULE_PATH), *args],
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )


@pytest.mark.parametrize("env_id", REFERENCE_ENVS)
def test_cli_contract_only_prints_adapter_and_runs_no_probe(env_id):
    completed = _cli("status", env_id, "--contract-only")
    assert completed.returncode == 0, completed.stderr
    payload = json.loads(completed.stdout)
    assert payload["env_id"] == env_id
    assert payload["readiness"]


def test_cli_unknown_environment_is_fail_closed():
    completed = _cli("status", "does-not-exist-env")
    assert completed.returncode == readiness.EXIT_FAIL_CLOSED
    payload = json.loads(completed.stdout)
    assert payload["lifecycle_state"] == readiness.STATE_UNKNOWN
    assert any(readiness.REASON_ENV_UNKNOWN in reason for reason in payload["failure_reasons"])


def test_cli_coverage_json_lists_reference_environments():
    completed = _cli("coverage", "--json")
    assert completed.returncode == 0, completed.stderr
    payload = json.loads(completed.stdout)
    present = {row["env_id"] for row in payload["environments"] if row["adapter"] == "PRESENT"}
    assert set(REFERENCE_ENVS).issubset(present)
    assert payload["executable_gaps"] >= 0
