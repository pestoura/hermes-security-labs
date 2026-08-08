# EPIC-12 — Redaction and data classification

## 1. Metadata

| Field | Value |
| --- | --- |
| Concept epic ID | `EPIC-12` |
| Slug | `redaction-and-data-classification` |
| Pillar | `D` — Evidence Observability and Assurance |
| Phase | 2 |
| Priority | P0 |
| Delivery umbrella | `SVP2-D-01` (issue [#84](https://github.com/pestoura/hermes-security-labs/issues/84)) |
| Document version | 1.2.0 |
| Document date | 2026-08-08 |
| Catalogue | [Epic catalogue 45](../epic-catalogue-45.md) |
| Lifecycle contract | [Architecture documentation lifecycle](../../architecture/architecture-documentation-lifecycle.md) |

## 2. Current status

**IMPLEMENTING** — PR #141 integrated repository-level classification/redaction constraints. PR #219 added a deterministic structured redaction engine exercised with synthetic fixtures and integrated with the controlled local Evidence Plane store. The engine removes explicitly sensitive classes, overrides sensitive field names even when misclassified as safe, rejects unknown shapes/classifications and preserves source-digest lineage for derived evidence.

| Lifecycle state | Reached |
| --- | --- |
| INTENT | yes |
| IMPLEMENTING | yes |
| AS_BUILT | no |
| FINAL | no |

Current factual boundary:

- evidence classification contract: implemented;
- structured label-driven redaction: `PASS_CONTROLLED_CI`;
- sensitive-name override: `PASS_CONTROLLED_CI`;
- derived lineage into local store: `PASS_CONTROLLED_CI`;
- free-text/heuristic secret discovery: `NOT_CLAIMED`;
- redaction before persistence of sensitive source material: `NOT_RUN`;
- production redaction/publication enforcement: `NOT_RUN`;
- telemetry/report coverage: `NOT_RUN`;
- Human-in-the-Loop publication review: `NOT_RUN`.

## 3. Problem and motivation

Sensitive material can appear in outputs, logs and evidence without a classification model or an enforced redaction boundary.

## 4. Intended outcome

A data classification scheme with enforced redaction at emission and clear rules on what may ever be persisted or published.

## 5. Scope and non-goals

### In scope

- Classification levels for evidence, telemetry and reports
- Redaction rules and enforcement points
- Prohibited persistence list
- Review procedure for sanitized publication
- Controlled deterministic redaction for explicitly classified structured evidence

### Non-goals of the current controlled engine

- Weakening existing prohibitions on secrets in the repository
- Claiming heuristic detection of arbitrary secrets embedded in free text
- Processing customer evidence or credentials in CI
- Claiming redaction-before-persistence until that specific boundary is demonstrated

## 6. Intent architecture

Classification is assigned at production time; redaction is applied before persistence and again before publication, with the stricter rule winning.

The currently implemented controlled engine demonstrates the transformation itself and the derived lineage boundary, but the technical #219 fixture persists its synthetic source before derivation. Therefore it is evidence for deterministic structured redaction, not yet evidence that production-sensitive source material is always redacted before persistence.

## 7. Contracts, data and capabilities

Canonical implementation:

- `platform/evidence-plane/evidence-policy.yaml`;
- `platform/evidence-plane/evidence_plane.py`;
- `platform/evidence-plane/local_store.py`;
- `platform/evidence-plane/redaction.py`.

The structured redactor accepts only the canonical envelope `schema_version + fields`. Every field must declare `name`, `classification` and `value`.

Safe field classifications are limited to `public` and `operational`. Sensitive classes include `secret`, `credential`, `token`, `cookie`, `personal_data`, `customer_data`, `raw_command` and `raw_output`.

Sensitive field names and compound names such as token/cookie/password-bearing keys are removed even when a caller mislabels them as safe. Sensitive nested keys in retained structures fail closed. Unknown classifications, duplicate fields, unsupported shapes and excessive nesting fail closed.

The engine does not infer execution authority. Redaction metadata and evidence records are descriptive only and never grant or expand authorization.

## 8. Dependencies and sequencing

- [EPIC-10 — Evidence Plane](EPIC-10-evidence-plane.md)

PR #217 delivered the controlled local persistence boundary consumed by the PR #219 redaction integration tests. The next dependency-safe block is redaction-before-persistence for structured source material, so synthetic sensitive canaries are transformed before any persistent object is created.

## 9. Security, risks and failure modes

- Over-redaction destroying analytic value
- Redaction bypass through new output paths
- Classification mismatch between evidence, telemetry and reports
- Treating label-driven redaction as heuristic discovery of secrets in arbitrary text
- Sensitive field names being deliberately misclassified as safe
- Persisting source material before applying the redaction boundary
- Treating controlled CI evidence as production redaction coverage

Platform-wide invariants that this epic must not weaken:

- absence of evidence never produces a `PASS` verdict;
- no execution outside an active authorization contract;
- no secrets, tokens, cookies or raw credential material in documentation or telemetry;
- no target outside registered laboratories;
- unknown classification or redaction shape fails closed;
- derived evidence does not become authorization.

## 10. Deliverables

Delivered so far:

- classification and redaction specification;
- deterministic structured redaction engine;
- fail-closed field/classification/shape validation;
- synthetic canary tests for credential/token/cookie/raw-output classes;
- sensitive-name override tests including compound names;
- deterministic output tests;
- local Evidence Plane parent/source-digest lineage integration.

Still pending:

- redaction-before-persistence boundary for source material;
- production telemetry/report integration;
- customer publication/export path;
- Human-in-the-Loop publication approval evidence;
- any free-text secret-discovery capability, if ever adopted.

## 11. Acceptance criteria

Partially demonstrated:

- persisted Evidence Plane records carry a classification label by contract;
- the structured redactor removes classified credential/token/cookie fields from its derived payload;
- sensitive names are removed even when explicitly misclassified as `public`;
- derived payloads preserve verified parent/source-digest lineage;
- raw/restricted evidence remains non-exportable by default.

Not yet demonstrated:

- no credential/token/cookie value is ever persisted from a sensitive source: the current #219 integration deliberately stores only synthetic source fixtures before derivation, so redaction-before-persistence is still `NOT_RUN`;
- all telemetry/report persistence paths apply the same classification/redaction policy;
- production publication/review enforcement.

## 12. Evidence and validation plan

Current evidence:

- PR #141 — contract/schema constraints;
- PR #219 validated head `1e694b6ab4303e55ac671a3721e461018dfcb045`;
- PR #219 `security` run `31266256283`: PASS;
- PR #219 `validate` run `31266256292`: PASS;
- PR #219 squash merge `383d60479f5874ac103fe3a74654e85690be19d0`;
- post-merge `security` run `31266367567`: PASS;
- post-merge `validate` run `31266367331`: PASS.

Next evidence must prove that structured sensitive source material is transformed in memory before any local persistence occurs, and that the persisted lineage contains only a safe source manifest/digest plus the derived sanitized payload.

## 13. Decisions and open questions

### Decisions taken

- Unclassified or unsupported evidence never receives a permissive path.
- Raw/restricted evidence is non-exportable by default.
- Derived evidence preserves parent/redaction lineage.
- The controlled redactor is label-driven, not heuristic free-text discovery.
- Sensitive-name overrides are fail-closed even when classification is falsely permissive.
- PR #219 is not sufficient evidence for redaction-before-persistence because its raw source fixture is persisted in the disposable CI store.

### Open questions

- Whether hashes of real secrets are acceptable for correlation in production policy
- Canonical cross-plane classification labels for telemetry and reports
- Publication review workflow and retention of approval evidence
- Whether a future free-text detector is needed or explicit structured classification is sufficient for the MVP

## 14. Implementation notes

> Reserved. Populate during implementation with pull request references, deviations from intent, and decisions taken while building. Do not delete this heading.

- PR #141 integrated classification, non-exportability, metadata refusal and derived-evidence lineage constraints.
- PR #219 integrated deterministic structured redaction and synthetic canary coverage.
- All #219 values are synthetic test canaries; no customer payload or credential was used.
- Production/deployed redaction remains `NOT_RUN`.

## 15. As-built / final architecture

> Reserved. This section records the current controlled boundary but remains non-final.

Current state:

- classification contract: implemented;
- structured redaction engine: `PASS_CONTROLLED_CI`;
- sensitive classes removed from derived payload: `PASS_CONTROLLED_CI`;
- sensitive-name override: `PASS_CONTROLLED_CI`;
- derived local-store lineage: `PASS_CONTROLLED_CI`;
- free-text secret discovery: `NOT_CLAIMED`;
- redaction before persistence: `NOT_RUN`;
- telemetry/report integration: `NOT_RUN`;
- publication review/enforcement: `NOT_RUN`;
- deployed runtime: `NO_RUNTIME_CHANGE`.

`AS_BUILT` for the complete concept remains false and `FINAL` remains false.

## 16. Document change log

| Date | Version | Change |
| --- | --- | --- |
| 2026-08-06 | 1.0.0 | Initial intent document created from the concept epic catalogue. |
| 2026-08-07 | 1.1.0 | Reconciled lifecycle to IMPLEMENTING against PR #141 while preserving production redaction/persistence/publication claims as NOT_IMPLEMENTED/NOT_RUN. |
| 2026-08-08 | 1.2.0 | Record PR #219 deterministic structured-redaction evidence and explicitly preserve redaction-before-persistence, telemetry/report and publication boundaries as NOT_RUN. |
