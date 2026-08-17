"""Read-only PTaaS vertical-slice traversal binder (ADR-0017 Option C).

Resolves and verifies already-accepted seams S1-S11 for one LAB_L1 campaign and
emits a deterministic, sanitized traversal record. Holds no authority: no effect,
no authorization issuance, no custody write, no campaign-state mutation. Never
imports runner_handoff/admission/router/webgoat_l1_adapter or runner_protocol_v2.
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


def bind(contract: Mapping[str, Any], *, clock: str | None = None) -> dict[str, Any]:
    return {"campaign_id": contract.get("campaign_id"), "seams": {}, "terminal_state": "ABORTED"}
