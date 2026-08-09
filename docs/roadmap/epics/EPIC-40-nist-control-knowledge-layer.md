# EPIC-40 — NIST Control Knowledge Layer

## 1. Metadata

| Field | Value |
| --- | --- |
| Concept epic ID | `EPIC-40` |
| Slug | `nist-control-knowledge-layer` |
| Pillar | `E` — Security Knowledge Fabric |
| Phase | 5 |
| Priority | P1 |
| Delivery umbrella | `SVP2-E-02` (issue [#87](https://github.com/pestoura/hermes-security-labs/issues/87)) |
| Document version | 1.2.0 |
| Document date | 2026-08-08 |
| Catalogue | [Epic catalogue 45](../epic-catalogue-45.md) |
| Lifecycle contract | [Architecture documentation lifecycle](../../architecture/architecture-documentation-lifecycle.md) |

## 2. Current status

**IMPLEMENTING** — PR #190 integrated the repository-level NIST control knowledge contract over explicitly supplied catalogue snapshots. It provides typed controls, mappings and conservative evidence projections, but it is deliberately not a compliance engine or formal control assessment service.

| Lifecycle state | Reached |
| --- | --- |
| INTENT | yes |
| IMPLEMENTING | yes |
| AS_BUILT | no |
| FINAL | no |

Implemented at repository-contract level:

- strict supplied NIST control-catalogue schema and deterministic catalogue identity;
- canonical control identifiers, objectives and Knowledge Fabric provenance;
- strict mappings from controls to ATT&CK techniques, `runbook:` references or `evidence:` requirements;
- per-mapping confidence, rationale and provenance;
- mappings must reference controls present in the supplied catalogue;
- explicit observation states `OBSERVED`, `NOT_OBSERVED`, `NOT_RUN`, `INCONCLUSIVE`;
- only `OBSERVED` may carry canonical Evidence Plane IDs;
- conservative projection states `UNMAPPED`, `MAPPED_NO_OBSERVATION`, `MAPPED_EVIDENCE_PRESENT`, `REVIEW_REQUIRED`;
- partial observation of a multi-mapping control is `REVIEW_REQUIRED`;
- all mappings must be observed before `MAPPED_EVIDENCE_PRESENT` is possible;
- low-confidence, inconclusive and explicitly not-observed mappings require review;
- bounded catalogue, mapping, observation, provenance and evidence collections;
- authority-, execution-, secret- and compliance-shaped input fields fail closed.

Every control projection fixes:

- `coverage_semantics = MAPPED_VALIDATION_COVERAGE_ONLY`;
- `compliance_verdict = NOT_EVALUATED`;
- `certification_claim = NONE`;
- `planning_effect = ADVISORY_ONLY`;
- `execution_authority = NONE`.

The following capabilities remain explicitly `NOT_IMPLEMENTED` / `NOT_RUN`:

- external NIST catalogue acquisition: `NOT_RUN`;
- authoritative/current source verification: `NOT_IMPLEMENTED` / `NOT_RUN`;
- complete production NIST control population: `NOT_RUN`;
- production graph persistence/query integration: `NOT_IMPLEMENTED`;
- production planner/report consumer integration: `NOT_IMPLEMENTED` / `NOT_RUN`;
- formal control-effectiveness assessment workflow: `NOT_IMPLEMENTED` / `NOT_RUN`;
- formal compliance/certification conclusion: not implemented and not claimed.

The repository contract therefore supports `IMPLEMENTING`, but not `AS_BUILT` or `FINAL`.

## 3. Problem and motivation

Control catalogues are referenced textually, so validation results cannot be expressed against control objectives in a structured, auditable way.

## 4. Intended outcome

A control knowledge layer linking controls to techniques, runbooks and evidence, enabling control-oriented reporting without compliance claims.

## 5. Scope and non-goals

### In scope

- Versioned supplied control catalogue representation
- Control-to-technique, control-to-runbook and control-to-evidence mappings
- Control-oriented validation coverage projection
- Mapping confidence, provenance and limitations

### Non-goals

- Asserting formal compliance or certification
- Treating evidence presence as proof of control effectiveness
- Treating supplied catalogue content as authoritative/current solely because it validates structurally

## 6. Intent architecture

Controls are typed knowledge objects; validation evidence projects onto controls through explicit, confidence-bearing mappings. Projection semantics describe mapped validation coverage only and never produce a compliance verdict.

PR #190 implements this as a repository-only contract under `platform/knowledge-fabric/control_knowledge.py`. No NIST network acquisition or production assessment service is introduced.

## 7. Contracts, data and capabilities

Canonical implementation paths from PR #190:

- `platform/knowledge-fabric/control_knowledge.py`;
- `platform/knowledge-fabric/control-catalogue.schema.json`;
- `platform/knowledge-fabric/control-mapping.schema.json`;
- `platform/knowledge-fabric/control-projection.schema.json`;
- `platform/tests/test_control_knowledge.py`;
- `platform/tests/test_control_knowledge_hardening.py`.

A catalogue is `SUPPLIED_SNAPSHOT` only and declares `external_fetch = NOT_PERFORMED`. Control mappings are advisory knowledge relations. A projection may report mapped evidence, but its fixed limitations explicitly state that mapping does not establish compliance and evidence does not establish control effectiveness by itself.

Contracts are canonical in Git. Where this epic reuses a platform-wide contract, the canonical definition lives in the [reference architecture](../../architecture/security-validation-reference-architecture.md), [EPIC-01](EPIC-01-architecture-and-canonical-contracts.md) and the generic snapshot/query substrate from PR #148.

## 8. Dependencies and sequencing

- [EPIC-36 — Security Knowledge Fabric](EPIC-36-security-knowledge-fabric.md)
- [EPIC-21 — Framework Crosswalk and canonical methodology](EPIC-21-framework-crosswalk-and-canonical-methodology.md)

Sequencing follows the phase model in the [intent document](../../architecture/security-validation-platform-v2-intent.md). This epic is planned for phase 5.

## 9. Security, risks and failure modes

- Coverage projections read as compliance attestations
- Catalogue version drift or unverified supplied content
- Generic relations being mistaken for verified control mappings
- Evidence presence being mistaken for control effectiveness
- Partial mapping observation being reported as complete coverage
- Mappings referencing controls absent from the selected catalogue

Platform-wide invariants that this epic must not weaken:

- absence of evidence never produces a `PASS` verdict;
- no execution outside an active authorization contract;
- no secrets, tokens, cookies or raw credential material in documentation, telemetry or persisted evidence;
- no target outside registered laboratories;
- control mappings/projections never create or expand execution authorization;
- Hermes / Control Plane remains the sole execution-authorization authority.

## 10. Deliverables

- NIST control knowledge contract — implemented repository-side
- Strict catalogue/mapping/projection schemas — implemented repository-side
- Conservative evidence projection logic — implemented repository-side
- External catalogue ingestion and formal assessment/reporting service — not implemented / not run

## 11. Acceptance criteria

- Coverage output states mapped validation coverage, never certified/compliant — covered by fixed projection semantics and schemas.
- Every projection carries mapping confidence where mappings exist — covered by contract/tests.
- Unmapped/unobserved/NOT_RUN never become positive verdicts — covered by projection states/tests.
- Partial multi-mapping observation requires review — covered by hardening tests.
- Mappings for controls absent from the selected catalogue fail closed — covered by hardening tests.
- Evidence presence does not become a formal control-effectiveness or compliance conclusion — covered by fixed non-claims.

Operational acceptance remains incomplete because no authoritative NIST acquisition, complete control population, formal assessment workflow or production report/planner integration has been executed.

## 12. Evidence and validation plan

Repository evidence integrated by PR #190:

- final PR head `670984fdd9e73ea2e388898f6bcbbc6c1c64ee44`;
- pre-merge `security = PASS` (`31230900392`);
- pre-merge `validate = PASS` (`31230900374`);
- integrated `main` `560cfa44c10d8a7de285a2e83e51c62df9ec7582`;
- post-merge `security = PASS` (`31230978272`);
- post-merge `validate = PASS` (`31230978273`).

Future operational evidence required before `AS_BUILT`:

- controlled authoritative NIST catalogue acquisition/version evidence;
- provenance/integrity verification for adopted catalogue content;
- complete supported-control population and mapping-curation evidence;
- formal control-assessment workflow semantics separated from mapped validation coverage;
- production report/query/planner consumer evidence;
- explicit review demonstrating no compliance/certification claim leakage.

## 13. Decisions and open questions

### Decisions taken

- The platform does not emit a compliance verdict from this layer.
- `MAPPED_EVIDENCE_PRESENT` means evidence exists for all mappings selected for the control; it does not mean the control is effective or compliant.
- Partial mapping observation is `REVIEW_REQUIRED`.
- PR #148 remains generic snapshot/query substrate only.
- PR #190 promotes EPIC-40 only to `IMPLEMENTING` after exact-SHA post-merge validation.

### Open questions

- Which authoritative NIST catalogue/baseline and version-acquisition mechanism to support first.
- Governance/curation workflow for control mappings and confidence changes.
- Boundary between future control-oriented reporting and a separately governed formal assessment capability.

## 14. Implementation notes

> Reserved. Populate during implementation with pull request references, deviations from intent, and decisions taken while building. Do not delete this heading.

- PR #148 supplies generic immutable snapshot/query primitives only.
- PR #190 supplies the NIST/control-specific catalogue, mapping and projection contracts plus adversarial tests.
- External NIST acquisition and source verification remain `NOT_RUN` / `NOT_IMPLEMENTED`.
- Formal control assessment, compliance/certification and production consumers remain `NOT_IMPLEMENTED` / `NOT_RUN` or not claimed.
- `NO_RUNTIME_CHANGE`.

## 15. As-built / final architecture

> Reserved. Populate when the delivery umbrella reaches completion. Must record what was actually built, evidence links, and every divergence from sections 6 to 11. No umbrella may be closed while this section is empty.

_Lifecycle unchanged: EPIC-40 is `IMPLEMENTING`; `AS_BUILT` and `FINAL` remain no._

### What is actually built and merged

- strict supplied NIST control-catalogue schema with deterministic catalogue identity;
- canonical control identifiers, objectives and typed control mappings;
- conservative evidence projections where unmapped, unobserved and `NOT_RUN` never become
  positive verdicts;
- partial multi-mapping observation forced to review, and mappings for controls absent from
  the selected catalogue fail closed;
- fixed non-claims `compliance_verdict = NOT_EVALUATED` and `certification_claim = NONE`.

Canonical implementation: `platform/knowledge-fabric/control_knowledge.py` with
`control-catalogue.schema.json`, `control-mapping.schema.json` and
`control-projection.schema.json`. Dedicated tests:
`platform/tests/test_control_knowledge.py` and
`platform/tests/test_control_knowledge_hardening.py`.

### Exact evidence

| Evidence | Value |
| --- | --- |
| Technical pull request | [#190](https://github.com/pestoura/hermes-security-labs/pull/190) |
| Validated PR head | `670984fdd9e73ea2e388898f6bcbbc6c1c64ee44` |
| Integrated `main` merge commit | `560cfa44c10d8a7de285a2e83e51c62df9ec7582` |
| Pre-merge `validate` | success — run `31230900374` |
| Pre-merge `security` | success — run `31230900392` |
| Post-merge `main` `validate` | success — run `31230978273` |
| Post-merge `main` `security` | success — run `31230978272` |

The merge commit is an ancestor of `main`.

### Evidence that is missing for promotion

- external NIST catalogue acquisition: `NOT_RUN`;
- authoritative/current source verification: `NOT_IMPLEMENTED` / `NOT_RUN`;
- complete production NIST control population: `NOT_RUN`;
- production graph persistence/query and planner/report consumers:
  `NOT_IMPLEMENTED` / `NOT_RUN`;
- formal control-effectiveness assessment workflow: `NOT_IMPLEMENTED` / `NOT_RUN`;
- formal compliance/certification conclusion: not implemented and not claimed.

`NO_RUNTIME_CHANGE`.

## 16. Document change log

| Date | Version | Change |
| --- | --- | --- |
| 2026-08-09 | 1.3.0 | Populated section 15 with the exact merged evidence for PR #190 and the explicit list of evidence still missing for promotion; lifecycle unchanged at `IMPLEMENTING`. |
| 2026-08-06 | 1.0.0 | Initial intent document created from the concept epic catalogue. |
| 2026-08-07 | 1.1.0 | Clarified that PR #148 does not implement the NIST/control-specific layer; lifecycle remains INTENT. |
| 2026-08-08 | 1.2.0 | Reconciled PR #190 repository-level control knowledge contract to `IMPLEMENTING`; recorded exact pre/post-merge gates and preserved assessment/compliance/source non-claims. |
