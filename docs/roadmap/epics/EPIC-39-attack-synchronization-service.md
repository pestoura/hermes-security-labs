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
| Document version | 1.2.0 |
| Document date | 2026-08-08 |
| Catalogue | [Epic catalogue 45](../epic-catalogue-45.md) |
| Lifecycle contract | [Architecture documentation lifecycle](../../architecture/architecture-documentation-lifecycle.md) |

## 2. Current status

**IMPLEMENTING** — PR #188 integrated the repository-level ATT&CK version-pinning and migration-impact contract over explicitly supplied snapshots. It does not perform TAXII or other external ATT&CK synchronization.

| Lifecycle state | Reached |
| --- | --- |
| INTENT | yes |
| IMPLEMENTING | yes |
| AS_BUILT | no |
| FINAL | no |

Implemented at repository-contract level:

- strict supplied ATT&CK dataset and migration-report schemas;
- deterministic dataset identity over provider, domain, version, publication timestamp, locator and normalized technique content;
- canonical ATT&CK technique/sub-technique and STIX object identifiers;
- unique technique/STIX identifiers and bounded datasets/mapping sets;
- replacement validation, same-dataset replacement targets and replacement-cycle refusal;
- migration requires the same ATT&CK domain plus a strictly newer version and publication timestamp;
- deterministic change reporting for added, removed, renamed, revoked/deprecated, replaced and STIX-object-id-changed techniques;
- impact analysis over explicitly supplied historical mappings pinned to the source dataset;
- affected mappings are review-only and are never rewritten;
- blocking findings for removed techniques, stable ATT&CK IDs changing STIX object identity, and revoked/deprecated techniques without a replacement;
- even a no-impact migration is only `ELIGIBLE_FOR_REVIEW`; automatic adoption is always false;
- outputs declare `historical_rewrite = false`, `external_sync = NOT_PERFORMED` and `execution_authority = NONE`.

The following capabilities remain explicitly `NOT_IMPLEMENTED` / `NOT_RUN`:

- TAXII or equivalent external ATT&CK synchronization: `NOT_RUN`;
- upstream source provenance/signature verification: `NOT_IMPLEMENTED` / `NOT_RUN`;
- scheduled synchronization or upstream release polling: `NOT_IMPLEMENTED`;
- automatic ATT&CK version adoption: `NOT_IMPLEMENTED`;
- production migration/adoption workflow: `NOT_IMPLEMENTED` / `NOT_RUN`;
- production graph/planner consumption of migration reports: `NOT_IMPLEMENTED` / `NOT_RUN`;
- authoritative/current-source claim for supplied snapshots: not claimed.

The repository contract therefore supports `IMPLEMENTING`, but not `AS_BUILT` or `FINAL`.

## 3. Problem and motivation

ATT&CK content evolves across versions; without managed synchronization, mappings silently break or drift between releases.

## 4. Intended outcome

A managed synchronization process for ATT&CK content with version pinning, deprecation handling and migration reporting.

## 5. Scope and non-goals

### In scope

- Version-pinned dataset contract
- Deprecation, revocation, replacement and rename handling
- Migration report between versions
- Impact analysis on existing mappings

### Non-goals

- Automatically rewriting historical campaign mappings
- Treating a supplied snapshot as authoritative/current solely because it validates structurally
- Automatically adopting an upstream version

## 6. Intent architecture

Each ATT&CK version is a distinct dataset; migrations produce a deterministic report of changes and affected mappings.

PR #188 implements this as a repository-only contract under `platform/knowledge-fabric/attack_sync.py`. Input datasets must be explicitly supplied snapshots. No network acquisition is performed.

## 7. Contracts, data and capabilities

Canonical implementation paths from PR #188:

- `platform/knowledge-fabric/attack_sync.py`;
- `platform/knowledge-fabric/attack-dataset.schema.json`;
- `platform/knowledge-fabric/attack-migration-report.schema.json`;
- `platform/tests/test_attack_sync.py`.

The dataset contract fixes `source_origin = SUPPLIED_SNAPSHOT` and `external_fetch = NOT_PERFORMED`. Migration output fixes `automatic_adoption = false`, `historical_rewrite = false`, `external_sync = NOT_PERFORMED` and `execution_authority = NONE`.

Contracts are canonical in Git. Where this epic reuses a platform-wide contract, the canonical definition lives in the [reference architecture](../../architecture/security-validation-reference-architecture.md) and in [EPIC-01](EPIC-01-architecture-and-canonical-contracts.md); this document references it instead of restating it.

## 8. Dependencies and sequencing

- [EPIC-36 — Security Knowledge Fabric](EPIC-36-security-knowledge-fabric.md)

Sequencing follows the phase model in the [intent document](../../architecture/security-validation-platform-v2-intent.md). This epic is planned for phase 5.

## 9. Security, risks and failure modes

- Mappings referencing revoked techniques
- Version upgrades applied without impact review
- Treating entity support as proof of current synchronized ATT&CK content
- Treating supplied data as authoritative without source verification
- Automatic replacement of historical mappings
- Replacement cycles or replacement targets absent from the adopted dataset
- Stable ATT&CK IDs silently resolving to a different STIX object

Platform-wide invariants that this epic must not weaken:

- absence of evidence never produces a `PASS` verdict;
- no execution outside an active authorization contract;
- no secrets, tokens, cookies or raw credential material in documentation, telemetry or persisted evidence;
- no target outside registered laboratories;
- ATT&CK migration output never creates or expands execution authorization;
- Hermes / Control Plane remains the sole execution-authorization authority.

## 10. Deliverables

- ATT&CK supplied-dataset/version contract — implemented repository-side
- Deterministic migration/impact report — implemented repository-side
- External TAXII/synchronization and production adoption service — not implemented / not run

## 11. Acceptance criteria

- Every mapping records the dataset version — covered by the source-dataset-bound mapping contract used for migration impact analysis.
- Version upgrade emits an impact report before adoption — covered by the deterministic migration-report contract.
- Historical mappings are never automatically rewritten — covered by contract/tests.
- Removed/revoked/deprecated/object-identity changes are explicit review or blocking conditions — covered by contract/tests.
- No-impact changes still require a review decision before adoption — covered by `automatic_adoption = false`.

Operational acceptance remains incomplete because no authoritative external ATT&CK synchronization or production adoption has been executed.

## 12. Evidence and validation plan

Repository evidence integrated by PR #188:

- PR head `06fcaf2f7c1179fac59954581bdcff1b2b6e08ee`;
- pre-merge `security = PASS` (`31229852229`);
- pre-merge `validate = PASS` (`31229852214`);
- integrated `main` `a702fd70a7a6bc65653cfde270ca8de0b48a2460`;
- post-merge `security = PASS` (`31229951534`);
- post-merge `validate = PASS` (`31229951514`).

Future operational evidence required before `AS_BUILT`:

- controlled TAXII/equivalent external synchronization evidence;
- authoritative source provenance and integrity/signature verification evidence where available;
- release polling/checkpoint/retry evidence;
- controlled adoption approval and rollback evidence;
- production graph/planner migration-consumer evidence;
- demonstrated migration against real ATT&CK release changes while preserving historical snapshots.

## 13. Decisions and open questions

### Decisions taken

- Historical campaigns keep their original dataset reference.
- Supplied snapshots are structurally validated but are not claimed authoritative/current without source-verification evidence.
- No migration result can auto-adopt a version or rewrite historical mappings.
- Replacement cycles and missing replacement targets fail closed.
- PR #146 is shared knowledge substrate only.
- PR #188 promotes EPIC-39 only to `IMPLEMENTING` after exact-SHA post-merge validation.

### Open questions

- Adoption lag policy after upstream releases.
- Authoritative TAXII/source-verification mechanism and operational credentials model.
- Rollback and emergency freeze policy for a future production synchronizer.

## 14. Implementation notes

> Reserved. Populate during implementation with pull request references, deviations from intent, and decisions taken while building. Do not delete this heading.

- PR #146 provides ATT&CK entity/provenance support only.
- PR #188 provides version-pinned supplied-snapshot, migration and impact-analysis contracts.
- TAXII/external synchronization remains `NOT_RUN`.
- No network client, scheduled poller or automatic adoption path was introduced.
- `NO_RUNTIME_CHANGE`.

## 15. As-built / final architecture

> Reserved. Populate when the delivery umbrella reaches completion. Must record what was actually built, evidence links, and every divergence from sections 6 to 11. No umbrella may be closed while this section is empty.

_Not populated. EPIC-39 is IMPLEMENTING; AS_BUILT and FINAL remain no._

## 16. Document change log

| Date | Version | Change |
| --- | --- | --- |
| 2026-08-06 | 1.0.0 | Initial intent document created from the concept epic catalogue. |
| 2026-08-07 | 1.1.0 | Clarified that PR #146 does not implement ATT&CK synchronization; lifecycle remains INTENT. |
| 2026-08-08 | 1.2.0 | Reconciled PR #188 supplied-snapshot ATT&CK migration contract to `IMPLEMENTING`; recorded exact pre/post-merge gates and preserved external-sync/adoption non-claims. |
