# EPIC-32 — Resilience Validation and TLPT

## 1. Metadata

| Field | Value |
| --- | --- |
| Concept epic ID | `EPIC-32` |
| Slug | `resilience-validation-and-tlpt` |
| Pillar | `F` — Threat-Informed Validation |
| Phase | 7 |
| Priority | P2 |
| Delivery umbrella | `SVP2-F-02` (issue [#89](https://github.com/pestoura/hermes-security-labs/issues/89)) |
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

Threat-led testing exercises require structured scoping, control and reporting that the platform does not yet model.

## 4. Intended outcome

A structured resilience exercise model aligned with recognised threat-led testing practices, including roles, phases, control and reporting.

## 5. Scope and non-goals

### In scope

- Exercise phases and role model
- Control and white-team oversight requirements
- Reporting structure and remediation follow-up
- Alignment mapping to recognised practices

### Non-goals

- Claiming formal accreditation under any regulatory testing framework

## 6. Intent architecture

An exercise is a long-running campaign with additional oversight roles, stricter authorization and mandatory white-team visibility.

## 7. Contracts, data and capabilities

- Exercise definition record
- Oversight and escalation matrix

Contracts are canonical in Git. Where this epic reuses a platform-wide contract, the
canonical definition lives in the
[reference architecture](../../architecture/security-validation-reference-architecture.md)
and in [EPIC-01](EPIC-01-architecture-and-canonical-contracts.md); this document
references it instead of restating it.

## 8. Dependencies and sequencing

- [EPIC-22 — Threat-Informed Security Validation](EPIC-22-threat-informed-security-validation.md)
- [EPIC-24 — Purple Team and detection validation](EPIC-24-purple-team-and-detection-validation.md)

Sequencing follows the phase model in the
[intent document](../../architecture/security-validation-platform-v2-intent.md).
This epic is planned for phase 7.

## 9. Security, risks and failure modes

- Exercise scope creep
- Oversight bypass under time pressure

Platform-wide invariants that this epic must not weaken:

- absence of evidence never produces a `PASS` verdict;
- no execution outside an active authorization contract;
- no secrets, tokens, cookies or raw credential material in documentation, telemetry
  or persisted evidence;
- no target outside registered laboratories.

## 10. Deliverables

- Resilience exercise specification

## 11. Acceptance criteria

- Every exercise declares oversight roles and escalation paths
- Alignment is expressed as aligned or mapped, never as accredited

## 12. Evidence and validation plan

- Exercise records with oversight sign-off

Evidence must be referenced from the delivery umbrella issue before the umbrella can
be closed, and this document must record the references in section 15.

## 13. Decisions and open questions

### Decisions taken at intent time

- White-team visibility is mandatory at all times

### Open questions

- Whether exercises require a distinct authorization contract type

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
