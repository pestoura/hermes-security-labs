# EPIC-45 — Operational Query and Discovery

## 1. Metadata

| Field | Value |
| --- | --- |
| Concept epic ID | `EPIC-45` |
| Slug | `operational-query-and-discovery` |
| Pillar | `E` — Security Knowledge Fabric |
| Phase | 7 |
| Priority | P1 |
| Delivery umbrella | `SVP2-E-02` (issue [#87](https://github.com/pestoura/hermes-security-labs/issues/87)) |
| Document version | 1.2.0 |
| Document date | 2026-08-08 |
| Catalogue | [Epic catalogue 45](../epic-catalogue-45.md) |
| Lifecycle contract | [Architecture documentation lifecycle](../../architecture/architecture-documentation-lifecycle.md) |

## 2. Current status

**IMPLEMENTING** — PR #148 established the immutable snapshot/minimum-confidence query substrate. PR #196 adds a repository-level canonical operational question catalogue, content-addressed access/query/index/result contracts, deterministic access filtering, exact index/evidence-id scope and sanitized-metadata-only result semantics. HTTP serving, persistent database/graph execution and production evidence/finding index integration remain `NOT_IMPLEMENTED` / `NOT_RUN`.

| Lifecycle state | Reached |
| --- | --- |
| INTENT | yes |
| IMPLEMENTING | yes |
| AS_BUILT | no |
| FINAL | no |

Implemented contract state:

- canonical operational questions cover controls for a technique, assets unvalidated for a vulnerability, findings for an asset and campaigns using a snapshot;
- every request is content-addressed, read-only, bound to one immutable knowledge snapshot and an explicit minimum confidence threshold;
- access policies are content-addressed and bind a principal to allowed asset/campaign scopes, allowed index kinds and explicit permission for unscoped knowledge;
- sanitized index entries are content-addressed and limited to `ASSET`, `CONTROL_MAPPING`, `VALIDATION`, `FINDING` and `CAMPAIGN` metadata;
- index semantic shapes fail closed when required asset, vulnerability, technique/control, finding or campaign identifiers are missing;
- query/index snapshot mixing fails closed;
- principal, query, policy, index and result tampering fails closed by canonical identity recomputation;
- questions that require multiple index kinds are denied unless the access policy authorizes all required kinds;
- asset/campaign scope filtering is deterministic;
- every result records its exact knowledge snapshot, access-policy id, index scope and evidence-id scope;
- raw/unredacted evidence is never returned by the contract: `sanitization_state = SANITIZED_METADATA_ONLY`, `raw_evidence_exposed=false`;
- results fix `read_only=true`, `assurance_effect=NONE`, `compliance_effect=NONE`, `execution_authority=NONE`;
- empty or negative results never imply `PASS` and are explicitly limited to the supplied authorized index scope.

The repository candidate still does not implement an HTTP API/server, persistent database/graph query engine, production sanitized evidence/finding index ingestion, upstream identity/RBAC policy source, production temporal ingestion or a production authorization service for query access. Those gaps prevent `AS_BUILT` or `FINAL`.

## 3. Problem and motivation

Operators need reproducible answers across knowledge, campaigns, evidence metadata and findings without exposing raw evidence or allowing partial access scopes to create misleading negative conclusions.

## 4. Intended outcome

A defined operational query surface that answers canonical questions against pinned knowledge and sanitized indexes, records the exact scope used, applies explicit read-access policy and remains auditable, read-only and non-assuring.

## 5. Scope and non-goals

### In scope

- canonical operational question catalogue;
- content-addressed query/access/index/result contracts;
- snapshot-scoped reproducible answers;
- asset/campaign/index-kind access filtering;
- exact index/evidence-id result scope;
- sanitized metadata-only query results;
- conservative negative-result semantics.

### Non-goals

- exposing raw or unredacted evidence;
- issuing commands or execution requests;
- turning query results into assurance/compliance conclusions;
- implementing HTTP, database or graph runtime in this block.

## 6. Intent architecture

Queries execute as deterministic read-only projections over explicitly supplied sanitized metadata indexes that are pinned to the same knowledge snapshot as the request. Access policy is evaluated before answering. A result records the precise authorized index/evidence-id scope used; a missing or unauthorized required index produces `DENY`, not an inferred negative conclusion.

## 7. Contracts, data and capabilities

Canonical repository contracts introduced by PR #196:

- `platform/knowledge-api/operational_query.py`
- `platform/knowledge-api/operational-query-access-policy.schema.json`
- `platform/knowledge-api/operational-query-request.schema.json`
- `platform/knowledge-api/operational-query-index.schema.json`
- `platform/knowledge-api/operational-query-result.schema.json`

The query contract recursively refuses raw-evidence, secret, target, execution and authorization-receipt-shaped fields.

## 8. Dependencies and sequencing

- [EPIC-36 — Security Knowledge Fabric](EPIC-36-security-knowledge-fabric.md)
- [EPIC-43 — Knowledge-Driven Campaign Planner](EPIC-43-knowledge-driven-campaign-planner.md)
- [EPIC-33 — Finding and remediation lifecycle](EPIC-33-finding-and-remediation-lifecycle.md)

## 9. Security, risks and failure modes

- query results interpreted as security assurance or compliance;
- sensitive/raw evidence exposure through query results;
- unpinned or mixed-snapshot queries producing non-reproducible answers;
- partial authorization over required indexes creating false negative conclusions;
- cross-asset/campaign data leakage;
- tampered sanitized index metadata;
- evidence identifiers being mistaken for evidence content.

Platform invariants:

- absence of results never produces a `PASS` verdict;
- negative results are limited to the supplied authorized index scope;
- raw evidence is never returned by this query contract;
- query access cannot create execution authority;
- no secrets, credentials, targets or commands enter query artefacts;
- Hermes / Control Plane remains the sole execution-authorization authority for executable operations.

## 10. Deliverables

- operational query implementation contract;
- canonical question catalogue;
- read-access policy contract;
- sanitized operational index contract;
- deterministic result/evidence-scope contract;
- adversarial tests.

## 11. Acceptance criteria

- every result cites its immutable knowledge snapshot and exact index/evidence-id scope;
- raw or unredacted evidence is never returned;
- read access is fail-closed for asset, campaign, unscoped knowledge and required index kinds;
- identical authorized inputs produce identical results;
- cross-snapshot mixing and content tampering fail closed;
- empty/negative results never imply PASS, assurance or compliance.

These repository-level criteria are covered by PR #196. Production serving/persistence/integration criteria remain incomplete.

## 12. Evidence and validation plan

Integrated evidence:

- PR #148 — immutable snapshot and minimum-confidence query substrate;
- PR #196 final head: `e2991e4500c14d1526c2c22f7c005974a9b29844`;
- pre-merge `security = PASS`: `31233653404`;
- pre-merge `validate = PASS`: `31233653405`;
- integrated main: `54da73138b3de098e7911852616ffdc5f26d0005`;
- post-merge `security = PASS`: `31233734226`;
- post-merge `validate = PASS`: `31233734241`.

Future evidence required:

- production HTTP/API query surface;
- persistent database/graph query engine;
- production sanitized evidence/finding index integration;
- upstream identity/RBAC policy source and operational authorization tests;
- production temporal ingestion and reproducibility evidence.

## 13. Decisions and open questions

### Decisions taken

- canonical operational questions are explicit rather than arbitrary free-form queries;
- results are read-only metadata projections;
- all query artefacts are content-addressed and tamper-resistant;
- raw evidence is excluded from the query surface;
- a policy must authorize every index kind required to answer a question;
- denial is safer than a partial negative inference;
- negative/empty results are never security or compliance verdicts.

### Open questions

- production API protocol and deployment boundary;
- upstream identity/RBAC integration;
- persistent query/index storage model;
- retention/refresh policy for sanitized indexes;
- whether controlled ad hoc queries are introduced after the canonical catalogue is operationally validated.

## 14. Implementation notes

- PR #148 integrated snapshot/query validation and temporal-series contracts.
- PR #196 integrated canonical questions, read-access policy, sanitized indexes, deterministic results and exact index/evidence-id scope.
- PR #196 hardening denies queries when the policy does not authorize all required index kinds.
- HTTP API, database and graph query engine remain `NOT_IMPLEMENTED`.
- Production evidence/finding index and temporal ingestion remain `NOT_RUN`.
- `NO_RUNTIME_CHANGE`.

## 15. As-built / final architecture

> Reserved for validated operational delivery.

_Lifecycle unchanged: EPIC-45 is `IMPLEMENTING`; `AS_BUILT` and `FINAL` remain no._

### What is actually built and merged

- canonical operational question catalogue and content-addressed access, query, index and
  result contracts;
- deterministic fail-closed access filtering for asset, campaign, unscoped knowledge and
  required index kinds, including denial when the policy does not authorize every required
  index kind;
- exact index and evidence-id scope carried on every result;
- fixed sanitization and non-claims: `sanitization_state = SANITIZED_METADATA_ONLY`,
  `raw_evidence_exposed=false`, `read_only=true`, `assurance_effect=NONE`,
  `compliance_effect=NONE`, `execution_authority=NONE`;
- empty or negative results never imply `PASS`.

Canonical implementation: `platform/knowledge-api/operational_query.py` with
`operational-query-access-policy.schema.json`, `operational-query-index.schema.json`,
`operational-query-request.schema.json` and `operational-query-result.schema.json`.
Dedicated tests: `platform/tests/test_operational_query.py` and
`platform/tests/test_operational_query_hardening.py`.

### Exact evidence

| Evidence | Value |
| --- | --- |
| Technical pull request | [#196](https://github.com/pestoura/hermes-security-labs/pull/196) |
| Validated PR head | `e2991e4500c14d1526c2c22f7c005974a9b29844` |
| Integrated `main` merge commit | `54da73138b3de098e7911852616ffdc5f26d0005` |
| Pre-merge `validate` | success — run `31233653405` |
| Pre-merge `security` | success — run `31233653404` |
| Post-merge `main` `validate` | success — run `31233734241` |
| Post-merge `main` `security` | success — run `31233734226` |

The merge commit is an ancestor of `main`.

### Evidence that is missing for promotion

The epic's target state is *operational query and discovery*; nothing is served:

- HTTP API or query server: `NOT_IMPLEMENTED`;
- persistent database/graph query engine: `NOT_IMPLEMENTED`;
- production sanitized evidence and finding index ingestion: `NOT_RUN`;
- upstream identity/RBAC policy source and production authorization service for query
  access: `NOT_IMPLEMENTED` / `NOT_RUN`;
- production temporal ingestion: `NOT_RUN`.

`NO_RUNTIME_CHANGE`.

## 16. Document change log

| Date | Version | Change |
| --- | --- | --- |
| 2026-08-09 | 1.3.0 | Populated section 15 with the exact merged evidence and the explicit list of evidence still missing for promotion; lifecycle unchanged at `IMPLEMENTING`. |
| 2026-08-06 | 1.0.0 | Initial intent document created from the concept epic catalogue. |
| 2026-08-07 | 1.1.0 | Reconciled lifecycle to IMPLEMENTING against PR #148. |
| 2026-08-08 | 1.2.0 | Reconciled PR #196 canonical questions, access filtering, sanitized indexes, exact result scope and fail-closed negative-query semantics. |
