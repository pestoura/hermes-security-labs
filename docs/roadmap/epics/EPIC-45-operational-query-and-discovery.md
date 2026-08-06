# EPIC-45 — Operational Query and Discovery

## 1. Metadata

| Field | Value |
| --- | --- |
| Concept epic ID | `EPIC-45` |
| Slug | `operational-query-and-discovery` |
| Pillar | `E` — Security Knowledge Fabric |
| Phase | 7 |
| Priority | P1 |
| Delivery umbrella | `SVP2-E-02` (issue [#87](https://github.com/pestoura/hermes-security-labs/issues/87)) |
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

Operators cannot ask direct questions such as which controls were validated against a technique, or which assets remain unvalidated for a vulnerability.

## 4. Intended outcome

A defined query surface answering operational questions across knowledge, campaigns, evidence and findings, with reproducible results.

## 5. Scope and non-goals

### In scope

- Canonical operational question catalogue
- Query surface and result contracts
- Snapshot-scoped reproducible answers
- Access control on query results

### Non-goals

- Exposing raw evidence through the query surface

## 6. Intent architecture

Queries execute against pinned snapshots plus evidence indexes; results carry the snapshot reference so answers are reproducible and auditable.

## 7. Contracts, data and capabilities

- Query request and result schema
- Result provenance reference

Contracts are canonical in Git. Where this epic reuses a platform-wide contract, the
canonical definition lives in the
[reference architecture](../../architecture/security-validation-reference-architecture.md)
and in [EPIC-01](EPIC-01-architecture-and-canonical-contracts.md); this document
references it instead of restating it.

## 8. Dependencies and sequencing

- [EPIC-36 — Security Knowledge Fabric](EPIC-36-security-knowledge-fabric.md)
- [EPIC-43 — Knowledge-Driven Campaign Planner](EPIC-43-knowledge-driven-campaign-planner.md)
- [EPIC-33 — Finding and remediation lifecycle](EPIC-33-finding-and-remediation-lifecycle.md)

Sequencing follows the phase model in the
[intent document](../../architecture/security-validation-platform-v2-intent.md).
This epic is planned for phase 7.

## 9. Security, risks and failure modes

- Query results interpreted as assurance
- Sensitive data exposure through aggregation

Platform-wide invariants that this epic must not weaken:

- absence of evidence never produces a `PASS` verdict;
- no execution outside an active authorization contract;
- no secrets, tokens, cookies or raw credential material in documentation, telemetry
  or persisted evidence;
- no target outside registered laboratories.

## 10. Deliverables

- Operational query specification
- Canonical question catalogue

## 11. Acceptance criteria

- Every result cites its snapshot and evidence scope
- Raw or unredacted evidence is never returned

## 12. Evidence and validation plan

- Question catalogue with sample result shapes

Evidence must be referenced from the delivery umbrella issue before the umbrella can
be closed, and this document must record the references in section 15.

## 13. Decisions and open questions

### Decisions taken at intent time

- Query results are read-only projections

### Open questions

- Whether ad hoc queries are permitted alongside canonical ones

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
