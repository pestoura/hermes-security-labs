# ADR-0013 — Minimal dedicated custody for signer trust manifests

- **Status:** Accepted — implementation tracked by CHG-HSL-077
- **Date:** 2026-08-16
- **Decision source:** CHG-HSL-077 design approval
- **Supersedes:** none
- **Superseded by:** none

## Context

CHG-HSL-074 introduced a deterministic public `signer-trust-manifest/v1` that binds one already-verified external signer identity/provenance to one already-reviewed trust-store generation. The human signer decision contract requires a future `trust_store_manifest` evidence reference plus exact SHA-256, but CHG-HSL-074 deliberately did not persist that manifest or imply operational trust binding.

The architectural question is how to make the manifest verifiable in the Evidence Plane without over-coupling the MVP to additional chain logic or prematurely generalising all evidence custody.

## Decision

**Selected:** implement a dedicated, minimal custody bridge for `signer-trust-manifest/v1`.

The bridge validates the existing closed schema, independently recomputes and verifies `manifest_id`, canonical-JSON encodes the public manifest, persists only that exact public object through an injected existing Evidence Plane store, requires post-write integrity verification and returns a canonical evidence reference plus digest. Later verification uses the existing `LocalEvidenceVerifier`.

The canonical policy remains `DISABLED / deny / NOT_RUN / execution_authority=none`. Tests may enable a disposable copy only against temporary storage.

This decision does not install trust, select a provider, provision keys, change #403, grant execution authority or enable LAB_L1 promotion.

## Positive consequences

- Produces the exact evidence reference/digest primitive needed by the future human decision contract.
- Reuses the existing Evidence Plane store and verifier rather than introducing competing integrity semantics.
- Independently detects schema-valid manifest mutation with stale/reused `manifest_id`.
- Keeps the immediate change small, provider-neutral and testable.
- Leaves AuditSink/EvidenceChain coupling optional until a concrete consumer requires it.

## Negative consequences

- Adds another narrow custody adapter beside signer-audit custody.
- Repeats a small amount of policy/persistence plumbing that may later justify abstraction.
- Does not immediately place the trust manifest into the AuditSink/EvidenceChain.

## Security implications

- Schema validation and manifest-id recomputation occur before any write.
- Only closed-schema public manifest data is persisted; no private key, raw signing payload/signature, credential, token or provider secret is admitted.
- Missing store capabilities, backend errors, failed integrity verification, tamper, digest mismatch or invalid manifest identity fail closed.
- `promotion_allowed=false`, `runtime_status=NOT_RUN`, `execution_authority=NONE`, no trust installation and no provider selection remain explicit.
- Custody of a public trust manifest is not proof that the referenced provider, signer or trust store has been observed live.

## Alternatives considered

### A. Dedicated minimal signer-trust-manifest custody bridge — **Selected**

Chosen because it is the smallest coherent implementation that makes the existing manifest content-addressed and independently verifiable using the canonical Evidence Plane.

### B. Custody plus immediate AuditSink/EvidenceChain linkage — **Deferred / Not selected for MVP**

This would provide immediate hash-chain traceability but is not required to satisfy the current evidence-reference contract and would add coupling before a demonstrated consumer requires it.

Reconsider when PRE_PROMOTION packaging explicitly requires trust-manifest chain membership, when a reviewer requires chronological audit linkage, or when the same object must participate in a sealed multi-evidence package.

### C. Generic public-evidence custody framework — **Deferred / Not selected for MVP**

A generic framework could reduce future adapter duplication, but the repository currently has too few materially similar custody consumers to justify a new abstraction layer safely.

Reconsider when at least four materially similar custody adapters exist, when repeated policy/retention code becomes a measurable maintenance problem, or when a production WORM/multi-tenant backend needs one common projection contract.

## Evidence and validation

The architectural design is recorded in `docs/superpowers/specs/2026-08-16-signer-trust-manifest-custody-design.md`. Implementation and exact-SHA CI evidence are tracked under CHG-HSL-077 and are not claimed by this ADR until observed.

## Review triggers

Review this decision when:

- four or more materially similar public-evidence custody adapters exist;
- PRE_PROMOTION requires signer trust manifests to participate directly in AuditSink/EvidenceChain sealing;
- a production WORM backend becomes available;
- multi-tenant evidence custody is introduced;
- repeated retention/policy/projection logic becomes costly or inconsistent;
- the Evidence Plane store/verifier contract changes materially.
