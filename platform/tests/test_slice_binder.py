import json, pathlib, yaml, jsonschema
SCHEMA = json.loads(pathlib.Path("platform/slice-contract/slice-contract.schema.json").read_text())

def _valid():
    return {
        "schema_version": "ptaas.slice/v1",
        "campaign_id": "camp-ptaas-webgoat-l1-001",
        "assurance_profile": "LAB_L1",
        "targets": [{"target_id": "webgoat-web", "authorization_state_required": "LAB_ONLY"}],
        "operations": [{"operation_id": "web.discovery.headers", "intrusiveness_level": "L1", "destructive": False}],
        "evidence_tuple": {"required": True},
        "finding_shape": {"required": True},
        "terminal_state": {"allowed": ["COMPLETED", "ABORTED", "STOPPED"]},
        "invariants": {
            "execution_authority": "none",
            "runtime_status": "NOT_RUN",
            "promotion_allowed": False,
            "trust_store": "ABSENT",
            "supplier_selection": "NO_SELECTION",
        },
    }

def test_valid_contract_passes():
    jsonschema.validate(_valid(), SCHEMA)  # raises nothing

def test_more_than_one_target_rejected():
    c = _valid(); c["targets"].append({"target_id": "x", "authorization_state_required": "LAB_ONLY"})
    try:
        jsonschema.validate(c, SCHEMA); assert False, "should reject"
    except jsonschema.ValidationError:
        pass

def test_more_than_one_operation_rejected():
    c = _valid(); c["operations"].append({"operation_id": "y", "intrusiveness_level": "L1", "destructive": False})
    try:
        jsonschema.validate(c, SCHEMA); assert False
    except jsonschema.ValidationError:
        pass

def test_intrusiveness_above_l1_rejected():
    c = _valid(); c["operations"][0]["intrusiveness_level"] = "L2"
    try:
        jsonschema.validate(c, SCHEMA); assert False
    except jsonschema.ValidationError:
        pass

def test_destructive_rejected():
    c = _valid(); c["operations"][0]["destructive"] = True
    try:
        jsonschema.validate(c, SCHEMA); assert False
    except jsonschema.ValidationError:
        pass

def test_missing_invariant_rejected():
    c = _valid(); del c["invariants"]["promotion_allowed"]
    try:
        jsonschema.validate(c, SCHEMA); assert False
    except jsonschema.ValidationError:
        pass

def test_instance_conforms_to_schema():
    import yaml
    doc = yaml.safe_load(pathlib.Path("platform/slice-contract/ptaas-webgoat-l1.slice.yaml").read_text())
    jsonschema.validate(doc, SCHEMA)

# --- Task 3: binder skeleton + seam-ownership resolver (AC4) ---
# NOTE: binder lives at platform/slice-contract/slice_binder.py (hyphenated dir,
# matches existing directory and Task 3 "Files" header). It is loaded via
# importlib rather than `import platform.slice_contract...` because `platform`
# is a stdlib module and the directory uses a hyphen. All AC4 assertions are kept.
import importlib.util as _ilu

def _load_binder():
    binder_path = pathlib.Path("platform/slice-contract/slice_binder.py")
    spec = _ilu.spec_from_file_location("slice_binder_task3", binder_path)
    mod = _ilu.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod

sb = _load_binder()

def test_all_seams_resolve_to_existing_components():
    owners = sb.resolve_seam_owners()
    for seam_id, abs_path in owners.items():
        assert pathlib.Path(abs_path).is_file(), f"{seam_id} -> {abs_path} missing"
    assert set(owners) >= {f"S{i}" for i in range(1, 12)}

# --- Task 4: S1 scope + S2 target authorization (AC2, AC5) ---

def _load_instance():
    import yaml
    return yaml.safe_load(
        pathlib.Path("platform/slice-contract/ptaas-webgoat-l1.slice.yaml").read_text()
    )

def test_s1_scope_verified_for_lab_l1_instance():
    rec = sb.bind(_load_instance())
    s1 = rec["seams"]["S1"]
    assert s1["precondition_verified"] is True
    assert s1["intrusiveness_ceiling"] == "L1"

def test_s2_uses_real_fail_closed_authorization():
    # The real authorize_operation for webgoat-web + web.discovery.headers
    # returns allowed=False (OPERATION_OUT_OF_SCOPE) because the target
    # registry declares coarse operations, not the slice operation id. The
    # binder must surface the REAL decision, never fabricate ALLOW.
    rec = sb.bind(_load_instance())
    s2 = rec["seams"]["S2"]
    assert s2["precondition_verified"] is False
    assert s2["allowed"] is False
    assert s2["reason_code"] == "OPERATION_OUT_OF_SCOPE"
    assert s2["target_id"] == "webgoat-web"
    assert s2["operation_id"] == "web.discovery.headers"
    # Precedence: unverified S2 aborts the traversal.
    assert rec["terminal_state"] == "ABORTED"

def test_s2_refuses_unknown_target_fail_closed():
    doc = {
        "campaign_id": "x",
        "assurance_profile": "LAB_L1",
        "targets": [{"target_id": "nope", "authorization_state_required": "LAB_ONLY"}],
        "operations": [{"operation_id": "web.discovery.headers", "intrusiveness_level": "L1", "destructive": False}],
    }
    rec = sb.bind(doc)
    assert rec["seams"]["S2"]["precondition_verified"] is False
    assert rec["terminal_state"] == "ABORTED"

def test_s1_scope_refusal_aborts_before_s2():
    # A non-LAB_L1 contract must fail at S1 (scope) and never reach a S2 record.
    doc = {
        "campaign_id": "x",
        "assurance_profile": "PROD_L3",
        "targets": [{"target_id": "webgoat-web", "authorization_state_required": "LAB_ONLY"}],
        "operations": [{"operation_id": "web.discovery.headers", "intrusiveness_level": "L2", "destructive": False}],
    }
    rec = sb.bind(doc)
    assert rec["seams"]["S1"]["precondition_verified"] is False
    assert "S2" not in rec["seams"]
    assert rec["terminal_state"] == "ABORTED"

# --- Task 5: S3 deterministic plan composition digest (AC3 contributor) ---
# CHG-HSL-084 Task 5 CORRECTION: the canonical webgoat-web + web.discovery.headers
# contract REFUSES at S2 (OPERATION_OUT_OF_SCOPE), and Task 4's precedence rule
# makes bind() early-return, so S3 is NEVER reached through bind() on the real
# contract. The S3 positive digest is therefore exercised SYNTHETICALLY /
# INDEPENDENTLY: we call the real _verify_s3 helper directly against the
# already-accepted webgoat-tls-transport-review scenario (a valid S2-equivalent
# seam outcome). This proves the deterministic digest derivation without
# widening the target-registry scope or authorizing web.discovery.headers.

def test_s3_plan_digest_deterministic_synthetic():
    r1 = sb._verify_s3(_load_instance())
    r2 = sb._verify_s3(_load_instance())
    assert r1["plan_digest"] is not None
    assert r1["plan_digest"] == r2["plan_digest"]
    assert r1["precondition_verified"] is True
    assert r1["reason_code"] == "PLAN_READY"

def test_canonical_bind_does_not_evaluate_s3_after_s2_refusal():
    # Reinforces the corrected precedence invariant: the canonical contract's
    # S2 refusal must keep bind() from evaluating S3 (or any later seam).
    rec = sb.bind(_load_instance())
    assert "S2" in rec["seams"]
    assert rec["seams"]["S2"]["precondition_verified"] is False
    assert "S3" not in rec["seams"]
    assert rec["terminal_state"] == "ABORTED"

# --- Task 6: S4 HITL resolution from assurance profile (AC9) ---
# CHG-HSL-084 Task 13 preflight reconciliation: the default bind short-circuits at
# S2 (OPERATION_OUT_OF_SCOPE), so S4 is NOT populated on the real contract. Verify
# S4 directly via _verify_s4 (or a synthetic S2-verified path); do NOT require S4 on
# the default bind output.

def test_s4_hitl_required_only_under_lab_l1():
    doc = yaml.safe_load(pathlib.Path("platform/slice-contract/ptaas-webgoat-l1.slice.yaml").read_text())
    s4 = sb._verify_s4(doc)
    assert s4["precondition_verified"] is True
    assert s4["hitl_required"] is True
    assert s4["source"] == "current-assurance-profile.yaml"
    assert s4["seam"] == "S4"

def test_s4_not_in_default_bind_output_short_circuits_at_s2():
    # Reconciled: default bind stops at S2; S4 must NOT be present on default output.
    doc = yaml.safe_load(pathlib.Path("platform/slice-contract/ptaas-webgoat-l1.slice.yaml").read_text())
    rec = sb.bind(doc)
    assert "S4" not in rec["seams"]
    assert rec["refusing_seam"] == "S2"
    assert rec["terminal_state"] == "ABORTED"

# --- Task 7: S5 authorization seam — read-only trust-store ABSENT refusal (AC10, AC11) ---
# CHG-HSL-084 Task 13 preflight reconciliation: the canonical default bind
# short-circuits at S2 (OPERATION_OUT_OF_SCOPE), so S5 is NOT populated on the
# default contract. S5 is a LATER seam that is never reached because S2 precedes
# it and short-circuits first. Verify S5 directly via _verify_s5 to confirm the
# trust-store-absent refusal shape; do NOT require S5 on the default bind output.

def test_s5_refuses_when_trust_store_absent():
    doc = yaml.safe_load(pathlib.Path("platform/slice-contract/ptaas-webgoat-l1.slice.yaml").read_text())
    s5 = sb._verify_s5(doc)
    assert s5["precondition_verified"] is False
    assert s5["reason_code"] == "TRUST_STORE_ABSENT"
    assert s5["authorization_ref"] == "NO_DECISION"
    assert s5["seam"] == "S5"

def test_s5_not_in_default_bind_output_short_circuits_at_s2():
    # Reconciled: default bind stops at S2; S5 (a later seam) must NOT be present.
    doc = yaml.safe_load(pathlib.Path("platform/slice-contract/ptaas-webgoat-l1.slice.yaml").read_text())
    rec = sb.bind(doc)
    assert "S5" not in rec["seams"]
    assert rec["refusing_seam"] == "S2"
    assert rec["terminal_state"] == "ABORTED"

# --- Task 8: S6 admission/handoff seam — read-only path assert, NOT_RUN ---
# CHG-HSL-084 Task 8: S6 is recorded under synthetic _force_complete derivation
# coverage ONLY. The binder asserts the seam-ownership path (admission.py) and
# records runtime_status=NOT_RUN. It NEVER imports admission.py / runner_handoff.py
# / runner_protocol_v2, never executes a runner, network, or subprocess, and never
# grants authority. The S1->S4->S2 precedence and the frozen-state S5 refusal
# (default path) are unchanged; the constraint stays intact for Task 13.

def test_s6_recorded_not_run_no_authority_import():
    doc = yaml.safe_load(pathlib.Path("platform/slice-contract/ptaas-webgoat-l1.slice.yaml").read_text())
    rec = sb.bind(doc, _force_complete=True)  # synthetic-complete mode for derivation coverage
    s6 = rec["seams"]["S6"]
    assert s6["owner"].endswith("admission.py")
    assert s6["runtime_status"] == "NOT_RUN"

# --- Task 9: S7 effect seam — read-only allowlist + adapter existence (AC2) ---
# CHG-HSL-084 Task 9: S7 proves the DECLARED read-only/L1 nature of the slice
# operation using the already-accepted operation registry
# (platform/gateway-protocol/operation-registry.yaml) plus adapter PRESENCE/PATH
# only. The binder NEVER imports or executes webgoat_l1_adapter.py, the router,
# the runner, a network call or a subprocess, so runtime_status stays NOT_RUN and
# no live effect exists. It is recorded under synthetic _force_complete derivation
# coverage ONLY; the frozen default path still refuses at S5 and stays ABORTED,
# and the S1->S4->S2 precedence (Task 13 constraint) is untouched. No
# target-registry widening: S2 still refuses OPERATION_OUT_OF_SCOPE.

def test_s7_proves_allowlisted_read_only_operation():
    doc = yaml.safe_load(pathlib.Path("platform/slice-contract/ptaas-webgoat-l1.slice.yaml").read_text())
    rec = sb.bind(doc, _force_complete=True)
    s7 = rec["seams"]["S7"]
    assert s7["owner"].endswith("webgoat_l1_adapter.py")
    assert s7["precondition_verified"] is True
    assert s7["intrusiveness_level"] == "L1"
    assert s7["side_effect"] == "read-only"
    assert s7["runtime_status"] == "NOT_RUN"
    assert s7["adapter_present"] is True
    assert s7["registry_entry_found"] is True

def test_s7_not_reached_on_frozen_default_path():
    doc = yaml.safe_load(pathlib.Path("platform/slice-contract/ptaas-webgoat-l1.slice.yaml").read_text())
    rec = sb.bind(doc)
    assert "S7" not in rec["seams"]
    assert rec["seams"]["S2"]["reason_code"] == "OPERATION_OUT_OF_SCOPE"
    assert rec["terminal_state"] == "ABORTED"

def test_s7_holds_no_authority_and_no_live_effect():
    src = pathlib.Path("platform/slice-contract/slice_binder.py").read_text()
    # inspect REAL import statements only (docstrings legitimately name the
    # forbidden modules to document the no-authority invariant)
    import_lines = [
        ln.strip() for ln in src.splitlines()
        if ln.strip().startswith(("import ", "from "))
    ]
    banned = ("subprocess", "requests", "socket", "http", "urllib",
              "runner_handoff", "runner_protocol_v2", "admission",
              "webgoat_l1_adapter", "router")
    for ln in import_lines:
        for mod in banned:
            assert mod not in ln, f"{mod} imported: {ln}"
    # the adapter is referenced as a PATH string only, never loaded/executed
    assert '_load_component(SEAM_OWNERS["S7"]' not in src

# --- Task 10: S8 evidence custody shape — in-memory sealed chain digest (AC6) ---
# CHG-HSL-084 Task 10: S8 derives the evidence-custody shape in-memory only, using
# the already-accepted EvidenceChain/evidence_plane (seal) interfaces. The seal/canonical
# digest is deterministic and verified; NO LocalEvidenceStore write / persistence occurs.
# The binder holds no authority and performs no effect: no filesystem write beyond
# normal git/test temp, no network/runner/effect/authority/Vault/secret. The default
# frozen-state path (no synthetic evidence refs) records S8 precondition_verified=False
# with persisted=False. The _force_complete synthetic path supplies synthetic valid
# evidence refs (digests only) for derivation coverage. The S1->S4->S2 precedence and
# the frozen S5 refusal are unchanged.

def test_s8_derives_sealed_chain_digest_without_persistence(tmp_path):
    doc = yaml.safe_load(pathlib.Path("platform/slice-contract/ptaas-webgoat-l1.slice.yaml").read_text())
    rec = sb.bind(doc, _force_complete=True)
    s8 = rec["seams"]["S8"]
    assert s8["chain_state_digest"] is not None
    assert s8["seal_verified"] is True
    assert s8["persisted"] is False  # no LocalEvidenceStore write

def test_s8_default_path_no_evidence_refs_not_persisted():
    doc = yaml.safe_load(pathlib.Path("platform/slice-contract/ptaas-webgoat-l1.slice.yaml").read_text())
    rec = sb.bind(doc)  # default frozen path: no synthetic evidence refs
    assert "S8" not in rec["seams"]  # not reached; S5 refuses first
    assert rec["terminal_state"] == "ABORTED"

def test_s8_holds_no_authority_and_no_live_effect():
    src = pathlib.Path("platform/slice-contract/slice_binder.py").read_text()
    import_lines = [
        ln.strip() for ln in src.splitlines()
        if ln.strip().startswith(("import ", "from "))
    ]
    banned = ("subprocess", "requests", "socket", "http", "urllib",
              "runner_handoff", "runner_protocol_v2", "admission",
              "webgoat_l1_adapter", "router", "vault", "secret", "signer",
              "trust", "evidence_plane", "evidence_chain", "seal")
    for ln in import_lines:
        for mod in banned:
            assert mod not in ln, f"{mod} imported: {ln}"

# --- Task 11: S9 finding derivation — deterministic, risk={}, or fail-closed (AC7) ---
# CHG-HSL-084 Task 11 CORRECTION: S9 is reached ONLY under synthetic
# _force_complete derivation coverage, reusing the SAME synthetic verified
# evidence refs derived by S8 (no live evidence, no new evidence source). The
# default frozen path (no _force_complete) must NOT reach S9 — it stops at S2/S5.
# S9 normalizes a finding through the already-accepted create_finding interface
# with risk={} (never a fabricated canonical risk / CVSS / severity component);
# when no verified evidence ref is present it refuses fail-closed with
# NO_VERIFIED_EVIDENCE_REF and produces no finding. No persistence / network /
# runner / effect / authority / Vault / secret is involved.

def test_s9_derives_conforming_finding_without_fabricated_risk():
    doc = yaml.safe_load(pathlib.Path("platform/slice-contract/ptaas-webgoat-l1.slice.yaml").read_text())
    rec = sb.bind(doc, _force_complete=True)
    s9 = rec["seams"]["S9"]
    assert s9["finding_id"].startswith("fd_")
    assert s9["state"] == "OBSERVED"
    assert s9["risk"] == {}            # no fabricated canonical component
    assert s9["limitation_recorded"] is True

def test_s9_refuses_when_no_evidence_ref_fail_closed():
    # The fail-closed refusal is a UNIT property of _verify_s9: with no verified
    # evidence ref it must refuse (NO_VERIFIED_EVIDENCE_REF) and fabricate no finding.
    s9 = sb._verify_s9(_load_instance(), evidence_refs=[])
    assert s9["precondition_verified"] is False
    assert s9["reason_code"] == "NO_VERIFIED_EVIDENCE_REF"
    assert "finding_id" not in s9  # no finding fabricated on refusal

def test_s9_not_reached_on_frozen_default_path():
    # The default frozen bind() must not reach S9; it refuses earlier (S2/S5).
    rec = sb.bind(_load_instance())
    assert "S9" not in rec["seams"]
    assert rec["terminal_state"] == "ABORTED"

# --- Task 12: S10 reset / zero-residue proof — read-only contract assert (AC shape) ---
# CHG-HSL-084 Task 12 (already-approved fail-closed correction): S10 is the
# reset/zero-residue proof seam, asserted as a READ-ONLY contract check only —
# proof-schema presence + runtime_status=NOT_RUN. It executes NO cleanup/reset,
# performs NO filesystem mutation, runner, network, subprocess, effect, authority,
# Vault, or secret. It is reached ONLY under synthetic _force_complete derivation
# coverage; the frozen default path (no _force_complete) must NOT reach S10 — it
# refuses earlier (S2/S5) and stays ABORTED. Task 13 precedence/order constraints
# and the target-registry are NOT altered by this task.

def test_s10_zero_residue_contract_present():
    doc = yaml.safe_load(pathlib.Path("platform/slice-contract/ptaas-webgoat-l1.slice.yaml").read_text())
    rec = sb.bind(doc, _force_complete=True)
    s10 = rec["seams"]["S10"]
    assert s10["owner"].endswith("lifecycle_protocol.py")
    assert s10["proof_schema_present"] is True
    assert s10["runtime_status"] == "NOT_RUN"

def test_s10_not_reached_on_frozen_default_path():
    # The default frozen bind() must not reach S10; it refuses earlier (S2/S5).
    rec = sb.bind(_load_instance())
    assert "S10" not in rec["seams"]
    assert rec["seams"]["S2"]["reason_code"] == "OPERATION_OUT_OF_SCOPE"
    assert rec["terminal_state"] == "ABORTED"

def test_s10_does_no_reset_and_no_live_effect():
    # Unit property of _verify_s10: read-only assert of the proof-schema path,
    # runtime_status NOT_RUN, no reset/cleanup/runner/effect/authority granted.
    s10 = sb._verify_s10(_load_instance())
    assert s10["seam"] == "S10"
    assert s10["owner"].endswith("lifecycle_protocol.py")
    assert s10["proof_schema_present"] is True
    assert s10["precondition_verified"] is True
    assert s10["runtime_status"] == "NOT_RUN"
    # no fabricated effect/reset/authority field
    assert "reset_executed" not in s10
    assert "cleanup_performed" not in s10
    assert "authority_granted" not in s10

def test_s10_holds_no_authority_and_no_live_effect():
    src = pathlib.Path("platform/slice-contract/slice_binder.py").read_text()
    import_lines = [
        ln.strip() for ln in src.splitlines()
        if ln.strip().startswith(("import ", "from "))
    ]
    banned = ("subprocess", "requests", "socket", "http", "urllib",
              "runner_handoff", "runner_protocol_v2", "admission",
              "webgoat_l1_adapter", "router", "vault", "secret", "signer",
              "trust", "lifecycle_protocol")
    for ln in import_lines:
        for mod in banned:
            assert mod not in ln, f"{mod} imported: {ln}"
    # the lifecycle_protocol owner is a PATH string only, never loaded/executed
    assert '_load_component(SEAM_OWNERS["S10"]' not in src

# --- Task 13: S11 terminal-state derivation + full determinism (AC3, AC8) ---
# CHG-HSL-084 Task 13 preflight reconciliation (source-of-truth):
# Canonical seam order S1->S2->S3->S4->S5->S6->S7->S8->S9->S10->S11. Default bind
# short-circuits at S2 (OPERATION_OUT_OF_SCOPE), so S11 derives ABORTED/refusing_seam=S2
# with S3..S11 absent. COMPLETED is exercised only via _force_complete (private
# synthetic-only, in-memory, no authority/effect/trust-mutation). STOPPED only when
# kill_switch_engaged=True. S11 is a pure function: emits audit_record_present and a
# deterministic traversal_digest; identical contract + fixed clock => byte-identical.

def test_terminal_state_completed_when_all_seams_ok():
    # Synthetic-only COMPLETED via _force_complete (no live effect, no authority).
    doc = yaml.safe_load(pathlib.Path("platform/slice-contract/ptaas-webgoat-l1.slice.yaml").read_text())
    rec = sb.bind(doc, _force_complete=True)
    assert rec["terminal_state"] == "COMPLETED"
    assert rec["refusing_seam"] is None
    assert rec["audit_record_present"] is True
    # all S1..S10 present and verified under synthetic override
    for sid in (f"S{i}" for i in range(1, 11)):
        assert sid in rec["seams"]
        assert rec["seams"][sid].get("precondition_verified") is True
    assert rec["traversal_digest"] is not None

def test_terminal_state_aborted_on_refusal():
    # Default contract: real S2 refuses, short-circuits immediately at S2.
    doc = yaml.safe_load(pathlib.Path("platform/slice-contract/ptaas-webgoat-l1.slice.yaml").read_text())
    rec = sb.bind(doc)
    assert rec["terminal_state"] == "ABORTED"
    assert rec["refusing_seam"] == "S2"
    # S3..S11 must be absent (short-circuit); only S1 and S2 populated.
    assert set(rec["seams"].keys()) == {"S1", "S2"}
    assert rec["seams"]["S2"]["reason_code"] == "OPERATION_OUT_OF_SCOPE"
    assert rec["audit_record_present"] is False

def test_terminal_state_stopped_when_kill_switch_engaged():
    # STOPPED is derived only when kill_switch_engaged=True (synthetic complete mode).
    doc = yaml.safe_load(pathlib.Path("platform/slice-contract/ptaas-webgoat-l1.slice.yaml").read_text())
    rec = sb.bind(doc, _force_complete=True, kill_switch_engaged=True)
    assert rec["terminal_state"] == "STOPPED"
    assert rec["kill_switch_engaged"] is True
    assert rec["audit_record_present"] is False

def test_kill_switch_engaged_real_default_path_derives_stopped():
    # Task 13 safety precedence regression: an engaged kill switch MUST derive
    # STOPPED on the REAL default path (no _force_complete) BEFORE any S1/S2
    # traversal, not fall through to the S2 OPERATION_OUT_OF_SCOPE refusal
    # (which would wrongly yield ABORTED). This guards the previously-violated
    # precedence where STOPPED was only derived under synthetic _force_complete.
    doc = yaml.safe_load(pathlib.Path("platform/slice-contract/ptaas-webgoat-l1.slice.yaml").read_text())
    rec = sb.bind(doc, kill_switch_engaged=True)
    assert rec["terminal_state"] == "STOPPED"
    assert rec["kill_switch_engaged"] is True
    assert rec["audit_record_present"] is False

def test_traversal_record_byte_identical():
    # Identical contract + fixed clock => byte-identical record (determinism, AC3).
    doc = yaml.safe_load(pathlib.Path("platform/slice-contract/ptaas-webgoat-l1.slice.yaml").read_text())
    a = json.dumps(sb.bind(doc, _force_complete=True, clock="2026-08-17T00:00:00Z"), sort_keys=True)
    b = json.dumps(sb.bind(doc, _force_complete=True, clock="2026-08-17T00:00:00Z"), sort_keys=True)
    assert a == b

def test_s10_not_run_non_gating_under_force_complete():
    # S10 runtime_status=NOT_RUN must NOT block COMPLETED when precondition_verified=True.
    doc = yaml.safe_load(pathlib.Path("platform/slice-contract/ptaas-webgoat-l1.slice.yaml").read_text())
    rec = sb.bind(doc, _force_complete=True)
    assert rec["seams"]["S10"]["runtime_status"] == "NOT_RUN"
    assert rec["seams"]["S10"]["precondition_verified"] is True
    assert rec["terminal_state"] == "COMPLETED"

def test_force_complete_is_synthetic_only_no_mutation():
    # _force_complete must not touch the registry/trust-store or grant authority.
    # It only synthesizes S2/S5 positive outcomes in-memory for derivation coverage.
    doc = yaml.safe_load(pathlib.Path("platform/slice-contract/ptaas-webgoat-l1.slice.yaml").read_text())
    rec = sb.bind(doc, _force_complete=True)
    assert rec["seams"]["S2"].get("synthetic_override") is True
    assert rec["seams"]["S5"].get("synthetic_override") is True
    assert rec["seams"]["S5"]["authorization_ref"] == "NO_DECISION"
    # invariants unchanged in the contract itself
    assert doc["invariants"]["trust_store"] == "ABSENT"
    assert doc["invariants"]["execution_authority"] == "none"

# --- Task 14: fail-closed precedence + authority-negative proof (AC5, AC11) ---
# CHG-HSL-084 Task 14 (source-of-truth, corrected first-refusal semantics):
# Canonical seam order S1->S2->S3->...->S11. The default frozen path uses the
# REAL authorize_operation, which refuses at S2. When BOTH an early refusal (S2,
# unknown target) AND a later refusal (S5, absent trust store) are plausible, the
# EARLIEST unverified seam wins and is recorded as refusing_seam; later seams are
# NOT evaluated/populated as pass. Critically, mere PRESENCE of a target_id in the
# contract (even one that exists in the registry, e.g. webgoat-web) grants NO
# authority: S2 still calls the real authorize_operation and refuses the typed op
# web.discovery.headers (OPERATION_OUT_OF_SCOPE). Contract presence is never
# authorization.

def test_refusal_precedence_earliest_seam_recorded():
    # S2 unknown target AND S5 absent trust store: earliest (S2) wins.
    doc = {
        "campaign_id": "x",
        "assurance_profile": "LAB_L1",
        "targets": [{"target_id": "nope", "authorization_state_required": "LAB_ONLY"}],
        "operations": [{"operation_id": "web.discovery.headers", "intrusiveness_level": "L1", "destructive": False}],
    }
    rec = sb.bind(doc)
    # earliest unverified seam is recorded as the refusing seam
    assert rec["refusing_seam"] == "S2"     # not S5
    # later seams must not be evaluated/populated as a pass
    assert "S5" not in rec["seams"] or rec["seams"].get("S5", {}).get("precondition_verified") in (None, False)
    # traversal aborts at the earliest refusal
    assert rec["terminal_state"] == "ABORTED"

def test_contract_presence_never_authorizes():
    # target_id present in the contract (and even registered) but UNVERIFIED for
    # the typed operation must deny before any handler; presence is not authority.
    doc = {
        "campaign_id": "x",
        "assurance_profile": "LAB_L1",
        "targets": [{"target_id": "webgoat-web", "authorization_state_required": "LAB_ONLY"}],
        "operations": [{"operation_id": "web.discovery.headers", "intrusiveness_level": "L1", "destructive": False}],
    }
    rec = sb.bind(doc)
    # S2 still calls the real authorize_operation (no synthetic allow); presence
    # alone is not authority.
    assert rec["seams"]["S2"]["owner"].endswith("execution_authorization.py")
    # the real interface refuses the typed op despite the target existing
    assert rec["seams"]["S2"]["precondition_verified"] is False
    assert rec["seams"]["S2"]["allowed"] is False
    assert rec["seams"]["S2"]["reason_code"] == "OPERATION_OUT_OF_SCOPE"
    assert rec["refusing_seam"] == "S2"
    assert rec["terminal_state"] == "ABORTED"

# --- Task 15: sanitization AST guard + literal invariant assertions (AC10, AC12) ---
# CHG-HSL-084 Task 15: the no-authority/no-effect property of the binder is proven
# by a real AST analysis (platform/tests/ast_sanitization_guard.py), not by a
# substring scan. The analyzer resolves import bindings (including aliases and
# `from X import y`) and only flags call surfaces whose base resolves to a
# forbidden authority/effect module, so docstrings and path STRINGS that legitimately
# name those modules (the binder documents them) are never false positives.
# The canonical contract's invariants are asserted literally (AC12).
import ast as _ast  # noqa: E402  (module-level import after in-file test sections, matching this file's existing layout)
from ast_sanitization_guard import (  # noqa: E402  (sibling test helper, resolved via pytest rootdir insertion)
    FORBIDDEN_MODULES,
    forbidden_imports,
    forbidden_calls,
)

_BINDER_PATH = pathlib.Path("platform/slice-contract/slice_binder.py")

def _binder_tree():
    return _ast.parse(_BINDER_PATH.read_text())

def test_binder_imports_no_forbidden_modules():
    found = forbidden_imports(_binder_tree())
    assert found == [], f"forbidden imports: {found}"
    # the plan-named authority/effect modules are actually covered by the guard
    assert {"runner_protocol_v2", "subprocess", "socket"} <= set(FORBIDDEN_MODULES)

def test_binder_performs_no_socket_or_subprocess_calls():
    found = forbidden_calls(_binder_tree())
    assert found == [], f"forbidden call surface: {found}"

def test_ast_guard_detects_forbidden_import_and_call_positively():
    # negative control: the analyzer must FLAG real authority/effect usage,
    # including aliased imports and `from` bindings.
    bad = _ast.parse(
        "import subprocess as sp\n"
        "from socket import socket as sk\n"
        "import runner_protocol_v2\n"
        "def f():\n"
        "    sp.run(['x'])\n"
        "    sk().sendall(b'x')\n"
    )
    imp = {f["module"] for f in forbidden_imports(bad)}
    assert {"subprocess", "socket", "runner_protocol_v2"} <= imp
    calls = {f["attr"] for f in forbidden_calls(bad)}
    assert "run" in calls and "sendall" in calls

def test_ast_guard_does_not_flag_path_strings_or_docstrings():
    # positive control: mentions in docstrings/strings and unrelated .run/.send
    # attributes on non-forbidden bases must NOT be flagged.
    ok = _ast.parse(
        '"""mentions subprocess, socket and runner_protocol_v2 for documentation."""\n'
        'P = "platform/adapters/webgoat_l1_adapter.py"\n'
        'import json\n'
        'def f(rec):\n'
        '    return json.dumps(rec, sort_keys=True)\n'
    )
    assert forbidden_imports(ok) == []
    assert forbidden_calls(ok) == []

def test_invariants_asserted_literal():
    doc = yaml.safe_load(pathlib.Path("platform/slice-contract/ptaas-webgoat-l1.slice.yaml").read_text())
    assert doc["invariants"]["execution_authority"] == "none"
    assert doc["invariants"]["runtime_status"] == "NOT_RUN"
    assert doc["invariants"]["promotion_allowed"] is False
    assert doc["invariants"]["trust_store"] == "ABSENT"
    assert doc["invariants"]["supplier_selection"] == "NO_SELECTION"

def test_binder_record_holds_invariants_and_no_promotion():
    doc = yaml.safe_load(_BINDER_PATH.parent.joinpath("ptaas-webgoat-l1.slice.yaml").read_text())
    rec = sb.bind(doc)
    assert rec["execution_authority"] == "none"
    assert rec["promotion_allowed"] is False
    assert rec["runtime_status"] == "NOT_RUN"
    assert rec["trust_store"] == "ABSENT"
    assert rec["supplier_selection"] == "NO_SELECTION"
    assert rec["refusing_seam"] == "S2"
    assert rec["terminal_state"] == "ABORTED"
