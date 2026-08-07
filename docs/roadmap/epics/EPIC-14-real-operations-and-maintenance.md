# EPIC-14 — Real operations and maintenance

## 1. Metadata

| Field | Value |
| --- | --- |
| Concept epic ID | `EPIC-14` |
| Slug | `real-operations-and-maintenance` |
| Pillar | `D` — Evidence Observability and Assurance |
| Phase | 4 |
| Priority | P1 |
| Delivery umbrella | `SVP2-D-02` (issue [#85](https://github.com/pestoura/hermes-security-labs/issues/85)) |
| Document version | 1.1.0 |
| Document date | 2026-08-07 |
| Catalogue | [Epic catalogue 45](../epic-catalogue-45.md) |
| Lifecycle contract | [Architecture documentation lifecycle](../../architecture/architecture-documentation-lifecycle.md) |

## 2. Current status

**INTENT** — this concept remains intentionally unpromoted. PR #144 implements shared readiness and maturity-assurance primitives used by the D-02 umbrella, but does **not** implement the operating model required by EPIC-14.

| Lifecycle state | Reached |
| --- | --- |
| INTENT | yes |
| IMPLEMENTING | no |
| AS_BUILT | no |
| FINAL | no |

The following EPIC-14-specific capabilities remain `NOT_IMPLEMENTED`/`NOT_RUN`:

- routine maintenance procedures and ownership;
- drift-response decision tree and operational workflow;
- incident handling for lab escape or policy violation;
- day-two upgrade/capacity/cleanup operating procedures;
- rehearsal records for critical procedures;
- operational maturity reassessment process.

The M0-M5 evidence model from PR #144 is a dependency/input, not sufficient evidence that this operating model exists.

## 3. Problem and motivation

Day-two operations (upgrades, cleanup, capacity, incident handling, drift response) are not documented as an operating model.

## 4. Intended outcome

An operating model with runbooks for routine maintenance, drift response, incident handling and capability maturity assessment M0-M5.

## 5. Scope and non-goals

### In scope

- Routine maintenance procedures
- Drift response decision tree
- Incident handling for lab escape or policy violation
- Capability maturity model M0-M5

### Non-goals

- Creating scheduled jobs or automations in this task

## 6. Intent architecture

Operations consume the drift verdict, telemetry and evidence; every corrective action is recorded and traceable to an owner.

## 7. Contracts, data and capabilities

- Maintenance procedure format
- Incident record

Contracts are canonical in Git. Where this epic reuses a platform-wide contract, the canonical definition lives in the [reference architecture](../../architecture/security-validation-reference-architecture.md) and in [EPIC-01](EPIC-01-architecture-and-canonical-contracts.md); this document references it instead of restating it.

## 8. Dependencies and sequencing

- [EPIC-02 — Single source of truth for runtime](EPIC-02-single-source-of-truth-for-runtime.md)
- [EPIC-11 — Technical observability](EPIC-11-technical-observability.md)

Sequencing follows the phase model in the [intent document](../../architecture/security-validation-platform-v2-intent.md). This epic is planned for phase 4.

## 9. Security, risks and failure modes

- Procedures decaying without periodic rehearsal
- Maturity levels claimed without evidence
- Incorrectly treating shared assurance primitives as a completed operating model

Platform-wide invariants that this epic must not weaken:

- absence of evidence never produces a `PASS` verdict;
- no execution outside an active authorization contract;
- no secrets, tokens, cookies or raw credential material in documentation, telemetry or persisted evidence;
- no target outside registered laboratories.

## 10. Deliverables

- Operating model documentation
- Maturity model definition

## 11. Acceptance criteria

- Every routine operation has a documented procedure and owner
- Maturity claims cite evidence

These acceptance criteria are not yet met for EPIC-14.

## 12. Evidence and validation plan

- Rehearsal records for critical procedures
- Owner/approval records for operational runbooks
- Drift and incident exercise evidence

## 13. Decisions and open questions

### Decisions taken

- Drift is never auto-remediated without a recorded decision.
- EPIC-14 remains `INTENT` until an actual day-two operating model exists; umbrella-level maturity primitives do not promote it automatically.

### Open questions

- Review cadence for maturity reassessment
- Ownership model for maintenance and incident runbooks

## 14. Implementation notes

> Reserved. Populate during implementation with pull request references, deviations from intent, and decisions taken while building. Do not delete this heading.

- PR #144 provides shared readiness/maturity primitives only.
- No EPIC-14 operating model or maintenance/incident runbook implementation is claimed.
- `NO_RUNTIME_CHANGE`.

## 15. As-built / final architecture

> Reserved. Populate when the delivery umbrella reaches completion. Must record what was actually built, evidence links, and every divergence from sections 6 to 11. No umbrella may be closed while this section is empty.

_Not started. EPIC-14 remains INTENT._

## 16. Document change log

| Date | Version | Change |
| --- | --- | --- |
| 2026-08-06 | 1.0.0 | Initial intent document created from the concept epic catalogue. |
| 2026-08-07 | 1.1.0 | Clarified that PR #144 does not promote EPIC-14; operating model/runbooks remain NOT_IMPLEMENTED/NOT_RUN. |
