#!/usr/bin/env python3
"""Cheap aggregate JDS gate for the Hermes Security Labs walking skeleton.

This gate is intentionally static and inert. It composes the existing canonical
contracts before CI spends Docker/runtime resources:

scenario/tool registry -> Evidence Plane contract -> target registry -> backend
matrix -> Scenario Plan Composer.

It never executes a target operation, opens the network, invokes Docker, starts a
subprocess, or mutates runtime state. Runtime source-of-truth validation remains a
separate existing CLI step in the same CI job.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence

import yaml

ROOT = Path(__file__).resolve().parents[2]
PLATFORM = ROOT / "platform"
SCENARIO_DIR = PLATFORM / "scenario-registry"
TARGET_DIR = PLATFORM / "targets"
SCRIPTS_DIR = PLATFORM / "scripts"

SCENARIO_REGISTRY = SCENARIO_DIR / "scenario-registry.yaml"
TOOL_REGISTRY = SCENARIO_DIR / "tool-registry.yaml"
OPERATION_REGISTRY = PLATFORM / "gateway-protocol" / "operation-registry.yaml"

STAGES = (
    "scenario_tool_registry",
    "structured_evidence",
    "target_registry",
    "backend_matrix",
    "scenario_plans",
)

EXIT_OK = 0
EXIT_FAIL_CLOSED = 2


@dataclass(frozen=True)
class GateResult:
    ok: bool
    stages: Mapping[str, str]
    findings: tuple[str, ...]

    def as_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "stages": dict(self.stages),
            "findings": list(self.findings),
        }


def _load_module(name: str, path: Path) -> Any:
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load module: {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def _load_yaml(path: Path) -> dict[str, Any]:
    value = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain a mapping")
    return value


def _stage_findings(prefix: str, values: Sequence[str]) -> list[str]:
    return [f"{prefix}: {value}" for value in values]


def backend_matrix_findings(rows: Sequence[Mapping[str, Any]]) -> list[str]:
    """Fail only on unresolved executable environment bindings.

    A backend may be deliberately modelled as DEFINED/NOT_READY. That is not a
    static-contract failure by itself; a FAIL_CLOSED matrix resolution is.
    """

    findings: list[str] = []
    for row in rows:
        if row.get("resolution") != "RESOLVED":
            findings.append(
                f"environment {row.get('env_id', '<unknown>')!r} backend resolution "
                f"is {row.get('resolution')!r}: {row.get('reason', 'no reason')}"
            )
    return findings


def scenario_plan_findings(
    scenario_doc: Mapping[str, Any],
    composer_module: Any,
) -> list[str]:
    scenarios = scenario_doc.get("scenarios")
    if not isinstance(scenarios, list) or not scenarios:
        return ["scenario registry has no scenarios to compose"]
    findings: list[str] = []
    for scenario in scenarios:
        if not isinstance(scenario, Mapping):
            findings.append("scenario entry is not a mapping")
            continue
        scenario_id = scenario.get("scenario_id")
        if not isinstance(scenario_id, str) or not scenario_id:
            findings.append("scenario entry has no canonical scenario_id")
            continue
        result = composer_module.compose_scenario_plan(scenario_id)
        if not result.ok:
            findings.append(
                f"scenario {scenario_id!r} did not compose: "
                f"{result.reason_code}: {result.detail or 'no detail'}"
            )
    return findings


def collect_gate_findings() -> GateResult:
    """Run the aggregate static gate using only committed repository state."""

    stages = {stage: "NOT_RUN" for stage in STAGES}
    findings: list[str] = []

    try:
        scenario_validator = _load_module(
            "lane_n_validate_registries",
            SCENARIO_DIR / "validate_registries.py",
        )
        evidence_contract = _load_module(
            "lane_n_evidence_contract",
            SCENARIO_DIR / "evidence_contract.py",
        )
        target_module = _load_module(
            "lane_n_target_registry",
            TARGET_DIR / "target_registry.py",
        )
        backend_module = _load_module(
            "lane_n_lab_backends",
            SCRIPTS_DIR / "lab_backends.py",
        )
        composer_module = _load_module(
            "lane_n_scenario_plan",
            SCENARIO_DIR / "scenario_plan.py",
        )
        scenario_doc = _load_yaml(SCENARIO_REGISTRY)
        tool_doc = _load_yaml(TOOL_REGISTRY)
        operation_doc = _load_yaml(OPERATION_REGISTRY)
    except Exception as exc:  # noqa: BLE001 - normalize static load failures
        findings.append(f"bootstrap: {exc}")
        return GateResult(False, stages, tuple(findings))

    try:
        registry_findings = scenario_validator.collect_findings(
            scenario_doc=scenario_doc,
            tool_doc=tool_doc,
            target_module=target_module,
            op_ids=scenario_validator.operation_ids(operation_doc),
        )
    except Exception as exc:  # noqa: BLE001
        registry_findings = [f"validator error: {exc}"]
    findings.extend(_stage_findings("scenario_tool_registry", registry_findings))
    stages["scenario_tool_registry"] = "PASS" if not registry_findings else "FAIL"

    try:
        evidence_findings = evidence_contract.validate_registry_document(scenario_doc)
    except Exception as exc:  # noqa: BLE001
        evidence_findings = [f"validator error: {exc}"]
    findings.extend(_stage_findings("structured_evidence", evidence_findings))
    stages["structured_evidence"] = "PASS" if not evidence_findings else "FAIL"

    try:
        target_registry = target_module.load_registry()
        target_findings = target_module.orphan_targets(target_registry)
    except Exception as exc:  # noqa: BLE001
        target_findings = [f"registry error: {exc}"]
    findings.extend(_stage_findings("target_registry", target_findings))
    stages["target_registry"] = "PASS" if not target_findings else "FAIL"

    try:
        backend_registry = backend_module.load_registry()
        matrix_findings = backend_matrix_findings(backend_module.backend_matrix(backend_registry))
    except Exception as exc:  # noqa: BLE001
        matrix_findings = [f"matrix error: {exc}"]
    findings.extend(_stage_findings("backend_matrix", matrix_findings))
    stages["backend_matrix"] = "PASS" if not matrix_findings else "FAIL"

    try:
        plan_findings = scenario_plan_findings(scenario_doc, composer_module)
    except Exception as exc:  # noqa: BLE001
        plan_findings = [f"composer error: {exc}"]
    findings.extend(_stage_findings("scenario_plans", plan_findings))
    stages["scenario_plans"] = "PASS" if not plan_findings else "FAIL"

    return GateResult(not findings, stages, tuple(findings))


def main(argv: Sequence[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(description="Run the inert aggregate JDS static gate")
    parser.add_argument("--json", action="store_true", help="emit the complete gate result as JSON")
    args = parser.parse_args(argv)

    result = collect_gate_findings()
    if args.json:
        print(json.dumps(result.as_dict(), indent=2, sort_keys=True))
    else:
        for stage in STAGES:
            print(f"{stage}\t{result.stages[stage]}")
        for finding in result.findings:
            print(f"FAIL-CLOSED\t{finding}", file=sys.stderr)
        print("JDS_STATIC_GATE_OK" if result.ok else "JDS_STATIC_GATE_FAIL_CLOSED")
    return EXIT_OK if result.ok else EXIT_FAIL_CLOSED


if __name__ == "__main__":
    raise SystemExit(main())
