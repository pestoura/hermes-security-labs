# EPIC-45 — Operational Query and Discovery

## 1. Metadata

| Field | Value |
| --- | --- |
| Concept epic ID | `EPIC-45` |
| Slug | `operational-query-and-discovery` |
| Pillar | `E` — Security Knowledge Fabric |
| Phase | 7 |
| Priority | P1 |
| Delivery umbrella | `SVP2-E-02` (issue [#87](https://github.com/pestoura/hermes-security-labs/issues/87)) |
| Document version | 1.1.0 |
| Document date | 2026-08-07 |
| Catalogue | [Epic catalogue 45](../epic-catalogue-45.md) |
| Lifecycle contract | [Architecture documentation lifecycle](../../architecture/architecture-documentation-lifecycle.md) |

## 2. Current status

**IMPLEMENTING** — PR #148 integrated a repository-level snapshot-scoped knowledge query contract. HTTP serving, database/graph query execution and evidence-index integration remain `NOT_IMPLEMENTED` / `NOT_RUN`.

| Lifecycle state | Reached |
| --- | --- |
| INTENT | yes |
| IMPLEMENTING | yes |
| AS_BUILT | no |
| FINAL | no |

Implemented contract state:

- query types are bounded to entity, relations, applicability and temporal series;
- every query requires an immutable knowledge snapshot id;
- every query requires an explicit minimum confidence threshold in `[0,1]`;
- confidence filtering is deterministic;
- EPSS, KEV and VEX observations have append-only temporal entry contracts with provenance;
- campaign records can bind the exact knowledge snapshot used for planning.

The candidate does not yet implement an HTTP API, persistent database, graph query engine, evidence/finding indexes, access-control enforcement on query results or a canonical operational question catalogue. Raw evidence exposure remains outside the contract. Runtime API serving and production temporal ingestion remain `NOT_IMPLEMENTED` / `NOT_RUN`.

## 3. Problem and motivation

Operators cannot ask direct questions such as which controls were validated against a technique, or which assets remain unvalidated for a vulnerability.

## 4. Intended outcome

A defined query surface answering operational questions across knowledge, campaigns, evidence and findings, with reproducible results.

## 5. Scope and non-goals

### In scope

- Canonical operational question catalogue
- Query surface and result contracts
- Snapshot-scoped reproducible answers
- Access control on query results

### Non-goals

- Exposing raw evidence through the query surface

## 6. Intent architecture

Queries execute against pinned snapshots plus evidence indexes; results carry the snapshot reference so answers are reproducible and auditable.

## 7. Contracts, data and capabilities

- Query request and result schema
- Result provenance reference

Contracts are canonical in Git. Where this epic reuses a platform-wide contract, the canonical definition lives in the [reference architecture](../../architecture/security-validation-reference-architecture.md) and in [EPIC-01](EPIC-01-architecture-and-canonical-contracts.md); this document references it instead of restating it.

## 8. Dependencies and sequencing

- [EPIC-36 — Security Knowledge Fabric](EPIC-36-security-knowledge-fabric.md)
- [EPIC-43 — Knowledge-Driven Campaign Planner](EPIC-43-knowledge-driven-campaign-planner.md)
- [EPIC-33 — Finding and remediation lifecycle](EPIC-33-finding-and-remediation-lifecycle.md)

Sequencing follows the phase model in the [intent document](../../architecture/security-validation-platform-v2-intent.md). This epic is planned for phase 7.

## 9. Security, risks and failure modes

- Query results interpreted as assurance
- Sensitive data exposure through aggregation
- Unpinned queries producing non-reproducible answers
- Generic knowledge queries being mistaken for evidence/finding query coverage

Platform-wide invariants that this epic must not weaken:

- absence of evidence never produces a `PASS` verdict;
- no execution outside an active authorization contract;
- no secrets, tokens, cookies or raw credential material in documentation, telemetry or persisted evidence;
- no target outside registered laboratories.

## 10. Deliverables

- Operational query specification
- Canonical question catalogue

## 11. Acceptance criteria

- Every result cites its snapshot and evidence scope
- Raw or unredacted evidence is never returned

Snapshot binding is implemented at request/campaign-contract level. Result/evidence scope, access control and raw-evidence guarantees still require the real query engine before `AS_BUILT` or `FINAL`.

## 12. Evidence and validation plan

- Contract tests from PR #148
- Future canonical question catalogue and result schemas
- Future access-control tests
- Future evidence/finding index integration and reproducibility evidence

## 13. Decisions and open questions

### Decisions taken

- Query results are read-only projections.
- Queries are always bound to an immutable snapshot and explicit confidence threshold.

### Open questions

- Whether ad hoc queries are permitted alongside canonical ones
- Canonical access-control model for query results

## 14. Implementation notes

> Reserved. Populate during implementation with pull request references, deviations from intent, and decisions taken while building. Do not delete this heading.

- PR #148 integrated snapshot/query validation and temporal-series contracts.
- HTTP API, database and graph query engine remain `NOT_IMPLEMENTED`.
- Production temporal ingestion remains `NOT_RUN`.
- `NO_RUNTIME_CHANGE`.

## 15. As-built / final architecture

> Reserved. Populate when the delivery umbrella reaches completion. Must record what was actually built, evidence links, and every divergence from sections 6 to 11. No umbrella may be closed while this section is empty.

_Not final. Real query engine, evidence/finding integration, result access control and production serving remain NOT_IMPLEMENTED/NOT_RUN._

## 16. Document change log

| Date | Version | Change |
| --- | --- | --- |
| 2026-08-06 | 1.0.0 | Initial intent document created from the concept epic catalogue. |
| 2026-08-07 | 1.1.0 | Reconciled lifecycle to IMPLEMENTING against PR #148 while preserving HTTP/database/graph/evidence-query runtime as NOT_IMPLEMENTED/NOT_RUN. |
