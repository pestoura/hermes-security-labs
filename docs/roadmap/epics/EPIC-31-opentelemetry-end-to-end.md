# EPIC-31 — OpenTelemetry end-to-end

## 1. Metadata

| Field | Value |
| --- | --- |
| Concept epic ID | `EPIC-31` |
| Slug | `opentelemetry-end-to-end` |
| Pillar | `D` — Evidence Observability and Assurance |
| Phase | 4 |
| Priority | P1 |
| Delivery umbrella | `SVP2-D-02` (issue [#85](https://github.com/pestoura/hermes-security-labs/issues/85)) |
| Document version | 1.1.0 |
| Document date | 2026-08-07 |
| Catalogue | [Epic catalogue 45](../epic-catalogue-45.md) |
| Lifecycle contract | [Architecture documentation lifecycle](../../architecture/architecture-documentation-lifecycle.md) |

## 2. Current status

**IMPLEMENTING** — PR #144 integrated the vendor-neutral OpenTelemetry/W3C context contract and canonical correlation attributes. End-to-end export/propagation through deployed runtimes remains `NOT_RUN`.

| Lifecycle state | Reached |
| --- | --- |
| INTENT | yes |
| IMPLEMENTING | yes |
| AS_BUILT | no |
| FINAL | no |

Implemented contract state:

- trace context standard is W3C;
- `traceparent` is required;
- campaign, run, step and attempt identifiers are canonical correlation attributes;
- telemetry conventions are OpenTelemetry;
- RED and USE metric semantics are declared;
- policy remains backend/exporter agnostic.

OpenTelemetry export, deployed cross-plane propagation, evidence-write trace linkage and production trace reconstruction remain `NOT_RUN`.

## 3. Problem and motivation

Telemetry is emitted in heterogeneous formats, preventing end-to-end tracing across control plane, gateway, runners and labs.

## 4. Intended outcome

A single vendor-neutral telemetry contract with consistent trace context propagation from campaign start to evidence persistence.

## 5. Scope and non-goals

### In scope

- Trace context propagation across plane boundaries
- Semantic conventions for campaign, step, capability and lab attributes
- Metric and log correlation with traces
- Exporter-agnostic configuration model

### Non-goals

- Selecting or deploying a specific backend in this task

## 6. Intent architecture

Trace context is created at campaign start and propagated through every typed request, runner step and evidence write, so a single trace reconstructs the whole campaign.

## 7. Contracts, data and capabilities

- Semantic attribute conventions
- Context propagation requirements

Contracts are canonical in Git. Where this epic reuses a platform-wide contract, the canonical definition lives in the [reference architecture](../../architecture/security-validation-reference-architecture.md) and in [EPIC-01](EPIC-01-architecture-and-canonical-contracts.md); this document references it instead of restating it.

## 8. Dependencies and sequencing

- [EPIC-11 — Technical observability](EPIC-11-technical-observability.md)

Sequencing follows the phase model in the [intent document](../../architecture/security-validation-platform-v2-intent.md). This epic is planned for phase 4.

## 9. Security, risks and failure modes

- Context loss at process boundaries
- Attribute cardinality growth
- Sensitive target data leaking into trace attributes
- Mistaking contract conformance for deployed propagation evidence

Platform-wide invariants that this epic must not weaken:

- absence of evidence never produces a `PASS` verdict;
- no execution outside an active authorization contract;
- no secrets, tokens, cookies or raw credential material in documentation, telemetry or persisted evidence;
- no target outside registered laboratories.

## 10. Deliverables

- Telemetry contract specification

## 11. Acceptance criteria

- A campaign is reconstructable as a single trace
- Attributes follow the declared conventions

Attribute conventions are now represented at contract level. A real campaign trace remains required before `AS_BUILT` or `FINAL`.

## 12. Evidence and validation plan

- Contract tests from PR #144
- Future trace-context propagation tests across control plane, gateway and runners
- Future evidence-write trace-link verification
- Future exporter-independent end-to-end trace reconstruction

## 13. Decisions and open questions

### Decisions taken

- W3C trace context is canonical.
- OpenTelemetry remains exporter-agnostic.
- Campaign/run/step/attempt identifiers are mandatory correlation attributes.

### Open questions

- Whether lab-internal telemetry is in scope or out of boundary
- Sampling and cardinality limits per runtime family

## 14. Implementation notes

> Reserved. Populate during implementation with pull request references, deviations from intent, and decisions taken while building. Do not delete this heading.

- PR #144 integrated the telemetry contract candidate.
- No OpenTelemetry exporter or runtime propagation was activated.
- `NO_RUNTIME_CHANGE`.

## 15. As-built / final architecture

> Reserved. Populate when the delivery umbrella reaches completion. Must record what was actually built, evidence links, and every divergence from sections 6 to 11. No umbrella may be closed while this section is empty.

_Not final. OpenTelemetry export and deployed end-to-end trace propagation remain NOT_RUN._


_Lifecycle unchanged: EPIC-31 is `IMPLEMENTING`; `AS_BUILT` and `FINAL` remain no. The record below states exactly what was merged and where the evidence lives, so that a future promotion decision is not made from memory or by association._

### What is actually built and merged

- W3C trace-context and OpenTelemetry semantic requirements with campaign/run/step/attempt correlation from PR #144 are integrated in main;
- export and deployed end-to-end propagation through gateway/runners/evidence remain NOT_RUN.

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

- OpenTelemetry export and deployed end-to-end trace propagation through gateway/runners/evidence: NOT_RUN.

`NO_RUNTIME_CHANGE`.

## 16. Document change log

| Date | Version | Change |
| --- | --- | --- |
| 2026-08-06 | 1.0.0 | Initial intent document created from the concept epic catalogue. |
| 2026-08-07 | 1.1.0 | Reconciled lifecycle to IMPLEMENTING against PR #144 while preserving OTel export/runtime propagation as NOT_RUN. |
