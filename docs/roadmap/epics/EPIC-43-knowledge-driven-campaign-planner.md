# EPIC-43 — Knowledge-Driven Campaign Planner

## 1. Metadata

| Field | Value |
| --- | --- |
| Concept epic ID | `EPIC-43` |
| Slug | `knowledge-driven-campaign-planner` |
| Pillar | `E` — Security Knowledge Fabric |
| Phase | 6 |
| Priority | P1 |
| Delivery umbrella | `SVP2-E-02` (issue [#87](https://github.com/pestoura/hermes-security-labs/issues/87)) |
| Document version | 1.2.0 |
| Document date | 2026-08-08 |
| Catalogue | [Epic catalogue 45](../epic-catalogue-45.md) |
| Lifecycle contract | [Architecture documentation lifecycle](../../architecture/architecture-documentation-lifecycle.md) |

## 2. Current status

**IMPLEMENTING** — PR #148 established the snapshot-bound non-executable proposal envelope. PR #194 adds deterministic repository-level plan derivation, explicit filtering/rationale, content-addressed planning/candidate/plan identities and deterministic plan diffing. A production planner service and runtime authorization verification remain `NOT_IMPLEMENTED` / `NOT_RUN`.

| Lifecycle state | Reached |
| --- | --- |
| INTENT | yes |
| IMPLEMENTING | yes |
| AS_BUILT | no |
| FINAL | no |

Implemented contract state:

- planning context is content-addressed and binds campaign id, immutable knowledge snapshot id, capability-registry version and supplied RoE contract id/payload hash;
- planning context explicitly includes asset ids, ATT&CK technique ids, CVE ids, allowed capability ids, intrusiveness ceiling and minimum confidence;
- supplied RoE data is a planning reference only: `constraint_effect = PLANNING_FILTER_ONLY`, `authorization_effect = NONE`;
- planning candidates are content-addressed, non-executable records carrying operation/capability, intrusiveness, assets, threat mappings, knowledge provenance, confidence and rationale;
- candidates are filtered deterministically for capability, intrusiveness, asset scope, confidence and threat-context match;
- every excluded candidate records deterministic exclusion reasons;
- selected steps are ordered deterministically and record their selection rationale;
- planning context, candidate and plan identities are recomputed from canonical content so post-creation tampering fails closed;
- plan diff is deterministic and limited to proposals from the same campaign;
- plans remain `PROPOSAL_ONLY`, `executable=false`, `planning_constraints_are_authorization=false`, `authorization_effect=NONE`, `requires_fresh_authorization=true`;
- execution authorization remains `CONTROL_PLANE_ONLY`.

The repository candidate still does not implement a production planner service, live asset/threat discovery, verification that a supplied RoE contract is currently active, runtime capability-registry lookup, dispatch, runner integration or execution. These gaps prevent `AS_BUILT` or `FINAL`.

## 3. Problem and motivation

Campaign content assembled manually is difficult to reproduce and audit. Planning needs deterministic derivation with explicit rationale while remaining strictly separate from execution authorization.

## 4. Intended outcome

A planner that deterministically derives a campaign proposal from asset/threat context, knowledge snapshot, capability-registry version and authorized-scope references, with every selection/exclusion explained and with fresh Control Plane authorization required before any execution.

## 5. Scope and non-goals

### In scope

- deterministic plan-derivation inputs and output;
- rationale trail for selected and excluded candidates;
- filtering by capability, intrusiveness, asset scope, confidence and threat context;
- content-addressed/tamper-resistant planning artefacts;
- plan diffing between proposals.

### Non-goals

- validating runtime authorization inside the knowledge planner;
- producing commands, targets, credentials or runner requests;
- executing or dispatching a plan;
- automatically approving a plan.

## 6. Intent architecture

Planner inputs are immutable references and advisory constraints. They produce a deterministic proposal only. Supplied RoE context does not become runtime authorization. A later execution path must independently obtain and validate fresh authorization through Hermes / Control Plane.

## 7. Contracts, data and capabilities

Canonical repository contracts:

- `platform/knowledge-api/campaign_planner.py`
- `platform/knowledge-api/campaign-planning-context.schema.json`
- `platform/knowledge-api/campaign-plan-candidate.schema.json`
- `platform/knowledge-api/campaign-plan.schema.json`
- `platform/knowledge-api/campaign-plan-diff.schema.json`

The contracts prohibit command-, target-, secret- and authorization-shaped input fields from entering the planner.

## 8. Dependencies and sequencing

- [EPIC-36 — Security Knowledge Fabric](EPIC-36-security-knowledge-fabric.md)
- [EPIC-28 — Rules of Engagement as Code](EPIC-28-rules-of-engagement-as-code.md)
- [EPIC-07 — Capability Registry](EPIC-07-capability-registry.md)

Sequencing follows the phase model in the [intent document](../../architecture/security-validation-platform-v2-intent.md).

## 9. Security, risks and failure modes

- planning constraints being mistaken for authorization;
- supplied RoE data being mistaken for a currently verified authorization receipt;
- non-determinism from unpinned inputs;
- tampered context/candidate/plan artefacts;
- plans over-fitted to available knowledge;
- stale capability or threat context;
- proposal data accidentally interpreted as executable work.

Platform invariants:

- absence of evidence never produces a `PASS` verdict;
- planning constraints never create or expand authorization;
- Hermes / Control Plane remains the sole execution-authorization authority;
- fresh authorization is mandatory before execution;
- no secrets, tokens, cookies or raw credential material enter planner artefacts;
- planner outputs contain no executable command/target payload.

## 10. Deliverables

- deterministic planning-context contract;
- candidate/rationale contract;
- deterministic campaign-plan proposal contract;
- deterministic plan-diff contract;
- adversarial contract tests.

## 11. Acceptance criteria

- identical canonical inputs yield an identical plan;
- candidate input order does not change the plan;
- every selected step records why it was selected;
- every excluded candidate records why it was excluded;
- context, candidate and plan tampering fail closed;
- plan diffs are deterministic and same-campaign only;
- plans remain non-executable and require fresh Control Plane authorization.

These repository-level criteria are covered by PR #194. Production-service and end-to-end runtime criteria remain incomplete.

## 12. Evidence and validation plan

Integrated evidence:

- PR #148 — snapshot-bound non-executable proposal substrate;
- PR #194 final head: `697b64ca5a4916d0fca99b96e16092e294002e46`;
- pre-merge `security = PASS`: `31232994632`;
- pre-merge `validate = PASS`: `31232994583`;
- integrated main: `52b355b61a3d273b8d6d934ab270157dc0a34c48`;
- post-merge `security = PASS`: `31233069181`;
- post-merge `validate = PASS`: `31233069182`.

Future evidence required:

- production planner service;
- live asset/threat source integration;
- runtime capability-registry lookup/version validation;
- independent active-RoE/authorization verification before execution;
- operational plan-to-approval-to-run evidence.

## 13. Decisions and open questions

### Decisions taken

- Plans are proposals, never authorization.
- Supplied RoE information is a planning constraint/reference only.
- Planner artefacts are content-addressed and fail closed on tampering.
- Exclusion is first-class and always carries explicit reasons.
- Identical inputs must yield identical ordering and content.
- Every plan requires fresh authorization before execution.

### Open questions

- Production planner service boundary and persistence model;
- live asset/threat discovery sources;
- runtime capability-registry query model;
- approval UX between proposal and execution.

## 14. Implementation notes

- PR #148 integrated the snapshot-bound non-executable proposal candidate.
- PR #194 integrated deterministic planning context, candidate filtering, selection/exclusion rationale, plan identity and plan diffing.
- No production planner, dispatch, runner call or target access was introduced.
- `NO_RUNTIME_CHANGE`.

## 15. As-built / final architecture

> Reserved for validated operational delivery.

_Lifecycle unchanged: EPIC-43 is `IMPLEMENTING`; `AS_BUILT` and `FINAL` remain no._

### What is actually built and merged

- deterministic plan derivation from a canonical planning context, independent of candidate
  input order;
- explicit selection and exclusion rationale for every candidate;
- content-addressed planning-context, candidate and plan identities recomputed from
  canonical content, so post-creation tampering fails closed;
- deterministic plan diffing restricted to proposals from the same campaign;
- fixed non-executable semantics: `PROPOSAL_ONLY`, `executable=false`,
  `authorization_effect=NONE`, `requires_fresh_authorization=true`,
  `CONTROL_PLANE_ONLY`.

Canonical implementation: `platform/knowledge-api/campaign_planner.py` with
`campaign-planning-context.schema.json`, `campaign-plan-candidate.schema.json`,
`campaign-plan.schema.json` and `campaign-plan-diff.schema.json`. Dedicated tests:
`platform/tests/test_campaign_planner.py`.

### Exact evidence

| Evidence | Value |
| --- | --- |
| Technical pull request | [#194](https://github.com/pestoura/hermes-security-labs/pull/194) |
| Validated PR head | `697b64ca5a4916d0fca99b96e16092e294002e46` |
| Integrated `main` merge commit | `52b355b61a3d273b8d6d934ab270157dc0a34c48` |
| Pre-merge `validate` | success — run `31232994583` |
| Pre-merge `security` | success — run `31232994632` |
| Post-merge `main` `validate` | success — run `31233069182` |
| Post-merge `main` `security` | success — run `31233069181` |

The merge commit is an ancestor of `main`.

### Evidence that is missing for promotion

The repository-level acceptance criteria in section 11 are covered, but the epic is a
*planner*, and no planning has ever run against live state:

- production planner service: `NOT_IMPLEMENTED`;
- live asset/threat discovery and context integration: `NOT_RUN`;
- verification that a supplied RoE contract is currently active: `NOT_IMPLEMENTED`;
- runtime capability-registry lookup, dispatch and runner integration:
  `NOT_IMPLEMENTED` / `NOT_RUN`.

`NO_RUNTIME_CHANGE`.

## 16. Document change log

| Date | Version | Change |
| --- | --- | --- |
| 2026-08-09 | 1.3.0 | Populated section 15 with the exact merged evidence and the explicit list of evidence still missing for promotion; lifecycle unchanged at `IMPLEMENTING`. |
| 2026-08-06 | 1.0.0 | Initial intent document created from the concept epic catalogue. |
| 2026-08-07 | 1.1.0 | Reconciled lifecycle to IMPLEMENTING against PR #148. |
| 2026-08-08 | 1.2.0 | Reconciled PR #194 deterministic derivation, filtering, tamper resistance and plan-diff evidence while preserving production/runtime non-claims. |
