#!/usr/bin/env python3
"""Fail-closed cross-registry validation for Runner adapter candidates.

The adapter registry is not an execution authority. This validator proves only
repository consistency across four existing authorities/contracts:

* canonical target registry;
* typed gateway operation registry;
* seeded scenario registry;
* committed adapter registry and implementation paths.

It never imports an adapter implementation, performs network I/O, invokes a
runner or changes runtime state.
"""

from __future__ import annotations

import argparse
import importlib.util
import sys
from collections.abc import Mapping
from pathlib import Path
from typing import Any, Sequence

import yaml

ROOT = Path(__file__).resolve().parents[2]
ADAPTER_REGISTRY = Path(__file__).resolve().parent / "adapter-registry.yaml"
TARGET_REGISTRY = ROOT / "platform" / "targets" / "target-registry.yaml"
TARGET_MODULE = ROOT / "platform" / "targets" / "target_registry.py"
OPERATION_REGISTRY = ROOT / "platform" / "gateway-protocol" / "operation-registry.yaml"
SCENARIO_REGISTRY = ROOT / "platform" / "scenario-registry" / "scenario-registry.yaml"
CANONICAL_HANDOFF = "platform/gateway-protocol/runner_handoff.py"
FORBIDDEN_TOKENS = frozenset({"command", "exec", "shell", "terminal", "generic_execution"})


class AdapterRegistryError(ValueError):
    """Adapter registry or dependency is unreadable or structurally unusable."""


def _load_yaml(path: Path) -> dict[str, Any]:
    try:
        document = yaml.safe_load(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise AdapterRegistryError(f"cannot read {path}: {exc}") from exc
    except yaml.YAMLError as exc:
        raise AdapterRegistryError(f"invalid YAML in {path}: {exc}") from exc
    if not isinstance(document, dict):
        raise AdapterRegistryError(f"{path}: document must be a mapping")
    return document


def _load_target_module():
    spec = importlib.util.spec_from_file_location("runner_adapter_target_registry", TARGET_MODULE)
    if spec is None or spec.loader is None:
        raise AdapterRegistryError("cannot load canonical target registry module")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _walk_forbidden(value: Any, path: str = "root") -> list[str]:
    findings: list[str] = []
    if isinstance(value, Mapping):
        for key, child in value.items():
            normalized = str(key).lower().replace("-", "_")
            tokens = set(normalized.replace(".", "_").split("_"))
            if normalized == "generic_execution" or tokens & FORBIDDEN_TOKENS:
                # `generic_execution: false` is the explicit required safety declaration.
                if not (normalized == "generic_execution" and child is False):
                    findings.append(f"{path}.{key}: forbidden execution surface")
            findings.extend(_walk_forbidden(child, f"{path}.{key}"))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            findings.extend(_walk_forbidden(child, f"{path}[{index}]"))
    return findings


def collect_findings(
    *,
    adapter_doc: dict[str, Any],
    target_doc: dict[str, Any],
    operation_doc: dict[str, Any],
    scenario_doc: dict[str, Any],
    target_module: Any,
    root: Path = ROOT,
) -> list[str]:
    findings: list[str] = []

    if adapter_doc.get("schema_version") != "1.0":
        findings.append("adapter registry schema_version must be '1.0'")

    contract = adapter_doc.get("contract")
    if not isinstance(contract, Mapping):
        findings.append("adapter registry contract must be an object")
    else:
        if contract.get("authorization_authority") != "Hermes":
            findings.append("adapter registry authorization_authority must be Hermes")
        if contract.get("fail_closed") is not True:
            findings.append("adapter registry fail_closed must be true")
        if contract.get("generic_execution") is not False:
            findings.append("adapter registry generic_execution must be false")
        if contract.get("runtime_status") != "NOT_RUN":
            findings.append("adapter registry runtime_status must remain NOT_RUN before live acceptance")

    findings.extend(_walk_forbidden(adapter_doc, "adapter_registry"))

    raw_adapters = adapter_doc.get("adapters")
    if not isinstance(raw_adapters, list) or not raw_adapters:
        return findings + ["adapter registry must contain at least one adapter"]

    try:
        target_index = target_module.index_by_id(target_doc)
    except Exception as exc:
        return findings + [f"canonical target registry is unusable: {type(exc).__name__}"]

    raw_operations = operation_doc.get("operations")
    if not isinstance(raw_operations, list):
        return findings + ["operation registry operations must be an array"]
    operation_index = {
        item.get("id"): item
        for item in raw_operations
        if isinstance(item, Mapping) and isinstance(item.get("id"), str)
    }

    raw_scenarios = scenario_doc.get("scenarios")
    if not isinstance(raw_scenarios, list):
        return findings + ["scenario registry scenarios must be an array"]
    scenarios = [item for item in raw_scenarios if isinstance(item, Mapping)]

    seen_ids: set[str] = set()
    for position, raw in enumerate(raw_adapters):
        label = f"adapters[{position}]"
        if not isinstance(raw, Mapping):
            findings.append(f"{label}: adapter must be an object")
            continue

        adapter_id = raw.get("adapter_id")
        if not isinstance(adapter_id, str) or not adapter_id.strip():
            findings.append(f"{label}: adapter_id is required")
            continue
        label = f"adapter '{adapter_id}'"
        if adapter_id in seen_ids:
            findings.append(f"{label}: duplicate adapter_id")
        seen_ids.add(adapter_id)

        implementation = raw.get("implementation")
        if not isinstance(implementation, str) or not implementation.strip():
            findings.append(f"{label}: implementation path is required")
        else:
            implementation_path = (root / implementation).resolve()
            try:
                implementation_path.relative_to(root.resolve())
            except ValueError:
                findings.append(f"{label}: implementation path escapes repository root")
            else:
                if not implementation_path.is_file():
                    findings.append(f"{label}: implementation path does not exist: {implementation}")
                if implementation_path.suffix != ".py":
                    findings.append(f"{label}: implementation must be a Python module")

        if raw.get("protocol") != "runner-protocol-v2":
            findings.append(f"{label}: protocol must be runner-protocol-v2")
        if raw.get("execution_class") != "LAB_ONLY":
            findings.append(f"{label}: first supported adapters must remain LAB_ONLY")
        if raw.get("status") != "CANDIDATE":
            findings.append(f"{label}: repository adapter status must remain CANDIDATE")
        if raw.get("runtime_status") != "NOT_RUN":
            findings.append(f"{label}: runtime_status must remain NOT_RUN before live acceptance")

        input_contract = raw.get("input_contract")
        if not isinstance(input_contract, Mapping):
            findings.append(f"{label}: input_contract is required")
            continue
        if input_contract.get("source") != CANONICAL_HANDOFF:
            findings.append(f"{label}: input_contract source must be the canonical gateway handoff")
        if input_contract.get("format") != "canonical-gateway-runner-handoff-v2":
            findings.append(f"{label}: unsupported input_contract format")
        if input_contract.get("arbitrary_locator_input") != "forbidden":
            findings.append(f"{label}: arbitrary_locator_input must be forbidden")

        target_ids = raw.get("target_ids")
        if not isinstance(target_ids, list) or not target_ids:
            findings.append(f"{label}: target_ids must be a non-empty array")
            target_ids = []
        if len(target_ids) != len(set(target_ids)):
            findings.append(f"{label}: target_ids contains duplicates")

        target_contract = input_contract.get("target")
        if not isinstance(target_contract, Mapping):
            findings.append(f"{label}: input_contract.target is required")
        else:
            if target_contract.get("type") != "lab-asset":
                findings.append(f"{label}: input target type must be lab-asset")
            target_value = target_contract.get("value")
            if target_value not in target_ids:
                findings.append(f"{label}: input target value must be one of adapter target_ids")

        valid_targets: list[str] = []
        environment_ids: set[str] = set()
        for target_id in target_ids:
            if not isinstance(target_id, str):
                findings.append(f"{label}: target_ids entries must be strings")
                continue
            entry = target_index.get(target_id)
            if entry is None:
                findings.append(f"{label}: target_id '{target_id}' is not canonical")
                continue
            decision = target_module.resolve_execution_eligibility(target_id, target_doc)
            if not decision.eligible:
                findings.append(f"{label}: target_id '{target_id}' is not execution-eligible: {decision.reason}")
                continue
            if entry.get("authorization_state") != raw.get("execution_class"):
                findings.append(f"{label}: target '{target_id}' authorization_state does not match execution_class")
            environment_id = entry.get("environment_id")
            if isinstance(environment_id, str):
                environment_ids.add(environment_id)
            valid_targets.append(target_id)

        capabilities = raw.get("capabilities")
        if not isinstance(capabilities, list) or not capabilities:
            findings.append(f"{label}: capabilities must be a non-empty array")
            capabilities = []
        if len(capabilities) != len(set(capabilities)):
            findings.append(f"{label}: capabilities contains duplicates")

        operation_version = input_contract.get("operation_version")
        intrusiveness = input_contract.get("intrusiveness_level")
        for capability in capabilities:
            if not isinstance(capability, str):
                findings.append(f"{label}: capabilities entries must be strings")
                continue
            lowered_tokens = set(capability.lower().replace("-", ".").split("."))
            if lowered_tokens & FORBIDDEN_TOKENS:
                findings.append(f"{label}: capability '{capability}' looks like generic execution")
                continue
            operation = operation_index.get(capability)
            if operation is None:
                findings.append(f"{label}: capability '{capability}' has no typed operation")
                continue
            if operation.get("version") != operation_version:
                findings.append(f"{label}: capability '{capability}' version differs from input_contract")
            if operation.get("intrusiveness_level") != intrusiveness:
                findings.append(f"{label}: capability '{capability}' intrusiveness differs from input_contract")
            required = operation.get("required_capabilities")
            if not isinstance(required, list) or capability not in required:
                findings.append(f"{label}: typed operation '{capability}' does not attest its own capability")
            if operation.get("production_status") != "NOT_RUN":
                findings.append(f"{label}: typed operation '{capability}' unexpectedly claims runtime production status")

        authorization = raw.get("authorization")
        if not isinstance(authorization, Mapping):
            findings.append(f"{label}: authorization contract is required")
        else:
            if authorization.get("mode") != "tb1_verified_resolver_required":
                findings.append(f"{label}: authorization mode must require verified TB1 resolution")
            if authorization.get("gateway_receipt_verification") != "required-before-handoff":
                findings.append(f"{label}: gateway TB1 receipt verification must be required before handoff")
            if authorization.get("default") != "deny-all":
                findings.append(f"{label}: authorization default must be deny-all")
            if authorization.get("runner_transport_identity") != "NOT_IMPLEMENTED":
                findings.append(f"{label}: transport identity must not be overstated before implementation")

        # Every adapter capability must be represented by a seeded scenario bound
        # to the same canonical target and authorization class. The scenario may
        # include extra health/lifecycle operations that are not adapter effects.
        for target_id in valid_targets:
            covering = []
            for scenario in scenarios:
                required_auth = scenario.get("required_authorization")
                semantic = scenario.get("semantic_operations")
                if not isinstance(required_auth, Mapping) or not isinstance(semantic, list):
                    continue
                if required_auth.get("target_id") != target_id:
                    continue
                if required_auth.get("class") != raw.get("execution_class"):
                    continue
                if not set(capabilities) <= set(semantic):
                    continue
                if environment_ids and scenario.get("environment_id") not in environment_ids:
                    continue
                covering.append(str(scenario.get("scenario_id", "<unnamed>")))
            if not covering:
                findings.append(
                    f"{label}: no seeded scenario covers target '{target_id}' and all adapter capabilities"
                )

    return findings


def validate_paths(
    *,
    adapter_registry: Path = ADAPTER_REGISTRY,
    target_registry: Path = TARGET_REGISTRY,
    operation_registry: Path = OPERATION_REGISTRY,
    scenario_registry: Path = SCENARIO_REGISTRY,
) -> list[str]:
    target_module = _load_target_module()
    return collect_findings(
        adapter_doc=_load_yaml(adapter_registry),
        target_doc=_load_yaml(target_registry),
        operation_doc=_load_yaml(operation_registry),
        scenario_doc=_load_yaml(scenario_registry),
        target_module=target_module,
    )


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--adapter-registry", default=str(ADAPTER_REGISTRY))
    parser.add_argument("--target-registry", default=str(TARGET_REGISTRY))
    parser.add_argument("--operation-registry", default=str(OPERATION_REGISTRY))
    parser.add_argument("--scenario-registry", default=str(SCENARIO_REGISTRY))
    args = parser.parse_args(list(argv) if argv is not None else None)

    try:
        findings = validate_paths(
            adapter_registry=Path(args.adapter_registry),
            target_registry=Path(args.target_registry),
            operation_registry=Path(args.operation_registry),
            scenario_registry=Path(args.scenario_registry),
        )
    except AdapterRegistryError as exc:
        print(f"FAIL {exc}", file=sys.stderr)
        return 1

    if findings:
        for finding in findings:
            print(f"FAIL {finding}", file=sys.stderr)
        return 1
    print("OK runner-adapter-registry cross-registry contract is consistent")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
