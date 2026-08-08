from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
PATH = ROOT / "platform/gateway-protocol/staged_ci_evidence.py"
spec = importlib.util.spec_from_file_location("gateway_staged_ci_evidence", PATH)
assert spec and spec.loader
module = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = module
spec.loader.exec_module(module)


def test_controlled_stage_passes_clean_and_refuses_drift() -> None:
    runtime = (ROOT / "platform/registry.yaml").read_bytes()
    registry = yaml.safe_load((ROOT / "platform/gateway-protocol/operation-registry.yaml").read_text())
    result = module.run_staged_evidence(canonical_runtime=runtime, operation_registry=registry)
    assert result["evidence_state"] == "PASS_CONTROLLED_CI"
    assert result["clean_stage_allowed"] is True
    assert result["drifted_stage_allowed"] is False
    assert "RUNTIME_DRIFT_DETECTED" in result["drift_codes"]
    assert result["production_runtime"] == "NOT_RUN"
    assert result["execution_authority"] == "NONE"
