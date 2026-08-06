# EPIC-39 — ATT&CK Synchronization Service

## 1. Metadata

| Field | Value |
| --- | --- |
| Concept epic ID | `EPIC-39` |
| Slug | `attack-synchronization-service` |
| Pillar | `E` — Security Knowledge Fabric |
| Phase | 5 |
| Priority | P1 |
| Delivery umbrella | `SVP2-E-01` (issue [#86](https://github.com/pestoura/hermes-security-labs/issues/86)) |
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

ATT&CK content evolves across versions; without managed synchronization, mappings silently break or drift between releases.

## 4. Intended outcome

A managed synchronization process for ATT&CK content with version pinning, deprecation handling and migration reporting.

## 5. Scope and non-goals

### In scope

- Version-pinned ingestion
- Deprecation, revocation and rename handling
- Migration report between versions
- Impact analysis on existing mappings

### Non-goals

- Automatically rewriting historical campaign mappings

## 6. Intent architecture

Each ATT&CK version is a distinct dataset; migrations produce a report of added, deprecated and renamed items plus affected mappings.

## 7. Contracts, data and capabilities

- ATT&CK dataset version record
- Migration report format

Contracts are canonical in Git. Where this epic reuses a platform-wide contract, the
canonical definition lives in the
[reference architecture](../../architecture/security-validation-reference-architecture.md)
and in [EPIC-01](EPIC-01-architecture-and-canonical-contracts.md); this document
references it instead of restating it.

## 8. Dependencies and sequencing

- [EPIC-36 — Security Knowledge Fabric](EPIC-36-security-knowledge-fabric.md)

Sequencing follows the phase model in the
[intent document](../../architecture/security-validation-platform-v2-intent.md).
This epic is planned for phase 5.

## 9. Security, risks and failure modes

- Mappings referencing revoked techniques
- Version upgrades applied without impact review

Platform-wide invariants that this epic must not weaken:

- absence of evidence never produces a `PASS` verdict;
- no execution outside an active authorization contract;
- no secrets, tokens, cookies or raw credential material in documentation, telemetry
  or persisted evidence;
- no target outside registered laboratories.

## 10. Deliverables

- ATT&CK synchronization specification

## 11. Acceptance criteria

- Every mapping records the dataset version
- Version upgrade emits an impact report before adoption

## 12. Evidence and validation plan

- Migration reports per version change

Evidence must be referenced from the delivery umbrella issue before the umbrella can
be closed, and this document must record the references in section 15.

## 13. Decisions and open questions

### Decisions taken at intent time

- Historical campaigns keep their original version reference

### Open questions

- Adoption lag policy after upstream releases

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
