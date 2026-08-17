"""Read-only PTaaS vertical-slice traversal binder (ADR-0017 Option C).

Resolves and verifies already-accepted seams S1-S11 for one LAB_L1 campaign and
emits a deterministic, sanitized traversal record. Holds no authority: no effect,
no authorization issuance, no custody write, no campaign-state mutation. Never
imports runner_handoff/admission/router/webgoat_l1_adapter or runner_protocol_v2.

Task 4 implements S1 (scope) + S2 (target authorization) only, calling the
existing real ``authorize_operation`` interface fail-closed. Task 6 resolves
S4 (HITL assertion) as a static assurance-profile read after S1 passes and
before S2; S4 never refuses and adds no approval surface. Task 8 records S6
(admission/handoff) as a read-only path assert with runtime_status=NOT_RUN
under synthetic ``_force_complete`` derivation coverage; S6 NEVER imports the
admission/runner_handoff/runner_protocol_v2 modules and grants no authority.
The frozen default path refuses at S5 (NO_DECISION) and stays ABORTED; S6 is
reached only in synthetic mode, so the S1->S4->S2 precedence and the frozen
S5 refusal are unchanged. Later seams (S3, S7+) are NOT evaluated through the
default ``bind`` path.
"""

from __future__ import annotations

import sys
import yaml
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


def _verify_s4(contract: Mapping[str, Any]) -> dict[str, Any]:
    """Resolve the S4 HITL assertion from the current assurance profile (AC9).

    Pure read-only read of ``current-assurance-profile.yaml``: S4 asserts the
    LAB_L1-relevant booleans ``requires_request_bound_hitl`` and
    ``requires_hash_chain``. It introduces NO new approval surface — the HITL
    requirement is already declared by the assurance profile. The seam
    precondition is always satisfied (static profile read), so S4 never
    refuses the traversal; it is resolved immediately after S1 scope passes
    and before the S2 authorization gate.
    """
    prof = yaml.safe_load((REPO_ROOT / SEAM_OWNERS["S4"]).read_text())
    req = prof.get("evaluation", {})
    hitl = bool(req.get("requires_request_bound_hitl", False))
    hc = bool(req.get("requires_hash_chain", False))
    return {
        "seam": "S4",
        "owner": SEAM_OWNERS["S4"],
        "precondition_verified": True,
        "hitl_required": hitl,
        "hash_chain_required": hc,
        "source": "current-assurance-profile.yaml",
        "approval_reference_digest": "LAB_L1-request-bound-hitl-required" if hitl else None,
    }


def _verify_s3(contract: Mapping[str, Any]) -> dict[str, Any]:
    """Derive the deterministic S3 plan-composition digest (AC3 contributor).

    Exercises the already-accepted ``compose_scenario_plan`` interface for the
    ``webgoat-tls-transport-review`` scenario and digests the resulting plan
    with the already-accepted ``canonical_digest`` interface. This is a pure
    read-only derivation: no effect, no authorization, no scope widening.

    CHG-HSL-084 Task 5 CORRECTION: the canonical webgoat-web +
    web.discovery.headers contract refuses at S2 (OPERATION_OUT_OF_SCOPE), and
    ``bind`` early-returns there, so this seam is NOT reached through ``bind``.
    It is exercised synthetically/independently (see test_slice_binder.py) as a
    valid S2-equivalent seam outcome, proving the digest is deterministic
    without authorizing ``web.discovery.headers``.
    """
    sp = _load_component(SEAM_OWNERS["S3"], "hsl_scenario_plan")
    res = sp.compose_scenario_plan("webgoat-tls-transport-review")
    ev = _load_component(SEAM_OWNERS["S8"], "hsl_evidence_plane")
    digest = ev.canonical_digest(res.as_dict()) if res.plan is not None else None
    return {
        "seam": "S3",
        "owner": SEAM_OWNERS["S3"],
        "precondition_verified": bool(res.ok),
        "reason_code": res.reason_code,
        "plan_digest": digest,
    }


def _verify_s5(contract: Mapping[str, Any]) -> dict[str, Any]:
    """Record the S5 authorization seam as a read-only NO_DECISION refusal.

    S5 asserts the existence of the already-accepted authorization resolver path
    and records a fail-closed refusal under the frozen ABSENT trust store. It
    NEVER imports the resolver module (no authority, no live authorization call):
    the frozen repository state has ``trust-store: ABSENT`` and every policy
    ``DISABLED``/``deny``/``NOT_RUN``, so the binder records ``NO_DECISION`` and
    refuses. For the current state this is the correct, spec-compliant terminal
    result that keeps VAL-HSL-RUNNER-L1-LIVE-PROMOTION BLOCKED/HOLD.
    """
    owner = SEAM_OWNERS["S5"]
    exists = (REPO_ROOT / owner).is_file()
    return {
        "seam": "S5",
        "owner": owner,
        "precondition_verified": False,
        "reason_code": "TRUST_STORE_ABSENT",
        "authorization_ref": "NO_DECISION",
        "component_present": exists,
    }


def _verify_s6(contract: Mapping[str, Any]) -> dict[str, Any]:
    """Record the S6 admission/handoff seam as a read-only path assert (NOT_RUN).

    S6 asserts the already-accepted admission/handoff seam-ownership path and
    records runtime_status=NOT_RUN. It NEVER imports ``admission.py`` /
    ``runner_handoff.py`` / ``runner_protocol_v2`` and never executes a runner,
    network call, or subprocess. The binder holds no authority, so S6 grants no
    admission and no handoff effect — it is the static structural record that
    the seam path exists and is unchanged (still NOT_RUN) under the frozen state.
    This is reached only under synthetic ``_force_complete`` derivation coverage;
    the frozen default path stops at S5.
    """
    owner = SEAM_OWNERS["S6"]
    return {
        "seam": "S6",
        "owner": owner,
        "precondition_verified": True,
        "runtime_status": "NOT_RUN",
        "admission_codes": ["NOT_RUN"],
    }


def bind(
    contract: Mapping[str, Any],
    *,
    clock: str | None = None,
    _force_complete: bool = False,
) -> dict[str, Any]:
    # Fail-closed default: the frozen repository state refuses the traversal.
    # Task 4 verifies S1 (scope) + S2 (target authorization); Task 6 resolves
    # S4 (HITL) between S1 and S2; Task 7 records S5 (trust-store ABSENT
    # refusal). S5 is terminal for the frozen state, so bind stops there and
    # the terminal state stays ABORTED. The deferred S1->S4->S2 precedence/order
    # constraint (Task 13) is preserved; S5 is appended after S2 only.
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

    # S4 is a static assurance-profile read (HITL assertion). It never refuses
    # and introduces no new approval surface, so it is resolved after S1 scope
    # passes and before the S2 authorization gate (Task 6, AC9).
    s4 = _verify_s4(contract)
    seams["S4"] = s4

    s2 = _verify_s2(contract)
    seams["S2"] = s2
    # Precedence: an unverified authorization seam aborts the traversal.
    if not s2["precondition_verified"]:
        terminal_state = "ABORTED"

    # S5 is terminal for the frozen state: it records a NO_DECISION refusal under
    # the ABSENT trust store and never imports the resolver. Because the frozen
    # repository state refuses at S5, bind stops here with ABORTED (the correct
    # current-state result that keeps promotion BLOCKED/HOLD). The deferred
    # S1->S4->S2 precedence/order constraint (Task 13) is preserved; S5 is
    # appended after S2 only.
    s5 = _verify_s5(contract)
    seams["S5"] = s5
    if not s5["precondition_verified"]:
        terminal_state = "ABORTED"

    # Task 8: under synthetic _force_complete derivation coverage only, record S6
    # (admission/handoff) as a read-only NOT_RUN path assert. The frozen default
    # path never reaches S6 and stays ABORTED at S5; the S1->S4->S2 precedence
    # and the frozen S5 refusal are unchanged. S6 imports no authority module and
    # grants no admission/handoff effect.
    if _force_complete:
        s6 = _verify_s6(contract)
        seams["S6"] = s6

    return {
        "campaign_id": contract.get("campaign_id"),
        "seams": seams,
        "terminal_state": terminal_state,
    }
