from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PATH = ROOT / "platform/lab-registry-v2/controlled_reset_ci.py"
spec = importlib.util.spec_from_file_location("controlled_lab_reset_ci", PATH)
assert spec and spec.loader
module = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = module
spec.loader.exec_module(module)


def test_controlled_reset_removes_runtime_drift_and_converges_identically() -> None:
    result = module.run_controlled_reset_evidence()
    assert result["boundary"] == "CONTROLLED_CI_FILESYSTEM"
    assert result["deterministic"] is True
    assert result["execution_count"] == 2
    assert result["codes"] == ["RESET_STATE_IDENTICAL"]
    assert result["production_lab_runtime"] == "NOT_RUN"
