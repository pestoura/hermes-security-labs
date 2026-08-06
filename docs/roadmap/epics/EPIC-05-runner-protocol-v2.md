# EPIC-05 — Runner Protocol v2

## 1. Metadata

| Field | Value |
| --- | --- |
| Concept epic ID | `EPIC-05` |
| Slug | `runner-protocol-v2` |
| Pillar | `B` — Runtime Foundation |
| Phase | 1 |
| Priority | P0 |
| Delivery umbrella | `SVP2-B-02` (issue [#80](https://github.com/pestoura/hermes-security-labs/issues/80)) |
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

Runners differ in invocation, correlation, cancellation and error reporting, which prevents uniform orchestration and uniform evidence.

## 4. Intended outcome

A single Runner Protocol covering correlation identifiers, cancellation, timeouts, progress, normalized errors and evidence emission.

## 5. Scope and non-goals

### In scope

- Correlation id propagation across campaign, step and runner
- Cooperative cancellation and hard timeout
- Normalized error taxonomy shared with the gateway
- Mandatory evidence emission per step

### Non-goals

- Changing runbook semantics of existing packs

## 6. Intent architecture

Runner exposes a uniform contract: accept typed step, stream progress, return typed outcome plus evidence references; failure modes are enumerated, not free text.

## 7. Contracts, data and capabilities

- Runner step envelope
- Runner outcome envelope
- Error taxonomy

Contracts are canonical in Git. Where this epic reuses a platform-wide contract, the
canonical definition lives in the
[reference architecture](../../architecture/security-validation-reference-architecture.md)
and in [EPIC-01](EPIC-01-architecture-and-canonical-contracts.md); this document
references it instead of restating it.

## 8. Dependencies and sequencing

- [EPIC-01 — Architecture and canonical contracts](EPIC-01-architecture-and-canonical-contracts.md)

Sequencing follows the phase model in the
[intent document](../../architecture/security-validation-platform-v2-intent.md).
This epic is planned for phase 1.

## 9. Security, risks and failure modes

- Legacy runners partially migrating and diverging
- Cancellation not honoured by long-running tools

Platform-wide invariants that this epic must not weaken:

- absence of evidence never produces a `PASS` verdict;
- no execution outside an active authorization contract;
- no secrets, tokens, cookies or raw credential material in documentation, telemetry
  or persisted evidence;
- no target outside registered laboratories.

## 10. Deliverables

- Runner Protocol v2 specification
- Migration notes for existing runners

## 11. Acceptance criteria

- Every step outcome carries correlation id and evidence reference
- Cancellation is observable and bounded in time

## 12. Evidence and validation plan

- Protocol conformance checklist per runner

Evidence must be referenced from the delivery umbrella issue before the umbrella can
be closed, and this document must record the references in section 15.

## 13. Decisions and open questions

### Decisions taken at intent time

- No PASS may be produced without an evidence reference

### Open questions

- Whether streaming progress is mandatory or optional for short steps

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
