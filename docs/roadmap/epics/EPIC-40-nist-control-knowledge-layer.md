# EPIC-40 — NIST Control Knowledge Layer

## 1. Metadata

| Field | Value |
| --- | --- |
| Concept epic ID | `EPIC-40` |
| Slug | `nist-control-knowledge-layer` |
| Pillar | `E` — Security Knowledge Fabric |
| Phase | 5 |
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

Control catalogues are referenced textually, so validation results cannot be expressed against control objectives in a structured, auditable way.

## 4. Intended outcome

A control knowledge layer linking controls to techniques, runbooks and evidence, enabling control-oriented reporting without compliance claims.

## 5. Scope and non-goals

### In scope

- Control catalogue ingestion and versioning
- Control to technique and runbook mappings
- Control-oriented result projection
- Explicit limitations of control coverage claims

### Non-goals

- Asserting formal compliance or certification

## 6. Intent architecture

Controls are graph nodes; validation results project onto controls through mapped techniques and runbooks, always carrying mapping confidence.

## 7. Contracts, data and capabilities

- Control node schema
- Control coverage projection record

Contracts are canonical in Git. Where this epic reuses a platform-wide contract, the
canonical definition lives in the
[reference architecture](../../architecture/security-validation-reference-architecture.md)
and in [EPIC-01](EPIC-01-architecture-and-canonical-contracts.md); this document
references it instead of restating it.

## 8. Dependencies and sequencing

- [EPIC-36 — Security Knowledge Fabric](EPIC-36-security-knowledge-fabric.md)
- [EPIC-21 — Framework Crosswalk and canonical methodology](EPIC-21-framework-crosswalk-and-canonical-methodology.md)

Sequencing follows the phase model in the
[intent document](../../architecture/security-validation-platform-v2-intent.md).
This epic is planned for phase 5.

## 9. Security, risks and failure modes

- Coverage projections read as compliance attestations
- Catalogue version drift

Platform-wide invariants that this epic must not weaken:

- absence of evidence never produces a `PASS` verdict;
- no execution outside an active authorization contract;
- no secrets, tokens, cookies or raw credential material in documentation, telemetry
  or persisted evidence;
- no target outside registered laboratories.

## 10. Deliverables

- Control knowledge layer specification

## 11. Acceptance criteria

- Coverage output states it is mapped, not certified
- Every projection carries mapping confidence

## 12. Evidence and validation plan

- Projection samples with confidence

Evidence must be referenced from the delivery umbrella issue before the umbrella can
be closed, and this document must record the references in section 15.

## 13. Decisions and open questions

### Decisions taken at intent time

- The platform never emits a compliance verdict

### Open questions

- Which catalogues and baselines to support first

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
