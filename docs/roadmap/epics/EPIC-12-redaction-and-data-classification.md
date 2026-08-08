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
| Document version | 1.3.0 |
| Document date | 2026-08-08 |
| Catalogue | [Epic catalogue 45](../epic-catalogue-45.md) |
| Lifecycle contract | [Architecture documentation lifecycle](../../architecture/architecture-documentation-lifecycle.md) |

## 2. Current status

**IMPLEMENTING** — PR #141 integrated repository-level classification/redaction constraints. PR #219 added a deterministic structured redaction engine over synthetic fixtures. PR #221 then added a controlled safe-ingress pipeline that performs structured redaction entirely in memory before the first Evidence Plane store write; the original sensitive source bytes are never passed to persistence.

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
- redaction before persistence of structured sensitive source material: `PASS_CONTROLLED_CI`;
- original source bytes persisted by safe-ingress path: `no`;
- free-text/heuristic secret discovery: `NOT_CLAIMED`;
- Production redaction: `NOT_IMPLEMENTED` / `NOT_RUN`;
- production publication enforcement: `NOT_IMPLEMENTED` / `NOT_RUN`;
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
- Controlled pre-persistence safe-ingress for structured source material

### Non-goals of the current controlled boundary

- Weakening existing prohibitions on secrets in the repository
- Claiming heuristic detection of arbitrary secrets embedded in free text
- Processing customer evidence or credentials in CI
- Claiming production telemetry/report/publication coverage

## 6. Intent architecture

Classification is assigned at production time; redaction is applied before persistence and again before publication, with the stricter rule winning.

PR #221 demonstrates the first half of that intent for the controlled structured local boundary. The source payload is redacted in memory first. Persistence then receives only:

1. a restricted digest-only source manifest containing the original source SHA-256 and an explicit `NOT_PERSISTED` state; and
2. the sanitized derived payload linked to that manifest.

The original source bytes and synthetic sensitive canary values are never passed to the local store. This does not claim production-wide coverage or free-text discovery.

## 7. Contracts, data and capabilities

Canonical implementation:

- `platform/evidence-plane/evidence-policy.yaml`;
- `platform/evidence-plane/evidence_plane.py`;
- `platform/evidence-plane/local_store.py`;
- `platform/evidence-plane/redaction.py`;
- `platform/evidence-plane/safe_persistence.py`.

The structured redactor accepts only the canonical envelope `schema_version + fields`. Every field must declare `name`, `classification` and `value`.

Safe field classifications are limited to `public` and `operational`. Sensitive classes include `secret`, `credential`, `token`, `cookie`, `personal_data`, `customer_data`, `raw_command` and `raw_output`.

Sensitive field names and compound names such as token/cookie/password-bearing keys are removed even when a caller mislabels them as safe. Sensitive nested keys in retained structures fail closed. Unknown classifications, duplicate fields, unsupported shapes and excessive nesting fail closed.

The safe-ingress pipeline executes redaction before the first store write. It persists a restricted source manifest containing only safe metadata and the original source hash, then persists the sanitized derivative with verified parent lineage. The manifest itself is non-exportable.

The engine and safe-ingress pipeline do not infer execution authority. Redaction metadata and evidence records are descriptive only and never grant or expand authorization.

## 8. Dependencies and sequencing

- [EPIC-10 — Evidence Plane](EPIC-10-evidence-plane.md)

PR #217 delivered controlled local persistence, PR #219 delivered structured redaction, and PR #221 closed the controlled redaction-before-persistence gap. The remaining D-01 work is replay/reconstruction semantics plus the production-only durability, retention, telemetry/report and publication boundaries.

## 9. Security, risks and failure modes

- Over-redaction destroying analytic value
- Redaction bypass through new output paths
- Classification mismatch between evidence, telemetry and reports
- Treating label-driven redaction as heuristic discovery of secrets in arbitrary text
- Sensitive field names being deliberately misclassified as safe
- A future path bypassing `safe_persistence.py` and persisting source bytes directly
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
- local Evidence Plane parent/source-digest lineage integration;
- controlled redaction-before-persistence safe-ingress;
- digest-only restricted source manifest plus sanitized derivative persistence.

Still pending:

- controlled replay/reconstruction proof for D-01;
- Production redaction integration;
- production telemetry/report integration;
- customer publication/export path;
- Human-in-the-Loop publication approval evidence;
- any free-text secret-discovery capability, if ever adopted.

## 11. Acceptance criteria

Demonstrated at the controlled structured local boundary:

- persisted Evidence Plane records carry a classification label by contract;
- the structured redactor removes classified credential/token/cookie fields from its derived payload;
- sensitive names are removed even when explicitly misclassified as `public`;
- derived payloads preserve verified parent/source-digest lineage;
- raw/restricted evidence remains non-exportable by default;
- structured sensitive source bytes are transformed before any store write;
- synthetic credential/token/cookie/raw-output canary values do not occur anywhere under the safe-ingress store root;
- repeated identical ingress is content/record idempotent;
- invalid structured source fails before any persisted object is created.

Not yet demonstrated:

- all production telemetry/report persistence paths apply the same classification/redaction policy;
- Production redaction and publication/review enforcement remain `NOT_IMPLEMENTED` / `NOT_RUN`;
- arbitrary free-text secret discovery is `NOT_CLAIMED`.

## 12. Evidence and validation plan

Current evidence:

- PR #141 — contract/schema constraints;
- PR #219 validated head `1e694b6ab4303e55ac671a3721e461018dfcb045`;
- PR #219 `security` `31266256283`: PASS;
- PR #219 `validate` `31266256292`: PASS;
- PR #219 squash merge `383d60479f5874ac103fe3a74654e85690be19d0`;
- PR #219 post-merge `security` `31266367567`: PASS;
- PR #219 post-merge `validate` `31266367331`: PASS;
- PR #221 validated head `2ea071b81930abc14f6dc84b2dc4831c67bf2d79`;
- PR #221 `security` `31267093045`: PASS;
- PR #221 `validate` `31267093060`: PASS;
- PR #221 squash merge `cbf88aecb9bf69ad4d7bd0164f8ac8f61f04b4aa`;
- PR #221 post-merge `security` `31267199992`: PASS;
- PR #221 post-merge `validate` `31267199995`: PASS.

Next evidence should address deterministic replay/reconstruction without equating a replay descriptor with re-executing a security tool.

## 13. Decisions and open questions

### Decisions taken

- Unclassified or unsupported evidence never receives a permissive path.
- Raw/restricted evidence is non-exportable by default.
- Derived evidence preserves parent/redaction lineage.
- The controlled redactor is label-driven, not heuristic free-text discovery.
- Sensitive-name overrides are fail-closed even when classification is falsely permissive.
- Safe ingress persists only a digest-only restricted source manifest and sanitized derivative; original source bytes are not persisted.
- A source hash is evidence of identity/correlation, not a substitute for production DLP or encryption.

### Open questions

- Whether hashes of real secrets are acceptable for correlation in production policy
- Canonical cross-plane classification labels for telemetry and reports
- Publication review workflow and retention of approval evidence
- Whether a future free-text detector is needed or explicit structured classification is sufficient for the MVP

## 14. Implementation notes

> Reserved. Populate during implementation with pull request references, deviations from intent, and decisions taken while building. Do not delete this heading.

- PR #141 integrated classification, non-exportability, metadata refusal and derived-evidence lineage constraints.
- PR #219 integrated deterministic structured redaction and synthetic canary coverage.
- PR #221 integrated redaction-before-persistence for structured synthetic source material.
- All #219/#221 sensitive values are synthetic test canaries; no customer payload or credential was used.
- Production redaction and deployed publication remain `NOT_IMPLEMENTED` / `NOT_RUN`.

## 15. As-built / final architecture

> Reserved. This section records the current controlled boundary but remains non-final.

Current state:

- classification contract: implemented;
- structured redaction engine: `PASS_CONTROLLED_CI`;
- sensitive classes removed from derived payload: `PASS_CONTROLLED_CI`;
- sensitive-name override: `PASS_CONTROLLED_CI`;
- derived local-store lineage: `PASS_CONTROLLED_CI`;
- redaction before persistence: `PASS_CONTROLLED_CI`;
- source sensitive bytes persisted by safe-ingress path: `no`;
- free-text secret discovery: `NOT_CLAIMED`;
- Production redaction: `NOT_IMPLEMENTED` / `NOT_RUN`;
- telemetry/report integration: `NOT_RUN`;
- publication review/enforcement: `NOT_IMPLEMENTED` / `NOT_RUN`;
- deployed runtime: `NO_RUNTIME_CHANGE`.

`AS_BUILT` for the complete concept remains false and `FINAL` remains false.

## 16. Document change log

| Date | Version | Change |
| --- | --- | --- |
| 2026-08-06 | 1.0.0 | Initial intent document created from the concept epic catalogue. |
| 2026-08-07 | 1.1.0 | Reconciled lifecycle to IMPLEMENTING against PR #141 while preserving production redaction/persistence/publication claims as NOT_IMPLEMENTED/NOT_RUN. |
| 2026-08-08 | 1.2.0 | Record PR #219 deterministic structured-redaction evidence and preserve Production redaction/telemetry/publication boundaries as non-final. |
| 2026-08-08 | 1.3.0 | Record PR #221 controlled redaction-before-persistence evidence while preserving production and free-text discovery non-claims. |
