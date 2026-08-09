from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "scripts" / "jds_static_gate.py"


def _load_gate():
    spec = importlib.util.spec_from_file_location("lane_n_jds_static_gate_tests", MODULE_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def gate():
    return _load_gate()


def test_live_repository_static_gate_is_green(gate):
    result = gate.collect_gate_findings()

    assert result.ok is True, result.findings
    assert result.findings == ()
    assert set(result.stages) == set(gate.STAGES)
    assert set(result.stages.values()) == {"PASS"}


def test_backend_matrix_fails_closed_only_on_unresolved_binding(gate):
    rows = [
        {
            "env_id": "docker-ready",
            "resolution": "RESOLVED",
            "support_state": "SUPPORTED",
            "readiness": "READY",
        },
        {
            "env_id": "k8s-defined",
            "resolution": "RESOLVED",
            "support_state": "DEFINED",
            "readiness": "NOT_READY",
        },
    ]
    assert gate.backend_matrix_findings(rows) == []

    rows.append(
        {
            "env_id": "broken",
            "resolution": "FAIL_CLOSED",
            "reason": "BACKEND_UNKNOWN",
        }
    )
    findings = gate.backend_matrix_findings(rows)
    assert len(findings) == 1
    assert "broken" in findings[0]
    assert "FAIL_CLOSED" in findings[0]


def test_scenario_plan_failure_preserves_reason_code(gate):
    scenario_doc = {"scenarios": [{"scenario_id": "example"}]}
    composer = SimpleNamespace(
        compose_scenario_plan=lambda _scenario_id: SimpleNamespace(
            ok=False,
            reason_code="UNAUTHORIZED_TARGET",
            detail="target not authorized",
        )
    )

    findings = gate.scenario_plan_findings(scenario_doc, composer)

    assert findings == [
        "scenario 'example' did not compose: UNAUTHORIZED_TARGET: target not authorized"
    ]


def test_scenario_plan_stage_rejects_missing_registry_entries(gate):
    assert gate.scenario_plan_findings({"scenarios": []}, object()) == [
        "scenario registry has no scenarios to compose"
    ]


def test_static_gate_source_has_no_runtime_or_network_primitives():
    source = MODULE_PATH.read_text(encoding="utf-8")

    for forbidden in (
        "import subprocess",
        "from subprocess",
        "import socket",
        "from socket",
        "import requests",
        "import httpx",
        "docker ",
        "os.system",
        "Popen(",
    ):
        assert forbidden not in source
