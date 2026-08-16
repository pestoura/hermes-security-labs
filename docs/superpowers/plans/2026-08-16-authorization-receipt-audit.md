# Authorization Receipt Audit Evidence Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add repository-only, fail-closed audit evidence for TB1 authorization receipt registration, lookup and refusal decisions without enabling receipt delivery, trust, signing, Runner execution or promotion.

**Architecture:** Introduce one dedicated authorization audit adapter that builds a closed public event and appends it to the existing canonical LAB_L1 `AuditSink` / EvidenceChain. Integrate it as an optional observer in `TrustedReceiptDelivery` and `VerifiedAuthorizationResolver`; when configured, audit availability becomes part of authorization success, while denial paths remain denial even if refusal auditing fails. The WebGoat L1 adapter supplies trusted request correlation for resolver lookups.

**Tech Stack:** Python 3, pytest, JSON Schema Draft 2020-12, existing `platform/evidence-plane/audit_sink.py`, existing TB1 authorization receipt/resolver/delivery contracts, GitHub Actions repository gates.

## Global Constraints

- `receipt-delivery-policy.yaml` remains `DISABLED / deny / NOT_RUN / execution_authority=none`.
- `resolver-policy.yaml` remains `DISABLED / deny / NOT_RUN / execution_authority=none`.
- #403 remains `NO_DECISION / NO_SELECTION`.
- No Vault/KMS/HSM/PKCS11 provider selection or call.
- No trust-store installation or key provisioning.
- No socket creation, service restart, Docker/network mutation or target effect.
- No raw receipt, signature/base64, public/private key material, raw target, raw operation parameters, credentials, secrets, tokens, cookies or headers in audit records.
- Canonical authorization references are represented in the public event only by lowercase SHA-256; malformed/unbounded references are recorded as `null`.
- Duplicate delivery of the same sequence remains idempotent and does not append a second registration audit event.
- Reuse the existing `AuditSink` / EvidenceChain; no second ledger, chain, seal, datastore or verifier.
- `promotion_allowed=false`, `runtime_status=NOT_RUN`, `execution_authority=NONE` remain mechanically locked in every public audit event.

---

### Task 1: Canonical ADR for authorization receipt audit coverage

**Files:**
- Create: `docs/architecture/adr/ADR-0015-authorization-receipt-audit-evidence.md`
- Modify: `docs/architecture/adr/README.md`

**Interfaces:**
- Consumes: approved CHG-HSL-078 design spec.
- Produces: accepted architectural record preserving Option 1/2/3 dispositions and review triggers.

- [ ] **Step 1: Add ADR-0015**

Record:
- Selected: registration + lookup + refusal auditing through a dedicated adapter feeding canonical AuditSink/EvidenceChain.
- Not selected for MVP: registration-only.
- Not selected for MVP: registration + lookup without refusal evidence.
- Consequences: more complete negative-path traceability, small integration coupling, audit becomes part of success boundary only when observer is configured.
- Review triggers: durable/WORM sink, multiple adapters, generic policy-decision framework, privacy/retention changes, live LAB_L1 promotion, multi-tenant PROD.

- [ ] **Step 2: Update ADR index and structural-decision coverage**

Add ADR-0015 to the decision index and map the new structural principle: authorization registration/lookup/refusal decisions are auditable through a dedicated domain adapter over canonical AuditSink.

- [ ] **Step 3: Run documentation/ADR contract tests through CI**

Expected: ADR/documentation gates GREEN; no production code has changed yet.

---

### Task 2: Closed public authorization audit event and adapter contract — TDD RED

**Files:**
- Create: `platform/schemas/authorization-receipt-audit.schema.json`
- Create later: `platform/runner-authorization/authorization_audit_adapter.py`
- Create tests first: `platform/tests/test_authorization_receipt_audit_adapter.py`

**Interfaces:**
- Produces: `AuthorizationAuditContext`, `AuthorizationAuditError`, `build_authorization_audit_record()`, `CanonicalAuthorizationAuditAdapter.record_event()`, `seal()`, `verify()`.
- Consumes: existing `AuditSink`, `AuditContext`.

Public event schema:

```text
schema_version = authorization-receipt-audit/v1
event_type = REGISTERED | LOOKUP_HIT | LOOKUP_MISS | LOOKUP_EXPIRED | REFUSED
phase = DELIVERY | REGISTRATION | LOOKUP
decision = ACCEPT | DENY
reason_code = bounded SAFE_ID string
authorization_ref_sha256 = lowercase SHA-256 | null
duplicate = boolean
capability_id = bounded public string | null
intrusiveness_level = bounded public string | null
promotion_allowed = false
runtime_status = NOT_RUN
execution_authority = NONE
```

- [ ] **Step 1: Write tests before implementation**

Cover:
- exact closed schema / `additionalProperties=false`;
- valid event matrix;
- invalid event/phase/decision combinations rejected;
- canonical authorization ref hashes correctly;
- malformed/unbounded reference produces `null` rather than persistence of raw input;
- stable reason codes only;
- capability/intrusiveness accepted only from verified metadata inputs;
- serialized record contains no forbidden fields/material;
- deterministic content digest/size;
- AuditSink receives object ref `evidence://authorization-receipt-audit/<event-sha256>`;
- event carries no execution/promotion authority;
- source has no runtime/provider/network/subprocess dependencies.

- [ ] **Step 2: Commit tests-only head and run CI**

Expected: clean RED because `authorization_audit_adapter.py` and/or schema implementation is absent; unrelated suites remain GREEN.

- [ ] **Step 3: Implement the minimal adapter and schema**

`AuthorizationAuditContext` fields:

```python
campaign_id: str
run_id: str
step_id: str
attempt_id: str
principal: str
correlation_id: str
```

`build_authorization_audit_record(...)` accepts only bounded enum/state inputs plus an optional canonical authorization ref and optional already-verified capability/intrusiveness metadata.

`CanonicalAuthorizationAuditAdapter.record_event(...)`:
- builds deterministic record;
- computes canonical JSON SHA-256 + size;
- creates `AuditContext` from trusted `AuthorizationAuditContext`;
- maps ACCEPT -> `recorded`, DENY -> `denied`;
- appends exactly once to existing `AuditSink` with `object_kind=evidence_record`, `object_media_type=application/json`, `object_ref=evidence://authorization-receipt-audit/<sha256>`;
- never persists raw authorization refs.

- [ ] **Step 4: Run adapter tests and full repository suite**

Expected: targeted tests GREEN, then full `platform/tests` GREEN.

---

### Task 3: Resolver lookup auditing — TDD

**Files:**
- Modify: `platform/runner-authorization/verified_authorization_resolver.py`
- Modify/create tests: existing resolver tests and `platform/tests/test_authorization_receipt_audit_integration.py`

**Interfaces:**
- `VerifiedAuthorizationResolver(policy, audit_observer=None)`.
- `resolve(authorization_ref, *, audit_context=None)` remains backward compatible when no observer is configured.
- Observer contract: `record_event(event_type=..., phase=..., decision=..., reason_code=..., authorization_ref=..., context=..., verified_authorization=..., duplicate=False)`.

- [ ] **Step 1: Write failing resolver integration tests**

Cover:
- no observer => legacy behavior unchanged;
- configured observer + missing trusted context => fail closed for a would-be hit;
- live cache hit => `LOOKUP_HIT / LOOKUP / ACCEPT / AUTHORIZATION_LIVE` then return verified metadata;
- unknown canonical ref => `LOOKUP_MISS / LOOKUP / DENY / AUTHORIZATION_NOT_FOUND`, return `None`;
- malformed ref => `LOOKUP_MISS / LOOKUP / DENY / AUTHORIZATION_REF_INVALID`, hash `null`, return `None`;
- expired/future-invalid cached entry => evict, emit `LOOKUP_EXPIRED / LOOKUP / DENY / AUTHORIZATION_NOT_LIVE`, return `None`;
- audit append failure on hit => return no authority / stable resolver audit failure;
- audit append failure on miss/expired never creates success.

- [ ] **Step 2: Observe RED**

Expected: failures only because resolver does not yet accept/use the observer/context.

- [ ] **Step 3: Implement minimal optional observer integration**

Preserve existing cache/verification logic; add audit only at decision boundaries. Do not infer trusted correlation from cached receipt metadata when request-bound context is required.

- [ ] **Step 4: Run resolver + full regression tests**

Expected: targeted GREEN and existing resolver behavior unchanged when observer is absent.

---

### Task 4: Receipt delivery registration/refusal auditing and rollback — TDD

**Files:**
- Modify: `platform/runner-authorization/receipt_delivery.py`
- Modify: `platform/tests/test_receipt_delivery_boundary.py`
- Modify: `platform/tests/test_authorization_receipt_audit_integration.py`

**Interfaces:**
- `TrustedReceiptDelivery(policy, resolver, audit_observer=None)`.
- `deliver(envelope, *, peer, audit_context=None)` remains backward compatible without observer.

- [ ] **Step 1: Write failing delivery integration tests**

Cover:
- successful first registration emits exactly one `REGISTERED / REGISTRATION / ACCEPT / RECEIPT_VERIFIED`;
- exact duplicate sequence returns duplicate without a second registration audit event;
- unauthenticated peer => `REFUSED / DELIVERY / DENY / PEER_UID_UNAUTHORIZED` or canonical peer code, no registration;
- invalid envelope/issuer/replay => sanitized `REFUSED` with stable existing delivery code;
- canonical receipt verification failure => `REFUSED / REGISTRATION / DENY / <stable resolver code>` with no raw exception text;
- observer configured but trusted audit context absent => no accepted delivery;
- audit append failure after resolver registration invokes `resolver.forget(authorization_ref)` and delivery fails closed;
- refusal-audit failure does not turn a denial into acceptance;
- no unverified receipt correlation is copied into audit context.

- [ ] **Step 2: Observe RED**

Expected: failures only because delivery has no observer/context integration.

- [ ] **Step 3: Implement minimal integration**

Order for success:
1. delivery peer/envelope checks;
2. resolver canonical verification/registration;
3. append `REGISTERED` audit;
4. only then return accepted outcome.

On post-registration audit failure: call `resolver.forget(ref)` before raising stable `DELIVERY_AUDIT_FAILED`.

On refusal: attempt sanitized `REFUSED`; failure remains denial and returns stable audit-failure wrapper without leaking exception strings.

- [ ] **Step 4: Run delivery + full regression tests**

Expected: GREEN; committed delivery policy unchanged.

---

### Task 5: Request-bound WebGoat lookup context — TDD

**Files:**
- Modify: `platform/runner-adapters/webgoat_l1_adapter.py`
- Modify: existing WebGoat adapter tests.

**Interfaces:**
- Adapter supplies trusted Runner correlation to resolver lookup when the resolver supports audited lookup.
- Fixed principal: bounded Runner-side principal label; no peer credentials or receipt fields copied into request audit context.

- [ ] **Step 1: Write failing tests**

Cover:
- successful authorization lookup receives campaign/run/step/attempt from schema-validated Runner request;
- lookup miss/refusal is request-bound to the same trusted correlation;
- target/parameter raw values remain absent from audit record;
- legacy/simple resolver test doubles remain supported through a compatibility boundary or updated protocol without weakening fail-closed behavior.

- [ ] **Step 2: Observe RED**

Expected: current adapter calls `resolve(ref)` without trusted audit context.

- [ ] **Step 3: Implement minimal request-bound context handoff**

Do not move authorization checks into the audit adapter. Existing full binding checks remain authoritative and unchanged.

- [ ] **Step 4: Run adapter + full regression tests**

Expected: GREEN, no target effect executed by tests.

---

### Task 6: Governance, roadmap and ChangeRecord reconciliation

**Files:**
- Create: `changes/CHG-HSL-078.yaml`
- Modify: `platform/runner-authorization/README.md`
- Modify: `deployment/runtime-promotion/README.md` only if necessary to accurately separate repository audit readiness from live delivery blockers.
- Modify: relevant roadmap/status document if the audit-evidence blocker is currently listed as missing.

**Interfaces:**
- Produces: factual repository state only.

- [ ] **Step 1: Record observed validation states**

Set:

```text
targeted = PASS
regression = PASS
security = PASS
runtime = NOT_RUN
```

only after exact-head evidence exists.

- [ ] **Step 2: Update docs without closing live blockers**

State explicitly:
- registration/lookup/refusal audit evidence is GREEN-REPO;
- real AF_UNIX endpoint remains not configured;
- resolver/delivery policies remain disabled;
- real signer/trust remain unresolved;
- campaign remains HOLD/BLOCKED;
- #403 remains open.

---

### Task 7: Review, exact-head CI, merge and post-merge verification

**Files:** none unless review finds a defect.

- [ ] **Step 1: Review full PR diff**

Block on:
- untrusted receipt fields becoming audit context;
- raw authorization reference persistence;
- secret/signature/target/parameter leakage;
- second audit/evidence primitive;
- observer failure accidentally granting authority;
- policy/runtime enablement;
- shallow mutable policy/context aliases that bypass prior validation.

- [ ] **Step 2: Verify PR state**

Require:
- all 4 workflows GREEN on exact final head;
- full `platform/tests` / source-of-truth GREEN;
- Exact-SHA GREEN;
- no pending reviews/threads;
- mergeable PR;
- `main` unchanged or PR rebased/revalidated if it advanced.

- [ ] **Step 3: Squash merge pinned to expected head SHA**

- [ ] **Step 4: Verify post-merge main SHA**

Require the same 4 workflows plus Exact-SHA GREEN on the squash commit.

- [ ] **Step 5: Close tracking issue as completed and update #403 only with non-authoritative progress**

Do not change #403 human/provider decision state.
