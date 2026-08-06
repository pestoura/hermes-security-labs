# EPIC-31 — OpenTelemetry end-to-end

## 1. Metadata

| Field | Value |
| --- | --- |
| Concept epic ID | `EPIC-31` |
| Slug | `opentelemetry-end-to-end` |
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

Telemetry is emitted in heterogeneous formats, preventing end-to-end tracing across control plane, gateway, runners and labs.

## 4. Intended outcome

A single vendor-neutral telemetry contract with consistent trace context propagation from campaign start to evidence persistence.

## 5. Scope and non-goals

### In scope

- Trace context propagation across plane boundaries
- Semantic conventions for campaign, step, capability and lab attributes
- Metric and log correlation with traces
- Exporter-agnostic configuration model

### Non-goals

- Selecting or deploying a specific backend in this task

## 6. Intent architecture

Trace context is created at campaign start and propagated through every typed request, runner step and evidence write, so a single trace reconstructs the whole campaign.

## 7. Contracts, data and capabilities

- Semantic attribute conventions
- Context propagation requirements

Contracts are canonical in Git. Where this epic reuses a platform-wide contract, the
canonical definition lives in the
[reference architecture](../../architecture/security-validation-reference-architecture.md)
and in [EPIC-01](EPIC-01-architecture-and-canonical-contracts.md); this document
references it instead of restating it.

## 8. Dependencies and sequencing

- [EPIC-11 — Technical observability](EPIC-11-technical-observability.md)

Sequencing follows the phase model in the
[intent document](../../architecture/security-validation-platform-v2-intent.md).
This epic is planned for phase 4.

## 9. Security, risks and failure modes

- Context loss at process boundaries
- Attribute cardinality growth

Platform-wide invariants that this epic must not weaken:

- absence of evidence never produces a `PASS` verdict;
- no execution outside an active authorization contract;
- no secrets, tokens, cookies or raw credential material in documentation, telemetry
  or persisted evidence;
- no target outside registered laboratories.

## 10. Deliverables

- Telemetry contract specification

## 11. Acceptance criteria

- A campaign is reconstructable as a single trace
- Attributes follow the declared conventions

## 12. Evidence and validation plan

- Trace attribute conformance checklist

Evidence must be referenced from the delivery umbrella issue before the umbrella can
be closed, and this document must record the references in section 15.

## 13. Decisions and open questions

### Decisions taken at intent time

- Telemetry remains exporter-agnostic

### Open questions

- Whether lab-internal telemetry is in scope or out of boundary

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
