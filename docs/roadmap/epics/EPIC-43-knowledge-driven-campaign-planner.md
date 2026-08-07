# EPIC-43 — Knowledge-Driven Campaign Planner

## 1. Metadata

| Field | Value |
| --- | --- |
| Concept epic ID | `EPIC-43` |
| Slug | `knowledge-driven-campaign-planner` |
| Pillar | `E` — Security Knowledge Fabric |
| Phase | 6 |
| Priority | P1 |
| Delivery umbrella | `SVP2-E-02` (issue [#87](https://github.com/pestoura/hermes-security-labs/issues/87)) |
| Document version | 1.1.0 |
| Document date | 2026-08-07 |
| Catalogue | [Epic catalogue 45](../epic-catalogue-45.md) |
| Lifecycle contract | [Architecture documentation lifecycle](../../architecture/architecture-documentation-lifecycle.md) |

## 2. Current status

**IMPLEMENTING** — PR #148 integrated a repository-level campaign proposal contract bound to an immutable knowledge snapshot and rationale. The full knowledge-driven production planner remains `NOT_RUN` / incomplete.

| Lifecycle state | Reached |
| --- | --- |
| INTENT | yes |
| IMPLEMENTING | yes |
| AS_BUILT | no |
| FINAL | no |

Implemented contract state:

- campaigns can be bound to the exact immutable knowledge snapshot used for planning;
- proposal records require campaign id, snapshot id and rationale;
- every proposed step requires an operation and reason;
- proposals are explicitly `PROPOSAL_ONLY`, `executable=false`;
- execution-shaped fields such as command, argv, shell, cwd, environment, executable and entrypoint are refused;
- execution authorization remains `CONTROL_PLANE_ONLY`.

The candidate does not yet derive plans from asset context, threat profile, active authorization contract and capability-registry version, does not provide plan diffing, and is not a production planner. `production_planner` remains `NOT_RUN`.

## 3. Problem and motivation

Campaign content is assembled manually, so planning is not reproducible and its rationale is not recorded.

## 4. Intended outcome

A planner that derives a campaign plan from asset context, threat profile, knowledge snapshot and the active authorization contract, with a recorded rationale.

## 5. Scope and non-goals

### In scope

- Plan derivation inputs and deterministic output
- Rationale trail per selected step
- Contract-aware filtering by intrusiveness and scope
- Plan diffing between runs

### Non-goals

- Executing a plan without human authorization

## 6. Intent architecture

Planner output is a proposal referencing the knowledge snapshot, the contract and the capability registry version; the same inputs must yield the same plan.

## 7. Contracts, data and capabilities

- Campaign plan record
- Selection rationale entry

Contracts are canonical in Git. Where this epic reuses a platform-wide contract, the canonical definition lives in the [reference architecture](../../architecture/security-validation-reference-architecture.md) and in [EPIC-01](EPIC-01-architecture-and-canonical-contracts.md); this document references it instead of restating it.

## 8. Dependencies and sequencing

- [EPIC-36 — Security Knowledge Fabric](EPIC-36-security-knowledge-fabric.md)
- [EPIC-28 — Rules of Engagement as Code](EPIC-28-rules-of-engagement-as-code.md)
- [EPIC-07 — Capability Registry](EPIC-07-capability-registry.md)

Sequencing follows the phase model in the [intent document](../../architecture/security-validation-platform-v2-intent.md). This epic is planned for phase 6.

## 9. Security, risks and failure modes

- Plans over-fitted to available content
- Non-determinism from unpinned inputs
- Proposal data accidentally interpreted as execution authorization
- Missing asset/threat/authorization bindings producing under-specified plans

Platform-wide invariants that this epic must not weaken:

- absence of evidence never produces a `PASS` verdict;
- no execution outside an active authorization contract;
- no secrets, tokens, cookies or raw credential material in documentation, telemetry or persisted evidence;
- no target outside registered laboratories.

## 10. Deliverables

- Campaign planner specification

## 11. Acceptance criteria

- Identical inputs yield an identical plan
- Every step records why it was selected

The repository candidate implements a deterministic non-executable proposal envelope and rationale trail, but full derivation inputs/filtering still require implementation before `AS_BUILT` or `FINAL`.

## 12. Evidence and validation plan

- Contract tests from PR #148
- Future plan records binding asset context, threat profile, RoE authorization contract and capability registry
- Future plan-diff/determinism evidence

## 13. Decisions and open questions

### Decisions taken

- Plans are proposals; execution authorization remains exclusively in the control plane.
- Command-shaped execution fields are forbidden from proposals.

### Open questions

- How to represent deliberately excluded steps
- Canonical asset/threat/authorization input envelope for plan derivation

## 14. Implementation notes

> Reserved. Populate during implementation with pull request references, deviations from intent, and decisions taken while building. Do not delete this heading.

- PR #148 integrated the snapshot-bound non-executable campaign proposal candidate.
- No production planner or campaign execution was activated.
- `NO_RUNTIME_CHANGE`.

## 15. As-built / final architecture

> Reserved. Populate when the delivery umbrella reaches completion. Must record what was actually built, evidence links, and every divergence from sections 6 to 11. No umbrella may be closed while this section is empty.

_Not final. Full knowledge-driven derivation and production planner execution remain incomplete/NOT_RUN._

## 16. Document change log

| Date | Version | Change |
| --- | --- | --- |
| 2026-08-06 | 1.0.0 | Initial intent document created from the concept epic catalogue. |
| 2026-08-07 | 1.1.0 | Reconciled lifecycle to IMPLEMENTING against PR #148 while preserving full derivation and production planner as incomplete/NOT_RUN. |
