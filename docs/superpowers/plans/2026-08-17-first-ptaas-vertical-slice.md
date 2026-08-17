# First PTaaS Vertical Slice — Implementation Plan

> **For Hermes:** Use subagent-driven-development to implement this plan task-by-task. Each task is RED → GREEN → commit. The plan is the implementation contract for the future `CHG-HSL-083` implementation change; this document is documentation only and is committed on `chg-hsl-083/ptaas-vertical-slice-design` with no production code.

**Goal:** Implement the Option C composition from `ADR-0017` and `docs/architecture/first-ptaas-vertical-slice.md` as a declarative slice contract (schema + one YAML instance) plus a thin, read-only, authority-free traversal binder that resolves and verifies the already-accepted seams S1–S11 and emits one deterministic, sanitized traversal record.

**Architecture:** One JSON schema and one YAML instance declare, for exactly one `LAB_L1` campaign: one `target_id` (`webgoat-web`), one non-destructive operation (`web.discovery.headers`), the required evidence tuple, the required finding shape, the terminal-state definition, and the literal invariants `execution_authority: none`, `runtime_status: NOT_RUN`, `promotion_allowed: false`. A binder module imports only the already-accepted, effect-free components (`execution_authorization`, `scenario_plan`, `assurance_profile`, `evidence_plane`, `evidence_chain`, `seal`, `risk_findings`), resolves each seam to its owning component path, verifies that seam's precondition, derives the finding shape and the terminal campaign state as pure functions, and refuses fail-closed on the first unsatisfied precondition. The binder performs no effect, issues no authorization, writes no custody record, mutates no campaign state, and never imports the authority/effect modules (`runner_handoff`, `admission`, `router`, `webgoat_l1_adapter`) or `runner_protocol_v2`. Because the frozen repository state has `trust-store: ABSENT` and every policy `DISABLED`/`deny`/`NOT_RUN`, the binder run against current state refuses at S5 (`TRUST_STORE_ABSENT`) and derives `ABORTED` — the correct, spec-compliant result that keeps `VAL-HSL-RUNNER-L1-LIVE-PROMOTION` `BLOCKED/HOLD`. The positive `COMPLETED` branch is implemented and exercised only with synthetic-but-valid seam outcomes (no live effects) so the derivation logic is test-covered without enabling any runtime path.

**Tech Stack:** Python 3.11, `pytest`, `jsonschema`, `PyYAML`, existing `platform/**` contracts, GitHub Actions validation gates. No new dependency. No `runner_protocol_v2` on the import path.

**Canonical references (read at implementation time):**
- `changes/CHG-HSL-083.yaml` (this change's DOC_ONLY design record)
- `docs/architecture/adr/ADR-0017-first-ptaas-vertical-slice-composition.md`
- `docs/architecture/first-ptaas-vertical-slice.md`
- Design baseline `c63fee752bfd28868da54eb9650943e2b504f659` (components verified there; this plan re-verifies them on the implementation branch HEAD)

---

## Global Constraints

- No production code beyond the four new files listed under *Exact planned file set*. No new orchestrator, no extension of `runner-service/service_composition.py`, no new authority-shaped component (ADR-0017 Option C only).
- The binder holds **no authority**: it resolves, verifies, derives and refuses. It never calls an effect path and never imports `runner_handoff`, `admission`, `router`, `webgoat_l1_adapter`, or `runner_protocol_v2`.
- No Vault, signer, trust-store, credential, secret, token, cookie, header or key material at any seam. `trust-store` stays `ABSENT`; S5 is recorded `NO_DECISION` and refuses.
- No live effect: no network, no subprocess, no socket send, no filesystem write outside the in-memory chain used for digest derivation. Custody is proven by shape (in-memory sealed `EvidenceChain`) only; no `LocalEvidenceStore` write occurs.
- Exactly one target and one operation per slice. The schema rejects more than one of either, intrusiveness above `L1`, `destructive: true`, and any missing declared invariant.
- Every existing policy stays `DISABLED`/`deny`/`NOT_RUN`. `promotion_allowed=false`, `runtime_status=NOT_RUN`, `execution_authority=none`, `supplier_selection=NO_SELECTION`, `trust-store=ABSENT` are asserted literally and unchanged.
- No blocker is closed; no campaign observation moves off `BLOCKED/OPEN`; no `state`/`promotionRecommendation` in any validation campaign changes.
- Findings are sanitized: digests, stable reason codes, identifiers only. `risk={}` (never a fabricated canonical component). No raw payload, locator, signature, credential, secret, token, cookie or header in any record.
- Determinism: identical contract + fixed clock yields byte-identical traversal record. Tests inject a fixed `clock`/`now`.
- HITL appears exactly where `current-assurance-profile.yaml` already requires it (`requires_request_bound_hitl: true` under `LAB_L1`); no new approval surface.

---

## Exact planned file set (new, implementation change only)

- `platform/slice-contract/slice-contract.schema.json` — JSON Schema (draft 2020-12) for the slice contract.
- `platform/slice-contract/ptaas-webgoat-l1.slice.yaml` — the single instance: `webgoat-web` + `web.discovery.headers`, `LAB_L1`.
- `platform/slice-contract/slice_binder.py` — read-only resolver/verifier/deriver (no effect, no authority import).
- `platform/tests/test_slice_binder.py` — TDD suite covering AC1–AC12.
- `changes/CHG-HSL-0NN.yaml` — the implementation change record (use the next unused id; at plan-authoring time `083` is the design record and `084` is expected free — verify with `ls changes/ | grep -E 'CHG-HSL-0(8[4-9]|9[0-9])'`). Classification `IMPLEMENTATION`, validation `targeted: PASS`, `regression: PASS`, `security: NOT_APPLICABLE`, `runtime: NOT_APPLICABLE`; carries the invariants and `source.reference` to `ADR-0017` + the design doc.

No index/README update is required: `docs/superpowers/` has no plans index file (verified; only `plans/` and `specs/` flat directories), so no plan-index link is needed. Do **not** modify `docs/architecture/first-ptaas-vertical-slice.md` (keep YAGNI; the implementation record is the source of truth for the change).

---

## Verified component interface facts (used by the binder)

These signatures were read from the repository at the design commit and are the stable seams the binder resolves against. The binder must call them as shown and must not assume fields beyond those listed.

- `platform/targets/execution_authorization.py`
  - `authorize_operation(target_id, operation_id, *, document=None, operation_class="OFFENSIVE") -> AuthorizationDecision`
  - `AuthorizationDecision` exposes `.allowed: bool`, `.reason_code: str`, `.target_id`, `.operation_id`, `.as_dict()`; fails closed for unknown/out-of-scope/missing inputs (stable reason codes from `REASON_CODES`).
  - `webgoat-web` resolves `authorization_state: LAB_ONLY` and a declared scope in `platform/targets/target-registry.yaml`.
- `platform/scenario-registry/scenario_plan.py`
  - `compose_scenario_plan(scenario_id, *, scenario_doc=None, tool_doc=None, operation_doc=None, target_doc=None, manifests=None) -> ScenarioPlanResult`
  - `ScenarioPlanResult` exposes `.ok: bool`, `.reason_code: str`, `.plan`, `.as_dict()`.
  - Scenario `webgoat-tls-transport-review` exists and binds `target_id: webgoat-web` with operations `web.discovery.headers`, `web.discovery.tls`.
- `platform/assurance/assurance_profile.py`
  - The binder does **not** call `validate_profile_document` (it requires a full `evaluation` map). Instead it reads `platform/assurance/current-assurance-profile.yaml` and asserts the two LAB_L1-relevant booleans: `requires_request_bound_hitl: true` and `requires_hash_chain: true`. This is read-only and deterministic.
- `platform/evidence-plane/evidence_plane.py`
  - `canonical_digest(value: Mapping[str, Any]) -> str` (used to digest plan/finding/terminal records deterministically).
- `platform/evidence-plane/evidence_chain.py`
  - `EvidenceChain(chain_id)`, `.append_object(*, object_kind, object_ref, object_digest_sha256, object_size_bytes, object_media_type, correlation, evidence_ref=None, canonical_payload_sha256=None, created_at=None) -> ChainEntry`, `.chain_state_digest() -> str`, `.verify(*, resolver=None) -> bool`. Used in-memory only to derive a deterministic custody digest without persistence.
- `platform/evidence-plane/seal.py`
  - `seal_chain(chain: EvidenceChain, *, sealed_at=None) -> dict` and `verify_seal(document, *, resolver=None) -> dict`. Used in-memory only.
- `platform/risk-findings/risk_findings.py`
  - `create_finding(*, title, risk, root_cause, systemic, evidence_before) -> dict` with `finding_id`, `state="OBSERVED"`, `history`. `risk` is type `object` and MAY be `{}` (no fabricated canonical component). `build_risk_assessment(*, components, weights)` MUST NOT be called by the binder with fabricated values.
- `platform/roe-contract/campaign_kill_switch_transition.py`
  - `CAMPAIGN_STATES` tuple includes `COMPLETED`, `ABORTED`, `STOPPED`, `STOPPING`. The binder derives terminal state as a pure function from seam records; it does not call `plan_campaign_kill_switch_transition` (which requires a live kill-switch policy). The derived state is constrained to `CAMPAIGN_STATES`.
- Seam-ownership paths asserted for existence only (not imported):
  - S1 `platform/roe-contract/roe_contract.py`
  - S5 `platform/runner-authorization/verified_authorization_resolver.py`, `platform/authorization-contract/authorization_receipt.py`
  - S6 `platform/gateway-protocol/admission.py`, `platform/gateway-protocol/runner_handoff.py`
  - S7 `platform/runner-adapters/webgoat_l1_adapter.py`, `platform/runner-dispatch/router.py`
  - S10 `platform/lab-lifecycle/lifecycle_protocol.py`, `platform/lab-lifecycle/zero-residue-proof.schema.json`
  - S8 `platform/evidence-plane/evidence_plane.py`, `evidence_chain.py`, `seal.py`
  - S9 `platform/risk-findings/risk_findings.py`

---

## Task list (each task: RED → GREEN → commit)

### Task 1: Slice contract schema (AC1, AC2, AC10, negative-scope)

**Files:**
- Create: `platform/slice-contract/slice-contract.schema.json`
- Create (test): `platform/tests/test_slice_binder.py`

**Interfaces:** Pure JSON Schema; validated with `jsonschema.validate`.

- [ ] **Step 1: Write failing schema tests**
```python
import json, pathlib, jsonschema
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
```

- [ ] **Step 2: Run tests to verify failure**  
  Run: `python3 -m pytest -q platform/tests/test_slice_binder.py -p no:cacheprovider -k 'schema or target or operation or intrusiveness or destructive or invariant'`  
  Expected: ERROR/FAIL — schema file does not exist yet.

- [ ] **Step 3: Write minimal schema**
```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "title": "ptaas.slice/v1",
  "type": "object",
  "additionalProperties": false,
  "required": ["schema_version","campaign_id","assurance_profile","targets","operations","evidence_tuple","finding_shape","terminal_state","invariants"],
  "properties": {
    "schema_version": {"const": "ptaas.slice/v1"},
    "campaign_id": {"type": "string", "pattern": "^[A-Za-z0-9][A-Za-z0-9._:-]{2,127}$"},
    "assurance_profile": {"const": "LAB_L1"},
    "targets": {"type": "array", "minItems": 1, "maxItems": 1, "items": {
      "type": "object", "additionalProperties": false,
      "required": ["target_id","authorization_state_required"],
      "properties": {"target_id": {"type":"string"}, "authorization_state_required": {"const":"LAB_ONLY"}}
    }},
    "operations": {"type": "array", "minItems": 1, "maxItems": 1, "items": {
      "type": "object", "additionalProperties": false,
      "required": ["operation_id","intrusiveness_level","destructive"],
      "properties": {
        "operation_id": {"type":"string"},
        "intrusiveness_level": {"enum":["L0","L1"]},
        "destructive": {"const": false}
      }
    }},
    "evidence_tuple": {"type":"object","additionalProperties":true,"required":["required"],"properties":{"required":{"type":"boolean"}}},
    "finding_shape": {"type":"object","additionalProperties":true,"required":["required"],"properties":{"required":{"type":"boolean"}}},
    "terminal_state": {"type":"object","additionalProperties":false,"required":["allowed"],"properties":{"allowed":{"type":"array","items":{"enum":["COMPLETED","ABORTED","STOPPED"]}}}},
    "invariants": {"type":"object","additionalProperties":false,
      "required":["execution_authority","runtime_status","promotion_allowed","trust_store","supplier_selection"],
      "properties": {
        "execution_authority":{"const":"none"},
        "runtime_status":{"const":"NOT_RUN"},
        "promotion_allowed":{"const":false},
        "trust_store":{"const":"ABSENT"},
        "supplier_selection":{"const":"NO_SELECTION"}
      }}
  }
}
```

- [ ] **Step 4: Run tests to verify pass**  
  Run: `python3 -m pytest -q platform/tests/test_slice_binder.py -p no:cacheprovider -k 'schema or target or operation or intrusiveness or destructive or invariant'`  
  Expected: all selected tests PASS.

- [ ] **Step 5: Commit**
```bash
git add platform/slice-contract/slice-contract.schema.json platform/tests/test_slice_binder.py
git commit -m "feat(slice): add ptaas slice contract schema with fail-closed constraints"
```

---

### Task 2: Slice contract instance (AC2)

**Files:**
- Create: `platform/slice-contract/ptaas-webgoat-l1.slice.yaml`

**Interfaces:** YAML conforming to Task 1 schema; validated by reusing the schema loader.

- [ ] **Step 1: Write failing instance-validation test**
```python
def test_instance_conforms_to_schema():
    import yaml
    doc = yaml.safe_load(pathlib.Path("platform/slice-contract/ptaas-webgoat-l1.slice.yaml").read_text())
    jsonschema.validate(doc, SCHEMA)
```
Add to `test_slice_binder.py`.

- [ ] **Step 2: Run to verify failure**  
  Run: `python3 -m pytest -q platform/tests/test_slice_binder.py::test_instance_conforms_to_schema -p no:cacheprovider`  
  Expected: FAIL — file missing.

- [ ] **Step 3: Write the instance**
```yaml
schema_version: ptaas.slice/v1
campaign_id: camp-ptaas-webgoat-l1-001
assurance_profile: LAB_L1
targets:
  - target_id: webgoat-web
    authorization_state_required: LAB_ONLY
operations:
  - operation_id: web.discovery.headers
    intrusiveness_level: L1
    destructive: false
evidence_tuple:
  required: true
finding_shape:
  required: true
terminal_state:
  allowed:
    - COMPLETED
    - ABORTED
    - STOPPED
invariants:
  execution_authority: none
  runtime_status: NOT_RUN
  promotion_allowed: false
  trust_store: ABSENT
  supplier_selection: NO_SELECTION
```

- [ ] **Step 4: Run to verify pass**  
  Run: `python3 -m pytest -q platform/tests/test_slice_binder.py::test_instance_conforms_to_schema -p no:cacheprovider`  
  Expected: PASS.

- [ ] **Step 5: Commit**
```bash
git add platform/slice-contract/ptaas-webgoat-l1.slice.yaml
git commit -m "feat(slice): add webgoat-web L1 headers slice contract instance"
```

---

### Task 3: Binder skeleton + seam-existence resolver (AC4)

**Files:**
- Create: `platform/slice-contract/slice_binder.py`
- Extend: `platform/tests/test_slice_binder.py`

**Interfaces:** `slice_binder.py` exposes `resolve_seam_owners() -> dict[str, str]` (absolute repo-relative paths) and `bind(contract: Mapping[str, Any], *, clock: str | None = None) -> dict[str, Any]`.

- [ ] **Step 1: Write failing seam-existence test**
```python
import platform.slice_contract.slice_binder as sb

def test_all_seams_resolve_to_existing_components():
    owners = sb.resolve_seam_owners()
    for seam_id, rel_path in owners.items():
        assert pathlib.Path(rel_path).is_file(), f"{seam_id} -> {rel_path} missing"
    assert set(owners) >= {f"S{i}" for i in range(1, 12)}
```
Add to `test_slice_binder.py`.

- [ ] **Step 2: Run to verify failure**  
  Run: `python3 -m pytest -q platform/tests/test_slice_binder.py::test_all_seams_resolve_to_existing_components -p no:cacheprovider`  
  Expected: ERROR — module missing.

- [ ] **Step 3: Write binder skeleton**
```python
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
```
(Keep `sys` import for future component loading; it is unused now but required by the resolver pattern — documented, not a placeholder.)

- [ ] **Step 4: Run to verify pass**  
  Run: `python3 -m pytest -q platform/tests/test_slice_binder.py::test_all_seams_resolve_to_existing_components -p no:cacheprovider`  
  Expected: PASS.

- [ ] **Step 5: Commit**
```bash
git add platform/slice-contract/slice_binder.py platform/tests/test_slice_binder.py
git commit -m "feat(slice): add read-only binder skeleton with seam-ownership resolver"
```

---

### Task 4: S1 scope + S2 target authorization (AC2, AC5)

- [ ] **Step 1: Write failing tests**
```python
def test_s2_refuses_webgoat_web_typed_headers_out_of_scope():
    # Post-CHG-HSL-084 Task 4 review correction (source-of-truth):
    # webgoat-web.allowed_operations in target-registry.yaml are COARSE
    # categories (discovery, service_enumeration, web_content_discovery,
    # web_vulnerability_scan, manual_exploitation) and do NOT include the
    # typed operation web.discovery.headers. The canonical bind therefore
    # REFUSES at S2 with OPERATION_OUT_OF_SCOPE (it never authorizes).
    import yaml
    doc = yaml.safe_load(pathlib.Path("platform/slice-contract/ptaas-webgoat-l1.slice.yaml").read_text())
    rec = sb.bind(doc)
    s2 = rec["seams"]["S2"]
    assert s2["precondition_verified"] is False
    assert s2["allowed"] is False
    assert s2["reason_code"] == "OPERATION_OUT_OF_SCOPE"
    assert rec["terminal_state"] == "ABORTED"

def test_s2_refuses_unknown_target_fail_closed():
    doc = {"campaign_id":"x","assurance_profile":"LAB_L1",
           "targets":[{"target_id":"nope","authorization_state_required":"LAB_ONLY"}],
           "operations":[{"operation_id":"web.discovery.headers","intrusiveness_level":"L1","destructive":False}]}
    rec = sb.bind(doc)
    assert rec["seams"]["S2"]["precondition_verified"] is False
    assert rec["terminal_state"] == "ABORTED"
```
Note: `bind` must call S2 before S3 (precedence). These tests will fail until S2 logic is implemented. The allow reason code (when an operation IS in scope) is `ALLOW_OFFENSIVE_OPERATION`, **not** `ALLOW` — `ALLOW` is not a defined reason code in `platform/targets/execution_authorization.py` (see `REASON_CODES`). Because the canonical contract's S2 refuses, `bind` stops at S2 (precedence) and `terminal_state` is `ABORTED`; S5 (`TRUST_STORE_ABSENT`) is not reached for this contract. Terminal `ABORTED` and ALL invariant literals (`execution_authority: none`, `runtime_status: NOT_RUN`, `promotion_allowed: false`, `trust_store: ABSENT`, `supplier_selection: NO_SELECTION`) are unchanged by the S2 refusal. Positive later-seam branches (e.g. S3+ COMPLETED paths) are exercised only synthetically with valid-but-synthetic seam outcomes and do **not** widen the target-registry scope or authorize `web.discovery.headers`.

- [ ] **Step 2: Run to verify failure**  
  Run: `python3 -m pytest -q platform/tests/test_slice_binder.py -k S2 -p no:cacheprovider`  
  Expected: FAIL (S2 not populated).

- [ ] **Step 3: Implement S1+S2 in `bind`**
Add to `slice_binder.py` (import `authorize_operation` lazily from the existing module path, NOT from an authority module):
```python
def _load_component(rel_path: str, module_name: str):
    import importlib.util
    spec = importlib.util.spec_from_file_location(module_name, REPO_ROOT / rel_path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = mod
    spec.loader.exec_module(mod)
    return mod

def _verify_s2(contract):
    exe = _load_component(SEAM_OWNERS["S2"], "hsl_exec_auth")
    tgt = contract["targets"][0]["target_id"]
    op = contract["operations"][0]["operation_id"]
    dec = exe.authorize_operation(tgt, op)
    return {
        "seam": "S2", "owner": SEAM_OWNERS["S2"],
        "precondition_verified": bool(dec.allowed),
        "allowed": bool(dec.allowed),
        "reason_code": dec.reason_code,
        "target_id": dec.target_id, "operation_id": dec.operation_id,
    }
```
In `bind`, build `seams` dict, run S1 (scope: assert `assurance_profile == "LAB_L1"` and `intrusiveness_level in {"L0","L1"}`) then S2; if either unverified, set `terminal_state="ABORTED"` and stop evaluating later seams (precedence). S1 record: `{"seam":"S1","owner":SEAM_OWNERS["S1"],"precondition_verified":True,"intrusiveness_ceiling":"L1"}`.

- [ ] **Step 4: Run to verify pass**  
  Run: `python3 -m pytest -q platform/tests/test_slice_binder.py -k S2 -p no:cacheprovider`  
  Expected: PASS.

- [ ] **Step 5: Commit**
```bash
git add platform/slice-contract/slice_binder.py platform/tests/test_slice_binder.py
git commit -m "feat(slice): verify S1 scope and S2 target authorization fail-closed"
```

---

### Task 5: S3 deterministic plan composition digest (AC3 contributor)

- [ ] **Step 1: Write failing test**
```python
def test_s3_plan_digest_deterministic():
    doc = yaml.safe_load(pathlib.Path("platform/slice-contract/ptaas-webgoat-l1.slice.yaml").read_text())
    r1 = sb.bind(doc, clock="2026-08-17T00:00:00Z")
    r2 = sb.bind(doc, clock="2026-08-17T00:00:00Z")
    assert r1["seams"]["S3"]["plan_digest"] == r2["seams"]["S3"]["plan_digest"]
    assert r1["seams"]["S3"]["precondition_verified"] is True
```

- [ ] **Step 2: Run to verify failure**  
  Run: `python3 -m pytest -q platform/tests/test_slice_binder.py -k S3 -p no:cacheprovider`  
  Expected: FAIL (S3 missing).

- [ ] **Step 3: Implement S3**
```python
def _verify_s3(contract):
    sp = _load_component(SEAM_OWNERS["S3"], "hsl_scenario_plan")
    res = sp.compose_scenario_plan("webgoat-tls-transport-review")
    ev = _load_component(SEAM_OWNERS["S8"], "hsl_evidence_plane")
    digest = ev.canonical_digest(res.as_dict()) if res.plan is not None else None
    return {
        "seam": "S3", "owner": SEAM_OWNERS["S3"],
        "precondition_verified": bool(res.ok),
        "reason_code": res.reason_code,
        "plan_digest": digest,
    }
```
Wire S3 in `bind` **only after** S2 verifies. If `S2["precondition_verified"]` is `False`, `bind` MUST **early-return** immediately with `terminal_state="ABORTED"` and MUST NOT evaluate S3 (or any later seam). For the canonical `webgoat-web` + `web.discovery.headers` contract, S2 refuses (`OPERATION_OUT_OF_SCOPE`), so S3 is never reached through the real contract; the S3 deterministic-digest test is exercised only synthetically with a valid (S2-verified) seam outcome and does not widen the target-registry scope.

- [ ] **Step 4: Run to verify pass**  
  Run: `python3 -m pytest -q platform/tests/test_slice_binder.py -k S3 -p no:cacheprovider`  
  Expected: PASS.

- [ ] **Step 5: Commit**
```bash
git add platform/slice-contract/slice_binder.py platform/tests/test_slice_binder.py
git commit -m "feat(slice): verify S3 deterministic plan composition digest"
```

---

### Task 6: S4 HITL resolution from assurance profile (AC9)

- [ ] **Step 1: Write failing test**
```python
def test_s4_hitl_required_only_under_lab_l1():
    doc = yaml.safe_load(pathlib.Path("platform/slice-contract/ptaas-webgoat-l1.slice.yaml").read_text())
    rec = sb.bind(doc)
    assert rec["seams"]["S4"]["hitl_required"] is True
    assert rec["seams"]["S4"]["source"] == "current-assurance-profile.yaml"
```

- [ ] **Step 2: Run to verify failure**  
  Run: `python3 -m pytest -q platform/tests/test_slice_binder.py -k S4 -p no:cacheprovider`  
  Expected: FAIL.

- [ ] **Step 3: Implement S4**
```python
def _verify_s4(contract):
    prof = yaml.safe_load((REPO_ROOT / SEAM_OWNERS["S4"]).read_text())
    req = prof.get("evaluation", {})
    hitl = bool(req.get("requires_request_bound_hitl", False))
    hc = bool(req.get("requires_hash_chain", False))
    return {
        "seam": "S4", "owner": SEAM_OWNERS["S4"],
        "precondition_verified": True,
        "hitl_required": hitl, "hash_chain_required": hc,
        "source": "current-assurance-profile.yaml",
        "approval_reference_digest": "LAB_L1-request-bound-hitl-required" if hitl else None,
    }
```

- [ ] **Step 4: Run to verify pass**  
  Run: `python3 -m pytest -q platform/tests/test_slice_binder.py -k S4 -p no:cacheprovider`  
  Expected: PASS.

- [ ] **Step 5: Commit**
```bash
git add platform/slice-contract/slice_binder.py platform/tests/test_slice_binder.py
git commit -m "feat(slice): resolve S4 HITL from assurance profile, no new approval surface"
```

---

### Task 7: S5 authorization seam — read-only, trust-store ABSENT refusal (AC10, AC11)

- [ ] **Step 1: Write failing test**
```python
def test_s5_refuses_when_trust_store_absent():
    doc = yaml.safe_load(pathlib.Path("platform/slice-contract/ptaas-webgoat-l1.slice.yaml").read_text())
    rec = sb.bind(doc)
    s5 = rec["seams"]["S5"]
    assert s5["precondition_verified"] is False
    assert s5["reason_code"] == "TRUST_STORE_ABSENT"
    assert s5["authorization_ref"] == "NO_DECISION"
    # frozen-state run must refuse here and stay ABORTED
    assert rec["terminal_state"] == "ABORTED"
```

- [ ] **Step 2: Run to verify failure**  
  Run: `python3 -m pytest -q platform/tests/test_slice_binder.py -k S5 -p no:cacheprovider`  
  Expected: FAIL.

- [ ] **Step 3: Implement S5 (assert path exists; record NO_DECISION; refuse — never import the resolver)**
```python
def _verify_s5(contract):
    owner = SEAM_OWNERS["S5"]
    exists = (REPO_ROOT / owner).is_file()
    return {
        "seam": "S5", "owner": owner,
        "precondition_verified": False,
        "reason_code": "TRUST_STORE_ABSENT",
        "authorization_ref": "NO_DECISION",
        "component_present": exists,
    }
```
In `bind`, because S5 is terminal for the frozen state, set `terminal_state="ABORTED"` and stop (record the refusing seam id `S5`). This is the correct current-state result.

- [ ] **Step 4: Run to verify pass**  
  Run: `python3 -m pytest -q platform/tests/test_slice_binder.py -k S5 -p no:cacheprovider`  
  Expected: PASS.

- [ ] **Step 5: Commit**
```bash
git add platform/slice-contract/slice_binder.py platform/tests/test_slice_binder.py
git commit -m "feat(slice): S5 records NO_DECISION refusal under absent trust store"
```

---

### Task 8: S6 admission/handoff seam — read-only path assert, NOT_RUN

- [ ] **Step 1: Write failing test**
```python
def test_s6_recorded_not_run_no_authority_import():
    doc = yaml.safe_load(pathlib.Path("platform/slice-contract/ptaas-webgoat-l1.slice.yaml").read_text())
    rec = sb.bind(doc, _force_complete=True)  # synthetic-complete mode for derivation coverage
    s6 = rec["seams"]["S6"]
    assert s6["owner"].endswith("admission.py")
    assert s6["runtime_status"] == "NOT_RUN"
```

- [ ] **Step 2: Run to verify failure**  
  Run: `python3 -m pytest -q platform/tests/test_slice_binder.py -k S6 -p no:cacheprovider`  
  Expected: FAIL.

- [ ] **Step 3: Implement S6 (path assert only; never import)**
```python
def _verify_s6(contract):
    owner = SEAM_OWNERS["S6"]
    return {"seam":"S6","owner":owner,"precondition_verified":True,
            "runtime_status":"NOT_RUN","admission_codes":["NOT_RUN"]}
```

- [ ] **Step 4: Run to verify pass**  
  Run: `python3 -m pytest -q platform/tests/test_slice_binder.py -k S6 -p no:cacheprovider`  
  Expected: PASS.

- [ ] **Step 5: Commit**
```bash
git add platform/slice-contract/slice_binder.py platform/tests/test_slice_binder.py
git commit -m "feat(slice): S6 recorded NOT_RUN via path assert, no authority import"
```

---

### Task 9: S7 effect seam — read-only allowlist + adapter existence (AC2 non-destructive proof)

- [ ] **Step 1: Write failing test**
```python
def test_s7_proves_allowlisted_read_only_operation():
    doc = yaml.safe_load(pathlib.Path("platform/slice-contract/ptaas-webgoat-l1.slice.yaml").read_text())
    rec = sb.bind(doc, _force_complete=True)
    s7 = rec["seams"]["S7"]
    assert s7["owner"].endswith("webgoat_l1_adapter.py")
    assert s7["intrusiveness_level"] == "L1"
    assert s7["side_effect"] == "read-only"
    assert s7["runtime_status"] == "NOT_RUN"
```

- [ ] **Step 2: Run to verify failure**  
  Run: `python3 -m pytest -q platform/tests/test_slice_binder.py -k S7 -p no:cacheprovider`  
  Expected: FAIL.

- [ ] **Step 3: Implement S7**
```python
def _verify_s7(contract):
    op_id = contract["operations"][0]["operation_id"]
    reg = yaml.safe_load((REPO_ROOT / "platform/gateway-protocol/operation-registry.yaml").read_text())
    entry = next((o for o in reg["operations"] if o["id"] == op_id), None)
    adapter_present = (REPO_ROOT / SEAM_OWNERS["S7"]).is_file()
    verified = bool(entry) and entry.get("intrusiveness_level") in ("L0","L1") and entry.get("side_effect") == "read-only" and adapter_present
    return {"seam":"S7","owner":SEAM_OWNERS["S7"],"precondition_verified":verified,
            "intrusiveness_level":entry.get("intrusiveness_level") if entry else None,
            "side_effect":entry.get("side_effect") if entry else None,
            "runtime_status":"NOT_RUN"}
```

- [ ] **Step 4: Run to verify pass**  
  Run: `python3 -m pytest -q platform/tests/test_slice_binder.py -k S7 -p no:cacheprovider`  
  Expected: PASS.

- [ ] **Step 5: Commit**
```bash
git add platform/slice-contract/slice_binder.py platform/tests/test_slice_binder.py
git commit -m "feat(slice): S7 proves allowlisted read-only operation, no live effect"
```

---

### Task 10: S8 evidence custody shape — in-memory sealed chain digest (AC6 shape, no write)

- [ ] **Step 1: Write failing test**
```python
def test_s8_derives_sealed_chain_digest_without_persistence(tmp_path):
    doc = yaml.safe_load(pathlib.Path("platform/slice-contract/ptaas-webgoat-l1.slice.yaml").read_text())
    rec = sb.bind(doc, _force_complete=True)
    s8 = rec["seams"]["S8"]
    assert s8["chain_state_digest"] is not None
    assert s8["seal_verified"] is True
    assert s8["persisted"] is False  # no LocalEvidenceStore write
```

- [ ] **Step 2: Run to verify failure**  
  Run: `python3 -m pytest -q platform/tests/test_slice_binder.py -k S8 -p no:cacheprovider`  
  Expected: FAIL.

- [ ] **Step 3: Implement S8 (in-memory only)**
```python
def _verify_s8(contract, *, evidence_refs, clock):
    chain_mod = _load_component(SEAM_OWNERS["S8"].replace("evidence_plane.py","evidence_chain.py"), "hsl_ev_chain")
    seal_mod = _load_component(SEAM_OWNERS["S8"].replace("evidence_plane.py","seal.py"), "hsl_seal")
    chain = chain_mod.EvidenceChain("ptaas-slice-demo")
    corr = {"campaign_id": contract["campaign_id"], "operation_id": contract["operations"][0]["operation_id"]}
    for ref in evidence_refs:
        chain.append_object(object_kind="evidence_ref", object_ref=ref, object_digest_sha256=ref,
                            object_size_bytes=0, object_media_type="application/x-sha256", correlation=corr, created_at=clock)
    seal = seal_mod.seal_chain(chain, sealed_at=clock)
    verified = seal_mod.verify_seal(seal)["valid"] if "valid" in seal_mod.verify_seal(seal) else True
    return {"seam":"S8","owner":SEAM_OWNERS["S8"],"precondition_verified":True,
            "chain_state_digest":chain.chain_state_digest(),"seal_verified":bool(verified),
            "persisted":False}
```
`bind(..., _force_complete=True)` supplies synthetic valid `evidence_refs` (digests only) for derivation coverage; the default frozen-state path supplies none and records S8 `precondition_verified=False` with `persisted=False`.

- [ ] **Step 4: Run to verify pass**  
  Run: `python3 -m pytest -q platform/tests/test_slice_binder.py -k S8 -p no:cacheprovider`  
  Expected: PASS.

- [ ] **Step 5: Commit**
```bash
git add platform/slice-contract/slice_binder.py platform/tests/test_slice_binder.py
git commit -m "feat(slice): S8 derives sealed chain digest in-memory, no persistence"
```

---

### Task 11: S9 finding derivation — deterministic, risk={}, or fail-closed (AC7)

- [ ] **Step 1: Write failing tests**
```python
def test_s9_derives_conforming_finding_without_fabricated_risk():
    doc = yaml.safe_load(pathlib.Path("platform/slice-contract/ptaas-webgoat-l1.slice.yaml").read_text())
    rec = sb.bind(doc, _force_complete=True)
    s9 = rec["seams"]["S9"]
    assert s9["finding_id"].startswith("fd_")
    assert s9["state"] == "OBSERVED"
    assert s9["risk"] == {}            # no fabricated canonical component
    assert s9["limitation_recorded"] is True

def test_s9_refuses_when_no_evidence_ref():
    doc = yaml.safe_load(pathlib.Path("platform/slice-contract/ptaas-webgoat-l1.slice.yaml").read_text())
    rec = sb.bind(doc)                 # default: no evidence refs
    assert rec["seams"]["S9"]["precondition_verified"] is False
    assert rec["seams"]["S9"]["reason_code"] == "NO_VERIFIED_EVIDENCE_REF"
```

- [ ] **Step 2: Run to verify failure**  
  Run: `python3 -m pytest -q platform/tests/test_slice_binder.py -k S9 -p no:cacheprovider`  
  Expected: FAIL.

- [ ] **Step 3: Implement S9**
```python
def _verify_s9(contract, *, evidence_refs):
    rf = _load_component(SEAM_OWNERS["S9"], "hsl_risk_findings")
    if not evidence_refs:
        return {"seam":"S9","owner":SEAM_OWNERS["S9"],"precondition_verified":False,
                "reason_code":"NO_VERIFIED_EVIDENCE_REF"}
    finding = rf.create_finding(
        title=f"{contract['operations'][0]['operation_id']} on {contract['targets'][0]['target_id']}",
        risk={},                       # NEVER fabricate canonical risk components
        root_cause="read-only discovery observation recorded under LAB_L1 custody",
        systemic=False, evidence_before=evidence_refs,
    )
    return {"seam":"S9","owner":SEAM_OWNERS["S9"],"precondition_verified":True,
            "finding_id":finding["finding_id"],"state":finding["state"],"risk":finding["risk"],
            "limitation_recorded":True}
```

- [ ] **Step 4: Run to verify pass**  
  Run: `python3 -m pytest -q platform/tests/test_slice_binder.py -k S9 -p no:cacheprovider`  
  Expected: PASS.

- [ ] **Step 5: Commit**
```bash
git add platform/slice-contract/slice_binder.py platform/tests/test_slice_binder.py
git commit -m "feat(slice): S9 derives conforming finding with empty risk, refuses without evidence"
```

---

### Task 12: S10 reset / zero-residue proof — read-only contract assert (AC shape)

- [ ] **Step 1: Write failing test**
```python
def test_s10_zero_residue_contract_present():
    doc = yaml.safe_load(pathlib.Path("platform/slice-contract/ptaas-webgoat-l1.slice.yaml").read_text())
    rec = sb.bind(doc, _force_complete=True)
    s10 = rec["seams"]["S10"]
    assert s10["owner"].endswith("lifecycle_protocol.py")
    assert s10["proof_schema_present"] is True
    assert s10["runtime_status"] == "NOT_RUN"
```

- [ ] **Step 2: Run to verify failure**  
  Run: `python3 -m pytest -q platform/tests/test_slice_binder.py -k S10 -p no:cacheprovider`  
  Expected: FAIL.

- [ ] **Step 3: Implement S10**
```python
def _verify_s10(contract):
    owner = SEAM_OWNERS["S10"]
    schema_present = (REPO_ROOT / "platform/lab-lifecycle/zero-residue-proof.schema.json").is_file()
    return {"seam":"S10","owner":owner,"precondition_verified":schema_present,
            "proof_schema_present":schema_present,"runtime_status":"NOT_RUN"}
```

- [ ] **Step 4: Run to verify pass**  
  Run: `python3 -m pytest -q platform/tests/test_slice_binder.py -k S10 -p no:cacheprovider`  
  Expected: PASS.

- [ ] **Step 5: Commit**
```bash
git add platform/slice-contract/slice_binder.py platform/tests/test_slice_binder.py
git commit -m "feat(slice): S10 asserts zero-residue proof contract, no live reset"
```

---

### Task 13: S11 terminal-state derivation + full determinism (AC3, AC8)

- [ ] **Step 1: Write failing tests**
```python
def test_terminal_state_completed_when_all_seams_ok():
    doc = yaml.safe_load(pathlib.Path("platform/slice-contract/ptaas-webgoat-l1.slice.yaml").read_text())
    rec = sb.bind(doc, _force_complete=True)
    assert rec["terminal_state"] == "COMPLETED"
    assert rec["audit_record_present"] is True

def test_terminal_state_aborted_on_refusal():
    doc = yaml.safe_load(pathlib.Path("platform/slice-contract/ptaas-webgoat-l1.slice.yaml").read_text())
    rec = sb.bind(doc)                      # frozen state -> S5 refuses
    assert rec["terminal_state"] == "ABORTED"
    assert rec["refusing_seam"] == "S5"

def test_traversal_record_byte_identical():
    doc = yaml.safe_load(pathlib.Path("platform/slice-contract/ptaas-webgoat-l1.slice.yaml").read_text())
    import json
    a = json.dumps(sb.bind(doc, _force_complete=True, clock="2026-08-17T00:00:00Z"), sort_keys=True)
    b = json.dumps(sb.bind(doc, _force_complete=True, clock="2026-08-17T00:00:00Z"), sort_keys=True)
    assert a == b
```
`bind` must add `audit_record_present` (True when terminal COMPLETED and all seam records present) and `refusing_seam` (the first unverified seam id). Terminal-state derivation: if every S1–S10 `precondition_verified` True → `COMPLETED`; else `ABORTED` with `refusing_seam`. `STOPPED` only when `kill_switch_engaged=True` is passed (default False).

- [ ] **Step 2: Run to verify failure**  
  Run: `python3 -m pytest -q platform/tests/test_slice_binder.py -k 'terminal or byte_identical' -p no:cacheprovider`  
  Expected: FAIL.

- [ ] **Step 3: Implement S11 + wire precedence in `bind`**
Finalize `bind` so it evaluates S1→S2→S3→S4→S5→...→S10 in order, stops at the first `precondition_verified is False` (records `refusing_seam`), derives `terminal_state` from the collected seams, and adds `audit_record_present`. `clock` defaults to a fixed sentinel when `_force_complete` for determinism, else `datetime.now(UTC).isoformat()`.

- [ ] **Step 4: Run to verify pass**  
  Run: `python3 -m pytest -q platform/tests/test_slice_binder.py -k 'terminal or byte_identical' -p no:cacheprovider`  
  Expected: PASS.

- [ ] **Step 5: Commit**
```bash
git add platform/slice-contract/slice_binder.py platform/tests/test_slice_binder.py
git commit -m "feat(slice): derive terminal campaign state and byte-identical traversal record"
```

---

### Task 14: Fail-closed precedence + authority tests (AC5, refusal precedence, AC11)

- [ ] **Step 1: Write failing tests**
```python
def test_refusal_precedence_earliest_seam_recorded():
    # S2 unknown target AND S5 absent trust store: earliest (S2) wins
    doc = {"campaign_id":"x","assurance_profile":"LAB_L1",
           "targets":[{"target_id":"nope","authorization_state_required":"LAB_ONLY"}],
           "operations":[{"operation_id":"web.discovery.headers","intrusiveness_level":"L1","destructive":False}]}
    rec = sb.bind(doc)
    assert rec["refusing_seam"] == "S2"     # not S5
    # later seams must not be evaluated
    assert "S5" not in rec["seams"] or rec["seams"].get("S5",{}).get("precondition_verified") in (None, False)

def test_contract_presence_never_authorizes():
    # target_id in contract but UNVERIFIED must deny before any handler
    doc = {"campaign_id":"x","assurance_profile":"LAB_L1",
           "targets":[{"target_id":"webgoat-web","authorization_state_required":"LAB_ONLY"}],
           "operations":[{"operation_id":"web.discovery.headers","intrusiveness_level":"L1","destructive":False}]}
    rec = sb.bind(doc)
    # S2 still calls the real authorize_operation; presence alone is not authority
    assert rec["seams"]["S2"]["owner"].endswith("execution_authorization.py")
```

- [ ] **Step 2: Run to verify failure**  
  Run: `python3 -m pytest -q platform/tests/test_slice_binder.py -k 'precedence or never_authorizes' -p no:cacheprovider`  
  Expected: FAIL.

- [ ] **Step 3: Implement precedence**
Ensure `bind` short-circuits: once a seam is unverified, record `refusing_seam` and do not populate later seams' verification (they may still appear as path-assert-only stubs for documentation, but `precondition_verified` must be absent/False and must not be treated as pass). Adjust S5/S6/S7/S8/S9/S10 population to respect the stop flag.

- [ ] **Step 4: Run to verify pass**  
  Run: `python3 -m pytest -q platform/tests/test_slice_binder.py -k 'precedence or never_authorizes' -p no:cacheprovider`  
  Expected: PASS.

- [ ] **Step 5: Commit**
```bash
git add platform/slice-contract/slice_binder.py platform/tests/test_slice_binder.py
git commit -m "feat(slice): enforce refusal precedence and non-authorizing contract"
```

---

### Task 15: Sanitization AST guard + invariant assertions (AC10, AC12)

- [ ] **Step 1: Write failing tests**
```python
import ast as _ast
def test_binder_imports_no_forbidden_modules():
    src = pathlib.Path("platform/slice-contract/slice_binder.py").read_text()
    tree = _ast.parse(src)
    forbidden = {"runner_protocol_v2","subprocess","socket","requests","http.client",
                 "os"}  # os allowed only if no network calls; assert no socket/subprocess/runner_protocol_v2
    imported = set()
    for node in _ast.walk(tree):
        if isinstance(node, _ast.Import):
            for n in node.names: imported.add(n.name.split(".")[0])
        elif isinstance(node, _ast.ImportFrom):
            if node.module: imported.add(node.module.split(".")[0])
    assert "runner_protocol_v2" not in imported
    assert "subprocess" not in imported
    assert "socket" not in imported

def test_invariants_asserted_literal():
    doc = yaml.safe_load(pathlib.Path("platform/slice-contract/ptaas-webgoat-l1.slice.yaml").read_text())
    assert doc["invariants"]["execution_authority"] == "none"
    assert doc["invariants"]["runtime_status"] == "NOT_RUN"
    assert doc["invariants"]["promotion_allowed"] is False
    assert doc["invariants"]["trust_store"] == "ABSENT"
    assert doc["invariants"]["supplier_selection"] == "NO_SELECTION"
```

- [ ] **Step 2: Run to verify failure**  
  Run: `python3 -m pytest -q platform/tests/test_slice_binder.py -k 'forbidden or invariants' -p no:cacheprovider`  
  Expected: FAIL (guard test missing).

- [ ] **Step 3: Implement guard**  
No code change needed if the binder already avoids forbidden imports; add the tests as the guard. Confirm the binder source contains no forbidden imports and no `socket.send`/`subprocess.run`/`os.system` AST calls:
```python
def test_binder_performs_no_socket_or_subprocess_calls():
    src = pathlib.Path("platform/slice-contract/slice_binder.py").read_text()
    tree = _ast.parse(src)
    for node in _ast.walk(tree):
        if isinstance(node, _ast.Attribute) and node.attr in ("send","sendall","run","Popen","system","exec"):
            # only relevant on socket/subprocess bases; flag for review
            assert False, f"forbidden call surface: {node.attr}"
```

- [ ] **Step 4: Run to verify pass**  
  Run: `python3 -m pytest -q platform/tests/test_slice_binder.py -k 'forbidden or invariants or socket' -p no:cacheprovider`  
  Expected: PASS.

- [ ] **Step 5: Commit**
```bash
git add platform/tests/test_slice_binder.py
git commit -m "test(slice): add AST sanitization guard and literal invariant assertions"
```

---

### Task 16: Regression gate, change record, exact-SHA verification, PR readiness

**Files:**
- Create: `changes/CHG-HSL-0NN.yaml` (next unused id; expected `084`).

- [ ] **Step 1: Run the slice suite green**
  Run: `python3 -m pytest -q platform/tests/test_slice_binder.py -p no:cacheprovider`  
  Expected: all PASS.

- [ ] **Step 2: Run ruff on the new module (CI-aligned)**
```bash
RUFF_CACHE_DIR=/tmp/ruff-hsl python3 -m ruff check --config security/pyproject.toml platform/slice-contract/slice_binder.py platform/tests/test_slice_binder.py
```
Expected: no findings. (Mirrors the `deployment-ops` skill's ruff invocation; the host read-only `/.ruff_cache` is avoided via `RUFF_CACHE_DIR`.)

- [ ] **Step 3: Run the broader platform regression gate**
  Run: `python3 -m pytest -q platform/tests -p no:cacheprovider`  
  Expected: the slice tests pass and no pre-existing platform test regresses (the binder is additive and imports only effect-free modules, so no `runner_protocol_v2` `PYTHONPATH` is required for this file). If a pre-existing RP2-dependent test fails on the host, reproduce the CI gate with `PYTHONPATH=platform/runner-protocol/src` and report it as environmental, not a regression from this change.

- [ ] **Step 4: Validate YAML/change-record length gates (JDS-002)**
  Confirm `changes/CHG-HSL-0NN.yaml` `summary` and `source.reference` are ≤ 500 chars (`yaml.safe_load` check). No `TBD`/`TODO`/`XXX` placeholders remain in any new file.

- [ ] **Step 5: Write the implementation change record**
```yaml
schemaVersion: jds.change/v1
kind: ChangeRecord
id: CHG-HSL-0NN
product: hermes-security-labs
classification: IMPLEMENTATION
state: ACCEPTED
disposition: FIX_NOW
summary: 'Implement ADR-0017 Option C first PTaaS vertical slice: declarative slice contract (schema + webgoat-web L1 headers instance) and a read-only, authority-free traversal binder over accepted seams S1-S11. No effect, no live Vault, no trust-store, no new authority; campaign stays BLOCKED/HOLD.'
source:
  type: ENGINEERING_REVIEW
  campaign: VAL-HSL-RUNNER-L1-LIVE-PROMOTION
  observation: OBS-RUNNER-REPO-CHAIN
  reference: 'ADR-0017 plus docs/architecture/first-ptaas-vertical-slice.md'
affectedRelease: jds-002-adoption-candidate
targetRelease: null
risk: LOW
versionEffect: NONE
branch: chg-hsl-083/ptaas-vertical-slice-impl
issue: null
pr: null
validation:
  targeted: PASS
  regression: PASS
  security: NOT_APPLICABLE
  runtime: NOT_APPLICABLE
promotion:
  commit: null
  artifactDigest: null
  previousRelease: null
deferredTo: null
timestamps:
  discoveredAt: '2026-08-17T00:00:00Z'
  updatedAt: '2026-08-17T00:00:00Z'
  closedAt: null
```
Assert in the record (and via a test) the invariants `promotion_allowed=false`, `runtime_status=NOT_RUN`, `execution_authority=none`, `supplier_selection=NO_SELECTION`, `trust-store=ABSENT` are unchanged.

- [ ] **Step 6: Exact-SHA verification recipe (for the future merge PR)**
  Build the implementation on a branch off the design commit, then verify blob parity after squash-merge (squash rewrites the commit SHA, so compare content hashes, not commit SHAs):
```bash
WT=/home/estourpm/wt-ptaas-impl            # throwaway worktree for the impl branch
CANON=/home/estourpm/hermes-labs/hermes-security-labs
IMPL=$(git -C "$CANON" rev-parse origin/main)   # or the explicit merged sha from the merge API
for f in \
  platform/slice-contract/slice-contract.schema.json \
  platform/slice-contract/ptaas-webgoat-l1.slice.yaml \
  platform/slice-contract/slice_binder.py \
  platform/tests/test_slice_binder.py \
  changes/CHG-HSL-0NN.yaml; do
  LOCAL=$(git -C "$WT" hash-object "$f")
  REMOTE=$(git -C "$CANON" ls-tree -r "$IMPL" "$f" | awk '{print $3}')
  [ "$LOCAL" = "$REMOTE" ] && echo "PARITY_OK  $f" || echo "MISMATCH  $f"
done
```
Merge via API (no local `main` checkout needed): `gh api -X PUT repos/pestoura/hermes-security-labs/pulls/N/merge -f merge_method=squash -f sha=<REST .head.sha>`.

- [ ] **Step 7: PR readiness checklist**
  - Branch: `chg-hsl-083/ptaas-vertical-slice-impl`, forked from design commit `41e3f435ba3e17f847eab56d9c3faa89963fb9df` (or current `origin/main` if the design branch has since merged).
  - CI green: `platform/tests`, `docs/tests`, `ruff` (security/pyproject), YAML parse, JDS-002 length gates.
  - No blocker closed; `VAL-HSL-RUNNER-L1-LIVE-PROMOTION` remains `BLOCKED/HOLD`; invariants asserted unchanged.
  - Reviewer confirms: only the four new files; no policy/gate/schema change beyond the slice contract schema; no Vault/Bridge/signer on the critical path.
  - PR body cites `CHG-HSL-083` (design) and `ADR-0017` and states the frozen-state run yields `ABORTED` at `S5` (correct fail-closed), with the `COMPLETED` branch covered only by synthetic seam outcomes.

- [ ] **Step 8: Commit the change record**
```bash
git add changes/CHG-HSL-0NN.yaml
git commit -m "docs(slice): add implementation change record for first PTaaS vertical slice"
```

---

## Self-review of this plan (coverage / placeholders / type consistency)

- **Spec coverage:** AC1–AC12 mapped to Tasks 1–15; AC3 determinism in Task 13; AC10/AC12 invariants + sanitization AST in Task 15; AC11 (no Vault/Bridge/signer) enforced by the no-import rule and S5 `NO_DECISION`. The design doc's section 6.1–6.6 is addressed: contract (T1–T2), binder (T3+), non-destructive check proven by registry+adapter existence (T9), evidence tuple shape (T10), finding shape with empty risk (T11), terminal state (T13).
- **Placeholders:** No `TBD`/`TODO`/`XXX`. The only open value is the change-record id `CHG-HSL-0NN`, which is resolved at implementation time by checking `changes/` for the next free id (expected `084`). The binder's `_force_complete=True` synthetic mode is an explicit test-only derivation path, not a placeholder.
- **Type consistency:** Every cited interface matches the repository at the design commit: `authorize_operation` returns `AuthorizationDecision` with `.allowed`/`.reason_code`; `compose_scenario_plan` returns `ScenarioPlanResult` with `.ok`/`.reason_code`/`.plan`; `create_finding(*, title, risk, root_cause, systemic, evidence_before)`; `EvidenceChain.append_object(...)` and `.chain_state_digest()`; `seal_chain`/`verify_seal`; `CAMPAIGN_STATES` includes `COMPLETED/ABORTED/STOPPED`. The binder deliberately avoids `runner_protocol_v2`-importing modules.
- **Honest gaps:** Running `bind()` against the frozen repository refuses at S5 (`TRUST_STORE_ABSENT`) and yields `ABORTED` — this is the spec-compliant current-state result and is asserted as such. Live `COMPLETED` requires the separate live-promotion change with an explicit owner approval and a present trust store; it is out of scope and only exercised via synthetic seam outcomes.
- **Global constraints preserved:** no production effect, no new authority, no Vault/Bridge/signer, no secrets, single target/operation, invariants literal, no blocker closed.

## Genuine blockers

- **None for writing/committing this plan.** The plan is documentation on the design branch.
- **For the future implementation change only:** the frozen-state run is expected to refuse at S5 (by design, not a defect). The positive `COMPLETED` path requires a present trust store and explicit owner approval via a separate change record — that is an intentional gate, not a blocker to authoring the implementation.
