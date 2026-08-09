#!/usr/bin/env python3
"""Deterministic fail-closed dry-run Scenario Plan Composer (Lane K).

The composer only resolves committed contracts and produces a JSON-serializable
plan. It never executes subprocesses, Docker, network requests, tools, scans, or
runtime mutations.

Composition path:
scenario -> environment -> target authorization -> semantic operations
-> tool/operation registry -> backend -> BackendPlan -> lifecycle/readiness
-> evidence expectations -> reset/cleanup proof expectations
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence

import yaml

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]

SCENARIO_REGISTRY = HERE / "scenario-registry.yaml"
TOOL_REGISTRY = HERE / "tool-registry.yaml"
OPERATION_REGISTRY = ROOT / "platform" / "gateway-protocol" / "operation-registry.yaml"
TARGET_REGISTRY_MODULE = ROOT / "platform" / "targets" / "target_registry.py"
BACKEND_MODULE = ROOT / "platform" / "scripts" / "lab_backends.py"

REASON_CODES = (
    "PLAN_READY",
    "UNKNOWN_SCENARIO",
    "MALFORMED_SCENARIO",
    "UNKNOWN_ENVIRONMENT",
    "UNKNOWN_TARGET",
    "UNAUTHORIZED_TARGET",
    "UNAUTHORIZED_SEMANTIC_OPERATION",
    "MISSING_TOOL_REFERENCE",
    "MISSING_OPERATION_REFERENCE",
    "UNSUPPORTED_BACKEND",
    "INVALID_BACKEND_ACTION",
    "MISSING_LIFECYCLE_CONTRACT",
    "MISSING_READINESS_CONTRACT",
    "MISSING_EVIDENCE_CONTRACT",
    "MISSING_RESET_PROOF",
    "AMBIGUOUS_REGISTRY_RESOLUTION",
    "REGISTRY_INVALID",
)

EXIT_OK = 0
EXIT_FAIL_CLOSED = 2


class PlanFailure(RuntimeError):
    """Internal deterministic fail-closed signal."""

    def __init__(self, reason_code: str, detail: str) -> None:
        if reason_code not in REASON_CODES:
            raise ValueError(f"unknown Scenario Plan reason code: {reason_code}")
        super().__init__(detail)
        self.reason_code = reason_code
        self.detail = detail


@dataclass(frozen=True)
class ScenarioPlanResult:
    scenario_id: str
    ok: bool
    reason_code: str
    plan: Mapping[str, Any] | None = None
    detail: str | None = None

    def __post_init__(self) -> None:
        if self.reason_code not in REASON_CODES:
            raise ValueError(f"unknown Scenario Plan reason code: {self.reason_code}")

    def as_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "scenario_id": self.scenario_id,
            "ok": self.ok,
            "reason_code": self.reason_code,
        }
        if self.plan is not None:
            payload["plan"] = dict(self.plan)
        if self.detail:
            payload["detail"] = self.detail
        return payload


def _load_module(name: str, path: Path) -> Any:
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise PlanFailure("REGISTRY_INVALID", f"cannot load module: {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    try:
        spec.loader.exec_module(module)
    except Exception as exc:  # noqa: BLE001 - normalize imported contract errors
        raise PlanFailure("REGISTRY_INVALID", f"cannot load {path.name}: {exc}") from exc
    return module


def _load_yaml(path: Path) -> dict[str, Any]:
    try:
        value = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        raise PlanFailure("REGISTRY_INVALID", f"cannot load {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise PlanFailure("REGISTRY_INVALID", f"{path} must contain a mapping")
    return value


def _mapping(value: Any, code: str, detail: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise PlanFailure(code, detail)
    return value


def _non_empty_list(value: Any, code: str, detail: str) -> list[Any]:
    if not isinstance(value, list) or not value:
        raise PlanFailure(code, detail)
    return value


def _unique_entry(
    entries: Any,
    *,
    key: str,
    value: str,
    missing_code: str,
    label: str,
) -> Mapping[str, Any]:
    if not isinstance(entries, list):
        raise PlanFailure("REGISTRY_INVALID", f"{label} registry entries must be an array")
    matches = [item for item in entries if isinstance(item, Mapping) and item.get(key) == value]
    if not matches:
        raise PlanFailure(missing_code, f"{label} {value!r} is not registered")
    if len(matches) != 1:
        raise PlanFailure(
            "AMBIGUOUS_REGISTRY_RESOLUTION",
            f"{label} {value!r} resolves to {len(matches)} entries",
        )
    return matches[0]


def _manifest_index(backend_module: Any) -> dict[str, Mapping[str, Any]]:
    try:
        discovered = backend_module.executable_manifests()
    except Exception as exc:  # noqa: BLE001
        raise PlanFailure("REGISTRY_INVALID", f"cannot enumerate executable manifests: {exc}") from exc
    out: dict[str, Mapping[str, Any]] = {}
    for env_id, value in discovered.items():
        if env_id in out:
            raise PlanFailure(
                "AMBIGUOUS_REGISTRY_RESOLUTION",
                f"environment {env_id!r} resolves more than once",
            )
        try:
            _path, manifest = value
        except (TypeError, ValueError) as exc:
            raise PlanFailure("REGISTRY_INVALID", f"invalid manifest record for {env_id!r}") from exc
        if isinstance(manifest, Mapping):
            out[str(env_id)] = manifest
    return out


def _select_gateway_profile(
    semantic_operations: Sequence[str],
    operation_doc: Mapping[str, Any],
) -> str:
    profiles = _mapping(
        operation_doc.get("profiles"),
        "REGISTRY_INVALID",
        "operation registry profiles contract is missing",
    )
    wanted = set(semantic_operations)
    preference = ["normal", "controlled"] + sorted(
        str(name) for name in profiles if name not in {"normal", "controlled"}
    )
    for profile_name in preference:
        raw = profiles.get(profile_name)
        if not isinstance(raw, Mapping):
            continue
        operations = raw.get("operations")
        if isinstance(operations, list) and wanted.issubset({str(op) for op in operations}):
            if raw.get("generic_execution") is not False:
                continue
            return profile_name
    raise PlanFailure(
        "UNAUTHORIZED_SEMANTIC_OPERATION",
        "no fail-closed gateway profile admits the complete scenario operation set",
    )


def _validate_scenario_shape(scenario: Mapping[str, Any]) -> tuple[str, str, list[str]]:
    env_id = scenario.get("environment_id")
    if not isinstance(env_id, str) or not env_id.strip():
        raise PlanFailure("MALFORMED_SCENARIO", "scenario.environment_id is required")
    auth = _mapping(
        scenario.get("required_authorization"),
        "MALFORMED_SCENARIO",
        "scenario.required_authorization is required",
    )
    target_id = auth.get("target_id")
    if not isinstance(target_id, str) or not target_id.strip():
        raise PlanFailure("MALFORMED_SCENARIO", "scenario required_authorization.target_id is required")
    raw_ops = _non_empty_list(
        scenario.get("semantic_operations"),
        "MALFORMED_SCENARIO",
        "scenario.semantic_operations must be a non-empty array",
    )
    operations: list[str] = []
    for raw in raw_ops:
        if not isinstance(raw, str) or not raw.strip():
            raise PlanFailure("MALFORMED_SCENARIO", "semantic operation ids must be non-empty strings")
        operations.append(raw.strip())
    if len(set(operations)) != len(operations):
        raise PlanFailure("MALFORMED_SCENARIO", "scenario.semantic_operations contains duplicates")
    return env_id.strip(), target_id.strip(), operations


def _validate_lifecycle(manifest: Mapping[str, Any]) -> list[str]:
    lifecycle = _non_empty_list(
        manifest.get("lifecycle"),
        "MISSING_LIFECYCLE_CONTRACT",
        "environment lifecycle contract is missing",
    )
    actions = [str(action) for action in lifecycle]
    required = {"start", "status", "reset", "destroy"}
    missing = sorted(required - set(actions))
    if missing:
        raise PlanFailure(
            "MISSING_LIFECYCLE_CONTRACT",
            f"environment lifecycle lacks required actions: {missing}",
        )
    return actions


def _validate_readiness(manifest: Mapping[str, Any]) -> dict[str, Any]:
    readiness = _mapping(
        manifest.get("readiness"),
        "MISSING_READINESS_CONTRACT",
        "environment readiness contract is missing",
    )
    probe = readiness.get("probe")
    timeout = readiness.get("timeout_seconds")
    success = readiness.get("success_criteria")
    if not isinstance(probe, str) or not probe.strip():
        raise PlanFailure("MISSING_READINESS_CONTRACT", "readiness.probe is required")
    if isinstance(timeout, bool) or not isinstance(timeout, int) or timeout <= 0:
        raise PlanFailure("MISSING_READINESS_CONTRACT", "readiness.timeout_seconds must be positive")
    if not isinstance(success, str) or not success.strip():
        raise PlanFailure("MISSING_READINESS_CONTRACT", "readiness.success_criteria is required")
    return {
        "probe": probe,
        "timeout_seconds": timeout,
        "success_criteria": success,
    }


def _validate_evidence(
    scenario: Mapping[str, Any],
    manifest: Mapping[str, Any],
) -> dict[str, Any]:
    requirements = _non_empty_list(
        scenario.get("evidence_requirements"),
        "MISSING_EVIDENCE_CONTRACT",
        "scenario evidence requirements are missing",
    )
    persistence = _mapping(
        manifest.get("persistence"),
        "MISSING_EVIDENCE_CONTRACT",
        "environment persistence contract is missing",
    )
    evidence = _mapping(
        persistence.get("evidence"),
        "MISSING_EVIDENCE_CONTRACT",
        "environment persistence.evidence contract is missing",
    )
    path = evidence.get("path")
    retention = evidence.get("retention_days")
    sanitized = evidence.get("sanitized")
    if not isinstance(path, str) or not path.strip():
        raise PlanFailure("MISSING_EVIDENCE_CONTRACT", "evidence.path is required")
    if isinstance(retention, bool) or not isinstance(retention, int) or retention <= 0:
        raise PlanFailure("MISSING_EVIDENCE_CONTRACT", "evidence.retention_days must be positive")
    if sanitized is not True:
        raise PlanFailure("MISSING_EVIDENCE_CONTRACT", "evidence.sanitized must be true")
    return {
        "environment": {
            "path": path,
            "retention_days": retention,
            "sanitized": True,
        },
        "scenario_requirements": [str(item) for item in requirements],
        "structure_state": "FREE_TEXT_REQUIREMENTS",
    }


def _validate_reset_proof(
    scenario: Mapping[str, Any],
    manifest: Mapping[str, Any],
) -> dict[str, Any]:
    strategy = _mapping(
        manifest.get("reset_strategy"),
        "MISSING_RESET_PROOF",
        "environment reset_strategy contract is missing",
    )
    mode = strategy.get("mode")
    destroys_state = strategy.get("destroys_state")
    if not isinstance(mode, str) or not mode.strip():
        raise PlanFailure("MISSING_RESET_PROOF", "reset_strategy.mode is required")
    if destroys_state is not True:
        raise PlanFailure("MISSING_RESET_PROOF", "reset_strategy.destroys_state must be true")
    if not isinstance(manifest.get("reset"), str) or not str(manifest.get("reset")).strip():
        raise PlanFailure("MISSING_RESET_PROOF", "environment reset lifecycle binding is missing")
    if not isinstance(manifest.get("cleanup"), str) or not str(manifest.get("cleanup")).strip():
        raise PlanFailure("MISSING_RESET_PROOF", "environment cleanup lifecycle binding is missing")
    expectations = _non_empty_list(
        scenario.get("cleanup_reset"),
        "MISSING_RESET_PROOF",
        "scenario cleanup/reset expectations are missing",
    )
    return {
        "mode": mode,
        "destroys_state": True,
        "expected_proof": [str(item) for item in expectations],
        "runtime_known_state_proof_required": True,
    }


def compose_scenario_plan(
    scenario_id: str,
    *,
    scenario_doc: Mapping[str, Any] | None = None,
    tool_doc: Mapping[str, Any] | None = None,
    operation_doc: Mapping[str, Any] | None = None,
    target_doc: Mapping[str, Any] | None = None,
    manifests: Mapping[str, Mapping[str, Any]] | None = None,
) -> ScenarioPlanResult:
    """Compose one inert Scenario Plan. Every invalid condition fails closed."""

    requested = str(scenario_id)
    try:
        scenarios = scenario_doc or _load_yaml(SCENARIO_REGISTRY)
        tools = tool_doc or _load_yaml(TOOL_REGISTRY)
        operations = operation_doc or _load_yaml(OPERATION_REGISTRY)
        target_module = _load_module("lane_k_target_registry", TARGET_REGISTRY_MODULE)
        backend_module = _load_module("lane_k_lab_backends", BACKEND_MODULE)

        scenario = _unique_entry(
            scenarios.get("scenarios"),
            key="scenario_id",
            value=requested,
            missing_code="UNKNOWN_SCENARIO",
            label="scenario",
        )
        env_id, target_id, semantic_operations = _validate_scenario_shape(scenario)

        manifest_index = dict(manifests) if manifests is not None else _manifest_index(backend_module)
        manifest = manifest_index.get(env_id)
        if not isinstance(manifest, Mapping):
            raise PlanFailure("UNKNOWN_ENVIRONMENT", f"environment {env_id!r} is not executable/registered")

        if target_doc is None:
            try:
                target_registry = target_module.load_registry()
            except Exception as exc:  # noqa: BLE001
                raise PlanFailure("REGISTRY_INVALID", f"target registry invalid: {exc}") from exc
        else:
            target_registry = target_doc

        target = target_module.resolve_target(target_id, target_registry)
        if target is None:
            raise PlanFailure("UNKNOWN_TARGET", f"target {target_id!r} is not registered")
        if target.get("environment_id") != env_id:
            raise PlanFailure(
                "UNAUTHORIZED_TARGET",
                f"target {target_id!r} is not bound to environment {env_id!r}",
            )
        decision = target_module.resolve_execution_eligibility(target_id, target_registry)
        if not decision.eligible:
            raise PlanFailure("UNAUTHORIZED_TARGET", decision.reason)

        operation_entries = operations.get("operations")
        resolved_operations: list[dict[str, Any]] = []
        resolved_tools: list[dict[str, Any]] = []
        for operation_id in semantic_operations:
            operation = _unique_entry(
                operation_entries,
                key="id",
                value=operation_id,
                missing_code="MISSING_OPERATION_REFERENCE",
                label="operation",
            )
            resolved_operations.append(
                {
                    "id": operation_id,
                    "version": operation.get("version"),
                    "intrusiveness_level": operation.get("intrusiveness_level"),
                    "side_effect": operation.get("side_effect"),
                    "production_status": operation.get("production_status"),
                }
            )

            matching_tools = [
                tool
                for tool in tools.get("tools", [])
                if isinstance(tool, Mapping) and tool.get("mapped_operation") == operation_id
            ] if isinstance(tools.get("tools"), list) else []
            if not matching_tools:
                raise PlanFailure(
                    "MISSING_TOOL_REFERENCE",
                    f"no tool maps semantic operation {operation_id!r}",
                )
            if len(matching_tools) != 1:
                raise PlanFailure(
                    "AMBIGUOUS_REGISTRY_RESOLUTION",
                    f"semantic operation {operation_id!r} maps to {len(matching_tools)} tools",
                )
            tool = matching_tools[0]
            resolved_tools.append(
                {
                    "tool_id": tool.get("tool_id"),
                    "mapped_operation": operation_id,
                    "availability": tool.get("availability"),
                    "risk": tool.get("risk"),
                    "timeout": tool.get("timeout"),
                    "output_format": tool.get("output_format"),
                    "evidence_parser": tool.get("evidence_parser"),
                }
            )

        gateway_profile = _select_gateway_profile(semantic_operations, operations)
        lifecycle = _validate_lifecycle(manifest)
        readiness = _validate_readiness(manifest)
        evidence = _validate_evidence(scenario, manifest)
        reset_proof = _validate_reset_proof(scenario, manifest)

        try:
            backend_registry = backend_module.load_registry()
            binding = backend_module.resolve_backend(manifest, registry=backend_registry)
        except Exception as exc:  # noqa: BLE001
            text = str(exc)
            if "BACKEND_NOT_SUPPORTED" in text or "BACKEND_NOT_READY" in text or "BACKEND_UNKNOWN" in text:
                raise PlanFailure("UNSUPPORTED_BACKEND", text) from exc
            raise PlanFailure("REGISTRY_INVALID", f"backend resolution failed: {text}") from exc

        if not binding.spec.is_supported or not binding.spec.is_ready:
            raise PlanFailure(
                "UNSUPPORTED_BACKEND",
                f"backend {binding.spec.backend_type} is "
                f"{binding.spec.support_state}/{binding.spec.readiness}",
            )
        try:
            backend_plan = binding.adapter.plan(env_id, "status")
        except Exception as exc:  # noqa: BLE001
            text = str(exc)
            if "OPERATION_" in text:
                raise PlanFailure("INVALID_BACKEND_ACTION", text) from exc
            raise PlanFailure("UNSUPPORTED_BACKEND", text) from exc
        if backend_plan.action not in lifecycle:
            raise PlanFailure(
                "INVALID_BACKEND_ACTION",
                f"backend status action {backend_plan.action!r} is absent from lifecycle contract",
            )

        plan = {
            "schema_version": "1.0",
            "mode": "DRY_RUN",
            "scenario": {
                "scenario_id": requested,
                "title": scenario.get("title"),
                "environment_id": env_id,
                "lab_id": scenario.get("lab_id"),
                "objective": scenario.get("objective"),
                "risk_intrusiveness": scenario.get("risk_intrusiveness"),
            },
            "target": {
                "target_id": target_id,
                "authorization": decision.as_dict(),
            },
            "gateway_profile": gateway_profile,
            "semantic_operations": resolved_operations,
            "tools": resolved_tools,
            "backend": binding.as_dict(),
            "backend_plan": backend_plan.as_dict(),
            "lifecycle": lifecycle,
            "readiness": readiness,
            "evidence": evidence,
            "reset_cleanup_proof": reset_proof,
            "execution": {
                "permitted": False,
                "reason": "dry-run composer is inert; execution requires a separate authorized runtime path",
            },
        }
        return ScenarioPlanResult(
            scenario_id=requested,
            ok=True,
            reason_code="PLAN_READY",
            plan=plan,
        )
    except PlanFailure as exc:
        return ScenarioPlanResult(
            scenario_id=requested,
            ok=False,
            reason_code=exc.reason_code,
            detail=exc.detail,
        )


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Compose an inert fail-closed Scenario Plan")
    parser.add_argument("scenario_id")
    args = parser.parse_args(argv)
    result = compose_scenario_plan(args.scenario_id)
    print(json.dumps(result.as_dict(), indent=2, sort_keys=True))
    return EXIT_OK if result.ok else EXIT_FAIL_CLOSED


if __name__ == "__main__":
    raise SystemExit(main())
