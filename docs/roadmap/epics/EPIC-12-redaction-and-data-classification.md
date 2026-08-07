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
| Document version | 1.1.0 |
| Document date | 2026-08-07 |
| Catalogue | [Epic catalogue 45](../epic-catalogue-45.md) |
| Lifecycle contract | [Architecture documentation lifecycle](../../architecture/architecture-documentation-lifecycle.md) |

## 2. Current status

**IMPLEMENTING** — PR #141 integrated repository-level classification and redaction constraints inside the Evidence Plane v2 contract. Production redaction and publication enforcement remain unimplemented/unexecuted.

| Lifecycle state | Reached |
| --- | --- |
| INTENT | yes |
| IMPLEMENTING | yes |
| AS_BUILT | no |
| FINAL | no |

Implemented contract state:

- evidence classification is mandatory as `raw`, `restricted`, `sanitized` or `summary`;
- sanitized/summary records require parent linkage and redaction lineage;
- raw/restricted evidence is non-exportable by default;
- secret-bearing metadata is refused;
- raw commands and raw stdout/stderr are refused from record metadata;
- replay descriptors exclude payload bytes and carry identifiers, provenance and hashes only;
- derived evidence validation fails closed on source-hash mismatch.

Production redaction at emission/persistence/publication, review workflow, telemetry/report coverage and real storage enforcement remain `NOT_IMPLEMENTED` or `NOT_RUN`.

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

Contracts are canonical in Git. Where this epic reuses a platform-wide contract, the canonical definition lives in the [reference architecture](../../architecture/security-validation-reference-architecture.md) and in [EPIC-01](EPIC-01-architecture-and-canonical-contracts.md); this document references it instead of restating it.

## 8. Dependencies and sequencing

- [EPIC-10 — Evidence Plane](EPIC-10-evidence-plane.md)

Sequencing follows the phase model in the [intent document](../../architecture/security-validation-platform-v2-intent.md). This epic is planned for phase 2.

## 9. Security, risks and failure modes

- Over-redaction destroying analytic value
- Redaction bypass through new output paths
- Classification mismatch between evidence, telemetry and reports
- Treating schema-level refusal as proof of production redaction coverage

Platform-wide invariants that this epic must not weaken:

- absence of evidence never produces a `PASS` verdict;
- no execution outside an active authorization contract;
- no secrets, tokens, cookies or raw credential material in documentation, telemetry or persisted evidence;
- no target outside registered laboratories.

## 10. Deliverables

- Classification and redaction specification

## 11. Acceptance criteria

- Every persisted artefact carries a classification label
- No credential, token or cookie value is persisted

These criteria are only partially represented at contract level. Real persistence paths and publication/export boundaries still require operational validation before `AS_BUILT` or `FINAL`.

## 12. Evidence and validation plan

- Contract/schema and adversarial tests from PR #141
- Future redaction rule coverage matrix across evidence, telemetry and reports
- Future storage/export tests demonstrating secret-bearing material is refused or redacted
- Future Human-in-the-Loop publication review evidence where required

## 13. Decisions and open questions

### Decisions taken

- Unclassified or unsupported evidence never receives a permissive export path.
- Raw/restricted evidence is non-exportable by default.
- Derived evidence must preserve parent/redaction lineage.

### Open questions

- Whether hashes of secrets are acceptable for correlation
- Canonical cross-plane classification labels for telemetry and reports
- Publication review workflow and retention of approval evidence

## 14. Implementation notes

> Reserved. Populate during implementation with pull request references, deviations from intent, and decisions taken while building. Do not delete this heading.

- PR #141 integrated classification, non-exportability, metadata refusal and derived-evidence lineage constraints.
- Production redaction and publication/export enforcement were deliberately not activated.
- `NO_RUNTIME_CHANGE`.

## 15. As-built / final architecture

> Reserved. Populate when the delivery umbrella reaches completion. Must record what was actually built, evidence links, and every divergence from sections 6 to 11. No umbrella may be closed while this section is empty.

_Not final. Production redaction, persistence, telemetry/report coverage and publication review/enforcement remain to be implemented and evidenced._

## 16. Document change log

| Date | Version | Change |
| --- | --- | --- |
| 2026-08-06 | 1.0.0 | Initial intent document created from the concept epic catalogue. |
| 2026-08-07 | 1.1.0 | Reconciled lifecycle to IMPLEMENTING against PR #141 while preserving production redaction/persistence/publication claims as NOT_IMPLEMENTED/NOT_RUN. |
