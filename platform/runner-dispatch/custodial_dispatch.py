#!/usr/bin/env python3
"""Custodial composition for authenticated Runner dispatch.

Adapters remain responsible for target-bound effect + durable idempotency. This
composition layer is responsible for authenticated routing and evidence custody.
Known-disabled custody blocks before the adapter. If custody becomes unavailable
only after the effect, an exact retry may invoke the adapter again solely to
obtain its durable replay; the target effect must not repeat.
"""

from __future__ import annotations

import importlib.util
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping

ROOT = Path(__file__).resolve().parents[2]
ROUTER_PATH = Path(__file__).resolve().parent / "router.py"
CUSTODY_PATH = ROOT / "platform" / "evidence-plane" / "runner_outcome_custody.py"


def _load_module(name: str, path: Path):
    existing = sys.modules.get(name)
    if existing is not None:
        return existing
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load composition dependency {path.name}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


router = _load_module("runner_custodial_router", ROUTER_PATH)
custody_contract = _load_module("runner_custodial_evidence", CUSTODY_PATH)


class CustodialDispatchError(ValueError):
    """Stable fail-closed composition error."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class CustodialDispatchResult:
    principal_id: str
    adapter_id: str
    transport: str
    custody: Mapping[str, Any]
    messages: tuple[dict[str, Any], ...] = field(repr=False)

    def as_safe_dict(self) -> dict[str, Any]:
        terminal = self.messages[-1] if self.messages else {}
        return {
            "principal_id": self.principal_id,
            "adapter_id": self.adapter_id,
            "transport": self.transport,
            "terminal_status": terminal.get("status"),
            "message_count": len(self.messages),
            "custody": dict(self.custody),
        }


def _preflight_custody(evidence_custody: Any, evidence_store: Any) -> None:
    if evidence_custody is None or not hasattr(evidence_custody, "persist"):
        raise CustodialDispatchError(
            "EVIDENCE_CUSTODY_UNAVAILABLE",
            "Runner outcome custody component is required before dispatch",
        )
    if getattr(evidence_custody, "enabled", False) is not True:
        raise CustodialDispatchError(
            "EVIDENCE_CUSTODY_DISABLED",
            "Runner outcome custody must be explicitly enabled before dispatch",
        )
    if evidence_store is None or not hasattr(evidence_store, "put"):
        raise CustodialDispatchError(
            "EVIDENCE_STORE_UNAVAILABLE",
            "Evidence Plane store is required before dispatch",
        )


def _terminal_outcome(messages: tuple[dict[str, Any], ...]) -> dict[str, Any]:
    if not messages:
        raise CustodialDispatchError(
            "RUNNER_OUTCOME_MISSING",
            "authenticated dispatch returned no Runner messages",
        )
    terminal = messages[-1]
    if terminal.get("message_type") != "runner.outcome":
        raise CustodialDispatchError(
            "RUNNER_OUTCOME_MISSING",
            "authenticated dispatch did not terminate in runner.outcome",
        )
    return terminal


def dispatch_with_custody_from_unix_peer(
    *,
    peer_socket: Any,
    request: dict[str, Any],
    transport_policy: Mapping[str, Any],
    routing_policy: Mapping[str, Any],
    adapter_registry: Mapping[str, Any],
    adapters: Mapping[str, Any],
    evidence_custody: Any,
    evidence_store: Any,
    results_root: str | Path,
) -> CustodialDispatchResult:
    """Dispatch one authenticated request and require successful evidence custody."""

    _preflight_custody(evidence_custody, evidence_store)

    try:
        dispatch = router.dispatch_from_unix_peer(
            peer_socket=peer_socket,
            request=request,
            transport_policy=transport_policy,
            routing_policy=routing_policy,
            adapter_registry=adapter_registry,
            adapters=adapters,
        )
    except router.DispatchRouterError as exc:
        raise CustodialDispatchError(exc.code, str(exc)) from exc

    terminal = _terminal_outcome(dispatch.messages)
    try:
        custody_result = evidence_custody.persist(
            request=request,
            outcome=terminal,
            adapter_id=dispatch.adapter_id,
            principal_id=dispatch.principal_id,
            results_root=results_root,
            evidence_store=evidence_store,
        )
    except custody_contract.RunnerOutcomeCustodyError as exc:
        raise CustodialDispatchError(
            "EVIDENCE_CUSTODY_FAILED",
            f"Runner effect completed but custodial persistence failed: {exc.code}",
        ) from exc
    except Exception as exc:
        raise CustodialDispatchError(
            "EVIDENCE_CUSTODY_FAILED",
            f"Runner effect completed but custodial persistence failed safely: {type(exc).__name__}",
        ) from exc

    if not hasattr(custody_result, "as_safe_dict"):
        raise CustodialDispatchError(
            "EVIDENCE_CUSTODY_INVALID",
            "custody component returned no safe custody result",
        )
    safe_custody = custody_result.as_safe_dict()
    if not isinstance(safe_custody, Mapping):
        raise CustodialDispatchError(
            "EVIDENCE_CUSTODY_INVALID",
            "custody safe result must be a mapping",
        )

    return CustodialDispatchResult(
        principal_id=dispatch.principal_id,
        adapter_id=dispatch.adapter_id,
        transport=dispatch.transport,
        custody=dict(safe_custody),
        messages=dispatch.messages,
    )
