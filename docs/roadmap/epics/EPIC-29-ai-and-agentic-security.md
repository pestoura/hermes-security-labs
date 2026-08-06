# EPIC-29 — AI and Agentic Security

## 1. Metadata

| Field | Value |
| --- | --- |
| Concept epic ID | `EPIC-29` |
| Slug | `ai-and-agentic-security` |
| Pillar | `L` — Domain Expansion |
| Phase | 8 |
| Priority | P2 |
| Delivery umbrella | `SVP2-L-01` (issue [#96](https://github.com/pestoura/hermes-security-labs/issues/96)) |
| Document version | 1.0.0 |
| Document date | 2026-08-06 |
| Catalogue | [Epic catalogue 45](../epic-catalogue-45.md) |
| Lifecycle contract | [Architecture documentation lifecycle](../../architecture/architecture-documentation-lifecycle.md) |

## 2. Current status

**INTENT** — nothing described in this document is implemented. Sections 14 and 15
are reserved and must be filled during and after implementation, as required by the
[documentation lifecycle contract](../../architecture/architecture-documentation-lifecycle.md).

| Lifecycle state | Reached |
| --- | --- |
| INTENT | yes |
| IMPLEMENTING | no |
| AS_BUILT | no |
| FINAL | no |

## 3. Problem and motivation

AI and agentic systems introduce prompt injection, tool abuse and autonomy risks that classical validation does not cover.

## 4. Intended outcome

A validation domain for AI and agentic systems, covering model endpoints, tool-calling surfaces and agent autonomy boundaries.

## 5. Scope and non-goals

### In scope

- AI/MCP target model and capability set
- Prompt injection and tool-abuse validation categories
- Agent autonomy boundary assertions
- Evidence types for non-deterministic targets

### Non-goals

- Attacking third-party model providers

## 6. Intent architecture

AI targets are laboratory-hosted; non-determinism is handled by repeated trials with recorded variance rather than single-shot verdicts.

## 7. Contracts, data and capabilities

- AI target manifest
- Trial and variance record

Contracts are canonical in Git. Where this epic reuses a platform-wide contract, the
canonical definition lives in the
[reference architecture](../../architecture/security-validation-reference-architecture.md)
and in [EPIC-01](EPIC-01-architecture-and-canonical-contracts.md); this document
references it instead of restating it.

## 8. Dependencies and sequencing

- [EPIC-03 — Typed Kali MCP](EPIC-03-typed-kali-mcp.md)
- [EPIC-07 — Capability Registry](EPIC-07-capability-registry.md)

Sequencing follows the phase model in the
[intent document](../../architecture/security-validation-platform-v2-intent.md).
This epic is planned for phase 8.

## 9. Security, risks and failure modes

- Non-deterministic results misread as regressions
- Model updates invalidating baselines

Platform-wide invariants that this epic must not weaken:

- absence of evidence never produces a `PASS` verdict;
- no execution outside an active authorization contract;
- no secrets, tokens, cookies or raw credential material in documentation, telemetry
  or persisted evidence;
- no target outside registered laboratories.

## 10. Deliverables

- AI and agentic security validation specification

## 11. Acceptance criteria

- Verdicts on non-deterministic targets record trial count and variance
- No third-party provider is targeted

## 12. Evidence and validation plan

- Trial records with variance statistics

Evidence must be referenced from the delivery umbrella issue before the umbrella can
be closed, and this document must record the references in section 15.

## 13. Decisions and open questions

### Decisions taken at intent time

- Single-trial PASS is not acceptable for stochastic targets

### Open questions

- Minimum trial count per validation category

## 14. Implementation notes

> Reserved. Populate during implementation with pull request references, deviations
> from intent, and decisions taken while building. Do not delete this heading.

_Not started._

## 15. As-built / final architecture

> Reserved. Populate when the delivery umbrella reaches completion. Must record what
> was actually built, evidence links, and every divergence from sections 6 to 11.
> No umbrella may be closed while this section is empty.

_Not started._

## 16. Document change log

| Date | Version | Change |
| --- | --- | --- |
| 2026-08-06 | 1.0.0 | Initial intent document created from the concept epic catalogue. |
