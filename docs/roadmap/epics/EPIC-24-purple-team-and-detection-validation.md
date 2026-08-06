# EPIC-24 — Purple Team and detection validation

## 1. Metadata

| Field | Value |
| --- | --- |
| Concept epic ID | `EPIC-24` |
| Slug | `purple-team-and-detection-validation` |
| Pillar | `F` — Threat-Informed Validation |
| Phase | 7 |
| Priority | P1 |
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

Offensive validation does not answer whether the defensive stack detected, alerted or blocked the behaviour.

## 4. Intended outcome

Every technique execution carries a detection expectation, and the outcome records prevented, detected, alerted or missed.

## 5. Scope and non-goals

### In scope

- Detection expectation model per technique
- Outcome taxonomy prevented/detected/alerted/missed
- Detection gap reporting
- Defensive mapping alignment

### Non-goals

- Modifying defensive tooling configuration automatically

## 6. Intent architecture

Detection expectations are declared alongside the runbook; the outcome is derived from defensive telemetry evidence, not from the offensive runner's own claim.

## 7. Contracts, data and capabilities

- Detection expectation record
- Detection outcome record

Contracts are canonical in Git. Where this epic reuses a platform-wide contract, the
canonical definition lives in the
[reference architecture](../../architecture/security-validation-reference-architecture.md)
and in [EPIC-01](EPIC-01-architecture-and-canonical-contracts.md); this document
references it instead of restating it.

## 8. Dependencies and sequencing

- [EPIC-23 — Attack Graph and Attack Flow](EPIC-23-attack-graph-and-attack-flow.md)
- [EPIC-11 — Technical observability](EPIC-11-technical-observability.md)

Sequencing follows the phase model in the
[intent document](../../architecture/security-validation-platform-v2-intent.md).
This epic is planned for phase 7.

## 9. Security, risks and failure modes

- Missing defensive telemetry recorded as missed detection
- Expectation drift as detections change

Platform-wide invariants that this epic must not weaken:

- absence of evidence never produces a `PASS` verdict;
- no execution outside an active authorization contract;
- no secrets, tokens, cookies or raw credential material in documentation, telemetry
  or persisted evidence;
- no target outside registered laboratories.

## 10. Deliverables

- Purple team validation specification

## 11. Acceptance criteria

- Absent defensive telemetry yields UNKNOWN, not missed
- Every outcome cites the telemetry evidence used

## 12. Evidence and validation plan

- Detection outcome matrix per campaign

Evidence must be referenced from the delivery umbrella issue before the umbrella can
be closed, and this document must record the references in section 15.

## 13. Decisions and open questions

### Decisions taken at intent time

- Detection outcomes require independent defensive evidence

### Open questions

- How to onboard defensive telemetry sources safely

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
