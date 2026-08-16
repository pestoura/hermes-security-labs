# Signer Trust Manifest Custody Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Preserve the recent architectural decision alternatives in canonical ADRs and implement a minimal provider-neutral custody bridge for `signer-trust-manifest/v1` using the existing Evidence Plane and EvidenceVerifier contracts.

**Architecture:** Governance work is recorded in the existing ADR register, not a parallel decision log. The custody implementation validates the existing closed manifest schema, independently recomputes `manifest_id`, persists only canonical public JSON through an injected existing Evidence Plane store, requires post-write integrity verification, and relies on the existing `LocalEvidenceVerifier` for later reference+digest verification. No provider, trust installation, key provisioning, Runner effect or promotion authority is introduced.

**Tech Stack:** Python 3, pytest, jsonschema, YAML, existing `platform/evidence-plane` contracts, GitHub Actions validation gates.

## Global Constraints

- Canonical operational signer state remains `NO_DECISION / NO_SELECTION`.
- Canonical custody policy remains `DISABLED / deny / NOT_RUN / execution_authority=none`.
- `promotion_allowed=false`, `runtime_status=NOT_RUN`, `execution_authority=NONE`, `Runner effect=NOT_RUN` remain invariant.
- No Vault/KMS/HSM/PKCS11 call, endpoint, credential, key generation/import/export or trust installation.
- Evidence payload is the exact public closed-schema `signer-trust-manifest/v1` JSON only.
- Retention policy is `default-30d` with `retention_days=30`.
- No second datastore, EvidenceVerifier, EvidenceChain, AuditSink, seal or ledger.
- Alternatives in structural decisions must be preserved with status and review triggers.

---

### Task 1: Canonical decision-history governance

**Files:**
- Create: `docs/architecture/adr/ADR-0012-signer-operation-audit-attribution.md`
- Create: `docs/architecture/adr/ADR-0013-signer-trust-manifest-custody.md`
- Create: `docs/architecture/adr/ADR-0014-vault-target-architecture-deferred-implementation.md`
- Modify: `docs/architecture/adr/README.md`

**Interfaces:**
- Consumes: existing ADR governance and CHG-HSL-073/075/077 design history.
- Produces: immutable architectural rationale preserving selected, deferred, not-selected-for-MVP and rejected alternatives plus future review triggers.

- [ ] **Step 1: Record ADR-0012**

Capture the CHG-HSL-075 decision:

- Selected: dedicated signer audit adapter feeding existing AuditSink/EvidenceChain.
- Not selected for MVP: adding signer-specific fields directly to generic AuditSink.
- Not selected for MVP: placing attribution/governance fields inside `SignatureEnvelope`.
- Review triggers: AuditSink schema pressure, multiple signer event families, production SIEM/export requirements, or evidence-chain coupling becoming operationally expensive.

- [ ] **Step 2: Record ADR-0013**

Capture the CHG-HSL-077 decision:

- Selected: minimal dedicated signer-trust-manifest custody bridge.
- Deferred / not selected for MVP: immediate AuditSink/EvidenceChain linkage.
- Deferred / not selected for MVP: generic public-evidence custody framework.
- Review triggers: four or more materially similar custody adapters, production WORM backend, multi-tenancy, or repeated policy/retention duplication.

- [ ] **Step 3: Record ADR-0014**

Capture the signer custody architecture direction:

- Selected architectural target: `VAULT`.
- Deferred: actual Vault implementation/provisioning/binding.
- Alternative admissible later: `KMS`.
- Not selected for MVP: `HSM` because of cost/friction proportionality.
- Rejected for LAB_L1 custody proof: local PEM/OpenSSL signer and standalone `PKCS11` interface.
- Review triggers: Hermes Vault capability becomes operational, cloud tenancy requirements change, HSM becomes an existing shared service, or R1-R8 cannot be satisfied by the target implementation.

The ADR must state that this architectural preference is not an operational supplier/provider selection and leaves #403 `NO_DECISION / NO_SELECTION`.

- [ ] **Step 4: Extend ADR governance**

Add a mandatory alternative disposition vocabulary to `docs/architecture/adr/README.md`:

```text
Selected
Deferred
Not selected for MVP
Rejected
Superseded
```

Require every material alternative to state why it has that disposition and at least one review trigger when future reconsideration is plausible.

- [ ] **Step 5: Validate documentation**

Run the repository documentation/source-of-truth validation through CI. Expected: ADR index and links are valid and no existing ADR semantics regress.

---

### Task 2: TDD contract for signer trust manifest custody

**Files:**
- Create: `platform/tests/test_signer_trust_manifest_custody.py`
- Later create: `platform/evidence-plane/signer_trust_manifest_custody.py`
- Later create: `platform/evidence-plane/signer-trust-manifest-custody-policy.yaml`

**Interfaces:**
- Consumes: `platform/assurance/signer_trust_manifest.py`, `platform/schemas/signer-trust-manifest.schema.json`, `platform/evidence-plane/evidence_plane.py`, injected store contract.
- Produces: failing tests defining policy, manifest identity, persistence, verification, idempotency and safety requirements.

- [ ] **Step 1: Write policy fail-closed tests**

Tests must assert canonical repository policy values exactly:

```text
schema_version: '1.0'
policy_id: hexor.signer.trust_manifest.custody
state: DISABLED
default: deny
runtime_status: NOT_RUN
execution_authority: none
classification: restricted
retention_policy_id: default-30d
retention_days: 30
include_private_key: false
include_raw_signing_payload: false
include_raw_signature: false
install_trust: false
```

Unknown/missing/mutated fields must fail policy validation.

- [ ] **Step 2: Write manifest identity tests**

Build a valid manifest using the existing composer/fixtures, validate its closed schema, remove `manifest_id`, canonical-JSON encode the remaining body, recompute SHA-256 and assert the supplied id equals:

```text
stm_<first 32 lowercase hex chars>
```

Mutating any valid field while reusing the original id must fail with `MANIFEST_ID_MISMATCH` before store access.

- [ ] **Step 3: Write Evidence Plane persistence tests**

Using a disposable `LocalEvidenceStore(tmp_path / "evidence")`, require:

- exact canonical public manifest bytes persisted;
- `classification=restricted`;
- `producer=signer-trust-manifest-custody-v1`;
- `operation=signer.trust_manifest.custody`;
- `protocol_version=signer-trust-manifest/v1`;
- `storage_ref=evidence://signer-trust-manifest/<payload_sha256>`;
- `retention_policy_id=default-30d`;
- post-write `store.verify(evidence_id)` succeeds;
- returned public ref is `evidence://ev_<32hex>`.

- [ ] **Step 4: Write EvidenceVerifier/tamper tests**

Use the existing `LocalEvidenceVerifier` only. Assert exact ref+digest succeeds; wrong digest, missing reference and tampered object fail.

- [ ] **Step 5: Write idempotency and safety tests**

Repeated identical persistence with identical correlation/timestamp must not create divergent content objects/records. Static tests must ensure the custody module does not import network/provider/runtime libraries and does not instantiate `LocalEvidenceStore`, `LocalEvidenceVerifier`, `EvidenceChain`, `AuditSink` or provider clients.

- [ ] **Step 6: Run CI to observe RED**

Expected: new tests fail because custody policy/module are absent. Existing suites remain otherwise GREEN.

---

### Task 3: Minimal custody implementation

**Files:**
- Create: `platform/evidence-plane/signer_trust_manifest_custody.py`
- Create: `platform/evidence-plane/signer-trust-manifest-custody-policy.yaml`
- Test: `platform/tests/test_signer_trust_manifest_custody.py`

**Interfaces:**
- Consumes: mapping manifest, correlation mapping, recorded timestamp, injected Evidence Plane store.
- Produces: immutable `SignerTrustManifestCustodyResult(evidence_id, evidence_ref, payload_sha256, classification, manifest_id)`.

- [ ] **Step 1: Implement policy loader/validator**

Implement stable fail-closed errors:

```text
CUSTODY_DISABLED
POLICY_INVALID
MANIFEST_INVALID
MANIFEST_ID_MISMATCH
EVIDENCE_STORE_UNAVAILABLE
EVIDENCE_PROJECTION_FAILED
EVIDENCE_VERIFICATION_FAILED
```

Backend exceptions must be sanitized to exception type only; no path/secret detail.

- [ ] **Step 2: Implement closed-schema and identity verification**

Load the existing schema, validate before write, recompute the canonical body digest excluding only `manifest_id`, and refuse exact mismatch.

- [ ] **Step 3: Implement Evidence Plane projection**

Canonical encode the full validated manifest, derive payload SHA-256, construct the existing Evidence Plane record with `restricted` classification and the exact storage ref, call injected `store.put()`, then require injected `store.verify(evidence_id) is True`.

- [ ] **Step 4: Return no-authority custody result**

Return only evidence location/integrity metadata and `manifest_id`; do not expose or mutate signer decision/trust state.

- [ ] **Step 5: Run focused/full tests to GREEN**

Expected: custody tests pass and existing `platform/tests` remain GREEN without weakening boundaries.

---

### Task 4: Governance reconciliation and tracking

**Files:**
- Create: `changes/CHG-HSL-077.yaml`
- Modify: `docs/roadmap/provider-neutral-signer-boundary-2026-08-15.md`
- Use existing spec: `docs/superpowers/specs/2026-08-16-signer-trust-manifest-custody-design.md`

**Interfaces:**
- Consumes: observed test/CI outcomes.
- Produces: truthful JDS ChangeRecord and roadmap status.

- [ ] **Step 1: Create tracking issue**

Record scope and acceptance criteria. Explicitly state #403 remains a separate human decision.

- [ ] **Step 2: Create ChangeRecord with truthful states**

Before validation, use canonical `NOT_RUN` where evidence has not been observed. After exact-head CI, set only observed targeted/regression/security fields to `PASS`; runtime remains `NOT_RUN`.

- [ ] **Step 3: Reconcile roadmap**

Mark signer trust-manifest custody/verifier linkage complete while leaving provider observation, operational trust binding, receipt delivery, PRE_PROMOTION, HITL and Runner effect unresolved.

---

### Task 5: PR, exact-SHA CI, merge and post-merge verification

**Files:**
- No new production files beyond Tasks 1–4.

**Interfaces:**
- Consumes: complete branch.
- Produces: merged verified main SHA or a fail-closed blocker report.

- [ ] **Step 1: Open draft PR**

PR must list selected ADR decisions, custody scope, locked authority invariants and tracking issue.

- [ ] **Step 2: Require all exact-head gates**

Require:

```text
validate
security
Release governance
Private VAmPI source-repo access deny
Exact-SHA validation evidence
```

Any RED is diagnosed and fixed; no gate is weakened.

- [ ] **Step 3: Review diff and PR state**

Verify mergeability, no unresolved reviews/threads, no provider/trust/runtime side effects, #403 unchanged, and main has not advanced incompatibly.

- [ ] **Step 4: Squash merge pinned to exact verified head SHA**

Do not merge if the head has changed since verification.

- [ ] **Step 5: Re-run post-merge gates on exact new main SHA**

Only after all post-merge workflows and Exact-SHA succeed may CHG-HSL-077 be marked complete.

- [ ] **Step 6: Close tracking issue and annotate #403**

Record only provider-neutral progress. Do not change `NO_DECISION / NO_SELECTION` or imply custody/provider evidence that has not been observed live.
