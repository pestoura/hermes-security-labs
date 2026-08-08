from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CANDIDATE = ROOT / "platform/gateway-protocol/controlled_runtime_candidate.py"
CANONICAL = ROOT / "platform/registry.yaml"
REGISTRY = ROOT / "platform/gateway-protocol/operation-registry.yaml"


def _send(process: subprocess.Popen[str], value: dict) -> dict:
    assert process.stdin and process.stdout
    process.stdin.write(json.dumps(value) + "\n")
    process.stdin.flush()
    return json.loads(process.stdout.readline())


def test_live_gateway_allows_typed_health_then_refuses_runtime_drift(tmp_path: Path) -> None:
    deployed = tmp_path / "registry.yaml"
    deployed.write_bytes(CANONICAL.read_bytes())
    process = subprocess.Popen(
        [
            sys.executable,
            str(CANDIDATE),
            "--canonical-runtime", str(CANONICAL),
            "--deployed-runtime", str(deployed),
            "--operation-registry", str(REGISTRY),
        ],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        clean = _send(process, {"profile": "normal", "operation_id": "system.health.read", "parameters": {}})
        assert clean["status"] == "PASS"
        assert clean["effect_executed"] is True
        assert clean["effect"] == {"health": "ok"}
        assert clean["execution_authority"] == "CONTROLLED_CI_ONLY"

        deployed.write_bytes(deployed.read_bytes() + b"\n# runtime-drift\n")
        drift = _send(process, {"profile": "normal", "operation_id": "system.health.read", "parameters": {}})
        assert drift["status"] == "REFUSED"
        assert drift["effect_executed"] is False
        assert "RUNTIME_DRIFT_DETECTED" in drift["codes"]
        assert drift["execution_authority"] == "NONE"
    finally:
        if process.stdin:
            process.stdin.close()
        process.wait(timeout=5)
        assert process.returncode == 0
        assert process.stderr and process.stderr.read() == ""


def test_normal_profile_refuses_generic_or_undeclared_operation(tmp_path: Path) -> None:
    deployed = tmp_path / "registry.yaml"
    deployed.write_bytes(CANONICAL.read_bytes())
    process = subprocess.Popen(
        [sys.executable, str(CANDIDATE), "--canonical-runtime", str(CANONICAL), "--deployed-runtime", str(deployed), "--operation-registry", str(REGISTRY)],
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
    )
    try:
        response = _send(process, {"profile": "normal", "operation_id": "execute.command", "parameters": {}})
        assert response["status"] == "REFUSED"
        assert response["effect_executed"] is False
        assert response["execution_authority"] == "NONE"
    finally:
        if process.stdin:
            process.stdin.close()
        process.wait(timeout=5)
