# EPIC-43 — Knowledge-Driven Campaign Planner

## 1. Metadata

| Field | Value |
| --- | --- |
| Concept epic ID | `EPIC-43` |
| Slug | `knowledge-driven-campaign-planner` |
| Pillar | `E` — Security Knowledge Fabric |
| Phase | 6 |
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

Campaign content is assembled manually, so planning is not reproducible and its rationale is not recorded.

## 4. Intended outcome

A planner that derives a campaign plan from asset context, threat profile, knowledge snapshot and the active authorization contract, with a recorded rationale.

## 5. Scope and non-goals

### In scope

- Plan derivation inputs and deterministic output
- Rationale trail per selected step
- Contract-aware filtering by intrusiveness and scope
- Plan diffing between runs

### Non-goals

- Executing a plan without human authorization

## 6. Intent architecture

Planner output is a proposal referencing the knowledge snapshot, the contract and the capability registry version; the same inputs must yield the same plan.

## 7. Contracts, data and capabilities

- Campaign plan record
- Selection rationale entry

Contracts are canonical in Git. Where this epic reuses a platform-wide contract, the
canonical definition lives in the
[reference architecture](../../architecture/security-validation-reference-architecture.md)
and in [EPIC-01](EPIC-01-architecture-and-canonical-contracts.md); this document
references it instead of restating it.

## 8. Dependencies and sequencing

- [EPIC-36 — Security Knowledge Fabric](EPIC-36-security-knowledge-fabric.md)
- [EPIC-28 — Rules of Engagement as Code](EPIC-28-rules-of-engagement-as-code.md)
- [EPIC-07 — Capability Registry](EPIC-07-capability-registry.md)

Sequencing follows the phase model in the
[intent document](../../architecture/security-validation-platform-v2-intent.md).
This epic is planned for phase 6.

## 9. Security, risks and failure modes

- Plans over-fitted to available content
- Non-determinism from unpinned inputs

Platform-wide invariants that this epic must not weaken:

- absence of evidence never produces a `PASS` verdict;
- no execution outside an active authorization contract;
- no secrets, tokens, cookies or raw credential material in documentation, telemetry
  or persisted evidence;
- no target outside registered laboratories.

## 10. Deliverables

- Campaign planner specification

## 11. Acceptance criteria

- Identical inputs yield an identical plan
- Every step records why it was selected

## 12. Evidence and validation plan

- Plan records with input version references

Evidence must be referenced from the delivery umbrella issue before the umbrella can
be closed, and this document must record the references in section 15.

## 13. Decisions and open questions

### Decisions taken at intent time

- Plans are proposals; authorization remains human

### Open questions

- How to represent deliberately excluded steps

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
