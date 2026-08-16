# Provider-neutral signer boundary status — CHG-HSL-073 through CHG-HSL-077

**Baseline date:** 2026-08-15  
**Reconciled:** 2026-08-16  
**Campaign:** `VAL-HSL-RUNNER-L1-LIVE-PROMOTION`  
**Effect:** repository-only hardening; no runtime/provider/trust mutation

## What is now implemented

### CHG-HSL-073 — provider-neutral signing boundary

- immutable bounded `SigningRequest` and `SigningResult` contracts;
- one-operation `SigningService` protocol;
- canonical TB1 domain/purpose binding;
- CI-only deterministic Ed25519 signer with no key file/network/provider SDK;
- LAB_L1 envelope guard rejects test/non-authoritative output and standalone `PKCS11`;
- no provider, trust or promotion authority.

The CI-only signer remains mechanically:

```text
CI_ONLY=true
NON_AUTHORITATIVE=true
NOT_ADMISSIBLE_FOR_LAB_L1_PROMOTION=true
```

### CHG-HSL-074 — signer ↔ trust-generation evidence composition

- composes only already-verified signer provenance with an already-reviewed trust generation;
- requires exact key id, algorithm and SPKI SHA-256 agreement;
- reuses the canonical trust-store lifecycle validator;
- emits a closed public `signer-trust-manifest/v1` with no-authority flags;
- installs no trust and selects no provider.

### CHG-HSL-075 — signer operation audit attribution

- dedicated `signer-operation-audit/v1` adapter;
- feeds the existing canonical AuditSink/EvidenceChain;
- deterministic content addressing and request/correlation attribution;
- no raw payload, raw signature/base64, private key, token, credential or secret;
- no second ledger, EvidenceChain or seal.

ADR-0012 preserves the selected adapter design and the alternatives that were not selected for the MVP.

### CHG-HSL-076 — signer audit EvidenceVerifier linkage

- canonical signer-audit custody policy remains `DISABLED / deny / NOT_RUN`;
- public signer audit event may be projected into an injected existing Evidence Plane store in disposable tests;
- `LocalEvidenceVerifier` proves exact reference + digest;
- AuditSink/EvidenceChain and Evidence Plane identify the same content-addressed audit object;
- `EvidenceVerifierChainResolver` is only an interface adapter and implements no second verifier;
- tamper, missing object, digest/ref mismatch and backend errors fail closed.

### CHG-HSL-077 — signer trust manifest custody

- dedicated minimal custody bridge for the existing public `signer-trust-manifest/v1`;
- canonical policy is `DISABLED / deny / NOT_RUN / execution_authority=none`;
- closed schema is validated before any write;
- `manifest_id` is independently recomputed from canonical manifest content before custody;
- schema-valid mutation with a stale/reused `manifest_id` is refused fail-closed;
- exact canonical public manifest JSON is projected through an injected existing Evidence Plane store;
- Evidence Plane classification is `restricted` with `default-30d` / 30-day retention;
- storage reference is content-addressed as `evidence://signer-trust-manifest/<sha256>`;
- post-write canonical store integrity verification is mandatory;
- the existing `LocalEvidenceVerifier` proves exact `evidence_ref + payload_sha256` and detects tamper/ref/digest mismatch;
- identical replay is content-addressed/idempotent under the existing store semantics;
- no second store, verifier, AuditSink, EvidenceChain, seal or ledger;
- no Vault/KMS/HSM/PKCS11 call, key provisioning, trust installation, Runner effect or promotion authority.

ADR-0013 preserves the selected minimal custody design and explicitly defers immediate chain linkage and a generic custody framework until concrete review triggers are met.

## Architecture decision history

The canonical ADR register now preserves material alternatives using explicit dispositions:

```text
Selected
Deferred
Not selected for MVP
Rejected
Superseded
```

Each material alternative records why that disposition applies and review triggers where reconsideration may become appropriate.

Recent decisions now captured:

- **ADR-0012:** dedicated signer-operation audit attribution adapter;
- **ADR-0013:** minimal dedicated signer-trust-manifest custody bridge;
- **ADR-0014:** VAULT as preferred future custody architecture, with implementation and operational selection deferred.

ADR-0014 does not alter the signer decision source of truth. KMS remains an admissible deferred alternative; HSM is not selected for the MVP; local PEM/OpenSSL is rejected for LAB_L1 custody proof; standalone PKCS11 remains an interface rather than a custody class.

## Existing trust lifecycle capability — not a remaining implementation gap

The repository already contains a provider-neutral trust-store lifecycle contract covering:

- content-addressed generations;
- freshness and future/stale refusal;
- monotonic sequence and predecessor binding;
- anti-rollback checks;
- safe `active → retired/revoked` transitions;
- refusal of retired/revoked key resurrection;
- key material, algorithm and validity-window mutation refusal;
- refusal of unsafe active-key removal;
- safe rotation with a new active key;
- explicit `automatic_activation=false`, `activation_effect=NONE`, `authorization_effect=NONE`, `execution_authority=NONE`.

CHG-HSL-074 already consumes this lifecycle assessment. Rotation/revocation is therefore **not** listed as an unimplemented provider-neutral signer lane. Real provider-side propagation/attestation remains later operational evidence.

## TDD / validation evidence

The signer boundary continues to be developed through fail-closed repository gates rather than by weakening contracts.

For CHG-HSL-077:

1. the tests-first head produced a clean RED: **20 failures, 2214 passes, 7 skipped**, all caused by the custody module being absent;
2. the minimal disabled-policy custody bridge and Evidence Plane integration were implemented;
3. the first implementation run produced **1 failure, 2233 passes, 7 skipped** because the new test expected `content.size` while the canonical Evidence Plane contract uses `content.size_bytes`;
4. the defect was corrected in the test only; production/store contracts were not weakened;
5. the corrected functional head passed the full `platform/tests`/source-of-truth suite and Exact-SHA, while `security`, `Release governance` and `Private VAmPI source-repo access deny` were also GREEN.

No RED was bypassed by loosening signer custody, trust, evidence or execution semantics.

## Canonical operational state

The following remains authoritative and unchanged:

```text
signer-human-decision = NO_DECISION
supplier_selection = NO_SELECTION
selected_class = null
human_decision_id = null
trust store = ABSENT
provider attestation = NOT_OBSERVED
signer-audit custody policy = DISABLED
signer-trust-manifest custody policy = DISABLED
promotion_allowed = false
runtime_status = NOT_RUN
execution_authority = none
campaign = BLOCKED / HOLD
```

Issue #403 remains open because real custody selection/provider evidence requires an explicit human decision and independently verified evidence.

## What the provider-neutral software does not prove

The following remain unresolved for actual LAB_L1 promotion:

- real external signer/provider observation;
- non-exportable real private-key proof;
- active/signing-enabled provider attestation;
- independently verified provider/source evidence;
- operational public trust-store binding and installation;
- provider-side rotation/revocation propagation evidence;
- complete R1–R8 operational review evidence;
- real authenticated receipt delivery;
- remaining PRE_PROMOTION evidence;
- request-bound HITL approval;
- live Runner effect/audit/outcome/reset evidence;
- POST_EFFECT acceptance.

The LAB_L1 hash seal remains integrity/tamper evidence only; it does not assert external authenticity or durable/WORM custody.

## Updated continuation path

Completed provider-neutral signer lanes:

- [x] provider-neutral signing boundary;
- [x] trust-generation lifecycle/rotation/revocation contract;
- [x] signer ↔ trust-generation manifest composition and exact provenance binding;
- [x] signer operation audit attribution;
- [x] signer audit -> Evidence Plane -> EvidenceVerifier -> AuditSink/EvidenceChain linkage;
- [x] signer trust manifest -> Evidence Plane -> EvidenceVerifier custody linkage;
- [x] ADR preservation of recent alternatives and future review triggers.

Safe remaining development that does not require a provider selection should focus on:

1. authenticated receipt-delivery contract/integration where it can remain disabled and fail-closed;
2. other non-signer PRE_PROMOTION evidence gaps;
3. PRE_PROMOTION package reconciliation as independent evidence becomes available.

The real Vault adapter/provisioning, human custody decision, operational trust installation, provider-side evidence and live Runner promotion remain separate governed changes. No target-interacting action becomes authorized because these repository boundaries are GREEN.
