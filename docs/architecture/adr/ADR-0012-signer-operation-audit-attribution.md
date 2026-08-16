# ADR-0012 — Dedicated signer operation audit attribution adapter

- **Status:** Accepted
- **Date:** 2026-08-16
- **Decision source:** CHG-HSL-075 / PR #408
- **Supersedes:** none
- **Superseded by:** none

## Context

The provider-neutral signing boundary introduced a public signing request/result contract, but LAB_L1 assurance also needs operations to be attributable without persisting private material, raw signing payloads, credentials or provider secrets.

The repository already had a canonical `AuditSink` and EvidenceChain. The architectural question was whether signer-specific attribution should be added directly to that generic sink, embedded into the cryptographic `SignatureEnvelope`, or translated through a dedicated domain adapter that feeds the existing audit/evidence chain.

The design must preserve separation between cryptographic result, governance attribution and evidence custody. It must not create execution authority, provider selection, trust installation or a second ledger.

## Decision

**Selected:** use a dedicated signer-operation audit attribution adapter that translates `SigningRequest + SigningResult + attribution context` into the closed public `signer-operation-audit/v1` event and appends that event through the existing canonical AuditSink/EvidenceChain.

The adapter owns signer-domain translation only. AuditSink remains generic; `SignatureEnvelope` remains a cryptographic result contract. Raw signing payloads, raw signature/base64, private keys, credentials, tokens and provider secrets are excluded from the event.

The decision is structural. It grants no runtime, signer, trust or promotion authority.

## Positive consequences

- Keeps signer-domain semantics out of the generic AuditSink schema.
- Keeps cryptographic result contracts independent from governance attribution.
- Reuses one canonical AuditSink, EvidenceChain and seal path rather than creating a signer-specific ledger.
- Supports provider-neutral attribution through public identifiers, hashes and correlation metadata.
- Makes later provider-specific audit evidence attachable without changing the cryptographic contract.

## Negative consequences

- Adds a small adapter and event schema that must be maintained beside the signer contract.
- Requires explicit mapping between signer result fields and audit event fields.
- A future proliferation of domain-specific audit adapters could justify a more generic translation framework.

## Security implications

- The adapter must fail closed on request/result mismatch or malformed attribution.
- The event must remain public/auditable only and must not contain key material, secrets, credentials or raw signing payload/signature data.
- CI/test signer events must remain mechanically test-only and non-admissible for LAB_L1 custody/promotion evidence.
- `promotion_allowed=false`, `runtime_status=NOT_RUN` and `execution_authority=NONE` remain explicit invariants.
- Reusing AuditSink does not make the audit event proof of external signer custody or provider authenticity.

## Alternatives considered

### A. Dedicated signer audit adapter feeding the existing AuditSink/EvidenceChain — **Selected**

Chosen because it preserves separation of concerns while reusing the canonical audit/evidence primitives. It is the smallest provider-neutral implementation that makes signer operations attributable.

### B. Add signer-specific fields directly to the generic AuditSink — **Not selected for MVP**

This could reduce one translation layer, but it couples a cross-domain generic component to signer semantics and risks turning the AuditSink schema into a monolithic union of every future domain.

Reconsider if the generic AuditSink evolves into a deliberately typed event envelope with stable extension semantics and the adapter layer becomes demonstrably redundant.

### C. Put principal/provider/correlation attribution inside `SignatureEnvelope` — **Not selected for MVP**

This would simplify some call sites but mixes governance attribution with a cryptographic result. It would make signer results harder to reuse and would blur the boundary between proof of signature and proof of who/what requested or observed it.

Reconsider only if a future canonical cryptographic envelope is explicitly redesigned as a complete signed operation receipt rather than a signature result.

## Evidence and validation

CHG-HSL-075 / PR #408 implemented the selected path and passed the repository validation gates before and after merge. The subsequent CHG-HSL-076 reused the event without changing this decision, confirming that the adapter boundary can feed Evidence Plane verification without modifying the AuditSink or signer result contract.

This ADR records the architectural rationale; it does not itself constitute runtime or provider evidence.

## Review triggers

Review this decision when any of the following occurs:

- signer-specific additions begin to pressure or duplicate the generic AuditSink schema;
- multiple signer event families require materially different adapters;
- production SIEM/export requirements demand a canonical typed audit event envelope;
- attribution-to-evidence-chain coupling becomes operationally expensive or error-prone;
- a future signature receipt standard intentionally combines cryptographic result and governance attribution;
- the number of domain audit adapters makes a generic translation framework materially simpler without weakening isolation.
