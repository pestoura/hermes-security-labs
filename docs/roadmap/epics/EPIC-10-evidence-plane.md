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
| Document version | 1.1.0 |
| Document date | 2026-08-07 |
| Catalogue | [Epic catalogue 45](../epic-catalogue-45.md) |
| Lifecycle contract | [Architecture documentation lifecycle](../../architecture/architecture-documentation-lifecycle.md) |

## 2. Current status

**IMPLEMENTING** — the repository-level Evidence Plane v2 contract candidate from PR #141 is integrated in `main`. This is not an operational or production claim.

| Lifecycle state | Reached |
| --- | --- |
| INTENT | yes |
| IMPLEMENTING | yes |
| AS_BUILT | no |
| FINAL | no |

Implemented contract state:

- strict Evidence Plane v2 record schema;
- campaign, run, step and attempt correlation identifiers;
- payload SHA-256, byte count, media type and storage-reference metadata;
- explicit `raw`, `restricted`, `sanitized` and `summary` classification;
- parent linkage and redaction lineage for derived evidence;
- default non-exportability of raw/restricted evidence;
- secret-bearing metadata, raw commands and raw stdout/stderr rejected;
- deterministic replay descriptors using identifiers, provenance and hashes only;
- derived evidence chains fail closed on parent digest mismatch.

Operational evidence store, encryption at rest, immutable/WORM storage, retention enforcement, object storage, production redaction/replay and customer export remain `NOT_IMPLEMENTED` or `NOT_RUN`.

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

Contracts are canonical in Git. Where this epic reuses a platform-wide contract, the canonical definition lives in the [reference architecture](../../architecture/security-validation-reference-architecture.md) and in [EPIC-01](EPIC-01-architecture-and-canonical-contracts.md); this document references it instead of restating it.

## 8. Dependencies and sequencing

- [EPIC-05 — Runner Protocol v2](EPIC-05-runner-protocol-v2.md)

Sequencing follows the phase model in the [intent document](../../architecture/security-validation-platform-v2-intent.md). This epic is planned for phase 2.

## 9. Security, risks and failure modes

- Evidence volume outgrowing retention budget
- Sanitization removing information needed for replay
- Storage or export layers bypassing classification rules
- Treating repository contract tests as evidence of production custody controls

Platform-wide invariants that this epic must not weaken:

- absence of evidence never produces a `PASS` verdict;
- no execution outside an active authorization contract;
- no secrets, tokens, cookies or raw credential material in documentation, telemetry or persisted evidence;
- no target outside registered laboratories.

## 10. Deliverables

- Evidence Plane v2 specification
- Retention and replay policy

## 11. Acceptance criteria

- No verdict is produced without a referenced evidence record
- Raw evidence is never published outside its retention class

The repository candidate partially supports these criteria at contract level only. Production persistence/export enforcement is still required before `AS_BUILT` or `FINAL`.

## 12. Evidence and validation plan

- Contract/schema tests and adversarial cases from PR #141
- Future custody-chain samples from the selected persistent evidence backend
- Future encryption-at-rest, immutability and retention observations
- Future production redaction/replay evidence

## 13. Decisions and open questions

### Decisions taken

- Missing evidence yields UNKNOWN, never PASS.
- Raw/restricted evidence is non-exportable by default.
- Replay descriptors carry provenance and hashes, not payload bytes.

### Open questions

- Whether replay requires pinned images or accepts equivalent digests
- Persistent evidence backend and WORM mechanism
- Retention classes and deletion policy

## 14. Implementation notes

> Reserved. Populate during implementation with pull request references, deviations from intent, and decisions taken while building. Do not delete this heading.

- PR #141 integrated the repository-owned Evidence Plane v2 contract candidate.
- Runtime/storage operations were deliberately not activated.
- `NO_RUNTIME_CHANGE`.

## 15. As-built / final architecture

> Reserved. Populate when the delivery umbrella reaches completion. Must record what was actually built, evidence links, and every divergence from sections 6 to 11. No umbrella may be closed while this section is empty.

_Not final. Persistent storage, retention, encryption, immutability, production redaction/replay and export controls remain to be implemented and evidenced._

## 16. Document change log

| Date | Version | Change |
| --- | --- | --- |
| 2026-08-06 | 1.0.0 | Initial intent document created from the concept epic catalogue. |
| 2026-08-07 | 1.1.0 | Reconciled lifecycle to IMPLEMENTING against PR #141 while preserving all operational storage/redaction/replay claims as NOT_IMPLEMENTED/NOT_RUN. |
