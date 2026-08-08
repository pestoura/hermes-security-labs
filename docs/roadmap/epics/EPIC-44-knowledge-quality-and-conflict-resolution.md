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
| Document version | 1.2.0 |
| Document date | 2026-08-08 |
| Catalogue | [Epic catalogue 45](../epic-catalogue-45.md) |
| Lifecycle contract | [Architecture documentation lifecycle](../../architecture/architecture-documentation-lifecycle.md) |

## 2. Current status

**IMPLEMENTING** — PR #146 and PR #148 provide the conflict, precedence, immutable-snapshot and confidence-filtering substrate. PR #192 adds repository-level deterministic quality metrics and accountable curation contracts. Production persistence, operational curator workflow/UI, external source-authority verification and quality dashboards remain `NOT_IMPLEMENTED` / `NOT_RUN`.

| Lifecycle state | Reached |
| --- | --- |
| INTENT | yes |
| IMPLEMENTING | yes |
| AS_BUILT | no |
| FINAL | no |

Implemented contract state:

- conflicting assertions from distinct provenance records are preserved rather than silently discarded;
- unresolved conflicts retain all assertions and no selected winner;
- conflict resolution requires an explicit precedence policy or an accountable curator decision;
- the selected assertion must already exist in the conflict or curation case;
- derived relations require bounded confidence and provenance within the assessed snapshot;
- knowledge snapshots are immutable and identify their exact source-record inventory;
- completeness is calculated deterministically against the immutable snapshot inventory;
- freshness is evaluated against an explicit positive maximum-age policy per supplied source;
- future retrieval timestamps fail closed;
- relation confidence is summarized against an explicit minimum policy;
- unresolved conflicts force `REVIEW_REQUIRED`;
- quality state is limited to `QUALITY_POLICY_MET` or `REVIEW_REQUIRED`;
- `QUALITY_POLICY_MET` is explicitly not a security verdict or assurance result;
- quality reports fix `assurance_effect = NONE` and `execution_authority = NONE`;
- curation cases are content-addressed and bound to snapshot, finding type, subject, candidates and rationale;
- post-creation tampering of curation-case canonical content fails closed;
- curator decisions record curator identity, rationale and timestamp;
- policy decisions record the precedence-policy identifier, rationale and timestamp;
- curation decisions fix `automatic_resolution = false`, `historical_rewrite = false`, `effect = KNOWLEDGE_CURATION_ONLY` and `execution_authority = NONE`.

The repository candidate still does not implement production graph/database persistence, an operational curator UI/workflow engine, external-source authority/currentness verification, source synchronization, persistent operational conflict/case storage, escalation automation or production quality dashboards. Those capabilities remain outside the current evidence and prevent `AS_BUILT` or `FINAL`.

## 3. Problem and motivation

Multiple sources disagree; without precedence, conflict detection, measurable quality policy and accountable curation, the graph can silently accumulate contradictions or present low-quality knowledge as trusted truth.

## 4. Intended outcome

Explicit conflict detection, precedence rules, deterministic quality metrics and an accountable curation process that keeps the graph trustworthy without turning data-quality state into a security or compliance verdict.

## 5. Scope and non-goals

### In scope

- Conflict detection between sources
- Precedence and tie-breaking rules
- Quality metrics: completeness, freshness, confidence distribution
- Accountable curation and correction contracts
- Tamper-resistant curation-case identity

### Non-goals

- Silently discarding conflicting data
- Automatic conflict resolution
- Rewriting historical snapshots
- Treating quality-policy success as security assurance
- Granting execution authority from knowledge or curation state

## 6. Intent architecture

Conflicts are recorded as first-class entities with all competing claims retained. Quality assessment is a deterministic read-only projection over an immutable snapshot. Curation cases bind the exact review subject and candidate records; resolution records either the curator or precedence policy that produced the decision. Historical snapshots remain unchanged.

## 7. Contracts, data and capabilities

- Conflict record
- Quality report
- Curation case
- Curation decision
- Resolution record
- Quality metric definitions

Canonical repository contracts introduced or extended by PR #192:

- `platform/knowledge-fabric/knowledge_quality.py`
- `platform/knowledge-fabric/knowledge-quality-report.schema.json`
- `platform/knowledge-fabric/knowledge-curation-case.schema.json`
- `platform/knowledge-fabric/knowledge-curation-decision.schema.json`

Contracts are canonical in Git. Where this epic reuses a platform-wide contract, the canonical definition lives in the [reference architecture](../../architecture/security-validation-reference-architecture.md) and in [EPIC-01](EPIC-01-architecture-and-canonical-contracts.md); this document references it instead of restating it.

## 8. Dependencies and sequencing

- [EPIC-36 — Security Knowledge Fabric](EPIC-36-security-knowledge-fabric.md)
- [EPIC-37 — Vulnerability Intelligence Synchronization](EPIC-37-vulnerability-intelligence-synchronization.md)
- [EPIC-39 — ATT&CK Synchronization Service](EPIC-39-attack-synchronization-service.md)

Sequencing follows the phase model in the [intent document](../../architecture/security-validation-platform-v2-intent.md). This epic is planned for phase 5.

## 9. Security, risks and failure modes

- Unresolved conflicts accumulating without operational escalation
- Precedence rules hiding better data
- Confidence filtering being misread as source correctness
- Quality metrics being claimed without authoritative synchronized source datasets
- `QUALITY_POLICY_MET` being misinterpreted as a security verdict
- Curation cases being altered after review initiation
- Curation decisions being applied as execution authorization

Platform-wide invariants that this epic must not weaken:

- absence of evidence never produces a `PASS` verdict;
- quality-policy success never establishes security assurance or compliance;
- no execution outside an active authorization contract;
- Hermes / Control Plane remains the sole execution-authorization authority;
- no secrets, tokens, cookies or raw credential material in documentation, telemetry or persisted evidence;
- no target outside registered laboratories.

## 10. Deliverables

- Knowledge quality specification
- Deterministic quality-report contract
- Content-addressed curation-case contract
- Accountable curator/policy decision contract

## 11. Acceptance criteria

- Conflicts are visible, never silently dropped
- Every resolution records the rule or curator applied
- Completeness, freshness and confidence quality metrics are deterministic for identical supplied inputs
- Unresolved conflicts, missing records, stale records or below-policy confidence require review
- Curation-case tampering fails closed
- Quality state never grants execution authority or security assurance

The repository candidate satisfies these contract-level criteria through PR #192. Production persistence, operational curator workflow/UI, source-authority verification and production observability remain required before `AS_BUILT` or `FINAL`.

## 12. Evidence and validation plan

Integrated evidence:

- PR #146 — conflict persistence and explicit precedence-policy resolution
- PR #148 — immutable snapshots and explicit confidence-threshold filtering
- PR #192 — quality metrics and accountable curation contracts
- PR #192 final head: `0adf35d6f179ee69871323a30c97ad6d2d92feec`
- pre-merge `security = PASS`: run `31232226665`
- pre-merge `validate = PASS`: run `31232226647`
- integrated main: `58fc929be589c3f5dbaaf0779a12c1060f7ad30e`
- post-merge `security = PASS`: run `31232309584`
- post-merge `validate = PASS`: run `31232309593`

Future evidence required:

- persistent operational conflict/case inventory
- production curator workflow and access-control evidence
- external source-authority/currentness verification
- production quality dashboards/observability
- end-to-end evidence using synchronized production-like source datasets

## 13. Decisions and open questions

### Decisions taken

- Both conflicting claims are retained with provenance.
- Silent conflict resolution is forbidden.
- Confidence thresholds are explicit policy inputs, not implicit trust decisions.
- Quality assessment is read-only and snapshot-scoped.
- `QUALITY_POLICY_MET` is a data-quality state only and has no assurance effect.
- Curation-case identity is content-addressed and tamper-resistant.
- Manual decisions identify the curator; policy decisions identify the precedence policy.
- Automatic resolution and historical snapshot rewrite are forbidden by the current contract.
- Knowledge curation never grants execution authority.

### Open questions

- Operational escalation thresholds for unresolved conflicts
- Production persistence model for conflict and curation inventories
- Curator RBAC and approval workflow
- Source-authority/currentness verification mechanism
- Quality dashboard and alert thresholds

## 14. Implementation notes

> Reserved. Populate during implementation with pull request references, deviations from intent, and decisions taken while building. Do not delete this heading.

- PR #146 integrated conflict persistence and explicit precedence-policy resolution.
- PR #148 integrated immutable snapshots and minimum-confidence query filtering.
- PR #192 integrated deterministic quality metrics, content-addressed curation cases and accountable curator/policy decisions.
- PR #192 hardening ensures `case_id` is recomputed from canonical case content before any decision is accepted.
- Production persistence, curator UI/workflow, source-authority verification and dashboards remain `NOT_IMPLEMENTED` / `NOT_RUN`.
- External synchronization remains `NOT_RUN`.
- `NO_RUNTIME_CHANGE`.

## 15. As-built / final architecture

> Reserved. Populate when the delivery umbrella reaches completion. Must record what was actually built, evidence links, and every divergence from sections 6 to 11. No umbrella may be closed while this section is empty.

_Not final. The repository-level quality and curation contracts are implemented, but production persistence, operational curator workflow/UI, source-authority verification and production quality observability remain incomplete/NOT_RUN._

## 16. Document change log

| Date | Version | Change |
| --- | --- | --- |
| 2026-08-06 | 1.0.0 | Initial intent document created from the concept epic catalogue. |
| 2026-08-07 | 1.1.0 | Reconciled lifecycle to IMPLEMENTING using PR #146/#148 conflict, precedence, snapshot and confidence primitives; quality metrics/curation remained incomplete. |
| 2026-08-08 | 1.2.0 | Reconciled PR #192 quality metrics, tamper-resistant curation cases and accountable curation decisions while preserving production persistence/UI/source-authority/dashboard non-claims. |
