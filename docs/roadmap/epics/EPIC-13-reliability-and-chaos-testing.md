# EPIC-13 — Reliability and chaos testing

## 1. Metadata

| Field | Value |
| --- | --- |
| Concept epic ID | `EPIC-13` |
| Slug | `reliability-and-chaos-testing` |
| Pillar | `D` — Evidence Observability and Assurance |
| Phase | 4 |
| Priority | P1 |
| Delivery umbrella | `SVP2-D-02` (issue [#85](https://github.com/pestoura/hermes-security-labs/issues/85)) |
| Document version | 1.1.0 |
| Document date | 2026-08-07 |
| Catalogue | [Epic catalogue 45](../epic-catalogue-45.md) |
| Lifecycle contract | [Architecture documentation lifecycle](../../architecture/architecture-documentation-lifecycle.md) |

## 2. Current status

**IMPLEMENTING** — PR #144 integrated the canonical failure-suite and fail-closed maturity gates as repository contract logic. Real chaos/fault injection remains `NOT_RUN`.

| Lifecycle state | Reached |
| --- | --- |
| INTENT | yes |
| IMPLEMENTING | yes |
| AS_BUILT | no |
| FINAL | no |

Implemented contract state:

- canonical failure cases: restart, invalid JSON, empty stdout, timeout, network loss, disk full, partial cleanup, concurrency, cancellation and incompatible version;
- readiness evidence is required before executable steps;
- M2 cannot be reached without the complete passing failure suite;
- missing required failure evidence blocks maturity promotion;
- advertised operations cannot be no-ops and require effect evidence.

No live fault injection, chaos execution or runtime failure observation is claimed. `chaos_execution` remains `NOT_RUN`.

## 3. Problem and motivation

Failure behaviour is asserted by design intent rather than demonstrated, so fail-safe claims are untested.

## 4. Intended outcome

A failure-injection programme that demonstrates fail-safe behaviour for timeouts, crashes, partial evidence, network loss and cancellation.

## 5. Scope and non-goals

### In scope

- Failure catalogue per plane
- Injection scenarios and expected verdicts
- Regression gating for fail-safe invariants

### Non-goals

- Running chaos experiments against non-laboratory systems

## 6. Intent architecture

Each invariant (no PASS without evidence, zero residue, bounded cancellation) has at least one injection scenario proving it.

## 7. Contracts, data and capabilities

- Failure scenario record
- Expected verdict matrix

Contracts are canonical in Git. Where this epic reuses a platform-wide contract, the canonical definition lives in the [reference architecture](../../architecture/security-validation-reference-architecture.md) and in [EPIC-01](EPIC-01-architecture-and-canonical-contracts.md); this document references it instead of restating it.

## 8. Dependencies and sequencing

- [EPIC-04 — Transactional lifecycle and isolation](EPIC-04-transactional-lifecycle-and-isolation.md)
- [EPIC-05 — Runner Protocol v2](EPIC-05-runner-protocol-v2.md)
- [EPIC-10 — Evidence Plane](EPIC-10-evidence-plane.md)

Sequencing follows the phase model in the [intent document](../../architecture/security-validation-platform-v2-intent.md). This epic is planned for phase 4.

## 9. Security, risks and failure modes

- Scenarios drifting from real failure modes
- Flaky scenarios eroding trust in the gate
- Treating contract tests as operational chaos evidence

Platform-wide invariants that this epic must not weaken:

- absence of evidence never produces a `PASS` verdict;
- no execution outside an active authorization contract;
- no secrets, tokens, cookies or raw credential material in documentation, telemetry or persisted evidence;
- no target outside registered laboratories.

## 10. Deliverables

- Chaos and reliability test plan
- Invariant to scenario matrix

## 11. Acceptance criteria

- Every fail-safe invariant maps to at least one scenario
- No scenario can pass while producing an unproven PASS

The repository currently defines the canonical suite and gating semantics; execution evidence is still required before `AS_BUILT` or `FINAL`.

## 12. Evidence and validation plan

- Contract tests from PR #144
- Future controlled failure-injection outcomes in registered laboratories
- Future verdict/evidence records for every canonical failure case

## 13. Decisions and open questions

### Decisions taken

- Fail-safe invariants are release-blocking.
- Missing failure-suite evidence prevents maturity promotion.

### Open questions

- Which scenarios are cheap enough to run per pull request
- Which scenarios require isolated scheduled/release-gate execution

## 14. Implementation notes

> Reserved. Populate during implementation with pull request references, deviations from intent, and decisions taken while building. Do not delete this heading.

- PR #144 integrated the failure-suite contract and promotion gates.
- Runtime fault injection was deliberately not executed.
- `NO_RUNTIME_CHANGE`.

## 15. As-built / final architecture

> Reserved. Populate when the delivery umbrella reaches completion. Must record what was actually built, evidence links, and every divergence from sections 6 to 11. No umbrella may be closed while this section is empty.

_Not final. Real chaos execution and runtime failure evidence remain NOT_RUN._

## 16. Document change log

| Date | Version | Change |
| --- | --- | --- |
| 2026-08-06 | 1.0.0 | Initial intent document created from the concept epic catalogue. |
| 2026-08-07 | 1.1.0 | Reconciled lifecycle to IMPLEMENTING against PR #144 while preserving chaos execution as NOT_RUN. |
