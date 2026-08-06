# EPIC-02 — Single source of truth for runtime

## 1. Metadata

| Field | Value |
| --- | --- |
| Concept epic ID | `EPIC-02` |
| Slug | `single-source-of-truth-for-runtime` |
| Pillar | `A` — Governance and Architecture |
| Phase | 1 |
| Priority | P0 |
| Delivery umbrella | `SVP2-A-01` (issue [#76](https://github.com/pestoura/hermes-security-labs/issues/76)) |
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

Runtime facts (labs, runners, images, bindings, capabilities) are declared in several places, so drift between Git, deployed state and documentation is possible and undetected.

## 4. Intended outcome

One versioned declarative source describes runtime intent; deployed state is compared against it and divergence is reported, never silently reconciled.

## 5. Scope and non-goals

### In scope

- Declarative runtime manifest inventory in Git
- Drift semantics IN_SYNC / DRIFT_DETECTED / UNKNOWN as a documented contract
- Rules for what may never be authoritative outside Git

### Non-goals

- Changing the existing deployment tracking implementation
- Automatic remediation of drift

## 6. Intent architecture

Git holds intent. A read-only comparator derives observed state and emits a tri-state verdict. Absence of evidence maps to UNKNOWN, never to IN_SYNC.

## 7. Contracts, data and capabilities

- Runtime manifest schema
- Drift verdict record with commit, inventory hashes and counters

Contracts are canonical in Git. Where this epic reuses a platform-wide contract, the
canonical definition lives in the
[reference architecture](../../architecture/security-validation-reference-architecture.md)
and in [EPIC-01](EPIC-01-architecture-and-canonical-contracts.md); this document
references it instead of restating it.

## 8. Dependencies and sequencing

- [EPIC-01 — Architecture and canonical contracts](EPIC-01-architecture-and-canonical-contracts.md)

Sequencing follows the phase model in the
[intent document](../../architecture/security-validation-platform-v2-intent.md).
This epic is planned for phase 1.

## 9. Security, risks and failure modes

- Manifest divergence from actual container state
- Tri-state collapsing into boolean under pressure

Platform-wide invariants that this epic must not weaken:

- absence of evidence never produces a `PASS` verdict;
- no execution outside an active authorization contract;
- no secrets, tokens, cookies or raw credential material in documentation, telemetry
  or persisted evidence;
- no target outside registered laboratories.

## 10. Deliverables

- Documented source-of-truth policy
- Drift contract specification

## 11. Acceptance criteria

- Every runtime asset has exactly one authoritative declaration
- UNKNOWN is produced whenever evidence is missing or unparsable

## 12. Evidence and validation plan

- Drift verdict samples recorded in campaign evidence

Evidence must be referenced from the delivery umbrella issue before the umbrella can
be closed, and this document must record the references in section 15.

## 13. Decisions and open questions

### Decisions taken at intent time

- Git is authoritative; GitHub issues are a working view

### Open questions

- Whether image digests are pinned per environment or per release

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
