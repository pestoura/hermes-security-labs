# Authorization Audit Evidence Custody — Design

**Change:** CHG-HSL-079  
**Decision:** ADR-0016  
**Status:** Approved design / repository-only  
**Date:** 2026-08-16

## 1. Objective

Close the repository-level custody gap left after CHG-HSL-078 by persisting the exact sanitized `authorization-receipt-audit/v1` object through the existing Evidence Plane and proving the resulting `evidence_ref + sha256` through the existing `EvidenceVerifier` contract before the same reference is used by the canonical `AuditSink` / EvidenceChain.

This design does not promote runtime or resolve the remaining live signer/trust/delivery/HITL/effect gates.

## 2. Existing state

CHG-HSL-078 provides:

- closed `authorization-receipt-audit/v1` schema;
- deterministic sanitized record construction;
- `CanonicalAuthorizationAuditAdapter` -> existing `AuditSink` / EvidenceChain;
- audit events `REGISTERED`, `LOOKUP_HIT`, `LOOKUP_MISS`, `LOOKUP_EXPIRED`, `REFUSED`;
- SHA-256-only persistence of canonical authorization references;
- trusted audit context supplied only by trusted composition/request boundaries;
- fail-closed behavior on positive registration/lookup paths when auditing is configured;
- no live delivery/resolver enablement or execution authority.

The adapter currently appends an `evidence://authorization-receipt-audit/<digest>` object reference to the AuditSink but does not persist the referenced JSON object into the Evidence Plane.

## 3. Selected architecture

Implement a dedicated `AuthorizationAuditCustody` bridge in the Evidence Plane boundary, patterned on the existing domain-specific custody bridges while reusing canonical store/verifier primitives.

### 3.1 Components

1. **Authorization audit record contract** — existing `authorization_audit_adapter.py` remains the canonical builder/validator for sanitized authorization audit records.
2. **Authorization audit custody policy** — new dedicated YAML policy, committed `DISABLED / deny / NOT_RUN / execution_authority: none`.
3. **Authorization audit custody bridge** — new module under `platform/evidence-plane/` accepting an injected Evidence Plane store.
4. **Existing Evidence Plane store** — no new datastore implementation.
5. **Existing `LocalEvidenceVerifier` / EvidenceVerifier contract** — no new verifier.
6. **Existing `CanonicalAuthorizationAuditAdapter` / AuditSink** — receives an optional custody dependency and, when configured, appends the exact verified Evidence Plane reference/digest rather than an unbacked synthetic reference.

### 3.2 Data flow

```text
verified authorization decision
        |
        v
build_authorization_audit_record()
        |
        | sanitized authorization-receipt-audit/v1 only
        v
AuthorizationAuditCustody.persist(record)
        |
        +--> validate closed schema
        +--> canonical JSON bytes
        +--> sha256(payload)
        +--> existing Evidence Plane store.write(...)
        +--> existing store.verify(evidence_id)
        +--> canonical evidence_ref + payload_sha256
        +--> LocalEvidenceVerifier.verify(ref, sha256)
        |
        v
CanonicalAuthorizationAuditAdapter
        |
        +--> AuditSink.append(same ref, same digest, same size)
        |
        v
AuditSink.verify(resolver=LocalEvidenceVerifier(...))
```

No raw receipt or decision input bypasses the canonical sanitized record contract.

## 4. Policy contract

Add `platform/evidence-plane/authorization-audit-custody-policy.yaml` with a closed, explicit policy surface matching existing repository conventions.

Committed state:

- `state: DISABLED`;
- `default: deny`;
- `runtime_status: NOT_RUN`;
- `execution_authority: none`;
- bounded retention aligned to the current LAB_L1 Evidence Plane default unless the existing canonical policy contract requires a stricter value;
- classification `restricted`;
- no backend/provider binding;
- no production durability/WORM claim.

Tests may construct a temporary ENABLED policy only inside `tmp_path` / in-memory test composition. Committed policy remains disabled.

## 5. Custody contract

The custody bridge accepts only an exact mapping that validates against `platform/schemas/authorization-receipt-audit.schema.json`.

On success it returns a bounded public result containing only:

- `evidence_id`;
- `evidence_ref`;
- `payload_sha256`;
- `payload_size_bytes`;
- `classification`;
- `retention_policy_id`;
- `retention_days`;
- `verified: true`.

The canonical reference is:

`evidence://authorization-receipt-audit/<payload_sha256>`

The bridge must independently recompute the SHA-256 from canonical JSON. Caller-provided digest/reference/verification flags are not authority and are not accepted as inputs.

## 6. Integration semantics

`CanonicalAuthorizationAuditAdapter` gains optional injected custody support.

### No custody configured

Preserve the CHG-HSL-078 repository-only behavior for compatibility. The adapter may build/append the current deterministic reference but makes no Evidence Plane custody claim.

### Custody configured

For a new non-duplicate event:

1. build sanitized record;
2. persist and verify through custody;
3. require returned digest equals the locally recomputed record digest;
4. require returned reference equals `evidence://authorization-receipt-audit/<digest>`;
5. append that exact reference/digest/size to AuditSink;
6. cache idempotency only after both custody and AuditSink append succeed.

Any failure before step 6 returns failure. No positive audit result is reported.

Exact duplicate events must remain idempotent and must not create a second Evidence Plane object or AuditSink entry.

## 7. Failure semantics

Stable public failures must be domain-specific and sanitized. Backend exception strings must not be exposed.

At minimum cover:

- policy disabled/invalid;
- record schema invalid;
- canonicalization/digest mismatch;
- Evidence Plane write failure;
- post-write verification failure;
- invalid/mismatched evidence reference;
- LocalEvidenceVerifier failure;
- AuditSink append failure;
- replay conflict / non-identical object collision if the canonical store reports one.

A denial/refusal decision remains a denial even if evidence persistence fails. However, where an audit observer/custody path is configured as required for a positive authorization path, inability to persist/verify the audit record remains fail-closed exactly as ADR-0015 requires.

## 8. Data minimization

Persisted payload is exactly the existing sanitized audit record. Forbidden material includes:

- raw receipt JSON;
- `signature_b64` or signature bytes;
- private/public key material beyond already approved public digests/metadata in the audit schema;
- raw authorization reference;
- target locator;
- raw operation parameters;
- credentials, secrets, tokens, cookies or headers;
- backend exception text;
- caller-supplied trust/verification/authority flags.

No new sensitive fields are introduced by CHG-HSL-079.

## 9. Idempotency and ordering

Content addressing makes the Evidence Plane object idempotent for exact replay. The authorization adapter's existing identity tuple remains authoritative for duplicate event suppression.

The bridge does not create ordering semantics of its own. Event ordering remains the responsibility of the existing AuditSink/EvidenceChain.

No mutable overwrite is permitted.

## 10. Test design

### RED first

Add tests before implementation proving absence of:

- custody module/policy;
- schema-before-write enforcement;
- post-write verification;
- EvidenceVerifier linkage;
- adapter use of persisted reference/digest.

RED must fail for those missing capabilities, not for unrelated repository defects.

### Functional tests

Cover:

- valid REGISTERED custody;
- valid LOOKUP_HIT/MISS/EXPIRED and REFUSED custody;
- exact canonical digest/reference;
- `restricted` classification and bounded retention;
- exact replay idempotency;
- closed-schema rejection before write;
- sensitive-field rejection;
- disabled policy fail-closed;
- store write failure sanitization;
- store verify false/exception fail-closed;
- tampered stored payload fails EvidenceVerifier;
- digest mismatch and ref mismatch fail;
- adapter uses exact custody ref/digest/size;
- adapter does not append AuditSink entry when custody fails;
- AuditSink resolver verification passes for intact object and fails on tamper;
- legacy no-custody path remains regression-compatible.

### Regression gates

Run at minimum:

- new focused CHG-HSL-079 tests;
- CHG-HSL-078 authorization audit tests;
- Evidence Plane tests;
- full `platform/tests` source-of-truth suite;
- repository `validate`;
- `security`;
- `Release governance`;
- `Private VAmPI source-repo access deny`;
- Exact-SHA validation on final PR head and post-merge main.

## 11. Non-goals

CHG-HSL-079 does not:

- enable receipt delivery or resolver policy;
- create/open an AF_UNIX endpoint;
- install trust;
- provision/select VAULT/KMS/HSM/PKCS11;
- generate/import/export private keys;
- attest a live signer/provider;
- dispatch a Runner request;
- contact WebGoat/Kali/any target;
- assemble a complete PRE_PROMOTION package by itself;
- satisfy HITL;
- promote LAB_L1;
- implement WORM/tenant isolation.

## 12. Acceptance boundary

Repository acceptance is achieved only when the exact PR head is GREEN and the merged main SHA is re-verified. Even then:

- `promotion_allowed=false`;
- `runtime_status=NOT_RUN`;
- `execution_authority=NONE`;
- delivery/resolver policies remain disabled;
- `VAL-HSL-RUNNER-L1-LIVE-PROMOTION` remains `BLOCKED / HOLD` until all independent live gates are satisfied.
