# Authorization Audit Evidence Custody — Design

**Change:** CHG-HSL-079  
**Decision:** ADR-0016  
**Status:** Approved design / repository-only  
**Date:** 2026-08-16

## 1. Objective

Close the repository-level custody gap left after CHG-HSL-078 by persisting the exact sanitized `authorization-receipt-audit/v1` object through the existing Evidence Plane, verifying that object through the existing `EvidenceVerifier` contract, and binding the canonical Evidence Plane custody ID into the existing `AuditSink` / EvidenceChain while preserving the content-addressed audit object reference.

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
6. **Existing `CanonicalAuthorizationAuditAdapter` / AuditSink** — receives optional custody dependencies and, when configured, retains the content-addressed `object_ref` while binding the canonical `ev_<id>` custody record in `evidence_ref`.

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
        +--> validate trusted correlation + timestamp before write
        +--> canonical JSON bytes
        +--> sha256(payload)
        +--> existing Evidence Plane store.put(...)
        +--> existing store.verify(evidence_id)
        +--> canonical ev_<id> custody identity + payload digest/size
        |
        v
CanonicalAuthorizationAuditAdapter
        |
        +--> require custody digest/size == canonical object digest/size
        +--> require evidence_id == normalized evidence_ref
        +--> AuditSink.append(
                object_ref=evidence://authorization-receipt-audit/<sha256>,
                evidence_ref=ev_<id>, ...)
        |
        v
AuditSink.verify(resolver=EvidenceVerifierChainResolver(...))
        |
        v
existing LocalEvidenceVerifier / EvidenceVerifier
```

No raw receipt or decision input bypasses the canonical sanitized record contract.

## 4. Policy contract

Add `platform/evidence-plane/authorization-audit-custody-policy.yaml` with a closed, explicit policy surface matching existing repository conventions.

Committed state:

- `state: DISABLED`;
- `default: deny`;
- `runtime_status: NOT_RUN`;
- `execution_authority: none`;
- retention `default-30d / 30 days` for the repository candidate;
- classification `restricted`;
- no backend/provider binding;
- no production durability/WORM claim;
- raw receipt and raw authorization-reference custody disabled.

Tests may construct a temporary ENABLED policy only inside isolated test composition. Committed policy remains disabled.

## 5. Custody contract

The custody bridge accepts only an exact mapping that validates against `platform/schemas/authorization-receipt-audit.schema.json`.

On success it returns a bounded public result containing only:

- `evidence_id` — canonical Evidence Plane record ID, `ev_<32 lowercase hex>`;
- `evidence_ref` — URI form `evidence://ev_<id>`;
- `payload_sha256` — digest of the exact canonical sanitized JSON object;
- `payload_size_bytes` — size of those exact canonical bytes;
- `classification` — `restricted` under the canonical policy.

The content-addressed storage/object reference is distinct:

```text
evidence://authorization-receipt-audit/<payload_sha256>
```

The bridge independently recomputes SHA-256 from canonical JSON. Caller-provided digest, evidence reference, verification flag, promotion flag or execution-authority flag is not accepted as authority.

Successful return means the injected store accepted the canonical Evidence Plane record and `store.verify(evidence_id)` succeeded. The result does not add a second `verified` authority field.

## 6. Integration semantics

`CanonicalAuthorizationAuditAdapter` gains optional injected custody support.

### No custody configured

Preserve the CHG-HSL-078 repository-only behavior for compatibility. The adapter may build/append the current deterministic content reference but makes no Evidence Plane custody claim and leaves AuditSink `evidence_ref` unset.

### Custody configured

For a new non-duplicate event:

1. build the sanitized record;
2. independently compute its canonical digest and size;
3. persist and post-write verify through custody;
4. require returned `payload_sha256` and `payload_size_bytes` to equal the locally recomputed values;
5. normalize the returned `evidence_ref` to canonical `ev_<id>` and require it to equal the returned `evidence_id`;
6. append to AuditSink using:
   - `object_ref=evidence://authorization-receipt-audit/<digest>`;
   - the same `object_digest_sha256` and canonical object size;
   - `evidence_ref=ev_<id>` as the custody binding;
7. cache adapter idempotency only after both custody and AuditSink append succeed.

Any failure before step 7 returns failure. No positive audit result is reported.

The content identity and custody identity are intentionally not interchangeable:

- `object_ref` identifies **which exact sanitized audit object**;
- `evidence_ref` identifies **which canonical Evidence Plane record holds that object**.

Exact duplicate events must remain idempotent and must not create a second Evidence Plane record or AuditSink entry.

If custody succeeds and AuditSink append fails, immutable evidence is retained. The adapter preserves the event's selected `recorded_at` so a deterministic retry can reuse the same content-addressed Evidence Plane record and complete one final chain append.

## 7. Failure semantics

Stable public failures must be domain-specific and sanitized. Backend exception strings must not be exposed.

At minimum cover:

- policy disabled/invalid;
- record schema invalid;
- invalid trusted correlation or timestamp before write;
- canonicalization/digest/size mismatch;
- Evidence Plane write failure;
- post-write verification failure;
- invalid/mismatched Evidence Plane `evidence_id` / `evidence_ref`;
- LocalEvidenceVerifier / chain-resolver failure;
- AuditSink append failure;
- replay conflict / non-identical object collision if the canonical store reports one.

A denial/refusal decision remains a denial even if evidence persistence fails. Where an audit observer/custody path is configured as required for a positive authorization path, inability to persist/verify the audit record remains fail-closed exactly as ADR-0015 requires.

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

The closed schema itself fixes `promotion_allowed=false`, `runtime_status=NOT_RUN` and `execution_authority=NONE`. No new sensitive or authority-bearing fields are introduced by CHG-HSL-079.

## 9. Idempotency and ordering

Content addressing makes the Evidence Plane object idempotent for exact replay. The authorization adapter's existing identity tuple remains authoritative for duplicate event suppression after successful chain append.

The bridge does not create ordering semantics of its own. Event ordering remains the responsibility of the existing AuditSink/EvidenceChain.

No mutable overwrite or evidence deletion is permitted to hide a partial append failure.

## 10. Test design

### RED first

Add tests before implementation proving absence of:

- custody module/policy;
- schema-before-write enforcement;
- post-write verification;
- EvidenceVerifier linkage;
- adapter custody binding.

RED must fail for those missing capabilities, not for unrelated repository defects.

### Functional and adversarial tests

Cover:

- valid REGISTERED custody;
- valid LOOKUP_HIT/MISS/EXPIRED and REFUSED custody;
- exact canonical digest, size, content reference and `ev_<id>` custody binding;
- `restricted` classification and bounded retention;
- exact replay idempotency;
- closed-schema rejection before write;
- sensitive-field rejection;
- disabled policy fail-closed;
- invalid trusted correlation/timestamp before write;
- store write failure sanitization;
- store verify false/exception fail-closed;
- intact and tampered stored payload through the existing EvidenceVerifier;
- digest, size, `evidence_id` and `evidence_ref` mismatch failures;
- adapter does not append AuditSink entry when required custody fails;
- AuditSink resolver verification passes for intact object and fails on tamper;
- retry after AuditSink append failure reuses one custody object and creates one final chain entry;
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
- custody/delivery/resolver policies remain disabled unless separately promoted with live evidence;
- `VAL-HSL-RUNNER-L1-LIVE-PROMOTION` remains `BLOCKED / HOLD` until all independent live gates are satisfied.
