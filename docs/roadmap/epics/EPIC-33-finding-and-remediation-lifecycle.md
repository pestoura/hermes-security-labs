# EPIC-33 — Finding and remediation lifecycle

## 1. Metadata

| Field | Value |
| --- | --- |
| Concept epic ID | `EPIC-33` |
| Slug | `finding-and-remediation-lifecycle` |
| Pillar | `J` — Risk Findings and Interoperability |
| Phase | 7 |
| Priority | P1 |
| Delivery umbrella | `SVP2-J-01` (issue [#93](https://github.com/pestoura/hermes-security-labs/issues/93)) |
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

Findings have no formal lifecycle, so remediation, retest, acceptance and closure are not tracked with evidence.

## 4. Intended outcome

A finding lifecycle from detection through remediation and evidence-backed retest to closure, with explicit risk acceptance.

## 5. Scope and non-goals

### In scope

- Finding states and permitted transitions
- Retest requirement and evidence linkage
- Risk acceptance with owner and expiry
- Reopen semantics on regression

### Non-goals

- Automatically closing findings without retest evidence

## 6. Intent architecture

A finding references originating evidence; closure requires new evidence from a retest, not a claim.

### Intent diagram

```mermaid
stateDiagram-v2
  [*] --> Detected
  Detected --> Triaged
  Triaged --> Remediating
  Triaged --> Accepted: risk accepted
  Remediating --> Retesting
  Retesting --> Closed: evidence confirms fix
  Retesting --> Remediating: still present
  Accepted --> Detected: acceptance expired
  Closed --> Detected: regression
```

## 7. Contracts, data and capabilities

- Finding record schema
- Transition rules
- Risk acceptance record

Contracts are canonical in Git. Where this epic reuses a platform-wide contract, the
canonical definition lives in the
[reference architecture](../../architecture/security-validation-reference-architecture.md)
and in [EPIC-01](EPIC-01-architecture-and-canonical-contracts.md); this document
references it instead of restating it.

## 8. Dependencies and sequencing

- [EPIC-10 — Evidence Plane](EPIC-10-evidence-plane.md)
- [EPIC-27 — Risk Intelligence and contextual prioritization](EPIC-27-risk-intelligence-and-contextual-prioritization.md)

Sequencing follows the phase model in the
[intent document](../../architecture/security-validation-platform-v2-intent.md).
This epic is planned for phase 7.

## 9. Security, risks and failure modes

- Findings closed administratively without retest
- Duplicate findings across campaigns

Platform-wide invariants that this epic must not weaken:

- absence of evidence never produces a `PASS` verdict;
- no execution outside an active authorization contract;
- no secrets, tokens, cookies or raw credential material in documentation, telemetry
  or persisted evidence;
- no target outside registered laboratories.

## 10. Deliverables

- Finding lifecycle specification

## 11. Acceptance criteria

- Closure requires referenced retest evidence
- Risk acceptance always carries an owner and expiry

## 12. Evidence and validation plan

- Lifecycle transition log per finding

Evidence must be referenced from the delivery umbrella issue before the umbrella can
be closed, and this document must record the references in section 15.

## 13. Decisions and open questions

### Decisions taken at intent time

- No closure without evidence

### Open questions

- Deduplication key for recurring findings

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
