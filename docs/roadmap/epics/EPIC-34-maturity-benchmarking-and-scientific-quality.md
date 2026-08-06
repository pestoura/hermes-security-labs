# EPIC-34 — Maturity, benchmarking and scientific quality

## 1. Metadata

| Field | Value |
| --- | --- |
| Concept epic ID | `EPIC-34` |
| Slug | `maturity-benchmarking-and-scientific-quality` |
| Pillar | `D` — Evidence Observability and Assurance |
| Phase | 4 |
| Priority | P2 |
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

Platform quality claims are qualitative; there is no benchmark, no reproducibility standard and no measurable maturity assessment.

## 4. Intended outcome

A maturity model M0-M5 per capability plus reproducibility and benchmarking requirements that make quality claims measurable.

## 5. Scope and non-goals

### In scope

- Capability maturity levels M0-M5 with evidence requirements
- Reproducibility criteria for content and campaigns
- Benchmark definitions and reporting
- False positive and false negative accounting

### Non-goals

- Publishing comparative claims against other products

## 6. Intent architecture

Maturity is asserted only with recorded evidence per level; benchmarks are versioned so results across time remain comparable.

## 7. Contracts, data and capabilities

- Maturity assessment record
- Benchmark definition and result record

Contracts are canonical in Git. Where this epic reuses a platform-wide contract, the
canonical definition lives in the
[reference architecture](../../architecture/security-validation-reference-architecture.md)
and in [EPIC-01](EPIC-01-architecture-and-canonical-contracts.md); this document
references it instead of restating it.

## 8. Dependencies and sequencing

- [EPIC-13 — Reliability and chaos testing](EPIC-13-reliability-and-chaos-testing.md)
- [EPIC-10 — Evidence Plane](EPIC-10-evidence-plane.md)

Sequencing follows the phase model in the
[intent document](../../architecture/security-validation-platform-v2-intent.md).
This epic is planned for phase 4.

## 9. Security, risks and failure modes

- Maturity inflation
- Benchmarks optimized for rather than measured by

Platform-wide invariants that this epic must not weaken:

- absence of evidence never produces a `PASS` verdict;
- no execution outside an active authorization contract;
- no secrets, tokens, cookies or raw credential material in documentation, telemetry
  or persisted evidence;
- no target outside registered laboratories.

## 10. Deliverables

- Maturity and benchmarking specification

## 11. Acceptance criteria

- Every maturity claim cites evidence
- Benchmark results record the benchmark version

## 12. Evidence and validation plan

- Assessment records per capability

Evidence must be referenced from the delivery umbrella issue before the umbrella can
be closed, and this document must record the references in section 15.

## 13. Decisions and open questions

### Decisions taken at intent time

- Unevidenced maturity defaults to M0

### Open questions

- Who performs independent maturity review

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
