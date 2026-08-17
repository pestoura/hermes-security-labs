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

def test_s4_hitl_required_only_under_lab_l1():
    doc = yaml.safe_load(pathlib.Path("platform/slice-contract/ptaas-webgoat-l1.slice.yaml").read_text())
    rec = sb.bind(doc)
    assert rec["seams"]["S4"]["hitl_required"] is True
    assert rec["seams"]["S4"]["source"] == "current-assurance-profile.yaml"

# --- Task 7: S5 authorization seam — read-only trust-store ABSENT refusal (AC10, AC11) ---
# CHG-HSL-084 Task 7 CORRECTION: S5 is evaluated AFTER S2 (precedence S1->S4->S2->S5
# is preserved; the deferred S1->S4->S2 precedence/order constraint is NOT changed).
# The canonical webgoat-web + web.discovery.headers contract reaches S5 through bind()
# only after S2 is recorded (S2 refuses first), and S5 records a NO_DECISION refusal
# under the frozen ABSENT trust store. The binder NEVER imports the resolver module.

def test_s5_refuses_when_trust_store_absent():
    doc = yaml.safe_load(pathlib.Path("platform/slice-contract/ptaas-webgoat-l1.slice.yaml").read_text())
    rec = sb.bind(doc)
    s5 = rec["seams"]["S5"]
    assert s5["precondition_verified"] is False
    assert s5["reason_code"] == "TRUST_STORE_ABSENT"
    assert s5["authorization_ref"] == "NO_DECISION"
    # frozen-state run must refuse here and stay ABORTED
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
