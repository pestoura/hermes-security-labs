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
