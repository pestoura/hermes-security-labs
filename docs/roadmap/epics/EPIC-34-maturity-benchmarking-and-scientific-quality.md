# EPIC-34 — Maturity, benchmarking and scientific quality

## 1. Metadata

| Field | Value |
| --- | --- |
| Concept epic ID | `EPIC-34` |
| Slug | `maturity-benchmarking-and-scientific-quality` |
| Pillar | `D` — Evidence Observability and Assurance |
| Phase | 4 |
| Priority | P2 |
| Delivery umbrella | `SVP2-D-02` (issue [#85](https://github.com/pestoura/hermes-security-labs/issues/85)) |
| Document version | 1.1.0 |
| Document date | 2026-08-07 |
| Catalogue | [Epic catalogue 45](../epic-catalogue-45.md) |
| Lifecycle contract | [Architecture documentation lifecycle](../../architecture/architecture-documentation-lifecycle.md) |

## 2. Current status

**IMPLEMENTING** — PR #144 integrated the repository-owned maturity M0-M5 evidence gates and reproducibility/quality requirements. Production maturity assessment and benchmark execution remain `NOT_RUN`.

| Lifecycle state | Reached |
| --- | --- |
| INTENT | yes |
| IMPLEMENTING | yes |
| AS_BUILT | no |
| FINAL | no |

Implemented contract state:

- explicit maturity levels M0-M5;
- M1 requires happy-path and readiness evidence;
- M2 requires the complete passing failure suite;
- M3 adds golden lab, golden finding and reproducibility evidence;
- M4 adds false-positive rate, false-negative rate and cleanup score;
- M5 adds production observation and retirement readiness;
- missing required evidence blocks maturity promotion;
- maturity cannot skip required gates.

Production maturity assessment, actual benchmark runs, empirical FP/FN measurement and M5 production observation remain `NOT_RUN`.

## 3. Problem and motivation

Platform quality claims are qualitative; there is no benchmark, no reproducibility standard and no measurable maturity assessment.

## 4. Intended outcome

A maturity model M0-M5 per capability plus reproducibility and benchmarking requirements that make quality claims measurable.

## 5. Scope and non-goals

### In scope

- Capability maturity levels M0-M5 with evidence requirements
- Reproducibility criteria for content and campaigns
- Benchmark definitions and reporting
- False positive and false negative accounting

### Non-goals

- Publishing comparative claims against other products

## 6. Intent architecture

Maturity is asserted only with recorded evidence per level; benchmarks are versioned so results across time remain comparable.

## 7. Contracts, data and capabilities

- Maturity assessment record
- Benchmark definition and result record

Contracts are canonical in Git. Where this epic reuses a platform-wide contract, the canonical definition lives in the [reference architecture](../../architecture/security-validation-reference-architecture.md) and in [EPIC-01](EPIC-01-architecture-and-canonical-contracts.md); this document references it instead of restating it.

## 8. Dependencies and sequencing

- [EPIC-13 — Reliability and chaos testing](EPIC-13-reliability-and-chaos-testing.md)
- [EPIC-10 — Evidence Plane](EPIC-10-evidence-plane.md)

Sequencing follows the phase model in the [intent document](../../architecture/security-validation-platform-v2-intent.md). This epic is planned for phase 4.

## 9. Security, risks and failure modes

- Maturity inflation
- Benchmarks optimized for rather than measured by
- Treating declared evidence gates as completed evidence

Platform-wide invariants that this epic must not weaken:

- absence of evidence never produces a `PASS` verdict;
- no execution outside an active authorization contract;
- no secrets, tokens, cookies or raw credential material in documentation, telemetry or persisted evidence;
- no target outside registered laboratories.

## 10. Deliverables

- Maturity and benchmarking specification

## 11. Acceptance criteria

- Every maturity claim cites evidence
- Benchmark results record the benchmark version

Maturity evidence gates are now contractually defined. Real assessments and benchmark result records are still required before `AS_BUILT` or `FINAL`.

## 12. Evidence and validation plan

- Contract tests from PR #144
- Future assessment records per capability
- Future versioned benchmark results
- Future reproducibility, FP/FN and cleanup-score evidence
- Future M5 production observation and retirement-readiness evidence

## 13. Decisions and open questions

### Decisions taken

- Unevidenced maturity defaults to M0.
- Missing evidence blocks promotion rather than producing an assumed score.
- M5 requires production observation and retirement readiness.

### Open questions

- Who performs independent maturity review
- Canonical benchmark set and review cadence

## 14. Implementation notes

> Reserved. Populate during implementation with pull request references, deviations from intent, and decisions taken while building. Do not delete this heading.

- PR #144 integrated maturity M0-M5 contract logic and evidence gates.
- Production maturity assessment and benchmark execution were deliberately not performed.
- `NO_RUNTIME_CHANGE`.

## 15. As-built / final architecture

> Reserved. Populate when the delivery umbrella reaches completion. Must record what was actually built, evidence links, and every divergence from sections 6 to 11. No umbrella may be closed while this section is empty.

_Not final. Production maturity assessment, benchmarks and empirical quality evidence remain NOT_RUN._


_Lifecycle unchanged: EPIC-34 is `IMPLEMENTING`; `AS_BUILT` and `FINAL` remain no. The record below states exactly what was merged and where the evidence lives, so that a future promotion decision is not made from memory or by association._

### What is actually built and merged

- M0-M5 evidence gates covering readiness/failure-suite/reproducibility/FP-FN/cleanup and M5 production-observation/retirement requirements from PR #144 are integrated in main;
- production maturity assessment and benchmark execution remain NOT_RUN.

### Exact evidence

| Evidence | Value |
| --- | --- |
| Technical pull request | [#144](https://github.com/pestoura/hermes-security-labs/pull/144) |
| Validated PR head | `0a0f7a61d903905a2aea45f1e6d4ea1040484a01` |
| Integrated `main` merge commit | `fc89eb4bbaa0a2f356d21ea42b7d0bf1bec6949f` |
| Pre-merge `validate` | success — run `31171158216` |
| Pre-merge `security` | success — run `31171158029` |
| Post-merge `main` `validate` | success — run `31171376644` |
| Post-merge `main` `security` | success — run `31171376622` |

The merge commit is an ancestor of `main`.

### Evidence that is missing for promotion

`AS_BUILT` is withheld because the epic's target state is not satisfied by repository-level contract integration alone:

- production maturity assessment, benchmark execution and empirical quality evidence: NOT_RUN.

`NO_RUNTIME_CHANGE`.

## 16. Document change log

| Date | Version | Change |
| --- | --- | --- |
| 2026-08-06 | 1.0.0 | Initial intent document created from the concept epic catalogue. |
| 2026-08-07 | 1.1.0 | Reconciled lifecycle to IMPLEMENTING against PR #144 while preserving production assessment/benchmark evidence as NOT_RUN. |
