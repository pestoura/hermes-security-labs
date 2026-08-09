# EPIC-22 — Threat-Informed Security Validation

## 1. Metadata

| Field | Value |
| --- | --- |
| Concept epic ID | `EPIC-22` |
| Slug | `threat-informed-security-validation` |
| Pillar | `F` — Threat-Informed Validation |
| Phase | 7 |
| Priority | P1 |
| Delivery umbrella | `SVP2-F-01` (issue [#88](https://github.com/pestoura/hermes-security-labs/issues/88)) |
| Document version | 1.1.0 |
| Document date | 2026-08-07 |
| Catalogue | [Epic catalogue 45](../epic-catalogue-45.md) |
| Lifecycle contract | [Architecture documentation lifecycle](../../architecture/architecture-documentation-lifecycle.md) |

## 2. Current status

**IMPLEMENTING** — PR #150 integrated a repository-level threat-profile and adversary-emulation planning contract. Real adversary emulation and campaign execution remain `NOT_RUN`.

| Lifecycle state | Reached |
| --- | --- |
| INTENT | yes |
| IMPLEMENTING | yes |
| AS_BUILT | no |
| FINAL | no |

Implemented contract state:

- every threat profile is bound to a named critical business function;
- every profile references a frozen knowledge snapshot;
- profiles contain actor references and objectives and are explicitly non-executable;
- adversary-emulation plans are proposal artefacts, never execution authorization;
- every plan step declares objective, technique and intrusiveness level L0-L4;
- execution-shaped and secret-bearing planning fields are refused;
- execution authorization remains `CONTROL_PLANE_ONLY`.

The profile does not yet carry a dedicated intelligence-source/date field; source/time provenance is currently inherited from the frozen knowledge snapshot. Full asset-context integration, threat-intelligence refresh workflow and real adversary emulation remain incomplete or `NOT_RUN`.

## 3. Problem and motivation

Validation activities are selected by tool availability rather than by relevant adversary behaviour for the asset under test.

## 4. Intended outcome

Threat profiles drive campaign content: relevant techniques are selected from threat intelligence and asset context, not from tool catalogues.

## 5. Scope and non-goals

### In scope

- Threat profile model per asset class and sector
- Adversary emulation plan structure
- Technique selection and justification trail

### Non-goals

- Attribution claims about specific actors

## 6. Intent architecture

A threat profile references techniques from the knowledge fabric; the planner selects runbooks whose mappings intersect the profile.

## 7. Contracts, data and capabilities

- Threat profile record
- Emulation plan record with technique justification

Contracts are canonical in Git. Where this epic reuses a platform-wide contract, the canonical definition lives in the [reference architecture](../../architecture/security-validation-reference-architecture.md) and in [EPIC-01](EPIC-01-architecture-and-canonical-contracts.md); this document references it instead of restating it.

## 8. Dependencies and sequencing

- [EPIC-21 — Framework Crosswalk and canonical methodology](EPIC-21-framework-crosswalk-and-canonical-methodology.md)
- [EPIC-43 — Knowledge-Driven Campaign Planner](EPIC-43-knowledge-driven-campaign-planner.md)

Sequencing follows the phase model in the [intent document](../../architecture/security-validation-platform-v2-intent.md). This epic is planned for phase 7.

## 9. Security, risks and failure modes

- Profiles based on stale intelligence
- Over-fitting campaigns to a single actor narrative
- Proposal artefacts being mistaken for execution authorization
- Snapshot provenance being mistaken for a complete threat-profile refresh process

Platform-wide invariants that this epic must not weaken:

- absence of evidence never produces a `PASS` verdict;
- no execution outside an active authorization contract;
- no secrets, tokens, cookies or raw credential material in documentation, telemetry or persisted evidence;
- no target outside registered laboratories.

## 10. Deliverables

- Threat-informed validation specification

## 11. Acceptance criteria

- Every planned step traces to a technique in the active profile
- Profiles record intelligence source and date

The first criterion is represented at contract level. Source/date provenance currently exists through the immutable knowledge snapshot rather than dedicated profile fields, so the epic remains `IMPLEMENTING` and not `AS_BUILT`.

## 12. Evidence and validation plan

- Contract tests from PR #150
- Future profile-level source/date provenance or explicit snapshot-provenance acceptance decision
- Future selection justification per campaign
- Future controlled adversary-emulation evidence in registered laboratories

## 13. Decisions and open questions

### Decisions taken

- Technique relevance beats tool availability in planning.
- Threat profiles and emulation plans are non-executable planning artefacts.
- Authorization remains exclusively in the control plane.

### Open questions

- Refresh cadence for threat profiles
- Whether snapshot provenance is sufficient for the profile source/date acceptance criterion or dedicated fields are required

## 14. Implementation notes

> Reserved. Populate during implementation with pull request references, deviations from intent, and decisions taken while building. Do not delete this heading.

- PR #150 integrated threat-profile and non-executable adversary-emulation plan contracts.
- Adversary emulation, credential use and lateral movement remain `NOT_RUN`.
- `NO_RUNTIME_CHANGE`.

## 15. As-built / final architecture

> Reserved. Populate when the delivery umbrella reaches completion. Must record what was actually built, evidence links, and every divergence from sections 6 to 11. No umbrella may be closed while this section is empty.

_Not final. Profile provenance decision, full planning integration and real emulation evidence remain incomplete/NOT_RUN._


_Lifecycle unchanged: EPIC-22 is `IMPLEMENTING`; `AS_BUILT` and `FINAL` remain no. The record below states exactly what was merged and where the evidence lives, so that a future promotion decision is not made from memory or by association._

### What is actually built and merged

- critical-function and frozen-knowledge-snapshot threat profiles plus non-executable adversary-emulation planning from PR #150 are integrated in main;
- dedicated profile source/date provenance, full asset/threat planning integration and real adversary emulation remain NOT_RUN.

### Exact evidence

| Evidence | Value |
| --- | --- |
| Technical pull request | [#150](https://github.com/pestoura/hermes-security-labs/pull/150) |
| Validated PR head | `7285c98a877dad21c7f0d74bec76f834c780d07f` |
| Integrated `main` merge commit | `f865bc9e2ff86684262c4eab45af0bc2e2f8a3c5` |
| Pre-merge `validate` | success — run `31173409373` |
| Pre-merge `security` | success — run `31173409095` |
| Post-merge `main` `validate` | success — run `31173980236` |
| Post-merge `main` `security` | success — run `31173980463` |

The merge commit is an ancestor of `main`.

### Evidence that is missing for promotion

`AS_BUILT` is withheld because the epic's target state is not satisfied by repository-level contract integration alone:

- dedicated profile source/date provenance, full asset/threat planning integration and real adversary emulation: NOT_RUN.

`NO_RUNTIME_CHANGE`.

## 16. Document change log

| Date | Version | Change |
| --- | --- | --- |
| 2026-08-06 | 1.0.0 | Initial intent document created from the concept epic catalogue. |
| 2026-08-07 | 1.1.0 | Reconciled lifecycle to IMPLEMENTING against PR #150 while preserving adversary emulation and remaining provenance/planning gaps. |
