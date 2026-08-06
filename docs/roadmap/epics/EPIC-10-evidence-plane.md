# EPIC-10 — Evidence Plane

## 1. Metadata

| Field | Value |
| --- | --- |
| Concept epic ID | `EPIC-10` |
| Slug | `evidence-plane` |
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

Evidence is produced per campaign without a unified, versioned model, so chain of custody, retention and replay are not guaranteed.

## 4. Intended outcome

An Evidence Plane v2 with normalized records, chain of custody, retention policy, separation of raw and sanitized artefacts and deterministic replay.

## 5. Scope and non-goals

### In scope

- Normalized evidence record envelope
- Chain of custody with hashes and timestamps
- Raw versus sanitized separation
- Retention and replay contract

### Non-goals

- Storing secret values or unredacted credentials as evidence

## 6. Intent architecture

Every step emits evidence with content hash, producer, capability, correlation id and classification; evaluation reads only evidence, never runner side channels.

## 7. Contracts, data and capabilities

- Evidence record schema
- Custody chain entry
- Retention class

Contracts are canonical in Git. Where this epic reuses a platform-wide contract, the
canonical definition lives in the
[reference architecture](../../architecture/security-validation-reference-architecture.md)
and in [EPIC-01](EPIC-01-architecture-and-canonical-contracts.md); this document
references it instead of restating it.

## 8. Dependencies and sequencing

- [EPIC-05 — Runner Protocol v2](EPIC-05-runner-protocol-v2.md)

Sequencing follows the phase model in the
[intent document](../../architecture/security-validation-platform-v2-intent.md).
This epic is planned for phase 2.

## 9. Security, risks and failure modes

- Evidence volume outgrowing retention budget
- Sanitization removing information needed for replay

Platform-wide invariants that this epic must not weaken:

- absence of evidence never produces a `PASS` verdict;
- no execution outside an active authorization contract;
- no secrets, tokens, cookies or raw credential material in documentation, telemetry
  or persisted evidence;
- no target outside registered laboratories.

## 10. Deliverables

- Evidence Plane v2 specification
- Retention and replay policy

## 11. Acceptance criteria

- No verdict is produced without a referenced evidence record
- Raw evidence is never published outside its retention class

## 12. Evidence and validation plan

- Custody chain samples with hashes

Evidence must be referenced from the delivery umbrella issue before the umbrella can
be closed, and this document must record the references in section 15.

## 13. Decisions and open questions

### Decisions taken at intent time

- Missing evidence yields UNKNOWN, never PASS

### Open questions

- Whether replay requires pinned images or accepts equivalent digests

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
