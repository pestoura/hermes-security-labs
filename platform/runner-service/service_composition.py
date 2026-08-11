"""Fail-closed Runner service composition for one already-accepted AF_UNIX peer.

The module composes existing security boundaries only. It does not create a
listener, daemon, target client, authorization authority or runtime promotion.
Canonical policies remain DISABLED / NOT_RUN.
"""

from __future__ import annotations

import importlib.util
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping

import yaml

ROOT = Path(__file__).resolve().parents[2]
RUNNER_SDK_SRC = ROOT / "platform" / "runner-protocol" / "src"
if str(RUNNER_SDK_SRC) not in sys.path:  # pragma: no cover - import wiring
    sys.path.insert(0, str(RUNNER_SDK_SRC))

HERE = Path(__file__).resolve().parent
POLICY_PATH = HERE / "composition-policy.yaml"
TRANSPORT_PATH = ROOT / "platform" / "runner-transport" / "unix_peer_identity.py"
ROUTER_PATH = ROOT / "platform" / "runner-dispatch" / "router.py"
AUDIT_PATH = ROOT / "platform" / "runner-dispatch" / "audit.py"

PRE_EFFECT_ROUTER_CODES = frozenset(
    {
        "ROUTING_POLICY_INVALID",
        "ROUTING_DISABLED",
        "RUNNER_REQUEST_INVALID",
        "ROUTE_INPUT_INVALID",
        "ROUTE_NOT_FOUND",
        "ROUTE_AMBIGUOUS",
        "ADAPTER_REGISTRY_INVALID",
        "ADAPTER_NOT_RUNTIME_READY",
        "ROUTING_BINDING_DENIED",
        "ADAPTER_NOT_COMPOSED",
    }
)


class RunnerServiceError(ValueError):
    """Stable fail-closed service-composition error."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


def _load_module(name: str, path: Path) -> Any:
    existing = sys.modules.get(name)
    if existing is not None:
        return existing
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:  # pragma: no cover - packaging defect
        raise RuntimeError(f"cannot load canonical module {path.name}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


unix_peer_identity = _load_module(
    "runner_service_unix_peer_identity", TRANSPORT_PATH
)
dispatch_router = _load_module("runner_service_dispatch_router", ROUTER_PATH)
dispatch_audit = _load_module("runner_service_dispatch_audit", AUDIT_PATH)


@dataclass(frozen=True)
class ServiceCompositionResult:
    principal_id: str
    adapter_id: str
    audit_evidence_ids: tuple[str, ...]
    outcome_manifest_evidence_id: str
    outcome_summary_evidence_id: str
    execution_id: str
    message_count: int
    terminal_status: str
    messages: tuple[dict[str, Any], ...] = field(repr=False)

    def as_safe_dict(self) -> dict[str, Any]:
        return {
            "principal_id": self.principal_id,
            "adapter_id": self.adapter_id,
            "audit_evidence_ids": list(self.audit_evidence_ids),
            "outcome_manifest_evidence_id": self.outcome_manifest_evidence_id,
            "outcome_summary_evidence_id": self.outcome_summary_evidence_id,
            "execution_id": self.execution_id,
            "message_count": self.message_count,
            "terminal_status": self.terminal_status,
        }


def validate_policy(document: Any) -> list[str]:
    if not isinstance(document, Mapping):
        return ["Runner service composition policy must be an object"]
    findings: list[str] = []
    if document.get("schema_version") != "1.0":
        findings.append("schema_version must be '1.0'")
    if document.get("policy_id") != "hexor.runner.service.composition":
        findings.append("policy_id must be hexor.runner.service.composition")
    if document.get("state") not in {"DISABLED", "ENABLED"}:
        findings.append("state must be DISABLED or ENABLED")
    if document.get("default") != "deny":
        findings.append("default must be deny")
    if document.get("runtime_status") != "NOT_RUN":
        findings.append("runtime_status must remain NOT_RUN before live acceptance")
    if document.get("execution_authority") != "none":
        findings.append("service composition must never claim execution authority")

    requirements = document.get("requirements")
    if not isinstance(requirements, Mapping):
        return findings + ["requirements must be an object"]
    expected = {
        "peer_authentication": "linux-so-peercred",
        "pre_dispatch_audit_custody": "required",
        "terminal_audit_custody": "required",
        "runner_outcome_custody": "required",
        "shared_evidence_plane_store": "required",
    }
    if dict(requirements) != expected:
        findings.append("requirements must match the exact canonical composition contract")
    return findings


def load_policy(path: Path | str = POLICY_PATH) -> dict[str, Any]:
    policy_path = Path(path)
    try:
        document = yaml.safe_load(policy_path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise RunnerServiceError("POLICY_UNREADABLE", str(exc)) from exc
    except yaml.YAMLError as exc:
        raise RunnerServiceError("POLICY_INVALID", str(exc)) from exc
    findings = validate_policy(document)
    if findings:
        raise RunnerServiceError("POLICY_INVALID", "; ".join(findings))
    return dict(document)


def _terminal_status(outcome: Mapping[str, Any]) -> str:
    status = outcome.get("status")
    if status in {"PASS", "FAIL", "INCONCLUSIVE"}:
        return "SUCCEEDED"
    if status == "REFUSED":
        return "REFUSED"
    if status == "CANCELLED":
        return "CANCELLED"
    if status == "TIMED_OUT":
        return "TIMED_OUT"
    if status == "ERROR":
        return "FAILED"
    raise RunnerServiceError(
        "TERMINAL_STATUS_INVALID", "Runner terminal status is unsupported"
    )


def _router_failure_is_pre_effect(code: str) -> bool:
    return code.startswith("TRANSPORT_") or code in PRE_EFFECT_ROUTER_CODES


def _audit_persist(
    audit_custody: Any,
    event: Mapping[str, Any],
    evidence_store: Any,
) -> str:
    if audit_custody is None or not hasattr(audit_custody, "persist"):
        raise RunnerServiceError(
            "AUDIT_CUSTODY_UNAVAILABLE",
            "dispatch audit custody dependency is required",
        )
    try:
        result = audit_custody.persist(event, evidence_store=evidence_store)
    except Exception as exc:  # noqa: BLE001 - dependency detail remains internal
        code = str(getattr(exc, "code", type(exc).__name__))
        raise RunnerServiceError(
            "AUDIT_CUSTODY_FAILED",
            f"dispatch audit custody failed safely: {code}",
        ) from exc
    evidence_id = getattr(result, "evidence_id", None)
    if not isinstance(evidence_id, str) or not evidence_id:
        raise RunnerServiceError(
            "AUDIT_CUSTODY_FAILED",
            "dispatch audit custody returned no evidence id",
        )
    return evidence_id


def _outcome_persist(
    outcome_custody: Any,
    *,
    request: dict[str, Any],
    outcome: dict[str, Any],
    evidence_store: Any,
    results_root: Path,
    principal_id: str,
    adapter_id: str,
) -> tuple[str, str, str]:
    if outcome_custody is None or not hasattr(outcome_custody, "persist"):
        raise RunnerServiceError(
            "OUTCOME_CUSTODY_UNAVAILABLE",
            "Runner outcome custody dependency is required",
        )
    try:
        result = outcome_custody.persist(
            request=request,
            outcome=outcome,
            adapter_id=adapter_id,
            principal_id=principal_id,
            results_root=results_root,
            evidence_store=evidence_store,
        )
    except Exception as exc:  # noqa: BLE001
        code = str(getattr(exc, "code", type(exc).__name__))
        raise RunnerServiceError(
            "OUTCOME_CUSTODY_FAILED",
            f"Runner outcome custody failed safely: {code}",
        ) from exc

    execution_id = getattr(result, "execution_id", None)
    manifest_id = getattr(result, "manifest_evidence_id", None)
    summary_id = getattr(result, "summary_evidence_id", None)
    if not all(isinstance(value, str) and value for value in (execution_id, manifest_id, summary_id)):
        raise RunnerServiceError(
            "OUTCOME_CUSTODY_FAILED",
            "Runner outcome custody returned incomplete evidence identifiers",
        )
    return execution_id, manifest_id, summary_id


class RunnerServiceComposition:
    """Compose one authenticated request through the existing Runner chain."""

    def __init__(self, policy: Mapping[str, Any]) -> None:
        findings = validate_policy(policy)
        if findings:
            raise RunnerServiceError("POLICY_INVALID", "; ".join(findings))
        self._policy = dict(policy)

    @property
    def enabled(self) -> bool:
        return self._policy.get("state") == "ENABLED"

    def handle_accepted_peer(
        self,
        *,
        peer_socket: Any,
        request: dict[str, Any],
        transport_policy: Mapping[str, Any],
        routing_policy: Mapping[str, Any],
        adapter_registry: Mapping[str, Any],
        adapters: Mapping[str, Any],
        audit_custody: Any,
        outcome_custody: Any,
        evidence_store: Any,
        results_root: Path,
    ) -> ServiceCompositionResult:
        if not self.enabled:
            raise RunnerServiceError(
                "SERVICE_DISABLED",
                "Runner service composition policy is disabled",
            )
        if evidence_store is None:
            raise RunnerServiceError(
                "EVIDENCE_STORE_UNAVAILABLE",
                "one shared Evidence Plane store is required",
            )
        if not isinstance(results_root, Path):
            raise RunnerServiceError(
                "RESULTS_ROOT_INVALID",
                "results_root must be an explicit Path",
            )

        try:
            peer = unix_peer_identity.authenticate_unix_peer(
                peer_socket, transport_policy
            )
        except Exception as exc:  # noqa: BLE001
            code = str(getattr(exc, "code", type(exc).__name__))
            raise RunnerServiceError(
                "PEER_AUTHENTICATION_FAILED",
                f"peer authentication failed safely: {code}",
            ) from exc

        try:
            admitted_event = dispatch_audit.build_dispatch_audit_event(
                principal_id=peer.principal_id,
                transport=peer.transport,
                request=request,
                phase="pre-dispatch",
                decision="ALLOW",
                reason_code="TRANSPORT_PEER_ADMITTED",
            )
        except Exception as exc:  # noqa: BLE001
            code = str(getattr(exc, "code", type(exc).__name__))
            raise RunnerServiceError(
                "AUDIT_EVENT_FAILED",
                f"transport-admission audit event failed safely: {code}",
            ) from exc

        audit_ids: list[str] = [
            _audit_persist(audit_custody, admitted_event, evidence_store)
        ]

        try:
            dispatch = dispatch_router.dispatch_from_unix_peer(
                peer_socket=peer_socket,
                request=request,
                transport_policy=transport_policy,
                routing_policy=routing_policy,
                adapter_registry=adapter_registry,
                adapters=adapters,
            )
        except Exception as exc:  # noqa: BLE001
            code = str(getattr(exc, "code", type(exc).__name__))
            if not _router_failure_is_pre_effect(code):
                raise RunnerServiceError(
                    "ROUTER_POST_DISPATCH_FAILED",
                    f"router failed after adapter invocation could have begun: {code}",
                ) from exc
            try:
                denied_event = dispatch_audit.build_dispatch_audit_event(
                    principal_id=peer.principal_id,
                    transport=peer.transport,
                    request=request,
                    phase="pre-dispatch",
                    decision="DENY",
                    reason_code="ROUTER_PRE_EFFECT_REFUSED",
                )
                audit_ids.append(
                    _audit_persist(audit_custody, denied_event, evidence_store)
                )
            except Exception as audit_exc:  # noqa: BLE001
                audit_code = str(
                    getattr(audit_exc, "code", type(audit_exc).__name__)
                )
                raise RunnerServiceError(
                    "ROUTER_AND_AUDIT_FAILED",
                    f"pre-effect router refusal custody failed safely: {audit_code}",
                ) from exc
            raise RunnerServiceError(
                "ROUTER_PRE_EFFECT_REFUSED",
                f"Runner router refused before adapter invocation: {code}",
            ) from exc

        if dispatch.principal_id != peer.principal_id:
            raise RunnerServiceError(
                "PEER_IDENTITY_MISMATCH",
                "router principal differs from transport-admission principal",
            )
        if dispatch.transport != peer.transport:
            raise RunnerServiceError(
                "PEER_TRANSPORT_MISMATCH",
                "router transport differs from transport-admission evidence",
            )
        if not dispatch.messages:
            raise RunnerServiceError(
                "TERMINAL_OUTCOME_MISSING",
                "router returned no Runner messages",
            )
        outcome = dispatch.messages[-1]
        if outcome.get("message_type") != "runner.outcome":
            raise RunnerServiceError(
                "TERMINAL_OUTCOME_MISSING",
                "router did not return a terminal Runner outcome",
            )

        terminal_status: str | None = None
        terminal_audit_id: str | None = None
        terminal_audit_failure: str | None = None
        try:
            terminal_status = _terminal_status(outcome)
            terminal_event = dispatch_audit.build_dispatch_audit_event(
                principal_id=dispatch.principal_id,
                transport=dispatch.transport,
                request=request,
                phase="terminal",
                decision="OUTCOME",
                reason_code="RUNNER_OUTCOME_RECORDED",
                adapter_id=dispatch.adapter_id,
                terminal_status=terminal_status,
            )
            terminal_audit_id = _audit_persist(
                audit_custody, terminal_event, evidence_store
            )
        except Exception as exc:  # noqa: BLE001
            terminal_audit_failure = str(
                getattr(exc, "code", type(exc).__name__)
            )

        execution_id: str | None = None
        outcome_manifest_id: str | None = None
        outcome_summary_id: str | None = None
        outcome_failure: str | None = None
        try:
            execution_id, outcome_manifest_id, outcome_summary_id = _outcome_persist(
                outcome_custody,
                request=request,
                outcome=outcome,
                evidence_store=evidence_store,
                results_root=results_root,
                principal_id=dispatch.principal_id,
                adapter_id=dispatch.adapter_id,
            )
        except RunnerServiceError as exc:
            outcome_failure = exc.code

        if terminal_audit_failure is not None or outcome_failure is not None:
            failures = [
                value
                for value in (terminal_audit_failure, outcome_failure)
                if value is not None
            ]
            raise RunnerServiceError(
                "POST_EFFECT_CUSTODY_FAILED",
                "post-effect custody failed safely: " + ",".join(failures),
            )

        assert terminal_status is not None
        assert terminal_audit_id is not None
        assert execution_id is not None
        assert outcome_manifest_id is not None
        assert outcome_summary_id is not None
        audit_ids.append(terminal_audit_id)
        return ServiceCompositionResult(
            principal_id=dispatch.principal_id,
            adapter_id=dispatch.adapter_id,
            audit_evidence_ids=tuple(audit_ids),
            outcome_manifest_evidence_id=outcome_manifest_id,
            outcome_summary_evidence_id=outcome_summary_id,
            execution_id=execution_id,
            message_count=len(dispatch.messages),
            terminal_status=terminal_status,
            messages=tuple(dispatch.messages),
        )
