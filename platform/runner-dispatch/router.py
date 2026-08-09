#!/usr/bin/env python3
"""Fail-closed Runner adapter router candidate.

This module routes only after transport authentication, Runner Protocol
validation, explicit routing policy and adapter runtime-readiness gates.
It creates no authorization and performs no dynamic adapter imports.
"""

from __future__ import annotations

import argparse
import importlib.util
import sys
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol

import yaml
from runner_protocol_v2 import ProtocolValidationError, validate_semantics

ROOT = Path(__file__).resolve().parents[2]
ROUTING_POLICY_PATH = Path(__file__).resolve().parent / "routing-policy.yaml"
TRANSPORT_MODULE_PATH = ROOT / "platform" / "runner-transport" / "unix_peer_identity.py"


def _load_transport_module():
    name = "runner_dispatch_unix_peer_identity"
    existing = sys.modules.get(name)
    if existing is not None:
        return existing
    spec = importlib.util.spec_from_file_location(name, TRANSPORT_MODULE_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError("cannot load Unix peer transport identity module")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


transport_identity = _load_transport_module()


class DispatchRouterError(ValueError):
    """Stable fail-closed router error."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


class RunnerAdapter(Protocol):
    def dispatch(self, request: dict[str, Any]) -> dict[str, Any]:
        ...


@dataclass(frozen=True)
class DispatchResult:
    principal_id: str
    adapter_id: str
    transport: str
    messages: tuple[dict[str, Any], ...] = field(repr=False)

    def as_safe_dict(self) -> dict[str, Any]:
        return {
            "principal_id": self.principal_id,
            "adapter_id": self.adapter_id,
            "transport": self.transport,
            "message_count": len(self.messages),
            "terminal_status": self.messages[-1].get("status") if self.messages else None,
        }


def load_yaml(path: Path | str) -> dict[str, Any]:
    document_path = Path(path)
    try:
        document = yaml.safe_load(document_path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise DispatchRouterError("CONFIG_UNREADABLE", str(exc)) from exc
    except yaml.YAMLError as exc:
        raise DispatchRouterError("CONFIG_INVALID", str(exc)) from exc
    if not isinstance(document, dict):
        raise DispatchRouterError("CONFIG_INVALID", "configuration must be a mapping")
    return document


def validate_routing_policy(document: Any) -> list[str]:
    if not isinstance(document, Mapping):
        return ["routing policy must be an object"]
    findings: list[str] = []
    if document.get("schema_version") != "1.0":
        findings.append("schema_version must be '1.0'")
    if document.get("policy_id") != "hexor.runner.dispatch.routing":
        findings.append("policy_id must be hexor.runner.dispatch.routing")
    if document.get("state") not in {"DISABLED", "ENABLED"}:
        findings.append("state must be DISABLED or ENABLED")
    if document.get("default") != "deny":
        findings.append("default must be deny")
    if document.get("runtime_status") != "NOT_RUN":
        findings.append("runtime_status must remain NOT_RUN before live acceptance")
    if document.get("execution_authority") != "none":
        findings.append("routing policy must never claim execution authority")

    bindings = document.get("bindings")
    if not isinstance(bindings, list):
        return findings + ["bindings must be an array"]
    if document.get("state") == "DISABLED" and bindings:
        findings.append("disabled routing policy must not retain bindings")
    if document.get("state") == "ENABLED" and not bindings:
        findings.append("enabled routing policy requires at least one exact binding")

    seen: set[tuple[str, str, str, str]] = set()
    for position, binding in enumerate(bindings):
        label = f"bindings[{position}]"
        if not isinstance(binding, Mapping):
            findings.append(f"{label}: binding must be an object")
            continue
        if set(binding) != {"principal_id", "adapter_id", "target_id", "capabilities"}:
            findings.append(
                f"{label}: exact fields principal_id, adapter_id, target_id, capabilities are required"
            )
            continue
        principal = binding.get("principal_id")
        adapter_id = binding.get("adapter_id")
        target_id = binding.get("target_id")
        capabilities = binding.get("capabilities")
        for name, value in (
            ("principal_id", principal),
            ("adapter_id", adapter_id),
            ("target_id", target_id),
        ):
            if not isinstance(value, str) or not value or "*" in value:
                findings.append(f"{label}: {name} must be an exact non-wildcard string")
        if not isinstance(capabilities, list) or not capabilities:
            findings.append(f"{label}: capabilities must be a non-empty array")
            continue
        if len(capabilities) != len(set(capabilities)):
            findings.append(f"{label}: capabilities contains duplicates")
        for capability in capabilities:
            if not isinstance(capability, str) or not capability or "*" in capability:
                findings.append(f"{label}: capabilities must contain exact strings")
                continue
            if all(isinstance(item, str) for item in (principal, adapter_id, target_id)):
                key = (principal, adapter_id, target_id, capability)
                if key in seen:
                    findings.append(f"{label}: duplicate routing binding")
                seen.add(key)
    return findings


def load_routing_policy(path: Path | str = ROUTING_POLICY_PATH) -> dict[str, Any]:
    document = load_yaml(path)
    findings = validate_routing_policy(document)
    if findings:
        raise DispatchRouterError("ROUTING_POLICY_INVALID", "; ".join(findings))
    return document


def _extract_route(request: Mapping[str, Any]) -> tuple[str, str]:
    try:
        capability = request["operation"]["capability_id"]
        operation_input = request["operation"]["input"]
        target = operation_input["target"]
        target_type = target["type"]
        target_id = target["value"]
    except (KeyError, TypeError):
        raise DispatchRouterError(
            "ROUTE_INPUT_INVALID",
            "request lacks canonical operation target routing fields",
        ) from None
    if not isinstance(capability, str) or not capability:
        raise DispatchRouterError("ROUTE_INPUT_INVALID", "capability_id is invalid")
    if target_type != "lab-asset" or not isinstance(target_id, str) or not target_id:
        raise DispatchRouterError(
            "ROUTE_INPUT_INVALID",
            "routing requires canonical lab-asset target_id",
        )
    return target_id, capability


def _resolve_adapter(
    adapter_registry: Mapping[str, Any],
    *,
    target_id: str,
    capability: str,
) -> tuple[str, Mapping[str, Any]]:
    raw = adapter_registry.get("adapters")
    if not isinstance(raw, list):
        raise DispatchRouterError("ADAPTER_REGISTRY_INVALID", "adapters must be an array")
    matches: list[Mapping[str, Any]] = []
    for adapter in raw:
        if not isinstance(adapter, Mapping):
            continue
        targets = adapter.get("target_ids")
        capabilities = adapter.get("capabilities")
        if not isinstance(targets, list) or not isinstance(capabilities, list):
            continue
        if target_id in targets and capability in capabilities:
            matches.append(adapter)
    if not matches:
        raise DispatchRouterError("ROUTE_NOT_FOUND", "no adapter matches target and capability")
    if len(matches) != 1:
        raise DispatchRouterError("ROUTE_AMBIGUOUS", "multiple adapters match target and capability")
    adapter = matches[0]
    adapter_id = adapter.get("adapter_id")
    if not isinstance(adapter_id, str) or not adapter_id:
        raise DispatchRouterError("ADAPTER_REGISTRY_INVALID", "matched adapter_id is invalid")
    if adapter.get("status") != "AS_BUILT" or adapter.get("runtime_status") != "READY":
        raise DispatchRouterError(
            "ADAPTER_NOT_RUNTIME_READY",
            "matched adapter has not passed explicit runtime promotion",
        )
    return adapter_id, adapter


def _binding_allows(
    routing_policy: Mapping[str, Any],
    *,
    principal_id: str,
    adapter_id: str,
    target_id: str,
    capability: str,
) -> bool:
    bindings = routing_policy.get("bindings")
    if not isinstance(bindings, list):
        return False
    for binding in bindings:
        if not isinstance(binding, Mapping):
            continue
        if binding.get("principal_id") != principal_id:
            continue
        if binding.get("adapter_id") != adapter_id:
            continue
        if binding.get("target_id") != target_id:
            continue
        capabilities = binding.get("capabilities")
        if isinstance(capabilities, list) and capability in capabilities:
            return True
    return False


def _logical_correlation_matches(
    actual: Any,
    expected: Mapping[str, Any],
) -> bool:
    """Match the logical step identity while preserving original attempt custody.

    Runner idempotency deliberately excludes ``attempt_id``. A replay may therefore
    return the terminal outcome from the attempt that originally performed the effect.
    Campaign/run/step must remain identical; both attempt identifiers must still be
    non-empty strings validated by Runner Protocol.
    """

    if not isinstance(actual, Mapping):
        return False
    for field in ("campaign_id", "run_id", "step_id"):
        if actual.get(field) != expected.get(field):
            return False
    return isinstance(actual.get("attempt_id"), str) and bool(actual.get("attempt_id"))


def _validate_adapter_result(
    result: Any,
    *,
    correlation: Mapping[str, Any],
) -> tuple[dict[str, Any], ...]:
    if not isinstance(result, Mapping):
        raise DispatchRouterError("ADAPTER_RESULT_INVALID", "adapter result must be an object")
    messages = result.get("messages")
    if not isinstance(messages, list) or not messages:
        raise DispatchRouterError("ADAPTER_RESULT_INVALID", "adapter result requires messages")
    validated: list[dict[str, Any]] = []
    for message in messages:
        if not isinstance(message, dict):
            raise DispatchRouterError("ADAPTER_RESULT_INVALID", "adapter message must be an object")
        try:
            validate_semantics(message)
        except ProtocolValidationError as exc:
            raise DispatchRouterError("ADAPTER_RESULT_INVALID", str(exc)) from exc
        if not _logical_correlation_matches(message.get("correlation"), correlation):
            raise DispatchRouterError(
                "ADAPTER_CORRELATION_MISMATCH",
                "adapter message logical correlation differs from request",
            )
        validated.append(message)
    if validated[-1].get("message_type") != "runner.outcome":
        raise DispatchRouterError(
            "ADAPTER_RESULT_INVALID",
            "adapter message sequence must terminate in runner.outcome",
        )
    if sum(item.get("message_type") == "runner.outcome" for item in validated) != 1:
        raise DispatchRouterError(
            "ADAPTER_RESULT_INVALID",
            "adapter result must contain exactly one terminal outcome",
        )
    return tuple(validated)


def dispatch_from_unix_peer(
    *,
    peer_socket: Any,
    request: dict[str, Any],
    transport_policy: Mapping[str, Any],
    routing_policy: Mapping[str, Any],
    adapter_registry: Mapping[str, Any],
    adapters: Mapping[str, RunnerAdapter],
) -> DispatchResult:
    """Authenticate channel, route exact target/capability and invoke one adapter."""

    try:
        peer = transport_identity.authenticate_unix_peer(peer_socket, transport_policy)
    except transport_identity.TransportIdentityError as exc:
        code = exc.code if exc.code.startswith("TRANSPORT_") else f"TRANSPORT_{exc.code}"
        raise DispatchRouterError(code, str(exc)) from exc

    findings = validate_routing_policy(routing_policy)
    if findings:
        raise DispatchRouterError("ROUTING_POLICY_INVALID", "; ".join(findings))
    if routing_policy.get("state") != "ENABLED":
        raise DispatchRouterError("ROUTING_DISABLED", "routing policy is disabled")

    try:
        validate_semantics(request)
    except ProtocolValidationError as exc:
        raise DispatchRouterError("RUNNER_REQUEST_INVALID", str(exc)) from exc
    if request.get("message_type") != "runner.step.request":
        raise DispatchRouterError(
            "RUNNER_REQUEST_INVALID",
            "router accepts runner.step.request only",
        )

    target_id, capability = _extract_route(request)
    adapter_id, _ = _resolve_adapter(
        adapter_registry,
        target_id=target_id,
        capability=capability,
    )
    if not _binding_allows(
        routing_policy,
        principal_id=peer.principal_id,
        adapter_id=adapter_id,
        target_id=target_id,
        capability=capability,
    ):
        raise DispatchRouterError(
            "ROUTING_BINDING_DENIED",
            "authenticated principal lacks an exact routing binding",
        )

    adapter = adapters.get(adapter_id)
    if adapter is None:
        raise DispatchRouterError(
            "ADAPTER_NOT_COMPOSED",
            "selected adapter is absent from the trusted composition root",
        )
    try:
        raw_result = adapter.dispatch(request)
    except Exception as exc:
        raise DispatchRouterError(
            "ADAPTER_DISPATCH_FAILED",
            f"adapter dispatch failed safely: {type(exc).__name__}",
        ) from exc
    messages = _validate_adapter_result(raw_result, correlation=request["correlation"])
    return DispatchResult(
        principal_id=peer.principal_id,
        adapter_id=adapter_id,
        transport=peer.transport,
        messages=messages,
    )


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--policy", default=str(ROUTING_POLICY_PATH))
    parser.add_argument("command", choices=("validate",))
    args = parser.parse_args(list(argv) if argv is not None else None)
    try:
        load_routing_policy(args.policy)
    except DispatchRouterError as exc:
        print(f"FAIL {exc.code}: {exc}", file=sys.stderr)
        return 1
    print("OK runner dispatch routing policy is fail-closed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
