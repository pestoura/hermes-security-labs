# CHG-HSL-078 — Authorization receipt audit evidence design

**Status:** design approved in conversation; written-spec review pending  
**Date:** 2026-08-16  
**Base:** `5f9440fa73b057390c024c601645b3e10c511300`  
**Scope:** repository-only hardening; no runtime enablement or target effect

## 1. Context

The repository already contains a trusted TB1 receipt-delivery boundary and a verified authorization resolver:

- `TrustedReceiptDelivery` authenticates the local control-plane peer with AF_UNIX peer credentials and delegates receipt verification to the canonical resolver;
- `VerifiedAuthorizationResolver` verifies signed TB1 receipts with the canonical authorization contract, caches only sanitized verified metadata, and resolves only still-live authorization references;
- the WebGoat L1 adapter independently binds the resolved authorization to campaign/run/step, operation/version, capability, intrusiveness, target digest and operation-parameter digest before any effect;
- committed delivery/resolver policies remain `DISABLED / deny / NOT_RUN / execution_authority=none`.

The remaining repository-safe gap in this path is auditable evidence for authorization receipt registration, lookup decisions and refusals. Live AF_UNIX socket provisioning, a real TB1 signer, installed trust material and runtime promotion remain separate governed work.

## 2. Decision

Implement **Option 3: registration + lookup + refusal auditing**.

The authorization path will emit sanitized, deterministic audit records into the **existing canonical LAB_L1 `AuditSink` / EvidenceChain**. No second datastore, ledger, evidence chain, seal or verifier is introduced.

### Alternatives preserved

1. **Registration only — Not selected for MVP.** Smallest change, but does not prove how an authorization reference was subsequently used or denied.
2. **Registration + lookup — Not selected for MVP.** Covers successful use and lookup misses, but leaves the most security-relevant negative decisions without auditable reason codes.
3. **Registration + lookup + refusals — Selected.** Provides the minimum useful PRE_PROMOTION audit trail for positive and negative authorization decisions while remaining repository-only and fail-closed.

A canonical ADR will preserve these alternatives, rationale and future review triggers.

## 3. Architecture

### 3.1 Dedicated audit adapter

Add a dedicated authorization audit adapter under `platform/runner-authorization/`.

Its responsibilities are limited to:

- building one closed public `authorization-receipt-audit/v1` record;
- validating event type, phase, decision, stable reason code and trusted correlation context;
- hashing any authorization reference before persistence;
- appending exactly one event to an injected/existing canonical `AuditSink`;
- exposing the existing sink `seal()` / `verify()` behavior without implementing parallel integrity primitives.

The adapter will not verify receipts, resolve authorization, issue authorization or perform network/runtime actions.

### 3.2 Existing boundaries remain authoritative

`TrustedReceiptDelivery` remains responsible for:

- policy state;
- AF_UNIX peer authentication;
- envelope validation;
- replay/sequence handling;
- delegation to `VerifiedAuthorizationResolver.register_receipt()`.

`VerifiedAuthorizationResolver` remains responsible for:

- canonical signature/trust-store verification;
- memory-only registration;
- expiration/future-window enforcement;
- lookup and eviction semantics.

The new audit adapter observes decisions; it does not replace either boundary.

### 3.3 Minimal integration points

Both existing boundaries receive an **optional injected audit observer**. With no observer, current behavior remains unchanged.

- Delivery emits `REGISTERED` after successful verified registration and emits `REFUSED` for delivery/verification refusals.
- Resolver emits lookup outcomes `LOOKUP_HIT`, `LOOKUP_MISS` and `LOOKUP_EXPIRED`.
- The first WebGoat L1 adapter supplies its already-validated Runner correlation context to resolver lookup so miss/expired decisions are request-bound rather than attributed to untrusted receipt fields.

No audit field may create or expand authorization.

## 4. Trusted audit context

Audit correlation must never be copied from an unverified receipt merely because the field names look valid.

A closed `AuthorizationAuditContext` is supplied by the trusted local composition/request boundary and contains:

- `campaign_id`;
- `run_id`;
- `step_id`;
- `attempt_id`;
- `principal`;
- `correlation_id`.

For WebGoat lookup, these values come from the already schema-validated Runner request/correlation and a fixed Runner principal.

For receipt delivery, the future composition layer supplies trusted correlation independently of the unverified receipt. The current repository tests use explicit bounded fixtures; committed runtime policies remain disabled.

If auditing is configured for a decision and the required trusted context is absent or invalid, the audited authorization path fails closed.

## 5. Public event model

The closed record schema is `authorization-receipt-audit/v1`.

Required semantic fields:

- `schema_version`;
- `event_type`: `REGISTERED | LOOKUP_HIT | LOOKUP_MISS | LOOKUP_EXPIRED | REFUSED`;
- `phase`: `DELIVERY | REGISTRATION | LOOKUP`;
- `decision`: `ACCEPT | DENY`;
- `reason_code`: stable bounded machine-readable code;
- `authorization_ref_sha256`: lowercase SHA-256 of the reference when a reference is present, otherwise `null`;
- `duplicate`: boolean, meaningful for registration replay/idempotency;
- `capability_id`: sanitized verified capability when available, otherwise `null`;
- `intrusiveness_level`: verified value when available, otherwise `null`;
- `promotion_allowed: false`;
- `runtime_status: NOT_RUN`;
- `execution_authority: NONE`.

Correlation/principal data is carried by the canonical `AuditContext`, not duplicated from untrusted payloads into the public record.

## 6. Data minimization and sanitization

The audit record must never contain:

- raw signed receipt JSON;
- signature bytes or base64;
- public/private key material;
- raw target locator or target digest copied from untrusted input;
- raw operation parameters;
- credentials, secrets, tokens, cookies or headers;
- raw invalid authorization references;
- caller-asserted trust/verification state;
- socket credentials beyond the bounded canonical principal label used in `AuditContext`.

Authorization references are persisted only as SHA-256 digests in the public event. Stable refusal codes are persisted; exception strings from lower layers are not.

## 7. Fail-closed behavior

### 7.1 Successful registration

When auditing is enabled for the repository composition test:

1. peer/envelope checks pass;
2. resolver verifies and registers the receipt;
3. audit adapter appends `REGISTERED`;
4. only then is delivery reported as accepted.

If the audit append fails after resolver registration, delivery calls the resolver's existing `forget(authorization_ref)` rollback and returns a stable audit failure. No authorization remains locally resolvable.

### 7.2 Registration refusal

A delivery or canonical receipt-verification refusal remains a denial. The audit adapter attempts to append `REFUSED` with only the stable refusal code and trusted audit context.

If refusal auditing itself fails, the original operation still remains denied. The outward error becomes a stable audit-failure code chained from the original exception; no success path is introduced.

### 7.3 Lookup

Resolver lookup with auditing configured requires trusted request correlation.

- live verified entry -> append `LOOKUP_HIT`, then return verified metadata;
- unknown reference -> append `LOOKUP_MISS`, return `None`;
- stale/future-invalid cached entry -> evict, append `LOOKUP_EXPIRED`, return `None`.

If audit append fails for a would-be lookup hit, resolver returns no authority. Audit availability is therefore part of the authorization success boundary once the observer is configured.

Audit failure during a miss/expired decision cannot turn the denial into success.

## 8. Idempotency and replay

Receipt delivery's existing monotonic sequence and exact-duplicate semantics remain authoritative.

- a first accepted registration produces one `REGISTERED` event;
- an exact duplicate delivery may produce a distinct sanitized duplicate registration observation only if its event identity differs deterministically by the trusted delivery attempt/sequence context;
- out-of-order/replay refusals produce `REFUSED` and never register a second authorization;
- the canonical `AuditSink` replay guard remains in force and is not weakened.

## 9. Policy and runtime posture

No committed policy is enabled by this change.

The following remain invariant:

```text
receipt-delivery-policy = DISABLED / deny / NOT_RUN
resolver-policy = DISABLED / deny / NOT_RUN
execution_authority = none
promotion_allowed = false
signer-human-decision = NO_DECISION
supplier_selection = NO_SELECTION
trust store = ABSENT / NOT_CONFIGURED
real signer = NOT_OBSERVED
Runner target effect = NOT_RUN
campaign = BLOCKED / HOLD
```

No socket is created, no service is restarted, no trust is installed and no provider is contacted.

## 10. Testing strategy

Implementation follows TDD.

Required test groups:

1. closed schema and committed-policy posture;
2. successful registration emits one sanitized `REGISTERED` event;
3. duplicate delivery remains idempotent and auditable;
4. unauthenticated peer, bad envelope, replay and receipt-verification failures emit/refuse correctly without trusting receipt correlation;
5. lookup hit emits `LOOKUP_HIT` with request-bound trusted correlation;
6. unknown lookup emits `LOOKUP_MISS` and no authority;
7. expired/future-invalid cached authorization emits `LOOKUP_EXPIRED`, evicts and denies;
8. audit sink failure after registration rolls back via `forget()`;
9. audit sink failure on lookup hit denies authority;
10. refusal-audit failure never converts denial to success;
11. serialized audit records contain no signature, receipt, key, secret, raw parameters, raw target or raw authorization reference;
12. existing receipt-delivery, resolver and WebGoat adapter suites remain GREEN;
13. full `platform/tests`, security, release-governance, private-VAmPI and Exact-SHA gates pass on the final head and again after merge.

## 11. Governance record

Implementation will add the next canonical ADR for this decision and classify the three alternatives with the repository dispositions introduced by ADR-0012..0014.

Suggested review triggers:

- authorization events move to a production-grade durable/WORM sink;
- more than one Runner adapter needs independent authorization-decision telemetry;
- a generic policy-decision audit framework becomes clearly less complex than dedicated adapters;
- privacy/data-retention requirements change;
- authenticated receipt delivery is promoted to live LAB_L1;
- LAB_L1 evolves into multi-tenant PROD.

## 12. Explicit non-goals

CHG-HSL-078 does not:

- enable receipt delivery or resolver policies;
- configure the AF_UNIX receipt socket;
- install the TB1 trust store;
- select or provision Vault/KMS/HSM;
- issue a real signed authorization receipt;
- change #403;
- authorize HITL or campaign promotion;
- execute WebGoat or any target effect;
- implement production WORM custody or multi-tenant isolation.

## 13. Success criterion

Repository tests can prove, with a single canonical audit chain, that a TB1 authorization receipt was registered, subsequently looked up or denied, and that refusal/expiry paths are auditable without exposing receipt/signature/target/parameter material or creating runtime authority.
