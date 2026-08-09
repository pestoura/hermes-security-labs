# EPIC-32 — Resilience Validation and TLPT

## 1. Metadata

| Field | Value |
| --- | --- |
| Concept epic ID | `EPIC-32` |
| Slug | `resilience-validation-and-tlpt` |
| Pillar | `F` — Threat-Informed Validation |
| Phase | 7 |
| Priority | P2 |
| Delivery umbrella | `SVP2-F-02` (issue [#89](https://github.com/pestoura/hermes-security-labs/issues/89)) |
| Document version | 1.1.0 |
| Document date | 2026-08-07 |
| Catalogue | [Epic catalogue 45](../epic-catalogue-45.md) |
| Lifecycle contract | [Architecture documentation lifecycle](../../architecture/architecture-documentation-lifecycle.md) |

## 2. Current status

**IMPLEMENTING** — PR #153 integrated a repository-level non-executable resilience exercise planning contract. Oversight roles, escalation matrix, regulatory-practice mapping and real exercises remain incomplete or `NOT_RUN`.

| Lifecycle state | Reached |
| --- | --- |
| INTENT | yes |
| IMPLEMENTING | yes |
| AS_BUILT | no |
| FINAL | no |

Implemented contract state:

- every resilience exercise is bound to a named critical function;
- exercises require one or more injects and recovery criteria;
- each inject declares a scenario and expected response;
- lessons learned can be recorded;
- injects refuse command, argv, shell, payload, credential, secret and token fields;
- exercise records are `EXERCISE_PLAN_ONLY`, `executable=false` and `CONTROL_PLANE_ONLY` for authorization.

The candidate does not yet model oversight roles, mandatory white-team membership/visibility, escalation paths, phase gates, reporting/remediation workflow or a TIBER-EU/TLPT alignment mapping. No resilience/TLPT exercise is executed by this contract.

## 3. Problem and motivation

Threat-led testing exercises require structured scoping, control and reporting that the platform does not yet model.

## 4. Intended outcome

A structured resilience exercise model aligned with recognised threat-led testing practices, including roles, phases, control and reporting.

## 5. Scope and non-goals

### In scope

- Exercise phases and role model
- Control and white-team oversight requirements
- Reporting structure and remediation follow-up
- Alignment mapping to recognised practices

### Non-goals

- Claiming formal accreditation under any regulatory testing framework

## 6. Intent architecture

An exercise is a long-running campaign with additional oversight roles, stricter authorization and mandatory white-team visibility.

## 7. Contracts, data and capabilities

- Exercise definition record
- Oversight and escalation matrix

Contracts are canonical in Git. Where this epic reuses a platform-wide contract, the canonical definition lives in the [reference architecture](../../architecture/security-validation-reference-architecture.md) and in [EPIC-01](EPIC-01-architecture-and-canonical-contracts.md); this document references it instead of restating it.

## 8. Dependencies and sequencing

- [EPIC-22 — Threat-Informed Security Validation](EPIC-22-threat-informed-security-validation.md)
- [EPIC-24 — Purple Team and detection validation](EPIC-24-purple-team-and-detection-validation.md)

Sequencing follows the phase model in the [intent document](../../architecture/security-validation-platform-v2-intent.md). This epic is planned for phase 7.

## 9. Security, risks and failure modes

- Exercise scope creep
- Oversight bypass under time pressure
- A non-executable planning record being mistaken for authorized exercise execution
- Using TLPT/TIBER terminology without the required governance/oversight model

Platform-wide invariants that this epic must not weaken:

- absence of evidence never produces a `PASS` verdict;
- no execution outside an active authorization contract;
- no secrets, tokens, cookies or raw credential material in documentation, telemetry or persisted evidence;
- no target outside registered laboratories.

## 10. Deliverables

- Resilience exercise specification

## 11. Acceptance criteria

- Every exercise declares oversight roles and escalation paths
- Alignment is expressed as aligned or mapped, never as accredited

The repository candidate establishes a safe exercise-plan envelope but does not yet satisfy the oversight/escalation acceptance criterion. Therefore the epic remains `IMPLEMENTING`, never `AS_BUILT` or `FINAL`.

## 12. Evidence and validation plan

- Contract tests from PR #153
- Future oversight-role and escalation-matrix records
- Future exercise records with white-team sign-off
- Future recognised-practice alignment mapping
- Future controlled resilience exercise evidence

## 13. Decisions and open questions

### Decisions taken

- Resilience exercises are non-executable planning artefacts until separately authorized.
- Execution authorization remains exclusively in the control plane.
- Execution-shaped and secret-bearing inject material is refused.

### Open questions

- Whether exercises require a distinct authorization contract type
- Canonical role/white-team/escalation model
- First recognised TLPT practice to map against

## 14. Implementation notes

> Reserved. Populate during implementation with pull request references, deviations from intent, and decisions taken while building. Do not delete this heading.

- PR #153 integrated the resilience exercise planning candidate.
- Defensive integrations, containment actions, adversary emulation and resilience exercises remain `NOT_IMPLEMENTED`/`NOT_RUN` as applicable.
- `NO_RUNTIME_CHANGE`.

## 15. As-built / final architecture

> Reserved. Populate when the delivery umbrella reaches completion. Must record what was actually built, evidence links, and every divergence from sections 6 to 11. No umbrella may be closed while this section is empty.

_Not final. Oversight/white-team/escalation/alignment and real exercise evidence remain incomplete/NOT_RUN._


_Lifecycle unchanged: EPIC-32 is `IMPLEMENTING`; `AS_BUILT` and `FINAL` remain no. The record below states exactly what was merged and where the evidence lives, so that a future promotion decision is not made from memory or by association._

### What is actually built and merged

- critical-function-bound, non-executable resilience exercise plan with injects, expected responses, recovery criteria and lessons learned from PR #153 are integrated in main;
- oversight roles, white-team visibility, escalation matrix, phase/reporting model and real resilience/TLPT exercise execution remain NOT_RUN.

### Exact evidence

| Evidence | Value |
| --- | --- |
| Technical pull request | [#153](https://github.com/pestoura/hermes-security-labs/pull/153) |
| Validated PR head | `647896148f0f811fee724f198e986e380c4ce767` |
| Integrated `main` merge commit | `483db2543c4a1ee9bbfb1fcb6e440ad9e00f19e2` |
| Pre-merge `validate` | success — run `31174234402` |
| Pre-merge `security` | success — run `31174234764` |
| Post-merge `main` `validate` | success — run `31174804664` |
| Post-merge `main` `security` | success — run `31174805423` |

The merge commit is an ancestor of `main`.

### Evidence that is missing for promotion

`AS_BUILT` is withheld because the epic's target state is not satisfied by repository-level contract integration alone:

- oversight roles, white-team visibility, escalation matrix, phase/reporting model and real resilience/TLPT exercise execution: NOT_RUN.

`NO_RUNTIME_CHANGE`.

## 16. Document change log

| Date | Version | Change |
| --- | --- | --- |
| 2026-08-06 | 1.0.0 | Initial intent document created from the concept epic catalogue. |
| 2026-08-07 | 1.1.0 | Reconciled lifecycle to IMPLEMENTING against PR #153 while preserving oversight/TLPT/runtime gaps. |
