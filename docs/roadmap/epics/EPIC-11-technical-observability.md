# EPIC-11 — Technical observability

## 1. Metadata

| Field | Value |
| --- | --- |
| Concept epic ID | `EPIC-11` |
| Slug | `technical-observability` |
| Pillar | `D` — Evidence Observability and Assurance |
| Phase | 4 |
| Priority | P1 |
| Delivery umbrella | `SVP2-D-02` (issue [#85](https://github.com/pestoura/hermes-security-labs/issues/85)) |
| Document version | 1.1.0 |
| Document date | 2026-08-07 |
| Catalogue | [Epic catalogue 45](../epic-catalogue-45.md) |
| Lifecycle contract | [Architecture documentation lifecycle](../../architecture/architecture-documentation-lifecycle.md) |

## 2. Current status

**IMPLEMENTING** — PR #144 integrated the repository-level observability and readiness contract candidate. Live telemetry/export and real readiness probes remain `NOT_RUN`.

| Lifecycle state | Reached |
| --- | --- |
| INTENT | yes |
| IMPLEMENTING | yes |
| AS_BUILT | no |
| FINAL | no |

Implemented contract state:

- W3C trace context is required;
- campaign/run/step/attempt correlation attributes are declared;
- OpenTelemetry conventions are declared;
- RED and USE service-metric semantics are defined;
- executable steps require fresh readiness evidence and fail closed when readiness is missing, stale, degraded, unknown or not ready;
- readiness evidence has bounded freshness;
- advertised operations cannot be declared no-ops and require effect evidence.

OpenTelemetry export, live signal emission across all planes, real readiness probes and production reconstruction remain `NOT_RUN`.

## 3. Problem and motivation

There is no consistent telemetry across control plane, gateway, runners and labs, so failures are diagnosed from ad hoc logs.

## 4. Intended outcome

Structured logs, metrics and traces with consistent correlation identifiers and documented signal semantics.

## 5. Scope and non-goals

### In scope

- Structured logging with correlation ids
- Core metrics for campaigns, steps, labs and refusals
- Health and readiness semantics
- Redaction applied at emission

### Non-goals

- Deploying a monitoring stack in this documentation task

## 6. Intent architecture

Telemetry is emitted at plane boundaries; every signal carries campaign, step and capability identifiers so evidence and telemetry can be correlated after the fact.

## 7. Contracts, data and capabilities

- Log record fields
- Metric names and labels
- Trace span naming

Contracts are canonical in Git. Where this epic reuses a platform-wide contract, the canonical definition lives in the [reference architecture](../../architecture/security-validation-reference-architecture.md) and in [EPIC-01](EPIC-01-architecture-and-canonical-contracts.md); this document references it instead of restating it.

## 8. Dependencies and sequencing

- [EPIC-10 — Evidence Plane](EPIC-10-evidence-plane.md)

Sequencing follows the phase model in the [intent document](../../architecture/security-validation-platform-v2-intent.md). This epic is planned for phase 4.

## 9. Security, risks and failure modes

- Telemetry leaking sensitive content
- Cardinality explosion from per-target labels
- Treating declared conventions as proof that every runtime emits them

Platform-wide invariants that this epic must not weaken:

- absence of evidence never produces a `PASS` verdict;
- no execution outside an active authorization contract;
- no secrets, tokens, cookies or raw credential material in documentation, telemetry or persisted evidence;
- no target outside registered laboratories.

## 10. Deliverables

- Observability specification
- Signal catalogue

## 11. Acceptance criteria

- Every campaign is reconstructable from telemetry plus evidence
- No telemetry field carries secret material

The repository candidate establishes contract semantics only. Live end-to-end telemetry and redaction evidence are still required before `AS_BUILT` or `FINAL`.

## 12. Evidence and validation plan

- Contract tests from PR #144
- Future signal catalogue review against redaction rules
- Future end-to-end trace/metric/log correlation evidence
- Future real readiness-probe evidence

## 13. Decisions and open questions

### Decisions taken

- W3C trace context is the correlation standard.
- OpenTelemetry is the vendor-neutral telemetry convention.
- Readiness is fail-closed and freshness-bounded.

### Open questions

- Sampling policy for high-volume runner traces
- Cardinality policy for target-derived attributes

## 14. Implementation notes

> Reserved. Populate during implementation with pull request references, deviations from intent, and decisions taken while building. Do not delete this heading.

- PR #144 integrated the observability/readiness contract candidate.
- OpenTelemetry export and real probes were deliberately not activated.
- `NO_RUNTIME_CHANGE`.

## 15. As-built / final architecture

> Reserved. Populate when the delivery umbrella reaches completion. Must record what was actually built, evidence links, and every divergence from sections 6 to 11. No umbrella may be closed while this section is empty.

_Not final. Live telemetry, readiness observations and production reconstruction remain to be implemented and evidenced._

## 16. Document change log

| Date | Version | Change |
| --- | --- | --- |
| 2026-08-06 | 1.0.0 | Initial intent document created from the concept epic catalogue. |
| 2026-08-07 | 1.1.0 | Reconciled lifecycle to IMPLEMENTING against PR #144 while preserving live telemetry/readiness as NOT_RUN. |
