# EPIC-27 — Risk Intelligence and contextual prioritization

## 1. Metadata

| Field | Value |
| --- | --- |
| Concept epic ID | `EPIC-27` |
| Slug | `risk-intelligence-and-contextual-prioritization` |
| Pillar | `J` — Risk Findings and Interoperability |
| Phase | 7 |
| Priority | P1 |
| Delivery umbrella | `SVP2-J-01` (issue [#93](https://github.com/pestoura/hermes-security-labs/issues/93)) |
| Document version | 1.1.0 |
| Document date | 2026-08-07 |
| Catalogue | [Epic catalogue 45](../epic-catalogue-45.md) |
| Lifecycle contract | [Architecture documentation lifecycle](../../architecture/architecture-documentation-lifecycle.md) |

## 2. Current status

**AS_BUILT — repository contract** — PR #155 integrated the repository-owned risk
assessment contract and tests. The contract is deterministic and auditable at repository
level, but production integrations and live scoring have not been executed.

| Lifecycle state | Reached |
| --- | --- |
| INTENT | yes |
| IMPLEMENTING | yes |
| AS_BUILT | yes |
| FINAL | no |

## 3. Problem and motivation

Findings are prioritized by raw severity, ignoring exploitability signals, asset context and validated reachability.

## 4. Intended outcome

An auditable scoring model combining severity, exploitability intelligence, asset criticality and validated attack-path reachability.

## 5. Scope and non-goals

### In scope

- Scoring model inputs and weights
- Auditability: every score explains its inputs
- Asset context model
- Reachability contribution from the attack graph

### Non-goals

- Opaque or unexplainable scoring

## 6. Intent architecture

Score is a pure function of recorded inputs; recomputation from stored inputs must reproduce the same score.

## 7. Contracts, data and capabilities

- Score record with inputs, weights and version
- Asset context record

Contracts are canonical in Git. Where this epic reuses a platform-wide contract, the
canonical definition lives in the
[reference architecture](../../architecture/security-validation-reference-architecture.md)
and in [EPIC-01](EPIC-01-architecture-and-canonical-contracts.md); this document
references it instead of restating it.

## 8. Dependencies and sequencing

- [EPIC-23 — Attack Graph and Attack Flow](EPIC-23-attack-graph-and-attack-flow.md)
- [EPIC-37 — Vulnerability Intelligence Synchronization](EPIC-37-vulnerability-intelligence-synchronization.md)

Sequencing follows the phase model in the
[intent document](../../architecture/security-validation-platform-v2-intent.md).
This epic is planned for phase 7.

## 9. Security, risks and failure modes

- Weight tuning without evidence
- Context data becoming stale

Platform-wide invariants that this epic must not weaken:

- absence of evidence never produces a `PASS` verdict;
- no execution outside an active authorization contract;
- no secrets, tokens, cookies or raw credential material in documentation, telemetry
  or persisted evidence;
- no target outside registered laboratories.

## 10. Deliverables

- Risk scoring specification

## 11. Acceptance criteria

- Every score is reproducible from stored inputs
- Model version is recorded with each score

## 12. Evidence and validation plan

- Recomputation samples

Evidence must be referenced from the delivery umbrella issue before the umbrella can
be closed, and this document must record the references in section 15.

## 13. Decisions and open questions

### Decisions taken at intent time

- Validated reachability outweighs theoretical severity

### Open questions

- Whether asset criticality is owner-declared or derived

## 14. Implementation notes

PR #155 (`feat(svp2-j-01): add auditable risk and finding lifecycle`) introduced the
repository-owned risk and finding contract under `platform/risk-findings/`.

For risk assessment, the implementation:

- keeps the canonical components separate: CVSS 4.0, EPSS, KEV, asset criticality,
  reachability, attack-path importance, threat relevance, compensating controls,
  detectability and remediation cost;
- requires every component to carry an explicit source reference;
- validates normalized values and requires the complete canonical component set;
- requires non-negative caller-supplied weights whose total is exactly `1.0`;
- records normalized component values and the effective weights alongside the
  composite score;
- computes the composite deterministically and marks the resulting record auditable;
- fails closed when required components, provenance or weight invariants are missing.

The repository tests delivered with PR #155 exercise deterministic scoring, input
validation and failure behaviour. No external vulnerability feed, asset inventory,
business criticality service or production scoring engine is invoked by this contract.

## 15. As-built / final architecture

The repository now contains an **as-built contract** for deterministic and auditable
contextual risk scoring. This satisfies the repository-level acceptance intent for an
explainable score whose inputs and weights are preserved with the result.

The following operational capabilities are explicitly outside the evidence currently
available:

- production risk ingestion/scoring: `NOT_RUN`;
- live asset/business criticality integration: `NOT_RUN`;
- production CVSS/EPSS/KEV feeds: `NOT_RUN`;
- attack-graph/runtime reachability integration: `NOT_RUN`;
- customer or production risk prioritization workflow: `NOT_RUN`;
- automated risk acceptance: `NOT_IMPLEMENTED`.

`AS_BUILT` therefore applies to the repository contract and tests only. `FINAL` remains
`no` until the lifecycle contract's final evidence requirements are satisfied.

`NO_RUNTIME_CHANGE`.

## 16. Document change log

| Date | Version | Change |
| --- | --- | --- |
| 2026-08-07 | 1.1.0 | Reconciled PR #155 repository contract as `AS_BUILT`; recorded production non-claims and retained `FINAL=no`. |
| 2026-08-06 | 1.0.0 | Initial intent document created from the concept epic catalogue. |
