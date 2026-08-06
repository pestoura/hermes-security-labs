# EPIC-11 — Technical observability

## 1. Metadata

| Field | Value |
| --- | --- |
| Concept epic ID | `EPIC-11` |
| Slug | `technical-observability` |
| Pillar | `D` — Evidence Observability and Assurance |
| Phase | 4 |
| Priority | P1 |
| Delivery umbrella | `SVP2-D-02` (issue [#85](https://github.com/pestoura/hermes-security-labs/issues/85)) |
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

There is no consistent telemetry across control plane, gateway, runners and labs, so failures are diagnosed from ad hoc logs.

## 4. Intended outcome

Structured logs, metrics and traces with consistent correlation identifiers and documented signal semantics.

## 5. Scope and non-goals

### In scope

- Structured logging with correlation ids
- Core metrics for campaigns, steps, labs and refusals
- Health and readiness semantics
- Redaction applied at emission

### Non-goals

- Deploying a monitoring stack in this documentation task

## 6. Intent architecture

Telemetry is emitted at plane boundaries; every signal carries campaign, step and capability identifiers so evidence and telemetry can be correlated after the fact.

## 7. Contracts, data and capabilities

- Log record fields
- Metric names and labels
- Trace span naming

Contracts are canonical in Git. Where this epic reuses a platform-wide contract, the
canonical definition lives in the
[reference architecture](../../architecture/security-validation-reference-architecture.md)
and in [EPIC-01](EPIC-01-architecture-and-canonical-contracts.md); this document
references it instead of restating it.

## 8. Dependencies and sequencing

- [EPIC-10 — Evidence Plane](EPIC-10-evidence-plane.md)

Sequencing follows the phase model in the
[intent document](../../architecture/security-validation-platform-v2-intent.md).
This epic is planned for phase 4.

## 9. Security, risks and failure modes

- Telemetry leaking sensitive content
- Cardinality explosion from per-target labels

Platform-wide invariants that this epic must not weaken:

- absence of evidence never produces a `PASS` verdict;
- no execution outside an active authorization contract;
- no secrets, tokens, cookies or raw credential material in documentation, telemetry
  or persisted evidence;
- no target outside registered laboratories.

## 10. Deliverables

- Observability specification
- Signal catalogue

## 11. Acceptance criteria

- Every campaign is reconstructable from telemetry plus evidence
- No telemetry field carries secret material

## 12. Evidence and validation plan

- Signal catalogue reviewed against redaction rules

Evidence must be referenced from the delivery umbrella issue before the umbrella can
be closed, and this document must record the references in section 15.

## 13. Decisions and open questions

### Decisions taken at intent time

- Correlation id is mandatory in every emitted signal

### Open questions

- Sampling policy for high-volume runner traces

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
