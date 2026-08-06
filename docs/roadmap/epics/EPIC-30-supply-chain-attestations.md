# EPIC-30 — Supply-chain attestations

## 1. Metadata

| Field | Value |
| --- | --- |
| Concept epic ID | `EPIC-30` |
| Slug | `supply-chain-attestations` |
| Pillar | `C` — Image and Capability Factory |
| Phase | 3 |
| Priority | P0 |
| Delivery umbrella | `SVP2-C-02` (issue [#83](https://github.com/pestoura/hermes-security-labs/issues/83)) |
| Document version | 1.0.0 |
| Document date | 2026-08-06 |
| Catalogue | [Epic catalogue 45](../epic-catalogue-45.md) |
| Lifecycle contract | [Architecture documentation lifecycle](../../architecture/architecture-documentation-lifecycle.md) |

## 2. Current status

**INTENT** — nothing described in this document is implemented. Sections 14 and 15
are reserved and must be filled during and after implementation, as required by the
[documentation lifecycle contract](../../architecture/architecture-documentation-lifecycle.md).

| Lifecycle state | Reached |
| --- | --- |
| INTENT | yes |
| IMPLEMENTING | no |
| AS_BUILT | no |
| FINAL | no |

## 3. Problem and motivation

Images and artefacts are consumed without a uniform attestation and verification requirement, so provenance claims are not enforceable.

## 4. Intended outcome

Every project-built artefact carries provenance and is verified before use; unverifiable artefacts are refused.

## 5. Scope and non-goals

### In scope

- Provenance attestation requirements for built images
- Signature verification at consumption
- SBOM generation and retention
- Third-party artefact policy

### Non-goals

- Publishing new public packages in this task

## 6. Intent architecture

Build emits attestation and SBOM; the runtime verifies digest and signature before instantiating any execution image.

## 7. Contracts, data and capabilities

- Attestation record
- SBOM retention policy
- Verification failure semantics

Contracts are canonical in Git. Where this epic reuses a platform-wide contract, the
canonical definition lives in the
[reference architecture](../../architecture/security-validation-reference-architecture.md)
and in [EPIC-01](EPIC-01-architecture-and-canonical-contracts.md); this document
references it instead of restating it.

## 8. Dependencies and sequencing

- [EPIC-06 — Kali Image Factory](EPIC-06-kali-image-factory.md)

Sequencing follows the phase model in the
[intent document](../../architecture/security-validation-platform-v2-intent.md).
This epic is planned for phase 3.

## 9. Security, risks and failure modes

- Verification disabled to unblock operations
- Third-party images without usable provenance

Platform-wide invariants that this epic must not weaken:

- absence of evidence never produces a `PASS` verdict;
- no execution outside an active authorization contract;
- no secrets, tokens, cookies or raw credential material in documentation, telemetry
  or persisted evidence;
- no target outside registered laboratories.

## 10. Deliverables

- Supply-chain attestation specification

## 11. Acceptance criteria

- Unverified artefacts are refused at consumption
- Every accepted image has an SBOM and provenance record

## 12. Evidence and validation plan

- Verification records per image digest

Evidence must be referenced from the delivery umbrella issue before the umbrella can
be closed, and this document must record the references in section 15.

## 13. Decisions and open questions

### Decisions taken at intent time

- Verification failure blocks execution, it does not warn

### Open questions

- Policy for necessary third-party images lacking attestations

## 14. Implementation notes

> Reserved. Populate during implementation with pull request references, deviations
> from intent, and decisions taken while building. Do not delete this heading.

_Not started._

## 15. As-built / final architecture

> Reserved. Populate when the delivery umbrella reaches completion. Must record what
> was actually built, evidence links, and every divergence from sections 6 to 11.
> No umbrella may be closed while this section is empty.

_Not started._

## 16. Document change log

| Date | Version | Change |
| --- | --- | --- |
| 2026-08-06 | 1.0.0 | Initial intent document created from the concept epic catalogue. |
