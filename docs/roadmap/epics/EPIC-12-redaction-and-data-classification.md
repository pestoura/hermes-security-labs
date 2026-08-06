# EPIC-12 — Redaction and data classification

## 1. Metadata

| Field | Value |
| --- | --- |
| Concept epic ID | `EPIC-12` |
| Slug | `redaction-and-data-classification` |
| Pillar | `D` — Evidence Observability and Assurance |
| Phase | 2 |
| Priority | P0 |
| Delivery umbrella | `SVP2-D-01` (issue [#84](https://github.com/pestoura/hermes-security-labs/issues/84)) |
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

Sensitive material can appear in outputs, logs and evidence without a classification model or an enforced redaction boundary.

## 4. Intended outcome

A data classification scheme with enforced redaction at emission and clear rules on what may ever be persisted or published.

## 5. Scope and non-goals

### In scope

- Classification levels for evidence, telemetry and reports
- Redaction rules and enforcement points
- Prohibited persistence list
- Review procedure for sanitized publication

### Non-goals

- Weakening existing prohibitions on secrets in the repository

## 6. Intent architecture

Classification is assigned at production time; redaction is applied before persistence and again before publication, with the stricter rule winning.

## 7. Contracts, data and capabilities

- Classification labels
- Redaction rule set
- Publication approval record

Contracts are canonical in Git. Where this epic reuses a platform-wide contract, the
canonical definition lives in the
[reference architecture](../../architecture/security-validation-reference-architecture.md)
and in [EPIC-01](EPIC-01-architecture-and-canonical-contracts.md); this document
references it instead of restating it.

## 8. Dependencies and sequencing

- [EPIC-10 — Evidence Plane](EPIC-10-evidence-plane.md)

Sequencing follows the phase model in the
[intent document](../../architecture/security-validation-platform-v2-intent.md).
This epic is planned for phase 2.

## 9. Security, risks and failure modes

- Over-redaction destroying analytic value
- Redaction bypass through new output paths

Platform-wide invariants that this epic must not weaken:

- absence of evidence never produces a `PASS` verdict;
- no execution outside an active authorization contract;
- no secrets, tokens, cookies or raw credential material in documentation, telemetry
  or persisted evidence;
- no target outside registered laboratories.

## 10. Deliverables

- Classification and redaction specification

## 11. Acceptance criteria

- Every persisted artefact carries a classification label
- No credential, token or cookie value is persisted

## 12. Evidence and validation plan

- Redaction rule coverage matrix

Evidence must be referenced from the delivery umbrella issue before the umbrella can
be closed, and this document must record the references in section 15.

## 13. Decisions and open questions

### Decisions taken at intent time

- Unclassified output is treated as most sensitive until classified

### Open questions

- Whether hashes of secrets are acceptable for correlation

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
