# EPIC-26 — Interoperable playbooks and results

## 1. Metadata

| Field | Value |
| --- | --- |
| Concept epic ID | `EPIC-26` |
| Slug | `interoperable-playbooks-and-results` |
| Pillar | `J` — Risk Findings and Interoperability |
| Phase | 7 |
| Priority | P2 |
| Delivery umbrella | `SVP2-J-02` (issue [#94](https://github.com/pestoura/hermes-security-labs/issues/94)) |
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

Playbooks and results are internal formats, preventing exchange with external tooling, governance systems and partners.

## 4. Intended outcome

Import and export mappings for recognised interchange formats covering playbooks, results and control assessments.

## 5. Scope and non-goals

### In scope

- Playbook interchange mapping
- Result and finding export mapping
- Control assessment export mapping
- Round-trip fidelity rules

### Non-goals

- Claiming certified conformance with any interchange standard

## 6. Intent architecture

Internal models remain canonical; interchange formats are projections with documented lossy fields.

## 7. Contracts, data and capabilities

- Export mapping tables
- Lossy field inventory

Contracts are canonical in Git. Where this epic reuses a platform-wide contract, the
canonical definition lives in the
[reference architecture](../../architecture/security-validation-reference-architecture.md)
and in [EPIC-01](EPIC-01-architecture-and-canonical-contracts.md); this document
references it instead of restating it.

## 8. Dependencies and sequencing

- [EPIC-10 — Evidence Plane](EPIC-10-evidence-plane.md)
- [EPIC-23 — Attack Graph and Attack Flow](EPIC-23-attack-graph-and-attack-flow.md)

Sequencing follows the phase model in the
[intent document](../../architecture/security-validation-platform-v2-intent.md).
This epic is planned for phase 7.

## 9. Security, risks and failure modes

- Silent information loss on export
- Standard version drift

Platform-wide invariants that this epic must not weaken:

- absence of evidence never produces a `PASS` verdict;
- no execution outside an active authorization contract;
- no secrets, tokens, cookies or raw credential material in documentation, telemetry
  or persisted evidence;
- no target outside registered laboratories.

## 10. Deliverables

- Interoperability specification

## 11. Acceptance criteria

- Every export documents its lossy fields
- Round-trip of supported fields is stable

## 12. Evidence and validation plan

- Round-trip test plan

Evidence must be referenced from the delivery umbrella issue before the umbrella can
be closed, and this document must record the references in section 15.

## 13. Decisions and open questions

### Decisions taken at intent time

- Interchange formats never become the internal source of truth

### Open questions

- Which formats justify first-wave support

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
