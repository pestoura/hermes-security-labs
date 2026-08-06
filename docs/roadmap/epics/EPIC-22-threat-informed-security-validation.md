# EPIC-22 — Threat-Informed Security Validation

## 1. Metadata

| Field | Value |
| --- | --- |
| Concept epic ID | `EPIC-22` |
| Slug | `threat-informed-security-validation` |
| Pillar | `F` — Threat-Informed Validation |
| Phase | 7 |
| Priority | P1 |
| Delivery umbrella | `SVP2-F-01` (issue [#88](https://github.com/pestoura/hermes-security-labs/issues/88)) |
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

Validation activities are selected by tool availability rather than by relevant adversary behaviour for the asset under test.

## 4. Intended outcome

Threat profiles drive campaign content: relevant techniques are selected from threat intelligence and asset context, not from tool catalogues.

## 5. Scope and non-goals

### In scope

- Threat profile model per asset class and sector
- Adversary emulation plan structure
- Technique selection and justification trail

### Non-goals

- Attribution claims about specific actors

## 6. Intent architecture

A threat profile references techniques from the knowledge fabric; the planner selects runbooks whose mappings intersect the profile.

## 7. Contracts, data and capabilities

- Threat profile record
- Emulation plan record with technique justification

Contracts are canonical in Git. Where this epic reuses a platform-wide contract, the
canonical definition lives in the
[reference architecture](../../architecture/security-validation-reference-architecture.md)
and in [EPIC-01](EPIC-01-architecture-and-canonical-contracts.md); this document
references it instead of restating it.

## 8. Dependencies and sequencing

- [EPIC-21 — Framework Crosswalk and canonical methodology](EPIC-21-framework-crosswalk-and-canonical-methodology.md)
- [EPIC-43 — Knowledge-Driven Campaign Planner](EPIC-43-knowledge-driven-campaign-planner.md)

Sequencing follows the phase model in the
[intent document](../../architecture/security-validation-platform-v2-intent.md).
This epic is planned for phase 7.

## 9. Security, risks and failure modes

- Profiles based on stale intelligence
- Over-fitting campaigns to a single actor narrative

Platform-wide invariants that this epic must not weaken:

- absence of evidence never produces a `PASS` verdict;
- no execution outside an active authorization contract;
- no secrets, tokens, cookies or raw credential material in documentation, telemetry
  or persisted evidence;
- no target outside registered laboratories.

## 10. Deliverables

- Threat-informed validation specification

## 11. Acceptance criteria

- Every planned step traces to a technique in the active profile
- Profiles record intelligence source and date

## 12. Evidence and validation plan

- Selection justification recorded per campaign

Evidence must be referenced from the delivery umbrella issue before the umbrella can
be closed, and this document must record the references in section 15.

## 13. Decisions and open questions

### Decisions taken at intent time

- Technique relevance beats tool availability in planning

### Open questions

- Refresh cadence for threat profiles

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
