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

Contracts are canonical in Git. Where this epic reuses a platform-wide contract, the
canonical definition lives in the
[reference architecture](../../architecture/security-validation-reference-architecture.md)
and in [EPIC-01](EPIC-01-architecture-and-canonical-contracts.md); this document
references it instead of restating it.

## 8. Dependencies and sequencing

- [EPIC-36 — Security Knowledge Fabric](EPIC-36-security-knowledge-fabric.md)
- [EPIC-37 — Vulnerability Intelligence Synchronization](EPIC-37-vulnerability-intelligence-synchronization.md)
- [EPIC-39 — ATT&CK Synchronization Service](EPIC-39-attack-synchronization-service.md)

Sequencing follows the phase model in the
[intent document](../../architecture/security-validation-platform-v2-intent.md).
This epic is planned for phase 5.

## 9. Security, risks and failure modes

- Unresolved conflicts accumulating
- Precedence rules hiding better data

Platform-wide invariants that this epic must not weaken:

- absence of evidence never produces a `PASS` verdict;
- no execution outside an active authorization contract;
- no secrets, tokens, cookies or raw credential material in documentation, telemetry
  or persisted evidence;
- no target outside registered laboratories.

## 10. Deliverables

- Knowledge quality specification

## 11. Acceptance criteria

- Conflicts are visible, never silently dropped
- Every resolution records the rule or curator applied

## 12. Evidence and validation plan

- Conflict and resolution inventory

Evidence must be referenced from the delivery umbrella issue before the umbrella can
be closed, and this document must record the references in section 15.

## 13. Decisions and open questions

### Decisions taken at intent time

- Both conflicting claims are retained with provenance

### Open questions

- Escalation threshold for unresolved conflicts

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
