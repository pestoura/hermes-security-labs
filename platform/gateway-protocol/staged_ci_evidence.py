"""Controlled-CI evidence for canonical gateway deployment drift enforcement.

This stages the exact repository runtime bytes into a temporary deployment copy,
proves the typed deployment gate passes, then mutates only the disposable copy and
proves drift is refused. It never touches a deployed Hermes/Kali runtime.
"""
from __future__ import annotations

import hashlib
import importlib.util
import tempfile
from pathlib import Path
from typing import Any, Mapping

HERE = Path(__file__).resolve().parent
SPEC = importlib.util.spec_from_file_location("gateway_deployment_gate_ci", HERE / "deployment_gate.py")
assert SPEC and SPEC.loader
GATE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(GATE)


def run_staged_evidence(*, canonical_runtime: bytes, operation_registry: Mapping[str, Any]) -> dict[str, Any]:
    canonical_sha = hashlib.sha256(canonical_runtime).hexdigest()
    with tempfile.TemporaryDirectory(prefix="hex0r-gateway-ci-") as tmp:
        staged = Path(tmp) / "deployed-runtime.yaml"
        staged.write_bytes(canonical_runtime)
        observed_before = hashlib.sha256(staged.read_bytes()).hexdigest()
        before = GATE.evaluate_deployment_gate(
            canonical_runtime=canonical_runtime,
            observed_sha256=observed_before,
            operation_registry=operation_registry,
        )
        staged.write_bytes(staged.read_bytes() + b"\n# controlled-drift\n")
        observed_after = hashlib.sha256(staged.read_bytes()).hexdigest()
        after = GATE.evaluate_deployment_gate(
            canonical_runtime=canonical_runtime,
            observed_sha256=observed_after,
            operation_registry=operation_registry,
        )
    passed = before.allowed is True and after.allowed is False and "RUNTIME_DRIFT_DETECTED" in after.codes
    return {
        "schema_version": "1.0.0",
        "evidence_state": "PASS_CONTROLLED_CI" if passed else "FAIL_CONTROLLED_CI",
        "canonical_sha256": canonical_sha,
        "staged_sha256_before": observed_before,
        "staged_sha256_after": observed_after,
        "clean_stage_allowed": before.allowed,
        "drifted_stage_allowed": after.allowed,
        "drift_codes": list(after.codes),
        "production_runtime": "NOT_RUN",
        "execution_authority": "NONE",
    }
