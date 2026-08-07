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
| Document version | 1.1.0 |
| Document date | 2026-08-07 |
| Catalogue | [Epic catalogue 45](../epic-catalogue-45.md) |
| Lifecycle contract | [Architecture documentation lifecycle](../../architecture/architecture-documentation-lifecycle.md) |

## 2. Current status

**INTENT** — this concept remains intentionally unpromoted. PR #146 declares ATT&CK as a supported knowledge entity/source and provides immutable provenance primitives, but it does not implement the managed ATT&CK synchronization service required by EPIC-39.

| Lifecycle state | Reached |
| --- | --- |
| INTENT | yes |
| IMPLEMENTING | no |
| AS_BUILT | no |
| FINAL | no |

The following EPIC-39-specific capabilities remain `NOT_IMPLEMENTED` / `NOT_RUN`:

- TAXII or equivalent ATT&CK dataset synchronization;
- version-pinned ATT&CK dataset records and adoption workflow;
- added/deprecated/revoked/renamed technique handling;
- migration reports between ATT&CK versions;
- impact analysis over existing mappings;
- adoption-lag and rollback policy.

The source policy from PR #146 explicitly records TAXII/external synchronization as `NOT_RUN`. ATT&CK being a valid entity type is not evidence of a synchronization service.

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

Contracts are canonical in Git. Where this epic reuses a platform-wide contract, the canonical definition lives in the [reference architecture](../../architecture/security-validation-reference-architecture.md) and in [EPIC-01](EPIC-01-architecture-and-canonical-contracts.md); this document references it instead of restating it.

## 8. Dependencies and sequencing

- [EPIC-36 — Security Knowledge Fabric](EPIC-36-security-knowledge-fabric.md)

Sequencing follows the phase model in the [intent document](../../architecture/security-validation-platform-v2-intent.md). This epic is planned for phase 5.

## 9. Security, risks and failure modes

- Mappings referencing revoked techniques
- Version upgrades applied without impact review
- Treating entity support as proof of current synchronized ATT&CK content

Platform-wide invariants that this epic must not weaken:

- absence of evidence never produces a `PASS` verdict;
- no execution outside an active authorization contract;
- no secrets, tokens, cookies or raw credential material in documentation, telemetry or persisted evidence;
- no target outside registered laboratories.

## 10. Deliverables

- ATT&CK synchronization specification

## 11. Acceptance criteria

- Every mapping records the dataset version
- Version upgrade emits an impact report before adoption

No managed ATT&CK synchronization or migration evidence exists yet.

## 12. Evidence and validation plan

- Migration reports per version change
- Dataset-version pinning evidence
- Deprecation/rename impact tests

## 13. Decisions and open questions

### Decisions taken

- Historical campaigns keep their original version reference.
- PR #146 is shared knowledge substrate only and does not promote EPIC-39.

### Open questions

- Adoption lag policy after upstream releases

## 14. Implementation notes

> Reserved. Populate during implementation with pull request references, deviations from intent, and decisions taken while building. Do not delete this heading.

- PR #146 provides ATT&CK entity/provenance support only.
- TAXII and other external synchronization remain explicitly `NOT_RUN`.
- `NO_RUNTIME_CHANGE`.

## 15. As-built / final architecture

> Reserved. Populate when the delivery umbrella reaches completion. Must record what was actually built, evidence links, and every divergence from sections 6 to 11. No umbrella may be closed while this section is empty.

_Not started. EPIC-39 remains INTENT._

## 16. Document change log

| Date | Version | Change |
| --- | --- | --- |
| 2026-08-06 | 1.0.0 | Initial intent document created from the concept epic catalogue. |
| 2026-08-07 | 1.1.0 | Clarified that PR #146 does not implement ATT&CK synchronization; lifecycle remains INTENT. |
