# EPIC-44 — Knowledge Quality and Conflict Resolution

## 1. Metadata

| Field | Value |
| --- | --- |
| Concept epic ID | `EPIC-44` |
| Slug | `knowledge-quality-and-conflict-resolution` |
| Pillar | `E` — Security Knowledge Fabric |
| Phase | 5 |
| Priority | P1 |
| Delivery umbrella | `SVP2-E-02` (issue [#87](https://github.com/pestoura/hermes-security-labs/issues/87)) |
| Document version | 1.1.0 |
| Document date | 2026-08-07 |
| Catalogue | [Epic catalogue 45](../epic-catalogue-45.md) |
| Lifecycle contract | [Architecture documentation lifecycle](../../architecture/architecture-documentation-lifecycle.md) |

## 2. Current status

**IMPLEMENTING** — repository contracts from PR #146 and PR #148 implement core conflict, precedence and confidence-filtering primitives. Quality metrics and the curation workflow remain incomplete.

| Lifecycle state | Reached |
| --- | --- |
| INTENT | yes |
| IMPLEMENTING | yes |
| AS_BUILT | no |
| FINAL | no |

Implemented contract state:

- conflicting assertions from distinct provenance records are persisted rather than silently discarded;
- unresolved conflicts retain all assertions and no selected winner;
- conflict resolution requires an explicit precedence policy;
- the selected assertion must already exist in the conflict;
- derived relations require bounded confidence;
- snapshot queries require a minimum confidence threshold and can filter records deterministically;
- knowledge snapshots are immutable and identify their exact source-record inventory.

The candidate does not yet implement completeness/freshness/confidence-distribution metrics, curator identity/approval workflow, escalation thresholds, persistent conflict inventory or production quality dashboards. External source synchronization and production persistence remain `NOT_RUN` / `NOT_IMPLEMENTED`.

## 3. Problem and motivation

Multiple sources disagree; without precedence, conflict detection and quality metrics, the graph silently accumulates contradictions.

## 4. Intended outcome

Explicit conflict detection, precedence rules, quality metrics and a curation process that keeps the graph trustworthy.

## 5. Scope and non-goals

### In scope

- Conflict detection between sources
- Precedence and tie-breaking rules
- Quality metrics: completeness, freshness, confidence distribution
- Curation and correction workflow

### Non-goals

- Silently discarding conflicting data

## 6. Intent architecture

Conflicts are recorded as first-class entities with both claims retained; resolution records the rule applied and the curator when manual.

## 7. Contracts, data and capabilities

- Conflict record
- Resolution record
- Quality metric definitions

Contracts are canonical in Git. Where this epic reuses a platform-wide contract, the canonical definition lives in the [reference architecture](../../architecture/security-validation-reference-architecture.md) and in [EPIC-01](EPIC-01-architecture-and-canonical-contracts.md); this document references it instead of restating it.

## 8. Dependencies and sequencing

- [EPIC-36 — Security Knowledge Fabric](EPIC-36-security-knowledge-fabric.md)
- [EPIC-37 — Vulnerability Intelligence Synchronization](EPIC-37-vulnerability-intelligence-synchronization.md)
- [EPIC-39 — ATT&CK Synchronization Service](EPIC-39-attack-synchronization-service.md)

Sequencing follows the phase model in the [intent document](../../architecture/security-validation-platform-v2-intent.md). This epic is planned for phase 5.

## 9. Security, risks and failure modes

- Unresolved conflicts accumulating
- Precedence rules hiding better data
- Confidence filtering being misread as source correctness
- Quality metrics being claimed without synchronized source datasets

Platform-wide invariants that this epic must not weaken:

- absence of evidence never produces a `PASS` verdict;
- no execution outside an active authorization contract;
- no secrets, tokens, cookies or raw credential material in documentation, telemetry or persisted evidence;
- no target outside registered laboratories.

## 10. Deliverables

- Knowledge quality specification

## 11. Acceptance criteria

- Conflicts are visible, never silently dropped
- Every resolution records the rule or curator applied

Conflict preservation and explicit policy-based resolution are implemented at contract level. Manual curator identity/workflow and measurable quality metrics still require implementation before `AS_BUILT` or `FINAL`.

## 12. Evidence and validation plan

- Contract tests from PR #146 and PR #148
- Future persistent conflict/resolution inventory
- Future completeness/freshness/confidence-distribution metrics
- Future curator/approval records

## 13. Decisions and open questions

### Decisions taken

- Both conflicting claims are retained with provenance.
- Silent conflict resolution is forbidden.
- Confidence thresholds are explicit query inputs, not implicit trust decisions.

### Open questions

- Escalation threshold for unresolved conflicts
- Canonical quality metric calculation and curator workflow

## 14. Implementation notes

> Reserved. Populate during implementation with pull request references, deviations from intent, and decisions taken while building. Do not delete this heading.

- PR #146 integrated conflict persistence and explicit precedence-policy resolution.
- PR #148 integrated immutable snapshots and minimum-confidence query filtering.
- Production persistence/curation remains unimplemented; external synchronization remains `NOT_RUN`.
- `NO_RUNTIME_CHANGE`.

## 15. As-built / final architecture

> Reserved. Populate when the delivery umbrella reaches completion. Must record what was actually built, evidence links, and every divergence from sections 6 to 11. No umbrella may be closed while this section is empty.

_Not final. Quality metrics, persistent conflict inventory and curation workflow remain incomplete/NOT_RUN._

## 16. Document change log

| Date | Version | Change |
| --- | --- | --- |
| 2026-08-06 | 1.0.0 | Initial intent document created from the concept epic catalogue. |
| 2026-08-07 | 1.1.0 | Reconciled lifecycle to IMPLEMENTING using PR #146/#148 conflict, precedence, snapshot and confidence primitives; quality metrics/curation remain incomplete. |
