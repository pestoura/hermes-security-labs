# EPIC-25 — Continuous Security Validation

## 1. Metadata

| Field | Value |
| --- | --- |
| Concept epic ID | `EPIC-25` |
| Slug | `continuous-security-validation` |
| Pillar | `H` — Continuous Content Factories |
| Phase | 7 |
| Priority | P1 |
| Delivery umbrella | `SVP2-H-01` (issue [#91](https://github.com/pestoura/hermes-security-labs/issues/91)) |
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

Validation is episodic, so control effectiveness between campaigns is unknown and regressions surface late.

## 4. Intended outcome

A continuous validation model with scheduled, low-intrusiveness recurring checks and trend reporting over time.

## 5. Scope and non-goals

### In scope

- Recurring low-intrusiveness validation profiles
- Trend and regression detection across runs
- Change-triggered validation model

### Non-goals

- Creating scheduled jobs as part of this documentation task

## 6. Intent architecture

Continuous runs reuse the same contracts at restricted intrusiveness; results feed a longitudinal store enabling trend and regression analysis.

## 7. Contracts, data and capabilities

- Continuous profile record
- Trend series definition

Contracts are canonical in Git. Where this epic reuses a platform-wide contract, the
canonical definition lives in the
[reference architecture](../../architecture/security-validation-reference-architecture.md)
and in [EPIC-01](EPIC-01-architecture-and-canonical-contracts.md); this document
references it instead of restating it.

## 8. Dependencies and sequencing

- [EPIC-10 — Evidence Plane](EPIC-10-evidence-plane.md)
- [EPIC-22 — Threat-Informed Security Validation](EPIC-22-threat-informed-security-validation.md)

Sequencing follows the phase model in the
[intent document](../../architecture/security-validation-platform-v2-intent.md).
This epic is planned for phase 7.

## 9. Security, risks and failure modes

- Alert fatigue from noisy recurring checks
- Continuous runs consuming lab capacity

Platform-wide invariants that this epic must not weaken:

- absence of evidence never produces a `PASS` verdict;
- no execution outside an active authorization contract;
- no secrets, tokens, cookies or raw credential material in documentation, telemetry
  or persisted evidence;
- no target outside registered laboratories.

## 10. Deliverables

- Continuous validation specification

## 11. Acceptance criteria

- Continuous profiles are limited to declared low intrusiveness
- Regressions are detectable against a recorded baseline

## 12. Evidence and validation plan

- Baseline and trend definitions

Evidence must be referenced from the delivery umbrella issue before the umbrella can
be closed, and this document must record the references in section 15.

## 13. Decisions and open questions

### Decisions taken at intent time

- Continuous validation never escalates intrusiveness automatically

### Open questions

- Retention horizon for longitudinal series

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
