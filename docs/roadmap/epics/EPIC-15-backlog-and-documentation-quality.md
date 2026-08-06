# EPIC-15 — Backlog and documentation quality

## 1. Metadata

| Field | Value |
| --- | --- |
| Concept epic ID | `EPIC-15` |
| Slug | `backlog-and-documentation-quality` |
| Pillar | `A` — Governance and Architecture |
| Phase | 1 |
| Priority | P1 |
| Delivery umbrella | `SVP2-A-03` (issue [#78](https://github.com/pestoura/hermes-security-labs/issues/78)) |
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

Concept-level planning and delivery-level backlog were maintained separately, and documentation could describe intent without recording what was actually built.

## 4. Intended outcome

A governed documentation and backlog system where 45 concept epics map to 21 delivery umbrellas and every epic document evolves intent to as-built to final.

## 5. Scope and non-goals

### In scope

- Concept epic catalogue and machine-readable registry
- 45 to 21 mapping maintained in Git
- Documentation lifecycle contract and Definition of Done
- Automated documentation and mapping tests

### Non-goals

- Opening 45 new GitHub issues
- Changing the scope of existing umbrella issues

## 6. Intent architecture

Concept registry references umbrella identifiers; documentation tests enforce completeness, uniqueness, link resolution and section presence.

## 7. Contracts, data and capabilities

- Concept epic record schema
- Epic document mandatory sections
- Documentation lifecycle states

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

- Catalogue drifting from the delivery backlog
- Documents becoming templates without content

Platform-wide invariants that this epic must not weaken:

- absence of evidence never produces a `PASS` verdict;
- no execution outside an active authorization contract;
- no secrets, tokens, cookies or raw credential material in documentation, telemetry
  or persisted evidence;
- no target outside registered laboratories.

## 10. Deliverables

- Epic catalogue, per-epic documents, lifecycle contract, tests

## 11. Acceptance criteria

- Exactly 45 concept epic documents exist and validate
- Every concept epic maps to an existing umbrella

## 12. Evidence and validation plan

- Documentation and roadmap test runs

Evidence must be referenced from the delivery umbrella issue before the umbrella can
be closed, and this document must record the references in section 15.

## 13. Decisions and open questions

### Decisions taken at intent time

- Concept epics never replace umbrella issues as delivery units

### Open questions

- When a concept epic should be promoted into its own umbrella

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
