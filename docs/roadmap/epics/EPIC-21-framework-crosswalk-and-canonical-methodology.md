# EPIC-21 — Framework Crosswalk and canonical methodology

## 1. Metadata

| Field | Value |
| --- | --- |
| Concept epic ID | `EPIC-21` |
| Slug | `framework-crosswalk-and-canonical-methodology` |
| Pillar | `E` — Security Knowledge Fabric |
| Phase | 5 |
| Priority | P0 |
| Delivery umbrella | `SVP2-E-01` (issue [#86](https://github.com/pestoura/hermes-security-labs/issues/86)) |
| Document version | 1.2.0 |
| Document date | 2026-08-07 |
| Catalogue | [Epic catalogue 45](../epic-catalogue-45.md) |
| Lifecycle contract | [Architecture documentation lifecycle](../../architecture/architecture-documentation-lifecycle.md) |

## 2. Current status

**AS_BUILT** — repository contract. PR #182 integrated the dedicated versioned framework-crosswalk and canonical-methodology implementation that EPIC-21 previously lacked. The repository now contains strict schemas, a seven-phase methodology, pinned manually reviewed NIST SP 800-115 and OWASP WSTG v4.2 baselines, advisory mappings with explicit relation/confidence/rationale/applicability, first-class coverage gaps and deterministic snapshot evidence. External framework synchronization and production consumer integration remain `NOT_RUN` / `NOT_IMPLEMENTED`; `FINAL = no`.

| Lifecycle state | Reached |
| --- | --- |
| INTENT | yes |
| IMPLEMENTING | yes |
| AS_BUILT | yes |
| FINAL | no |

## 3. Problem and motivation

Framework references (ATT&CK, CWE, CAPEC, NIST, OWASP, PTES) are used informally, so coverage claims cannot be substantiated or compared.

## 4. Intended outcome

A canonical crosswalk with declared confidence levels, plus a canonical methodology describing how a validation activity is structured end to end.

## 5. Scope and non-goals

### In scope

- Crosswalk between methodology phases and external frameworks
- Confidence levels for each mapping
- Canonical activity lifecycle from scoping to reporting

### Non-goals

- Claiming formal certification or compliance with any framework

## 6. Intent architecture

The crosswalk is data, not prose: each mapping carries source, target, relation type and confidence, and is consumed by planning and reporting.

## 7. Contracts, data and capabilities

- Crosswalk record schema
- Confidence level definitions
- Versioned canonical methodology record
- Versioned framework baseline and mapping dataset
- Deterministic coverage and snapshot-digest functions

Contracts are canonical in Git. Where this epic reuses a platform-wide contract, the canonical definition lives in the [reference architecture](../../architecture/security-validation-reference-architecture.md) and in [EPIC-01](EPIC-01-architecture-and-canonical-contracts.md); this document references it instead of restating it.

## 8. Dependencies and sequencing

- [EPIC-01 — Architecture and canonical contracts](EPIC-01-architecture-and-canonical-contracts.md)

Sequencing follows the phase model in the [intent document](../../architecture/security-validation-platform-v2-intent.md). This epic is planned for phase 5.

## 9. Security, risks and failure modes

- Mappings presented as authoritative equivalence
- Framework versions changing under stable mapping ids
- Incorrectly treating generic knowledge relations as a governed crosswalk
- Crosswalk content being treated as execution authorization
- Hidden authority-bearing fields being accepted by a consumer
- Stale framework baselines being silently described as current

Platform-wide invariants that this epic must not weaken:

- absence of evidence never produces a `PASS` verdict;
- no execution outside an active authorization contract;
- Hermes / Control Plane remains the sole execution-authorization authority;
- crosswalk records, methodology phases and framework references never create, grant or expand an `authorization_ref`;
- no secrets, tokens, cookies or raw credential material in documentation, telemetry or persisted evidence;
- no target outside registered laboratories.

## 10. Deliverables

- Crosswalk specification and canonical methodology document
- Strict JSON Schemas for methodology and crosswalk datasets
- Versioned baseline mappings with explicit provenance locators
- Deterministic validation, coverage summary and snapshot digest
- Regression tests for mapping semantics and authority/runtime boundaries

## 11. Acceptance criteria

- Every mapping declares relation type and confidence
- Documents use aligned or mapped, never certified or compliant

Repository-contract assessment:

- `MET` — every integrated mapping carries an explicit relation type, confidence label, numeric confidence score, target reference, rationale and applicability;
- `MET` — the semantic validator rejects certification/compliance language in mapping target/rationale and the repository documentation describes mappings as advisory alignment only.

These acceptance results apply to the repository contract and dataset only. They are not external certification or operational interoperability evidence.

## 12. Evidence and validation plan

- Crosswalk coverage summary
- Mapping records with source/target/relation/confidence
- Methodology lifecycle conformance evidence
- Strict JSON Schema validation
- Semantic fail-closed tests independent of schema validation
- Pull-request and exact-main `security` / `validate` gates

## 13. Decisions and open questions

### Decisions taken

- Mappings are advisory inputs, not compliance evidence.
- PR #146 is a dependency/substrate only and did not by itself promote EPIC-21.
- PR #182 is the dedicated EPIC-21 implementation and establishes the repository-level as-built boundary.
- The canonical methodology has seven fixed ordered phases: `scope_authorize`, `discover`, `analyze`, `validate`, `assess_impact`, `report`, `remediate_retest`.
- Execution-capable phases require `active_authorization`; `scope_authorize` is `CONTROL_PLANE_ONLY` and non-executable.
- Mapping gaps are first-class output; no relation is invented to improve apparent coverage.
- Framework baseline records are version-pinned and manually reviewed repository inputs, not evidence of live synchronization.
- Crosswalk data has `execution_effect: NONE` and cannot grant authority.

### Open questions

- Operational source synchronization/version-adoption policy belongs to the dedicated synchronization epics and remains outside this as-built contract.
- Planner/reporting consumer integration remains future work.

## 14. Implementation notes

> Reserved lifecycle section. It records the repository implementation integrated for this concept and preserves operational non-claims; do not delete this marker.

PR #182 (`feat(svp2-e01): add framework crosswalk and canonical methodology`) was squash-merged to `main` as `8800338f6ae69f61cc4cef3a5baf2bf79c0b0b97` after `security` and `validate` passed on the exact PR head. The same two gates passed again on the exact integrated `main` commit.

PR #182 introduced `platform/framework-crosswalk/` with:

- `methodology.yaml` and `methodology.schema.json`;
- `framework-crosswalk.yaml` and `framework-crosswalk.schema.json`;
- `crosswalk.py` semantic validators, coverage summary and deterministic SHA-256 snapshot digest;
- `README.md` documenting mapping, confidence, authority and runtime semantics;
- `platform/tests/test_framework_crosswalk.py` adversarial conformance tests.

The canonical methodology contains seven ordered phases:

1. `scope_authorize` — control-plane only and non-executable;
2. `discover` — authorized execution;
3. `analyze` — non-execution;
4. `validate` — authorized execution;
5. `assess_impact` — non-execution;
6. `report` — non-execution;
7. `remediate_retest` — authorized execution.

All execution-capable phases require `active_authorization` as an explicit input. The methodology does not issue that authorization.

The initial crosswalk baseline records manually reviewed, version-pinned references for:

- NIST SP 800-115 (`2008-09`);
- OWASP Web Security Testing Guide (`4.2`).

Every mapping is `advisory_only: true` and records a relation (`aligned_with`, `supports`, `informed_by`, or `overlaps`), deterministic confidence band/score, rationale and applicability. Coverage reporting exposes gaps instead of forcing equivalence. The initial OWASP mapping therefore deliberately leaves project phases without a strong equivalent as gaps.

The semantic validator fails closed independently of JSON Schema validation. It rejects unknown fields, unpinned/non-semantic dataset versions, unknown framework/phase identifiers, duplicate identifiers, invalid confidence ranges, hidden authority fields including `authorization_ref`, authorization receipts and caller-controlled `roe_decision`, and certification/compliance language in mapping claims.

No external framework API, TAXII service, scanner, runner, target, laboratory or production consumer is invoked by this component.

## 15. As-built / final architecture

> Reserved lifecycle section. EPIC-21 is `AS_BUILT` at repository-contract level but remains non-final while the wider E-01 delivery and operational consumers are incomplete.

Current factual as-built boundary:

- versioned canonical methodology: repository implemented/tested;
- strict methodology schema: repository implemented/tested;
- versioned framework crosswalk dataset: repository implemented/tested;
- strict crosswalk schema: repository implemented/tested;
- NIST SP 800-115 and OWASP WSTG v4.2 pinned baseline references: repository implemented;
- explicit mapping source/target/relation/confidence/rationale/applicability: repository implemented/tested;
- advisory-only mapping semantics and explicit gaps: repository implemented/tested;
- deterministic coverage summary: repository implemented/tested;
- deterministic snapshot SHA-256: repository implemented/tested;
- semantic exact-shape/version/authority/claim validation: repository implemented/tested;
- authoritative external framework synchronization: `NOT_RUN`;
- automatic framework updates/version adoption: `NOT_IMPLEMENTED`;
- planner consumer integration: `NOT_IMPLEMENTED`;
- reporting consumer integration: `NOT_IMPLEMENTED`;
- graph/database production consumer integration: `NOT_IMPLEMENTED` / `NOT_RUN`;
- external certification or compliance assessment: **not claimed**;
- execution effect of crosswalk data: `NONE`;
- execution authority: Hermes / Control Plane remains the sole execution-authorization authority;
- runtime/external changes: `NO_RUNTIME_CHANGE`.

Evidence:

- technical PR: #182;
- validated PR head: `15a1237edc4b4c9bc53a031c0b6140a595907ca1`;
- integrated `main`: `8800338f6ae69f61cc4cef3a5baf2bf79c0b0b97`;
- pre-merge `security`: PASS — run `31225779190`;
- pre-merge `validate`: PASS — run `31225779144`;
- post-merge `security`: PASS — run `31225883566`;
- post-merge `validate`: PASS — run `31225883573`.

`AS_BUILT` therefore applies to the dedicated repository contract and its validated static/synthetic test evidence only. `FINAL` remains `no`; no external sync, runtime consumer, certification or production execution is inferred.

`NO_RUNTIME_CHANGE`.

## 16. Document change log

| Date | Version | Change |
| --- | --- | --- |
| 2026-08-06 | 1.0.0 | Initial intent document created from the concept epic catalogue. |
| 2026-08-07 | 1.1.0 | Clarified that PR #146 is shared substrate only; crosswalk/methodology remain NOT_IMPLEMENTED/NOT_RUN and lifecycle remains INTENT. |
| 2026-08-07 | 1.2.0 | Reconciled dedicated PR #182 implementation to repository-level `AS_BUILT`; recorded gates, authority boundary, mapping semantics and operational non-claims; retained `FINAL=no`. |
