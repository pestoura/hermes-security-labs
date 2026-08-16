# ADR-0015 — Authorization receipt audit evidence

- **Status:** Accepted
- **Date:** 2026-08-16
- **Decision owners:** Hermes Security Labs architecture / assurance
- **Related change:** CHG-HSL-078
- **Supersedes:** none
- **Superseded by:** none

## Context

The repository already contains a fail-closed TB1 authorization chain:

- `TrustedReceiptDelivery` authenticates the local delivery peer and delegates receipt verification;
- `VerifiedAuthorizationResolver` verifies signed receipts with the canonical authorization contract and stores only sanitized `VerifiedAuthorization` metadata in memory;
- target-bound Runner adapters independently rebind verified authorization metadata to the exact request before any effect;
- all committed authorization/delivery policies remain `DISABLED / deny / NOT_RUN / execution_authority=none`.

The missing repository-level assurance evidence is a deterministic audit trail showing whether a receipt was registered, whether a later authorization lookup succeeded, missed or expired, and why a delivery or registration was refused.

This trail must not create a second ledger, expose receipt/signature/target/parameter material, infer trusted correlation from unverified receipts, or turn repository readiness into execution authority.

## Decision

Use a **dedicated authorization-receipt audit adapter** that records registration, lookup and refusal decisions into the existing canonical LAB_L1 `AuditSink` / EvidenceChain.

The selected event coverage is:

- `REGISTERED`;
- `LOOKUP_HIT`;
- `LOOKUP_MISS`;
- `LOOKUP_EXPIRED`;
- `REFUSED`.

The adapter is observation-only. Receipt verification, delivery peer authentication, resolver cache semantics and target-bound authorization binding remain owned by their existing components.

When an audit observer is configured, audit availability becomes part of the positive authorization path: a registration or lookup hit that cannot be audited fails closed. A denial remains denial even if refusal auditing itself fails.

Trusted audit correlation comes only from the surrounding trusted composition/request boundary, never from an unverified receipt.

## Consequences

### Positive

- Positive and negative authorization decisions become traceable through one canonical append-only/hash-linked audit chain.
- PRE_PROMOTION evidence can distinguish registration, successful use, lookup miss, expiry and refusal without storing raw security-sensitive payloads.
- No competing EvidenceChain, seal, datastore or verifier is introduced.
- Existing delivery/resolver behavior remains backward compatible when no observer is configured.
- Audit failure cannot create execution authority.

### Negative

- Delivery and resolver code gain a small optional observer integration surface.
- When auditing is configured, audit availability becomes a dependency of successful registration/lookup.
- Request-bound trusted context must be supplied correctly by composition/adapter layers; missing context must fail closed rather than being reconstructed from untrusted receipt fields.
- More negative-path audit events increase evidence volume compared with registration-only coverage.

## Security implications

- Raw receipt JSON, signature/base64, public/private key material, raw target locators, raw operation parameters, credentials, secrets, tokens, cookies and headers are forbidden from the public audit record.
- Canonical authorization references are persisted only as SHA-256 digests; malformed or unbounded references are represented as `null`.
- Capability and intrusiveness metadata may be recorded only when derived from already-verified authorization metadata.
- Stable reason codes are recorded; lower-layer exception strings are not.
- Trusted campaign/run/step/attempt/principal/correlation values are carried by canonical `AuditContext`, not copied from the receipt.
- Exact duplicate delivery remains idempotent and does not append a second registration audit event.
- `promotion_allowed=false`, `runtime_status=NOT_RUN` and `execution_authority=NONE` remain locked in every public event.

## Alternatives considered

### Option 1 — Registration only

**Disposition:** Not selected for MVP.

**Advantages:** smallest integration and evidence volume.

**Limitations:** cannot prove whether a registered authorization reference was later used, missed or expired; negative authorization behavior remains weakly attributable.

**Review trigger:** reconsider only if evidence-volume/privacy constraints make lookup/refusal telemetry disproportionate and another independent decision-trace mechanism exists.

### Option 2 — Registration + lookup

**Disposition:** Not selected for MVP.

**Advantages:** captures successful use and lookup misses with moderate complexity.

**Limitations:** omits the most security-relevant delivery/verification refusal reasons, weakening proof of fail-closed negative behavior.

**Review trigger:** reconsider if refusal evidence is provided authoritatively by a separate canonical policy-decision audit source.

### Option 3 — Registration + lookup + refusals

**Disposition:** Selected.

**Advantages:** minimum complete repository audit trail for positive and negative authorization decisions; directly supports PRE_PROMOTION assurance and negative tests.

**Limitations:** slightly larger observer surface and evidence volume.

**Review trigger:** revisit the dedicated adapter if authorization decision telemetry becomes a general cross-domain concern better served by one generic policy-decision audit framework.

## Evidence and validation

Acceptance requires:

- tests-first RED for the new adapter/integration contracts;
- closed JSON Schema and data-minimization tests;
- registration, duplicate, lookup hit/miss/expired and refusal tests;
- rollback test proving post-registration audit failure removes local resolvability;
- lookup-hit audit failure proving no authority is returned;
- full existing receipt delivery/resolver/WebGoat regressions;
- repository security/release/private-source gates;
- Exact-SHA validation before and after merge.

Live socket delivery, real signer/trust, runtime promotion and target effect are explicitly outside this ADR's acceptance evidence.

## Review triggers

Re-evaluate this decision when any of the following becomes true:

1. authorization events move to a production-grade durable/WORM sink;
2. multiple Runner adapters require independent authorization-decision telemetry and dedicated integration becomes repetitive;
3. a generic policy-decision audit framework becomes demonstrably simpler than dedicated adapters without weakening domain boundaries;
4. privacy/data-retention requirements change materially;
5. authenticated receipt delivery is promoted to live LAB_L1;
6. LAB_L1 evolves into multi-tenant production operation;
7. the current evidence volume or success-path dependency becomes operationally disproportionate.
