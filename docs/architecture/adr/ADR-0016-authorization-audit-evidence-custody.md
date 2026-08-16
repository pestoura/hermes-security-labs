# ADR-0016 — Authorization audit evidence custody

- **Status:** Accepted
- **Date:** 2026-08-16
- **Decision owners:** Hermes Security Labs architecture / assurance
- **Related change:** CHG-HSL-079
- **Supersedes:** none
- **Superseded by:** none

## Context

ADR-0015 / CHG-HSL-078 added a repository-only, fail-closed audit trail for TB1 authorization receipt registration, lookup and refusal decisions. The canonical authorization audit adapter builds sanitized `authorization-receipt-audit/v1` records and appends references to the existing LAB_L1 `AuditSink` / EvidenceChain.

The current adapter can therefore prove the hash-linked audit decision sequence, but the referenced authorization-audit JSON object is not yet persisted through the existing Evidence Plane. This is insufficient for a future live acceptance path that must independently resolve and verify the exact object behind an `evidence://...` reference. The live-promotion campaign consequently still lists live audit/outcome persistence as an open blocker.

The next increment must close only that repository-level custody gap. It must not create a second datastore, chain, seal or verifier; must not enable receipt delivery/resolver policies; and must not turn repository readiness into execution or promotion authority.

## Decision

Select **Option A — dedicated minimal authorization-audit custody bridge over the existing Evidence Plane**.

The bridge will:

1. accept only a schema-valid sanitized `authorization-receipt-audit/v1` record produced by the canonical authorization-audit contract;
2. independently canonicalize and hash the exact public JSON payload;
3. persist that payload through the existing injected Evidence Plane store under a dedicated disabled-by-default policy;
4. require successful post-write store verification before returning success;
5. return the canonical `evidence_ref` and SHA-256 for the exact persisted object;
6. prove that reference and digest through the existing `LocalEvidenceVerifier` / `EvidenceVerifier` contract;
7. allow the existing authorization audit adapter to append the verified `evidence_ref` and identical digest to the existing `AuditSink` / EvidenceChain;
8. remain content-addressed and idempotent for exact replay;
9. fail closed on schema, digest, reference, policy, storage, verification or linkage mismatch.

The bridge owns custody only. Receipt verification, authorization decisions, audit event construction, AuditSink chain semantics and target-bound authorization remain in their existing components.

## Alternatives considered

### Option A — Dedicated minimal custody bridge over the existing Evidence Plane

**Disposition:** Selected.

**Advantages:**

- closes the missing object-custody/verifiability gap with the smallest bounded change;
- mirrors an already accepted provider-neutral Evidence Plane pattern without changing canonical store or verifier responsibilities;
- keeps authorization-audit domain validation separate from generic Evidence Plane storage;
- permits `AuditSink.verify(resolver=...)` to prove the referenced object as well as chain integrity;
- remains migration-compatible with later durable/WORM custody without changing the public audit record contract.

**Limitations:**

- adds one domain-specific custody adapter and policy;
- creates another small integration surface that may become repetitive if many audit domains adopt the same pattern.

**Review triggers:**

- three or more additional audit domains require materially identical custody bridges;
- a production durable/WORM Evidence Plane backend becomes operational;
- multi-tenant production operation requires centralized retention/tenant policy enforcement;
- duplicated custody code becomes harder to assure than a generic, schema-bound audit-custody framework.

### Option B — Make the generic AuditSink persist referenced payloads itself

**Disposition:** Not selected for MVP.

**Advantages:**

- one call could persist the object and append the chain entry;
- less domain wiring at call sites.

**Limitations:**

- expands the canonical AuditSink from chain/reference integrity into payload custody;
- changes a cross-domain primitive for one domain-specific gap;
- increases regression and authority-boundary risk across existing AuditSink consumers;
- makes schema-specific validation and retention policy ownership less explicit.

**Review trigger:** reconsider only if payload persistence becomes a universal invariant of every AuditSink append and the repository can migrate all consumers atomically with equivalent fail-closed evidence.

### Option C — Introduce a generic audit-custody framework now

**Disposition:** Deferred.

**Advantages:**

- could reduce repeated bridge code across signer, authorization and future decision-audit domains;
- could centralize common content-addressing, retention and verifier linkage behavior.

**Limitations:**

- abstraction boundary is not yet proven by enough independent domains;
- risks coupling different schemas, lifecycle rules and failure semantics prematurely;
- adds design, testing and migration complexity before a demonstrated MVP need.

**Review trigger:** reconsider when at least three independent audit domains exhibit the same stable custody contract with no domain-specific divergence.

### Option D — Keep authorization audit chain-only and defer object custody

**Disposition:** Rejected for live promotion.

**Advantages:**

- no additional repository code now;
- existing hash-linked decision sequence remains available.

**Limitations:**

- the `evidence://authorization-receipt-audit/<digest>` reference cannot independently resolve to the exact persisted object;
- does not close the live audit/outcome persistence blocker;
- weakens PRE_PROMOTION assurance because chain integrity alone does not prove custody of the referenced record.

**Review trigger:** none for LAB_L1 live promotion. It may remain acceptable only for repository-only tests where no custody claim is made.

## Security implications

- Only the sanitized public `authorization-receipt-audit/v1` JSON object may enter custody.
- Raw receipt JSON, signatures, public/private key material, raw target locators, operation parameters, credentials, tokens, cookies, headers and lower-layer exception text remain forbidden.
- The canonical authorization-reference value is never persisted; only its SHA-256 already present in the sanitized record is eligible.
- The Evidence Plane store is injected; the custody bridge must not instantiate or invent a second datastore.
- Existing canonical serialization, content addressing, `LocalEvidenceVerifier` and `AuditSink` remain the sole corresponding primitives.
- Store write without successful verification is failure.
- Evidence reference/digest mismatch is failure.
- Audit append mismatch or resolver verification failure is failure.
- No failure path may create or preserve execution authority.

## Locked boundaries

This decision does **not** authorize or implement:

- receipt-delivery AF_UNIX endpoint promotion;
- resolver/delivery policy enablement;
- Vault/KMS/HSM/PKCS11 provider selection or provisioning;
- trust-store installation or key provisioning;
- live signer/provider attestation;
- Runner dispatch, target effect or Kali/scanner execution;
- live policy promotion;
- a production WORM backend or multi-tenant isolation;
- automatic Human-in-the-Loop approval.

Canonical state remains `DISABLED / deny / NOT_RUN`, `promotion_allowed=false`, `execution_authority=NONE`, and the live-promotion campaign remains `BLOCKED / HOLD`.

## Acceptance evidence

Acceptance of CHG-HSL-079 requires, at minimum:

- tests-first RED for the new custody contract before implementation;
- closed policy and fail-closed policy-state tests;
- schema validation before any write;
- exact canonical payload SHA-256 and content-addressed `evidence_ref` tests;
- post-write store verification tests;
- intact/tampered/digest-mismatch/reference-mismatch `EvidenceVerifier` tests;
- exact replay/idempotency tests;
- proof that forbidden sensitive fields cannot enter the persisted record;
- linkage test proving the AuditSink entry references the exact verified Evidence Plane object;
- backend exception sanitization tests;
- full authorization-audit, Evidence Plane and platform regressions;
- repository security/release/private-source gates;
- Exact-SHA validation before merge and after merge.

Live runtime acceptance remains outside this ADR and requires separate evidence and explicit Human-in-the-Loop promotion.

## Review triggers

Re-evaluate this decision when any of the following becomes true:

1. a durable/WORM Evidence Plane backend is selected and operational;
2. authorization receipt delivery is promoted to live LAB_L1;
3. LAB_L1 becomes multi-tenant or production-facing;
4. three or more additional audit domains require the same custody pattern;
5. retention/privacy rules require materially different treatment of authorization-decision evidence;
6. the custody bridge becomes a material availability dependency on a live authorization success path;
7. a generic audit-custody abstraction can be demonstrated to reduce complexity without weakening domain validation or fail-closed boundaries.
