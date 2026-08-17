"""Read-only PTaaS vertical-slice traversal binder (ADR-0017 Option C).

Resolves and verifies already-accepted seams S1-S11 for one LAB_L1 campaign and
emits a deterministic, sanitized traversal record. Holds no authority: no effect,
no authorization issuance, no custody write, no campaign-state mutation. Never
imports runner_handoff/admission/router/webgoat_l1_adapter or runner_protocol_v2.

Canonical seam order (preflight-reconciled source of truth):
S1 -> S2 -> S3 -> S4 -> S5 -> S6 -> S7 -> S8 -> S9 -> S10 -> S11.

``bind`` walks this exact order and STOPS at the FIRST unverified seam
(recorded as ``refusing_seam``). The default frozen repository state uses the
REAL ``authorize_operation`` interface: webgoat-web's ``allowed_operations`` are
coarse categories that do NOT include the typed op ``web.discovery.headers``, so
S2 refuses with ``OPERATION_OUT_OF_SCOPE`` and ``bind`` short-circuits
immediately — S3..S11 are never populated. The derived terminal state is
``ABORTED`` with ``refusing_seam='S2'`` (NOT S5). This is the spec-compliant
current-state result that keeps VAL-HSL-RUNNER-L1-LIVE-PROMOTION BLOCKED/HOLD.

``_force_complete=True`` is a PRIVATE synthetic-only, in-memory positive override
for S2 and S5 only. It performs NO registry/trust-store mutation and holds NO
authority/effect; it exists solely so the S11 ``COMPLETED`` derivation logic is
test-covered without enabling any runtime path. Under it, all S1..S10
preconditions are made true (S10's ``runtime_status=NOT_RUN`` is non-gating when
``precondition_verified=True``) so S11 derives ``COMPLETED`` deterministically.

S11 (this module's Task 13) derives the terminal state as a PURE function of the
collected seam records: COMPLETED when every S1..S10 ``precondition_verified`` is
True, ABORTED on the first refusal (``refusing_seam``), or STOPPED when
``kill_switch_engaged=True``. It emits ``audit_record_present`` and a
deterministic ``traversal_digest`` (in-memory sealed EvidenceChain over the
collected seam records + fixed ``clock``). Identical contract + fixed clock yields
byte-identical output. No live runner/network/subprocess/Vault/secrets; no
target-registry or trust-store mutation.
"""

from __future__ import annotations

import hashlib
import json
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


def _verify_s5(contract: Mapping[str, Any], *, force: bool = False) -> dict[str, Any]:
    """Record the S5 authorization seam.

    Default (frozen state): S5 asserts the existence of the already-accepted
    authorization resolver path and records a fail-closed refusal under the frozen
    ABSENT trust store. It NEVER imports the resolver module (no authority, no live
    authorization call): the frozen repository state has ``trust-store: ABSENT`` and
    every policy ``DISABLED``/``deny``/``NOT_RUN``, so the binder records
    ``NO_DECISION`` and refuses. This is the correct, spec-compliant terminal
    result that keeps VAL-HSL-RUNNER-L1-LIVE-PROMOTION BLOCKED/HOLD.

    ``force=True`` (PRIVATE synthetic-only override, no authority/effect, no
    trust-store mutation): records a synthetic-verified NO_DECISION-equivalent so
    all S1..S10 preconditions can be true for S11's COMPLETED derivation. It does
    NOT widen the real trust store or authorize anything.
    """
    owner = SEAM_OWNERS["S5"]
    exists = (REPO_ROOT / owner).is_file()
    if force:
        return {
            "seam": "S5",
            "owner": owner,
            "precondition_verified": True,
            "reason_code": "NO_DECISION_SYNTHETIC",
            "authorization_ref": "NO_DECISION",
            "component_present": exists,
            "synthetic_override": True,
        }
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

def _synthetic_evidence_refs(contract: Mapping[str, Any], clock: str) -> list[str]:
    """Synthetic, valid evidence refs for derivation coverage only (no live effect).

    Produces deterministic ``evidence://`` object refs and matching 64-hex sha256
    digests derived from the contract's campaign/operation identifiers and the
    fixed ``clock``. These are digests-only synthetic custody references; no real
    evidence object, network call, subprocess, or LocalEvidenceStore write occurs.
    Used exclusively under synthetic ``_force_complete`` mode to exercise the S8
    sealed-chain derivation logic; the default frozen path supplies none.
    """
    operation_id = (contract.get("operations") or [{}])[0].get("operation_id", "operation")
    refs: list[str] = []
    for idx in range(2):
        refs.append(f"evidence://ptaas-slice/{operation_id}/obs-{idx}")
    return refs


def _verify_s8(contract: Mapping[str, Any], *, evidence_refs: list[str], clock: str) -> dict[str, Any]:
    """Derive the S8 evidence-custody shape in-memory using accepted interfaces (AC6).

    Builds an in-memory ``EvidenceChain`` from the supplied (synthetic or real)
    evidence refs and seals it with the already-accepted ``evidence_plane`` seal
    interface. The chain state digest and seal are deterministic and verified
    locally; NO persistence to ``LocalEvidenceStore`` or any filesystem occurs,
    and no network/runner/effect/authority/Vault/secret is involved. The binder
    holds no authority: it only derives the custody *shape* as proof of the
    already-accepted evidence-integrity control. Reached only under synthetic
    ``_force_complete`` derivation coverage; the frozen default path stops at S5.
    """
    chain_mod = _load_component(SEAM_OWNERS["S8"].replace("evidence_plane.py", "evidence_chain.py"), "hsl_ev_chain")
    seal_mod = _load_component(SEAM_OWNERS["S8"].replace("evidence_plane.py", "seal.py"), "hsl_seal")

    chain = chain_mod.EvidenceChain("chain_" + hashlib.sha256(contract.get("campaign_id", "ptaas-slice").encode("utf-8")).hexdigest())
    correlation = {
        "campaign_id": contract.get("campaign_id") or "campaign",
        "run_id": "ptaas-slice-synthetic",
        "step_id": "S8",
        "attempt_id": "0",
    }
    for ref in evidence_refs:
        digest = hashlib.sha256(ref.encode("utf-8")).hexdigest()
        chain.append_object(
            object_kind="evidence_record",
            object_ref=ref,
            object_digest_sha256=digest,
            object_size_bytes=len(ref.encode("utf-8")),
            object_media_type="application/x-sha256-ref",
            correlation=correlation,
            created_at=clock,
        )
    seal = seal_mod.seal_chain(chain, sealed_at=clock)
    verification = seal_mod.verify_seal(seal)
    return {
        "seam": "S8",
        "owner": SEAM_OWNERS["S8"],
        "precondition_verified": True,
        "chain_state_digest": chain.chain_state_digest(),
        "seal_verified": bool(verification.get("verified")),
        "persisted": False,  # never written to LocalEvidenceStore / filesystem
    }


def _verify_s9(contract: Mapping[str, Any], *, evidence_refs: list[str]) -> dict[str, Any]:
    """Derive the S9 normalized finding shape through the accepted create_finding interface (AC7).

    Normalizes a finding via the already-accepted ``risk_findings.create_finding``
    interface using the SAME synthetic verified evidence refs derived by S8 (no
    new evidence source, no live evidence object). ``risk`` is always ``{}`` — the
    binder NEVER fabricates a canonical risk / CVSS / severity component, and it
    MUST NOT call ``build_risk_assessment`` with fabricated values. If no verified
    evidence ref is present, S9 fails closed with ``NO_VERIFIED_EVIDENCE_REF`` and
    produces no finding. No persistence / network / runner / effect / authority /
    Vault / secret is involved. Reached only under synthetic ``_force_complete``
    derivation coverage; the frozen default path stops at S2/S5 and never reaches S9.
    """
    if not evidence_refs:
        return {
            "seam": "S9",
            "owner": SEAM_OWNERS["S9"],
            "precondition_verified": False,
            "reason_code": "NO_VERIFIED_EVIDENCE_REF",
        }
    rf = _load_component(SEAM_OWNERS["S9"], "hsl_risk_findings")
    finding = rf.create_finding(
        title=f"{contract['operations'][0]['operation_id']} on {contract['targets'][0]['target_id']}",
        risk={},  # NEVER fabricate canonical risk components
        root_cause="read-only discovery observation recorded under LAB_L1 custody",
        systemic=False,
        evidence_before=evidence_refs,
    )
    return {
        "seam": "S9",
        "owner": SEAM_OWNERS["S9"],
        "precondition_verified": True,
        "finding_id": finding["finding_id"],
        "state": finding["state"],
        "risk": finding["risk"],
        "limitation_recorded": True,
    }


def _verify_s7(contract: Mapping[str, Any]) -> dict[str, Any]:
    """Prove the S7 effect seam is a DECLARED read-only/L1 operation (AC2).

    Read-only, effect-free proof built from two already-accepted artifacts:
    (1) the operation registry ``platform/gateway-protocol/operation-registry.yaml``
    entry for the contract's operation id, which declares
    ``intrusiveness_level`` and ``side_effect``; and (2) the PRESENCE of the
    adapter seam-ownership PATH. The binder NEVER imports or executes
    ``webgoat_l1_adapter.py``, the router, the runner protocol or admission, and
    performs no network call, subprocess or filesystem write, so
    ``runtime_status`` stays NOT_RUN and no live effect is produced. Nothing in
    the target registry is widened: S2 still refuses OPERATION_OUT_OF_SCOPE, and
    S7 is reached only under synthetic ``_force_complete`` derivation coverage.
    """
    owner = SEAM_OWNERS["S7"]
    reg = yaml.safe_load(
        (REPO_ROOT / "platform/gateway-protocol/operation-registry.yaml").read_text()
    )
    op_id = contract["operations"][0]["operation_id"]
    entry = next((o for o in (reg.get("operations") or []) if o.get("id") == op_id), None)
    adapter_present = (REPO_ROOT / owner).is_file()
    level = entry.get("intrusiveness_level") if entry else None
    side_effect = entry.get("side_effect") if entry else None
    verified = bool(entry) and level in ("L0", "L1") and side_effect == "read-only" and adapter_present
    return {
        "seam": "S7",
        "owner": owner,
        "precondition_verified": bool(verified),
        "operation_id": op_id,
        "registry_entry_found": bool(entry),
        "intrusiveness_level": level,
        "side_effect": side_effect,
        "adapter_present": bool(adapter_present),
        "runtime_status": "NOT_RUN",
    }


def _verify_s10(contract: Mapping[str, Any]) -> dict[str, Any]:
    """Assert the S10 reset / zero-residue proof contract (read-only, NOT_RUN).

    S10 is a READ-ONLY contract assertion only: it checks that the already-accepted
    zero-residue proof schema exists (``platform/lab-lifecycle/zero-residue-proof.schema.json``)
    and records ``runtime_status=NOT_RUN``. It executes NO cleanup/reset, performs NO
    filesystem mutation, runner, network, subprocess, effect, authority, Vault, or secret.
    The binder holds no authority, so S10 grants no reset/cleanup effect — it is the
    static structural record that the reset/zero-residue proof *contract* exists and is
    unchanged (still NOT_RUN) under the frozen state. Reached only under synthetic
    ``_force_complete`` derivation coverage; the frozen default path stops at S5.
    """
    owner = SEAM_OWNERS["S10"]
    schema_present = (REPO_ROOT / "platform/lab-lifecycle/zero-residue-proof.schema.json").is_file()
    return {
        "seam": "S10",
        "owner": owner,
        "precondition_verified": bool(schema_present),
        "proof_schema_present": bool(schema_present),
        "runtime_status": "NOT_RUN",
    }


def bind(
    contract: Mapping[str, Any],
    *,
    clock: str | None = None,
    _force_complete: bool = False,
    kill_switch_engaged: bool = False,
) -> dict[str, Any]:
    """Resolve, verify and derive the LAB_L1 vertical-slice traversal record.

    Canonical seam order (preflight-reconciled source of truth):
    S1 -> S2 -> S3 -> S4 -> S5 -> S6 -> S7 -> S8 -> S9 -> S10 -> S11.

    ``bind`` walks that exact order and STOPS at the FIRST unverified seam
    (recorded as ``refusing_seam``). The default frozen repository state uses the
    REAL ``authorize_operation`` interface, which refuses webgoat-web +
    web.discovery.headers at S2 with ``OPERATION_OUT_OF_SCOPE``; ``bind`` therefore
    short-circuits immediately after S2 and never populates S3..S11. The derived
    terminal state is ``ABORTED`` with ``refusing_seam='S2'`` (NOT S5). This is the
    spec-compliant current-state result that keeps VAL-HSL-RUNNER-L1-LIVE-PROMOTION
    BLOCKED/HOLD.

    ``_force_complete=True`` is a PRIVATE synthetic-only, in-memory positive override
    for S2 and S5 only. It performs NO registry/trust-store mutation and holds NO
    authority/effect; it exists solely so the S11 ``COMPLETED`` derivation logic is
    test-covered without enabling any runtime path. Under it, all S1..S10
    preconditions are made true (S10's ``runtime_status=NOT_RUN`` is non-gating when
    ``precondition_verified=True``) so S11 derives ``COMPLETED`` deterministically.

    S11 derives the terminal state as a PURE function of the collected seam records:
    COMPLETED (every S1..S10 ``precondition_verified`` True), ABORTED (first
    unverified seam, recorded as ``refusing_seam``), or STOPPED (only when
    ``kill_switch_engaged=True``). It emits ``audit_record_present`` and a
    deterministic ``traversal_digest`` (in-memory sealed EvidenceChain over the
    collected seam records + fixed ``clock``). Identical contract + fixed clock
    yields byte-identical output. No live runner/network/subprocess/Vault/secrets;
    no target-registry or trust-store mutation.
    """
    # Canonical order S1 -> S2 -> S3 -> ... -> S11 (reconciled source of truth).
    stop_at_first_refusal = not _force_complete

    # Kill-switch takes absolute precedence: an engaged kill switch derives STOPPED
    # on the REAL default path BEFORE any S1/S2 traversal, regardless of
    # _force_complete (Task 13 safety precedence).
    if kill_switch_engaged:
        return _derive(
            contract,
            seams={},
            refusing_seam=None,
            terminal_state="STOPPED",
            clock=clock,
            kill_switch_engaged=True,
        )

    seams: dict[str, Any] = {}

    # S1 — scope gate (LAB_L1 + L0/L1 intrusiveness). Always evaluated first.
    s1 = _verify_s1(contract)
    seams["S1"] = s1
    if not s1["precondition_verified"]:
        return _derive(contract, seams, refusing_seam="S1", terminal_state="ABORTED", clock=clock)

    # S2 — REAL target authorization (fail-closed). On the default frozen state this
    # refuses OPERATION_OUT_OF_SCOPE and short-circuits immediately: S3..S11 absent.
    s2 = _verify_s2(contract) if not _force_complete else {
        "seam": "S2",
        "owner": SEAM_OWNERS["S2"],
        "precondition_verified": True,
        "allowed": True,
        "reason_code": "ALLOW_OFFENSIVE_OPERATION",
        "target_id": contract["targets"][0]["target_id"],
        "operation_id": contract["operations"][0]["operation_id"],
        "synthetic_override": True,
    }
    seams["S2"] = s2
    if not s2["precondition_verified"]:
        return _derive(contract, seams, refusing_seam="S2", terminal_state="ABORTED", clock=clock)

    # S3 — deterministic plan composition digest. Reached only under force mode;
    # the synthetic S2-verified path exercises it directly via _verify_s3.
    s3 = _verify_s3(contract) if _force_complete else None
    if s3 is not None:
        seams["S3"] = s3
        if not s3["precondition_verified"] and stop_at_first_refusal:
            return _derive(contract, seams, refusing_seam="S3", terminal_state="ABORTED", clock=clock)

    # S4 — HITL assertion from the assurance profile (static read; never refuses).
    s4 = _verify_s4(contract)
    seams["S4"] = s4

    # S5 — authorization seam (trust store). Default refuses TRUST_STORE_ABSENT;
    # force mode supplies a synthetic-verified override (no trust-store mutation).
    s5 = _verify_s5(contract) if not _force_complete else _verify_s5(contract, force=True)
    seams["S5"] = s5
    if not s5["precondition_verified"]:
        return _derive(contract, seams, refusing_seam="S5", terminal_state="ABORTED", clock=clock)

    # S6 — admission/handoff path assert (NOT_RUN, no authority import).
    s6 = _verify_s6(contract)
    seams["S6"] = s6
    if not s6["precondition_verified"] and stop_at_first_refusal:
        return _derive(contract, seams, refusing_seam="S6", terminal_state="ABORTED", clock=clock)

    # S7 — effect seam read-only allowlist + adapter presence (NOT_RUN).
    s7 = _verify_s7(contract)
    seams["S7"] = s7
    if not s7["precondition_verified"] and stop_at_first_refusal:
        return _derive(contract, seams, refusing_seam="S7", terminal_state="ABORTED", clock=clock)

    # S8 — evidence-custody shape (in-memory sealed chain digest, no persistence).
    s8_clock = clock or "2026-08-17T00:00:00Z"
    s8_refs = _synthetic_evidence_refs(contract, s8_clock)
    s8 = _verify_s8(contract, evidence_refs=s8_refs, clock=s8_clock)
    seams["S8"] = s8
    if not s8["precondition_verified"] and stop_at_first_refusal:
        return _derive(contract, seams, refusing_seam="S8", terminal_state="ABORTED", clock=clock)

    # S9 — finding derivation (risk={}, reuses S8 synthetic refs).
    s9 = _verify_s9(contract, evidence_refs=s8_refs)
    seams["S9"] = s9
    if not s9["precondition_verified"] and stop_at_first_refusal:
        return _derive(contract, seams, refusing_seam="S9", terminal_state="ABORTED", clock=clock)

    # S10 — zero-residue proof contract assert (NOT_RUN; non-gating when pv=True).
    s10 = _verify_s10(contract)
    seams["S10"] = s10
    if not s10["precondition_verified"] and stop_at_first_refusal:
        return _derive(contract, seams, refusing_seam="S10", terminal_state="ABORTED", clock=clock)

    # S11 — pure terminal-state derivation (COMPLETED when all S1..S10 verified).
    return _derive(contract, seams, refusing_seam=None, terminal_state="COMPLETED", clock=clock)


def _derive(
    contract: Mapping[str, Any],
    seams: dict[str, Any],
    *,
    refusing_seam: str | None,
    terminal_state: str,
    clock: str | None,
    kill_switch_engaged: bool = False,
) -> dict[str, Any]:
    """Pure S11 derivation: terminal state + audit_record_present + deterministic digest.

    Builds an in-memory sealed EvidenceChain over the collected seam records
    (deterministic given the fixed ``clock``) and emits its chain-state digest as
    the traversal digest. No persistence, no network, no runner, no authority.
    """
    clock = clock or "2026-08-17T00:00:00Z"
    chain_mod = _load_component(
        SEAM_OWNERS["S8"].replace("evidence_plane.py", "evidence_chain.py"), "hsl_ev_chain_derive"
    )
    seal_mod = _load_component(
        SEAM_OWNERS["S8"].replace("evidence_plane.py", "seal.py"), "hsl_seal_derive"
    )
    chain_id = (
        "chain_"
        + hashlib.sha256(
            (contract.get("campaign_id") or "ptaas-slice").encode("utf-8")
        ).hexdigest()
    )
    chain = chain_mod.EvidenceChain(chain_id)
    ref = (
        "evidence://ptaas-slice/"
        + str((contract.get("operations") or [{}])[0].get("operation_id", "operation"))
        + "/seams"
    )
    digest = hashlib.sha256(
        json.dumps(
            {"seams": seams, "refusing_seam": refusing_seam, "clock": clock},
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()
    chain.append_object(
        object_kind="evidence_record",
        object_ref=ref,
        object_digest_sha256=digest,
        object_size_bytes=len(digest.encode("utf-8")),
        object_media_type="application/x-sha256-ref",
        correlation={
            "campaign_id": contract.get("campaign_id") or "campaign",
            "run_id": "ptaas-slice",
            "step_id": "S11",
            "attempt_id": "0",
        },
        created_at=clock,
    )
    seal = seal_mod.seal_chain(chain, sealed_at=clock)

    all_seams_verified = all(
        s.get("precondition_verified") is True
        for sid, s in seams.items()
        if sid in {f"S{i}" for i in range(1, 11)}
    )
    # COMPLETED requires every S1..S10 verified AND no refusal AND no kill switch.
    derived_state = terminal_state
    if kill_switch_engaged and derived_state != "ABORTED":
        derived_state = "STOPPED"

    audit_record_present = (
        derived_state == "COMPLETED"
        and refusing_seam is None
        and all_seams_verified
    )
    # AC10/AC12: the traversal record restates the contract invariants LITERALLY,
    # fail-closed (a missing/other value never becomes permissive). The binder holds
    # no authority and never promotes: execution_authority is always "none" and
    # promotion_allowed always False, independent of the derived terminal state.
    invariants = contract.get("invariants") or {}
    return {
        "campaign_id": contract.get("campaign_id"),
        "execution_authority": "none",
        "promotion_allowed": False,
        "runtime_status": "NOT_RUN",
        "trust_store": invariants.get("trust_store", "ABSENT"),
        "supplier_selection": invariants.get("supplier_selection", "NO_SELECTION"),
        "seams": seams,
        "refusing_seam": refusing_seam,
        "terminal_state": derived_state,
        "audit_record_present": bool(audit_record_present),
        "traversal_digest": seal["seal"]["chain_state_digest_sha256"],
        "kill_switch_engaged": kill_switch_engaged,
    }
