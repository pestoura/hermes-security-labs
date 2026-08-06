# EPIC-01 — Architecture and canonical contracts

## 1. Metadata

| Field | Value |
| --- | --- |
| Concept epic ID | `EPIC-01` |
| Slug | `architecture-and-canonical-contracts` |
| Pillar | `A` — Governance and Architecture |
| Phase | 1 |
| Priority | P0 |
| Delivery umbrella | `SVP2-A-01` (issue [#76](https://github.com/pestoura/hermes-security-labs/issues/76)) |
| Document version | 1.1.0 |
| Document date | 2026-08-06 |
| Catalogue | [Epic catalogue 45](../epic-catalogue-45.md) |
| Lifecycle contract | [Architecture documentation lifecycle](../../architecture/architecture-documentation-lifecycle.md) |

## 2. Current status

**IMPLEMENTING** — the first delivery block is active on branch
`docs/epic-01-canonical-contracts`. The architecture contracts, initial ADR set and
mechanical documentation gates are being implemented. No runtime enforcement is claimed.

| Lifecycle state | Reached |
| --- | --- |
| INTENT | yes |
| IMPLEMENTING | yes |
| AS_BUILT | no |
| FINAL | no |

## 3. Problem and motivation

Control plane and execution plane responsibilities are described informally across several documents; there is no single canonical contract set, no ADR trail and no explicit trust boundary model.

## 4. Intended outcome

A canonical reference architecture with numbered trust boundaries TB0-TB4, ADRs for every structural decision, and contract artefacts that all other epics reference instead of restating.

## 5. Scope and non-goals

### In scope

- Canonical reference architecture as the single architectural source of truth
- Trust boundaries TB0-TB4 with responsibilities, prohibitions and crossing rules
- ADR directory, numbering and review process
- Contract inventory: authorization, execution, evidence, knowledge

### Non-goals

- Implementing gateway or runner code
- Changing existing runtimes or compose files

## 6. Intent architecture

Control plane (Hermes) authorizes and plans; execution plane (Security Execution Gateway / Kali MCP) executes typed contracts; evidence plane records; knowledge plane proposes. No plane accumulates authorize+execute+attest.

### Intent diagram

```mermaid
flowchart LR
  A[Control plane: Hermes] -->|typed request| B[Execution plane: gateway]
  B --> C[Runners]
  C --> D[Evidence plane]
  E[Knowledge plane] -->|proposals| A
  D --> F[Assurance plane]
```

## 7. Contracts, data and capabilities

- Authorization contract (Rules of Engagement reference)
- Typed execution request/response envelope
- Evidence record envelope
- ADR record format

Contracts are canonical in Git. Where this epic reuses a platform-wide contract, the
canonical definition lives in the
[reference architecture](../../architecture/security-validation-reference-architecture.md),
the [contract inventory](../../architecture/contracts/README.md) and the
[ADR register](../../architecture/adr/README.md); this document references them instead of
restating them.

## 8. Dependencies and sequencing

- None. This concept epic can start once the umbrella is scheduled.

Sequencing follows the phase model in the
[intent document](../../architecture/security-validation-platform-v2-intent.md).
This epic is planned for phase 1.

## 9. Security, risks and failure modes

- Documented architecture drifting from implementation
- ADRs becoming stale without a review trigger

Platform-wide invariants that this epic must not weaken:

- absence of evidence never produces a `PASS` verdict;
- no execution outside an active authorization contract;
- no secrets, tokens, cookies or raw credential material in documentation, telemetry
  or persisted evidence;
- no target outside registered laboratories.

## 10. Deliverables

- Canonical reference architecture kept current
- ADR set under docs/architecture/adr
- Trust boundary table with crossing rules

## 11. Acceptance criteria

- Every trust boundary declares responsibilities and prohibitions
- Every structural roadmap decision has an ADR
- No executable offensive instruction is present in architecture documents

## 12. Evidence and validation plan

- Documentation tests pass
- ADR index resolves for every referenced decision

Evidence must be referenced from the delivery umbrella issue before the umbrella can
be closed, and this document must record the references in section 15.

## 13. Decisions and open questions

### Decisions taken at intent time

- Hermes remains the only authorization authority.

### Decisions taken during implementation

- `ADR-0001`: separate proposal, authorization, execution, evidence and assurance authority.
- `ADR-0002`: TB0-TB4 identify trust-domain crossings, resolving the pre-existing conflict
  with the initial plane-based numbering.
- `ADR-0003` to `ADR-0008`: type safety, fail-safe evaluation, isolation, provenance,
  evidence publication and human-controlled promotion become canonical structural decisions.

### Open questions

- None for this block. ADR supersession chains live in ADR metadata and the canonical ADR
  index; the process is defined in [`docs/architecture/adr/README.md`](../../architecture/adr/README.md).

## 14. Implementation notes

> Reserved lifecycle section. Updated during implementation with pull request references,
> deviations from intent and decisions taken while building. Do not delete this heading.

### Block 1 — canonical contracts and ADR foundation

- Branch: `docs/epic-01-canonical-contracts`
- Umbrella issue: [#76](https://github.com/pestoura/hermes-security-labs/issues/76)
- Pull request: pending creation from this branch
- Runtime declaration: `NO_RUNTIME_CHANGE`
- Added the ADR governance/index and eight initial structural ADRs.
- Added the canonical cross-plane contract inventory.
- Updated the reference architecture with the canonical TB0-TB4 crossing model.
- Added documentation tests for ADR numbering, coverage, contract inventory and boundary
  completeness.

### Recorded divergence

| Intent reference | Observed state | Resolution | Decision record |
| --- | --- | --- | --- |
| section 6 and platform intent trust boundaries | the initial reference architecture used TB0-TB4 as component/plane labels, while the platform intent used them as crossings | crossings are canonical; GitHub remains source-of-truth context without a numbered TB | `ADR-0002` |

## 15. As-built / final architecture

> Reserved. Populate after the implementation pull request is merged. Must record what
> was actually built, evidence links, and every divergence from sections 6 to 11.
> No umbrella may be closed while this section is empty.

_Not yet merged._

## 16. Document change log

| Date | Version | Change |
| --- | --- | --- |
| 2026-08-06 | 1.0.0 | Initial intent document created from the concept epic catalogue. |
| 2026-08-06 | 1.1.0 | Set IMPLEMENTING; record branch, initial ADR decisions, contract inventory and trust-boundary divergence. |
