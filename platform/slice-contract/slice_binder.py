"""Read-only PTaaS vertical-slice traversal binder (ADR-0017 Option C).

Resolves and verifies already-accepted seams S1-S11 for one LAB_L1 campaign and
emits a deterministic, sanitized traversal record. Holds no authority: no effect,
no authorization issuance, no custody write, no campaign-state mutation. Never
imports runner_handoff/admission/router/webgoat_l1_adapter or runner_protocol_v2.

Task 4 implements S1 (scope) + S2 (target authorization) only, calling the
existing real ``authorize_operation`` interface fail-closed. Later seams (S3+)
are intentionally NOT evaluated here; the traversal defaults to ABORTED until
those verifications exist.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Mapping

REPO_ROOT = Path(__file__).resolve().parents[2]

SEAM_OWNERS = {
    "S1": "platform/roe-contract/roe_contract.py",
    "S2": "platform/targets/execution_authorization.py",
    "S3": "platform/scenario-registry/scenario_plan.py",
    "S4": "platform/assurance/current-assurance-profile.yaml",
    "S5": "platform/runner-authorization/verified_authorization_resolver.py",
    "S6": "platform/gateway-protocol/admission.py",
    "S7": "platform/runner-adapters/webgoat_l1_adapter.py",
    "S8": "platform/evidence-plane/evidence_plane.py",
    "S9": "platform/risk-findings/risk_findings.py",
    "S10": "platform/lab-lifecycle/lifecycle_protocol.py",
    "S11": "platform/roe-contract/campaign_kill_switch_transition.py",
}


def resolve_seam_owners() -> dict[str, str]:
    return {seam: str(REPO_ROOT / rel) for seam, rel in SEAM_OWNERS.items()}


def _load_component(rel_path: str, module_name: str):
    import importlib.util

    spec = importlib.util.spec_from_file_location(module_name, REPO_ROOT / rel_path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = mod
    spec.loader.exec_module(mod)
    return mod


def _verify_s1(contract: Mapping[str, Any]) -> dict[str, Any]:
    assurance_profile = contract.get("assurance_profile")
    operation = (contract.get("operations") or [{}])[0]
    intrusiveness_level = operation.get("intrusiveness_level")
    verified = (assurance_profile == "LAB_L1") and (intrusiveness_level in ("L0", "L1"))
    return {
        "seam": "S1",
        "owner": SEAM_OWNERS["S1"],
        "precondition_verified": bool(verified),
        "intrusiveness_ceiling": intrusiveness_level if verified else None,
    }


def _verify_s2(contract: Mapping[str, Any]) -> dict[str, Any]:
    exe = _load_component(SEAM_OWNERS["S2"], "hsl_exec_auth")
    target_id = contract["targets"][0]["target_id"]
    operation_id = contract["operations"][0]["operation_id"]
    decision = exe.authorize_operation(target_id, operation_id)
    return {
        "seam": "S2",
        "owner": SEAM_OWNERS["S2"],
        "precondition_verified": bool(decision.allowed),
        "allowed": bool(decision.allowed),
        "reason_code": decision.reason_code,
        "target_id": decision.target_id,
        "operation_id": decision.operation_id,
    }


def bind(contract: Mapping[str, Any], *, clock: str | None = None) -> dict[str, Any]:
    # Fail-closed default: the frozen repository state refuses the traversal.
    # Task 4 only verifies S1 (scope) and S2 (target authorization). Later
    # seams are not evaluated here, so the terminal state stays ABORTED.
    terminal_state = "ABORTED"
    seams: dict[str, Any] = {}

    s1 = _verify_s1(contract)
    seams["S1"] = s1
    if not s1["precondition_verified"]:
        return {
            "campaign_id": contract.get("campaign_id"),
            "seams": seams,
            "terminal_state": terminal_state,
        }

    s2 = _verify_s2(contract)
    seams["S2"] = s2
    # Precedence: an unverified authorization seam aborts the traversal.
    if not s2["precondition_verified"]:
        terminal_state = "ABORTED"

    return {
        "campaign_id": contract.get("campaign_id"),
        "seams": seams,
        "terminal_state": terminal_state,
    }
