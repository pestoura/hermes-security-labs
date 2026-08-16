# Authorization Audit Evidence Custody Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Persist each sanitized `authorization-receipt-audit/v1` object through the existing Evidence Plane, verify its exact custody through the existing EvidenceVerifier contract, and bind the resulting canonical evidence ID into the existing authorization AuditSink/EvidenceChain without enabling runtime authorization or promotion.

**Architecture:** Add a dedicated disabled-by-default authorization-audit custody bridge that mirrors the already-accepted signer-audit custody pattern while keeping domain validation separate. The existing authorization AuditSink adapter retains `object_ref=evidence://authorization-receipt-audit/<payload_sha256>` as the object identity and gains an optional `evidence_ref=ev_<id>` custody binding, so AuditSink verification can independently resolve the exact persisted Evidence Plane object. The Evidence Plane store, LocalEvidenceVerifier, EvidenceChain and seal remain unchanged.

**Tech Stack:** Python 3, pytest, jsonschema Draft 2020-12, PyYAML, existing `platform/evidence-plane/evidence_plane.py`, `LocalEvidenceStore`, `LocalEvidenceVerifier`, `AuditSink`, GitHub Actions.

## Global Constraints

- Follow `ADR-0016` Option A; alternatives B/C/D remain non-selected/deferred/rejected as recorded there.
- Committed custody policy remains `DISABLED / deny / NOT_RUN / execution_authority=none`.
- Persist only the existing sanitized `authorization-receipt-audit/v1` JSON record.
- Never persist raw receipt JSON, raw authorization references, signatures, keys, targets, operation parameters, credentials, secrets, tokens, cookies, headers or backend exception text.
- Do not introduce a second datastore, EvidenceChain, seal or EvidenceVerifier.
- Preserve `object_ref=evidence://authorization-receipt-audit/<payload_sha256>` as object identity; use canonical `evidence_ref=ev_<32 lowercase hex>` only as the Evidence Plane custody binding.
- Do not enable receipt delivery/resolver policies, create an AF_UNIX endpoint, install trust, select/provision VAULT/KMS/HSM/PKCS11, dispatch Runner/Kali work or contact a target.
- Preserve `promotion_allowed=false`, `runtime_status=NOT_RUN`, `execution_authority=NONE` and campaign `BLOCKED/HOLD`.
- Strict TDD: tests-first RED must be observed for each new behavior before production implementation.
- Exact-SHA validation is mandatory on final PR head and post-merge main before declaring completion.

---

### Task 1: Reserve CHG-HSL-079 and create tests-first custody contract

**Files:**
- Create: `changes/CHG-HSL-079.yaml`
- Create: `platform/tests/test_authorization_audit_evidence_custody.py`
- Existing reference: `platform/tests/test_signer_audit_evidence_verifier.py`
- Existing contract: `platform/schemas/authorization-receipt-audit.schema.json`
- Existing audit builder: `platform/runner-authorization/authorization_audit_adapter.py`

**Interfaces:**
- Consumes: `build_authorization_audit_record(...)`, `authorization_audit_record_digest(record)`.
- Expects later task to produce: `AuthorizationAuditCustody`, `AuthorizationAuditCustodyError`, `AuthorizationAuditCustodyResult`, `EvidenceVerifierChainResolver`, `load_policy`, `validate_policy` in `platform/evidence-plane/authorization_audit_custody.py`.

- [ ] **Step 1: Add the change record without claiming implementation success**

Create `changes/CHG-HSL-079.yaml` with:

```yaml
schemaVersion: jds.change/v1
kind: ChangeRecord
id: CHG-HSL-079
product: hermes-security-labs
classification: HARDENING
state: IMPLEMENTING
disposition: FIX_NOW
summary: 'Persist sanitized TB1 authorization-decision audit records through the existing Evidence Plane and bind their verified custody to the canonical AuditSink/EvidenceChain without enabling runtime authorization or promotion.'
source:
  type: ENGINEERING_REVIEW
  campaign: VAL-HSL-RUNNER-L1-LIVE-PROMOTION
  observation: OBS-EVIDENCE-CUSTODY
  reference: 'Issue #416 / ADR-0016. Approved Option A: dedicated minimal authorization-audit custody bridge over the existing Evidence Plane. Runtime delivery, signer/trust, HITL and live effect remain separate blockers.'
affectedRelease: jds-002-adoption-candidate
targetRelease: null
risk: LOW
versionEffect: NONE
branch: chg-hsl-079/authorization-audit-evidence-custody
issue: 416
pr: null
validation:
  targeted: NOT_RUN
  regression: NOT_RUN
  security: NOT_RUN
  runtime: NOT_RUN
promotion:
  commit: null
  artifactDigest: null
  previousRelease: null
deferredTo: null
timestamps:
  discoveredAt: '2026-08-16T04:45:00Z'
  updatedAt: '2026-08-16T04:45:00Z'
  closedAt: null
```

- [ ] **Step 2: Write the failing custody tests**

Create `platform/tests/test_authorization_audit_evidence_custody.py` using the repository's dynamic import pattern. The first test set must require files that do not yet exist:

```python
ROOT = Path(__file__).resolve().parents[2]
RUNNER_AUTH = ROOT / "platform" / "runner-authorization"
EVIDENCE = ROOT / "platform" / "evidence-plane"
CUSTODY_PATH = EVIDENCE / "authorization_audit_custody.py"
POLICY_PATH = EVIDENCE / "authorization-audit-custody-policy.yaml"
ADAPTER_PATH = RUNNER_AUTH / "authorization_audit_adapter.py"
STORE_PATH = EVIDENCE / "local_store.py"
VERIFIER_PATH = EVIDENCE / "local_evidence_verifier.py"


def _load(path: Path, name: str) -> Any:
    assert path.exists(), f"{path.name} is not implemented yet"
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module
```

Build a canonical audit record only through the existing builder:

```python
def _event() -> dict[str, object]:
    adapter = _adapter()
    return adapter.build_authorization_audit_record(
        event_type="REGISTERED",
        phase="REGISTRATION",
        decision="ACCEPT",
        reason_code="RECEIPT_REGISTERED",
        authorization_ref="tb1-authz:v1:" + "a" * 64,
        duplicate=False,
        capability_id="web.discovery.headers",
        intrusiveness_level="L1",
    )


def _correlation() -> dict[str, str]:
    return {
        "campaign_id": "campaign-079",
        "run_id": "run-079",
        "step_id": "step-079",
        "attempt_id": "attempt-079",
    }
```

The initial tests must assert at least:

```python
def test_canonical_policy_is_disabled_and_fail_closed() -> None:
    custody = _custody()
    policy = custody.load_policy(POLICY_PATH)
    assert policy["state"] == "DISABLED"
    assert policy["default"] == "deny"
    assert policy["runtime_status"] == "NOT_RUN"
    assert policy["execution_authority"] == "none"
    assert policy["custody"]["classification"] == "restricted"
    assert policy["custody"]["include_raw_receipt"] is False
    assert policy["custody"]["include_raw_authorization_ref"] is False
    assert custody.validate_policy(policy) == []


def test_enabled_test_policy_projects_exact_sanitized_record(tmp_path: Path) -> None:
    custody = _custody()
    store = _store_module().LocalEvidenceStore(tmp_path / "evidence")
    event = _event()
    result = custody.AuthorizationAuditCustody(_enabled_policy()).persist(
        event,
        correlation=_correlation(),
        recorded_at="2026-08-16T04:50:00Z",
        evidence_store=store,
    )
    digest, size = _adapter().authorization_audit_record_digest(event)
    assert result.payload_sha256 == digest
    assert result.payload_size_bytes == size
    assert result.evidence_ref == f"evidence://{result.evidence_id}"
    assert store.verify(result.evidence_id) is True
```

Also require exact replay idempotency, LocalEvidenceVerifier intact/tamper behavior, invalid extra-field rejection before write, disabled policy failure, store write failure sanitization, store verify false/exception failure, exact storage ref `evidence://authorization-receipt-audit/<sha256>`, and absence of forbidden values in stored payload.

- [ ] **Step 3: Push tests and observe the required RED gate**

Open/update a draft PR if needed so GitHub Actions evaluates the branch. Run the focused suite through the repository's normal CI path. Expected RED reason:

```text
authorization_audit_custody.py is not implemented yet
```

or

```text
authorization-audit-custody-policy.yaml is not implemented yet
```

No unrelated test failure is acceptable as the RED evidence.

- [ ] **Step 4: Record the RED checkpoint**

Create `docs/superpowers/checkpoints/CHG-HSL-079-tests-first.md` containing exact branch head SHA, focused test command/job, failure count and confirmation that failures are limited to the intentionally absent custody contract.

- [ ] **Step 5: Commit the tests-first checkpoint**

```bash
git add changes/CHG-HSL-079.yaml platform/tests/test_authorization_audit_evidence_custody.py docs/superpowers/checkpoints/CHG-HSL-079-tests-first.md
git commit -m "test(chg-hsl-079): define authorization audit custody contract"
```

---

### Task 2: Implement the minimal Evidence Plane custody bridge

**Files:**
- Create: `platform/evidence-plane/authorization-audit-custody-policy.yaml`
- Create: `platform/evidence-plane/authorization_audit_custody.py`
- Test: `platform/tests/test_authorization_audit_evidence_custody.py`
- Reference: `platform/evidence-plane/signer_audit_custody.py`
- Reuse: `platform/evidence-plane/evidence_plane.py`

**Interfaces:**
- Produces:
  - `class AuthorizationAuditCustodyError(ValueError)` with `.code`.
  - `@dataclass(frozen=True) AuthorizationAuditCustodyResult` fields `evidence_id: str`, `evidence_ref: str`, `payload_sha256: str`, `payload_size_bytes: int`, `classification: str`.
  - `class EvidenceVerifierChainResolver` implementing the AuditSink resolver callable.
  - `validate_policy(document) -> list[str]`.
  - `load_policy(path=POLICY_PATH) -> dict[str, Any]`.
  - `AuthorizationAuditCustody(policy).persist(event, *, correlation, recorded_at, evidence_store) -> AuthorizationAuditCustodyResult`.

- [ ] **Step 1: Add the canonical disabled custody policy**

Create exactly:

```yaml
schema_version: '1.0'
policy_id: hexor.authorization.audit.custody
state: DISABLED
default: deny
runtime_status: NOT_RUN
execution_authority: none
custody:
  evidence_plane_projection: required
  classification: restricted
  retention_policy_id: default-30d
  retention_days: 30
  include_raw_receipt: false
  include_raw_authorization_ref: false
```

`validate_policy` must enforce exact top-level/custody fields, retention `1..3650`, and both sensitive-material flags exactly `false`.

- [ ] **Step 2: Implement schema-first validation and canonical payload construction**

Load `platform/schemas/authorization-receipt-audit.schema.json` with `jsonschema.Draft202012Validator` and reject before any store call. Canonical bytes must match the existing adapter digest function:

```python
def _canonical_bytes(value: Mapping[str, Any]) -> bytes:
    return json.dumps(
        dict(value), sort_keys=True, separators=(",", ":"), ensure_ascii=True
    ).encode("utf-8")
```

Use stable error codes:

```text
AUTHORIZATION_AUDIT_EVENT_INVALID
AUTHORIZATION_AUDIT_SCHEMA_UNAVAILABLE
AUTHORIZATION_AUDIT_TIMESTAMP_INVALID
AUTHORIZATION_AUDIT_CORRELATION_INVALID
POLICY_UNREADABLE
POLICY_INVALID
CUSTODY_DISABLED
EVIDENCE_STORE_UNAVAILABLE
EVIDENCE_PROJECTION_FAILED
EVIDENCE_VERIFICATION_FAILED
```

Backend messages must expose at most exception class, never the backend exception string.

- [ ] **Step 3: Implement canonical Evidence Plane projection**

Use only the existing injected `evidence_store.put(record, payload)` and `evidence_store.verify(evidence_id)`. Build the Evidence Plane record with:

```python
storage_ref = f"evidence://authorization-receipt-audit/{payload_sha256}"
record = evidence_contract.build_record(
    correlation=corr,
    classification=str(custody["classification"]),
    producer="authorization-receipt-audit-custody-v1",
    operation=f"authorization.audit.{validated['event_type']}",
    protocol_version=str(validated["schema_version"]),
    payload_sha256=payload_sha256,
    payload_size=len(payload),
    media_type="application/json",
    storage_ref=storage_ref,
    retention_policy_id=str(custody["retention_policy_id"]),
    retain_until=retain_until,
    legal_hold=False,
    metadata={
        "event_type": validated["event_type"],
        "phase": validated["phase"],
        "decision": validated["decision"],
        "reason_code": validated["reason_code"],
        "authorization_ref_sha256": validated["authorization_ref_sha256"],
        "duplicate": validated["duplicate"],
        "capability_id": validated["capability_id"],
        "intrusiveness_level": validated["intrusiveness_level"],
        "promotion_allowed": False,
        "runtime_status": "NOT_RUN",
        "execution_authority": "NONE",
    },
    created_at=recorded_at,
)
```

Return:

```python
AuthorizationAuditCustodyResult(
    evidence_id=str(evidence_id),
    evidence_ref=f"evidence://{evidence_id}",
    payload_sha256=payload_sha256,
    payload_size_bytes=len(payload),
    classification=str(custody["classification"]),
)
```

- [ ] **Step 4: Implement the verifier-to-chain interface adapter**

Mirror the existing fail-closed `EvidenceVerifierChainResolver`: validate `object_ref`, 64-char digest and non-negative integer size, call only `verifier.verify(object_ref, digest)`, return `False` on any exception. Do not implement verification logic here.

- [ ] **Step 5: Run focused tests and require GREEN**

Run:

```bash
pytest -q platform/tests/test_authorization_audit_evidence_custody.py
```

Expected: all Task 1 custody tests PASS.

- [ ] **Step 6: Run immediate Evidence Plane regression**

Run:

```bash
pytest -q platform/tests/test_signer_audit_evidence_verifier.py platform/tests/test_authorization_audit_evidence_custody.py
```

Expected: both existing signer custody and new authorization custody suites PASS.

- [ ] **Step 7: Commit minimal GREEN**

```bash
git add platform/evidence-plane/authorization-audit-custody-policy.yaml platform/evidence-plane/authorization_audit_custody.py platform/tests/test_authorization_audit_evidence_custody.py
git commit -m "feat(chg-hsl-079): persist authorization audit evidence"
```

---

### Task 3: Bind verified custody to the existing authorization AuditSink

**Files:**
- Modify: `platform/runner-authorization/authorization_audit_adapter.py`
- Create/extend: `platform/tests/test_authorization_audit_custody_integration.py`
- Reuse: `platform/evidence-plane/authorization_audit_custody.py`
- Reuse: `platform/evidence-plane/local_evidence_verifier.py`

**Interfaces:**
- Existing `record_event(...) -> dict[str, object]` remains source compatible for callers with no custody configured.
- Add optional constructor dependencies rather than caller-controlled evidence flags:

```python
CanonicalAuthorizationAuditAdapter(
    *,
    chain_id: str,
    custody: Any | None = None,
    evidence_store: Any | None = None,
    recorded_at_provider: Callable[[], str] | None = None,
)
```

- When custody is configured, derive Evidence Plane correlation from trusted `AuthorizationAuditContext` only: campaign/run/step/attempt. Never derive it from receipt/event payload.

- [ ] **Step 1: Write integration tests first**

Create tests requiring this behavior:

```python
def test_custodied_event_binds_exact_evidence_id_into_audit_sink(tmp_path: Path) -> None:
    custody = _enabled_custody()
    store = LocalEvidenceStore(tmp_path / "evidence")
    adapter = CanonicalAuthorizationAuditAdapter(
        chain_id="chain_" + "9" * 32,
        custody=custody,
        evidence_store=store,
        recorded_at_provider=lambda: "2026-08-16T05:00:00Z",
    )
    record = adapter.record_event(...)
    digest, size = authorization_audit_record_digest(record)
    sealed = adapter.seal(sealed_at="2026-08-16T05:01:00Z")
    entry = sealed["entries"][0]
    assert entry["object_ref"] == f"evidence://authorization-receipt-audit/{digest}"
    assert entry["object_digest_sha256"] == digest
    assert entry["object_size_bytes"] == size
    assert re.fullmatch(r"ev_[a-f0-9]{32}", entry["evidence_ref"])
```

Also require:

- LocalEvidenceVerifier + `EvidenceVerifierChainResolver` makes `adapter.verify(resolver=...)` PASS intact and FAIL after object tamper;
- custody failure creates **no AuditSink append** (`adapter.length == 0`);
- custody ref/digest/size mismatch fails before AuditSink append;
- exact duplicate creates one Evidence Plane record and one AuditSink entry;
- no-custody constructor preserves CHG-HSL-078 behavior and existing tests;
- trusted custody correlation equals context campaign/run/step/attempt and cannot be supplied through the event.

- [ ] **Step 2: Run integration tests and observe RED**

Run:

```bash
pytest -q platform/tests/test_authorization_audit_custody_integration.py
```

Expected RED: constructor rejects the new optional custody arguments or AuditSink entry lacks the expected `evidence_ref`. Existing CHG-HSL-078 tests must remain GREEN at this point.

- [ ] **Step 3: Add canonical evidence-ref normalization**

Reuse the signer adapter pattern locally in the authorization adapter:

```python
_EVIDENCE_ID = re.compile(r"^ev_[a-f0-9]{32}$")
_EVIDENCE_URI = re.compile(r"^evidence://(ev_[a-f0-9]{32})$")


def _canonical_evidence_id(evidence_ref: object) -> str | None:
    if evidence_ref is None:
        return None
    if isinstance(evidence_ref, str) and _EVIDENCE_ID.fullmatch(evidence_ref):
        return evidence_ref
    if isinstance(evidence_ref, str):
        match = _EVIDENCE_URI.fullmatch(evidence_ref)
        if match:
            return match.group(1)
    raise AuthorizationAuditError(
        "AUTHORIZATION_AUDIT_EVIDENCE_REF_INVALID",
        "evidence_ref must be ev_<32 lowercase hex> or evidence://ev_<32 lowercase hex>",
    )
```

The caller must never pass `evidence_ref` into `record_event`; it is obtained only from the injected custody bridge.

- [ ] **Step 4: Persist/verify before AuditSink append when custody is configured**

After building the sanitized record and before `AuditSink.append`:

```python
bound_evidence_id = None
if self._custody is not None:
    if self._evidence_store is None:
        raise AuthorizationAuditError(
            "AUTHORIZATION_AUDIT_CUSTODY_UNAVAILABLE",
            "authorization audit custody requires the canonical Evidence Plane store",
        )
    persisted = self._custody.persist(
        record,
        correlation={
            "campaign_id": normalized_context.campaign_id,
            "run_id": normalized_context.run_id,
            "step_id": normalized_context.step_id,
            "attempt_id": normalized_context.attempt_id,
        },
        recorded_at=self._recorded_at_provider(),
        evidence_store=self._evidence_store,
    )
    if persisted.payload_sha256 != digest or persisted.payload_size_bytes != size:
        raise AuthorizationAuditError(
            "AUTHORIZATION_AUDIT_CUSTODY_MISMATCH",
            "persisted authorization audit identity does not match the canonical record",
        )
    expected_storage_ref = f"evidence://authorization-receipt-audit/{digest}"
    bound_evidence_id = _canonical_evidence_id(persisted.evidence_ref)
```

Then append:

```python
self._sink.append(
    object_kind="evidence_record",
    object_ref=f"evidence://authorization-receipt-audit/{digest}",
    object_digest_sha256=digest,
    object_size_bytes=size,
    object_media_type="application/json",
    context=audit_context,
    evidence_ref=bound_evidence_id,
)
```

Do not cache `_emitted[identity]` until custody and AuditSink append both succeed.

If custody succeeds but AuditSink append fails, do **not** delete the immutable Evidence Plane object. A retry reuses the same content-addressed object and may complete the chain append; this is fail-closed and preserves evidence rather than mutating history.

- [ ] **Step 5: Run focused integration + CHG-HSL-078 regressions**

Run:

```bash
pytest -q \
  platform/tests/test_authorization_audit_custody_integration.py \
  platform/tests/test_authorization_receipt_audit_adapter.py \
  platform/tests/test_authorization_receipt_audit_integration.py \
  platform/tests/test_authorization_receipt_audit_review_hardening.py
```

Expected: all PASS.

- [ ] **Step 6: Commit custody binding**

```bash
git add platform/runner-authorization/authorization_audit_adapter.py platform/tests/test_authorization_audit_custody_integration.py
git commit -m "feat(chg-hsl-079): bind authorization audit custody"
```

---

### Task 4: Adversarial hardening and invariant proof

**Files:**
- Create: `platform/tests/test_authorization_audit_custody_review_hardening.py`
- Modify only if RED proves a real defect: `platform/evidence-plane/authorization_audit_custody.py`
- Modify only if RED proves a real defect: `platform/runner-authorization/authorization_audit_adapter.py`

**Interfaces:**
- No new public authority surfaces.
- Stable failures remain bounded and sanitized.

- [ ] **Step 1: Add review-hardening tests first**

Require at least these adversarial cases:

```python
@pytest.mark.parametrize("forbidden", [
    "receipt",
    "receipt_json",
    "signature_b64",
    "authorization_ref",
    "target",
    "parameters",
    "credential",
    "secret",
    "token",
    "cookie",
    "headers",
])
def test_closed_schema_refuses_sensitive_extra_fields_before_write(forbidden, tmp_path):
    ...
```

Also test:

- malformed/uppercase/non-canonical `evidence_ref` from a fake custody object;
- fake custody returns correct ref but wrong digest;
- fake custody returns correct digest but wrong size;
- fake custody raises an exception containing `/secret/path/token`; public adapter exception must not expose that string;
- store `put()` raises secret-bearing exception; custody error leaks only exception type;
- store `verify()` returns false or raises;
- verifier throws; chain resolver returns false;
- boolean `object_size_bytes` is rejected even though `bool` subclasses `int`;
- policy unknown/missing fields are rejected;
- invalid timestamp/correlation fails before write;
- exact replay after an AuditSink append failure reuses one content-addressed Evidence Plane object and creates one final chain entry after successful retry;
- `promotion_allowed`, `runtime_status`, `execution_authority` cannot be changed through custody metadata.

- [ ] **Step 2: Run and observe RED only for real uncovered gaps**

Run:

```bash
pytest -q platform/tests/test_authorization_audit_custody_review_hardening.py
```

If all tests are already GREEN, record that no production hardening was necessary. If RED appears, each failure must map to a concrete security invariant above; unrelated failures stop the lane for diagnosis.

- [ ] **Step 3: Apply the minimum hardening required by observed RED**

Examples of permitted fixes:

```python
except Exception as exc:  # noqa: BLE001
    raise AuthorizationAuditCustodyError(
        "EVIDENCE_PROJECTION_FAILED",
        f"Evidence Plane authorization-audit projection failed safely: {type(exc).__name__}",
    ) from exc
```

and wrapper sanitization in the authorization adapter:

```python
except Exception as exc:  # noqa: BLE001
    raise AuthorizationAuditError(
        "AUTHORIZATION_AUDIT_CUSTODY_FAILED",
        f"authorization audit custody failed safely: {type(exc).__name__}",
    ) from exc
```

Do not weaken schemas, exact-field policies or fail-closed behavior to make tests pass.

- [ ] **Step 4: Re-run focused hardening and all CHG-HSL-079 tests**

Run:

```bash
pytest -q \
  platform/tests/test_authorization_audit_evidence_custody.py \
  platform/tests/test_authorization_audit_custody_integration.py \
  platform/tests/test_authorization_audit_custody_review_hardening.py
```

Expected: PASS.

- [ ] **Step 5: Commit hardening only if code/tests changed**

```bash
git add platform/tests/test_authorization_audit_custody_review_hardening.py platform/evidence-plane/authorization_audit_custody.py platform/runner-authorization/authorization_audit_adapter.py
git commit -m "test(chg-hsl-079): harden authorization audit custody"
```

---

### Task 5: Governance and documentation reconciliation

**Files:**
- Modify: `docs/architecture/adr/README.md`
- Create: `docs/architecture/authorization-audit-evidence-custody.md`
- Modify: `platform/runner-authorization/README.md`
- Modify: `changes/CHG-HSL-079.yaml`
- Existing: `docs/architecture/adr/ADR-0016-authorization-audit-evidence-custody.md`
- Existing: `docs/superpowers/specs/2026-08-16-authorization-audit-evidence-custody-design.md`

**Interfaces:**
- Documentation must describe repository acceptance only; no runtime/live claim.

- [ ] **Step 1: Add ADR-0016 to the canonical ADR index**

Add a table row:

```markdown
| [ADR-0016](ADR-0016-authorization-audit-evidence-custody.md) | Use a dedicated minimal Evidence Plane custody bridge for sanitized authorization-decision audit objects and bind verified custody to the canonical AuditSink/EvidenceChain | Accepted | authorization audit evidence custody |
```

Add structural-decision coverage for the same decision without changing prior ADR dispositions.

- [ ] **Step 2: Add concise architecture/runbook documentation**

`docs/architecture/authorization-audit-evidence-custody.md` must document:

- sanitized record -> custody -> LocalEvidenceStore -> LocalEvidenceVerifier -> AuditSink/EvidenceChain flow;
- distinction between `object_ref=evidence://authorization-receipt-audit/<sha256>` and `evidence_ref=ev_<id>`;
- disabled committed policy;
- replay/idempotency behavior;
- failure semantics;
- explicit runtime non-claims.

- [ ] **Step 3: Update Runner authorization README**

State that repository support now includes optional Evidence Plane custody for authorization-decision audit records, but live persistence is not claimed until an enabled runtime composition is observed and verified. Preserve delivery/resolver policy `DISABLED/NOT_RUN` statements.

- [ ] **Step 4: Keep change record in IMPLEMENTING until exact-head CI is GREEN**

Update `source.reference` with the draft PR number once created, but do not set `state: ACCEPTED` or validation PASS values yet.

- [ ] **Step 5: Run documentation/source-of-truth tests**

Run the repository's canonical docs and source-of-truth gates, including:

```bash
pytest -q docs/tests
python3 platform/scripts/jds_static_gate.py
python3 platform/scripts/validate_source_of_truth.py
python3 security/tools/securityctl.py validate
```

Expected: all PASS / zero security warnings according to current repository baseline.

- [ ] **Step 6: Commit governance reconciliation**

```bash
git add docs/architecture/adr/README.md docs/architecture/authorization-audit-evidence-custody.md platform/runner-authorization/README.md changes/CHG-HSL-079.yaml
git commit -m "docs(chg-hsl-079): reconcile authorization audit custody"
```

---

### Task 6: Full verification, review and exact-SHA promotion of the repository change

**Files:**
- Modify after successful verification: `changes/CHG-HSL-079.yaml`
- Modify if required: draft PR body/checkpoints only

**Interfaces:**
- No code changes are permitted in this task unless a verification failure is first reproduced and returned to the relevant TDD task.

- [ ] **Step 1: Run full local/source-of-truth regression**

Run the repository's canonical full suites, at minimum:

```bash
pytest -q platform/tests
pytest -q deployment/tests
pytest -q docs/tests
pytest -q security/tests
python3 platform/scripts/jds_static_gate.py
python3 platform/scripts/validate_source_of_truth.py
python3 security/tools/securityctl.py validate
```

Also run any standard repository aggregate target used by CI (`make validate` / equivalent) and lint/static gates covering changed Python files.

- [ ] **Step 2: Perform static security review against ADR-0016**

Verify manually from the diff:

```text
[ ] no new datastore implementation
[ ] no second EvidenceChain/seal/verifier
[ ] no raw authorization_ref persisted
[ ] no receipt/signature/key/target/params/credentials/secrets
[ ] custody dependency is injected
[ ] committed policy remains DISABLED/NOT_RUN
[ ] no socket/runtime/policy enablement
[ ] object_ref and evidence_ref semantics remain distinct
[ ] positive path fails closed on required custody failure
[ ] denial remains denial
[ ] exact replay is idempotent
[ ] no promotion/runtime authority introduced
```

Any gap creates a new tests-first hardening cycle before proceeding.

- [ ] **Step 3: Update CHG-HSL-079 to candidate PASS only after local gates pass**

Set:

```yaml
state: ACCEPTED
validation:
  targeted: PASS
  regression: PASS
  security: PASS
  runtime: NOT_RUN
```

Set `pr` to the actual PR number and `timestamps.updatedAt` to the verification time. Keep `promotion.commit: null`, no artifact digest, no runtime claim.

- [ ] **Step 4: Push final candidate head and require exact-head CI GREEN**

Required GitHub checks:

```text
validate
security
Release governance
Private VAmPI source-repo access deny
Exact-SHA validation evidence
```

Fetch the workflow runs for the exact final head SHA. Do not infer success from an older commit or branch status.

- [ ] **Step 5: Review PR diff after CI**

Confirm no unexpected files, no secrets, no generated runtime evidence, and no authority/promotion changes. If CI or review finds an issue, return to the relevant RED -> fix -> GREEN task and obtain a new exact-head CI result.

- [ ] **Step 6: Merge only after exact-head GREEN**

Use squash merge with expected final head SHA. The merge message must describe repository-only authorization audit custody and preserve runtime HOLD/non-authority boundaries.

- [ ] **Step 7: Verify post-merge main exact SHA**

Fetch new `main` SHA and require fresh post-merge repository checks. Do not mark CHG-HSL-079 complete from PR CI alone.

- [ ] **Step 8: Reconcile issue #416 only after post-merge GREEN**

Close issue #416 as completed with exact merged main SHA and evidence of post-merge gates. State explicitly that this closes only repository custody/verifier linkage and does not close signer/trust, receipt-delivery, live runtime persistence, HITL, live effect or POST_EFFECT gates.

---

## Plan self-review

- **Spec coverage:** policy, schema-first validation, content addressing, post-write verify, LocalEvidenceVerifier linkage, AuditSink evidence binding, idempotency, tamper, backend failure sanitization, data minimization, backwards compatibility, governance and exact-SHA gates are each mapped to explicit tasks.
- **Authority boundary:** no task enables runtime, trust, provider, socket, Runner, Kali or target effect.
- **Type consistency:** custody result fields used by Tasks 2-4 are defined once as `evidence_id`, `evidence_ref`, `payload_sha256`, `payload_size_bytes`, `classification`.
- **Reference semantics:** `object_ref` remains content identity; `evidence_ref` is the Evidence Plane record ID binding.
- **No placeholders:** implementation steps contain exact target files, interfaces, error codes, commands and acceptance outcomes.
