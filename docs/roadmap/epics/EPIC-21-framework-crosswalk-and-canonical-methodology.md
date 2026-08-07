# EPIC-21 — Framework Crosswalk and canonical methodology

## 1. Metadata

| Field | Value |
| --- | --- |
| Concept epic ID | `EPIC-21` |
| Slug | `framework-crosswalk-and-canonical-methodology` |
| Pillar | `E` — Security Knowledge Fabric |
| Phase | 5 |
| Priority | P0 |
| Delivery umbrella | `SVP2-E-01` (issue [#86](https://github.com/pestoura/hermes-security-labs/issues/86)) |
| Document version | 1.1.0 |
| Document date | 2026-08-07 |
| Catalogue | [Epic catalogue 45](../epic-catalogue-45.md) |
| Lifecycle contract | [Architecture documentation lifecycle](../../architecture/architecture-documentation-lifecycle.md) |

## 2. Current status

**INTENT** — this concept remains intentionally unpromoted. PR #146 provides generic provenance, relation and confidence primitives for the Security Knowledge Fabric, but it does not implement the canonical framework crosswalk or the end-to-end validation methodology required by EPIC-21.

| Lifecycle state | Reached |
| --- | --- |
| INTENT | yes |
| IMPLEMENTING | no |
| AS_BUILT | no |
| FINAL | no |

The following EPIC-21-specific capabilities remain `NOT_IMPLEMENTED` / `NOT_RUN`:

- canonical framework crosswalk records between methodology phases and external frameworks;
- declared mapping relation types and governed confidence semantics specific to the crosswalk;
- canonical validation methodology lifecycle from scoping through reporting;
- versioned framework mapping datasets and coverage summaries;
- consumer integration into planning/reporting.

Generic `derive_relation()` support from PR #146 is a reusable substrate, not evidence that a framework crosswalk exists.

## 3. Problem and motivation

Framework references (ATT&CK, CWE, CAPEC, NIST, OWASP, PTES) are used informally, so coverage claims cannot be substantiated or compared.

## 4. Intended outcome

A canonical crosswalk with declared confidence levels, plus a canonical methodology describing how a validation activity is structured end to end.

## 5. Scope and non-goals

### In scope

- Crosswalk between methodology phases and external frameworks
- Confidence levels for each mapping
- Canonical activity lifecycle from scoping to reporting

### Non-goals

- Claiming formal certification or compliance with any framework

## 6. Intent architecture

The crosswalk is data, not prose: each mapping carries source, target, relation type and confidence, and is consumed by planning and reporting.

## 7. Contracts, data and capabilities

- Crosswalk record schema
- Confidence level definitions

Contracts are canonical in Git. Where this epic reuses a platform-wide contract, the canonical definition lives in the [reference architecture](../../architecture/security-validation-reference-architecture.md) and in [EPIC-01](EPIC-01-architecture-and-canonical-contracts.md); this document references it instead of restating it.

## 8. Dependencies and sequencing

- [EPIC-01 — Architecture and canonical contracts](EPIC-01-architecture-and-canonical-contracts.md)

Sequencing follows the phase model in the [intent document](../../architecture/security-validation-platform-v2-intent.md). This epic is planned for phase 5.

## 9. Security, risks and failure modes

- Mappings presented as authoritative equivalence
- Framework versions changing under stable mapping ids
- Incorrectly treating generic knowledge relations as a governed crosswalk

Platform-wide invariants that this epic must not weaken:

- absence of evidence never produces a `PASS` verdict;
- no execution outside an active authorization contract;
- no secrets, tokens, cookies or raw credential material in documentation, telemetry or persisted evidence;
- no target outside registered laboratories.

## 10. Deliverables

- Crosswalk specification and canonical methodology document

## 11. Acceptance criteria

- Every mapping declares relation type and confidence
- Documents use aligned or mapped, never certified or compliant

These criteria are not yet met by a dedicated crosswalk implementation.

## 12. Evidence and validation plan

- Crosswalk coverage summary
- Mapping records with source/target/relation/confidence
- Methodology lifecycle conformance evidence

## 13. Decisions and open questions

### Decisions taken

- Mappings are advisory inputs, not compliance evidence.
- PR #146 is a dependency/substrate only and does not promote EPIC-21.

### Open questions

- How to version mappings when upstream frameworks change

## 14. Implementation notes

> Reserved. Populate during implementation with pull request references, deviations from intent, and decisions taken while building. Do not delete this heading.

- PR #146 supplies generic knowledge provenance/relation primitives only.
- No canonical crosswalk or methodology implementation is claimed.
- `NO_RUNTIME_CHANGE`.

## 15. As-built / final architecture

> Reserved. Populate when the delivery umbrella reaches completion. Must record what was actually built, evidence links, and every divergence from sections 6 to 11. No umbrella may be closed while this section is empty.

_Not started. EPIC-21 remains INTENT._

## 16. Document change log

| Date | Version | Change |
| --- | --- | --- |
| 2026-08-06 | 1.0.0 | Initial intent document created from the concept epic catalogue. |
| 2026-08-07 | 1.1.0 | Clarified that PR #146 is shared substrate only; crosswalk/methodology remain NOT_IMPLEMENTED/NOT_RUN and lifecycle remains INTENT. |
