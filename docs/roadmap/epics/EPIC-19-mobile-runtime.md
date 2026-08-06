# EPIC-19 — Mobile Runtime

## 1. Metadata

| Field | Value |
| --- | --- |
| Concept epic ID | `EPIC-19` |
| Slug | `mobile-runtime` |
| Pillar | `L` — Domain Expansion |
| Phase | 8 |
| Priority | P3 |
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

Mobile application and device attack surface is unaddressed by the current laboratory families.

## 4. Intended outcome

A mobile runtime family using emulators and instrumented builds, with the same lifecycle and evidence guarantees.

## 5. Scope and non-goals

### In scope

- Emulator-based lab family
- Instrumented target applications
- Mobile-specific capabilities and evidence types

### Non-goals

- Testing third-party applications without authorization

## 6. Intent architecture

Emulators run as isolated labs; artefacts (APK, IPA equivalents) are versioned fixtures with digests.

## 7. Contracts, data and capabilities

- Mobile lab manifest
- Application fixture record

Contracts are canonical in Git. Where this epic reuses a platform-wide contract, the
canonical definition lives in the
[reference architecture](../../architecture/security-validation-reference-architecture.md)
and in [EPIC-01](EPIC-01-architecture-and-canonical-contracts.md); this document
references it instead of restating it.

## 8. Dependencies and sequencing

- [EPIC-04 — Transactional lifecycle and isolation](EPIC-04-transactional-lifecycle-and-isolation.md)
- [EPIC-07 — Capability Registry](EPIC-07-capability-registry.md)

Sequencing follows the phase model in the
[intent document](../../architecture/security-validation-platform-v2-intent.md).
This epic is planned for phase 8.

## 9. Security, risks and failure modes

- Emulator resource consumption
- Licence constraints on platform images

Platform-wide invariants that this epic must not weaken:

- absence of evidence never produces a `PASS` verdict;
- no execution outside an active authorization contract;
- no secrets, tokens, cookies or raw credential material in documentation, telemetry
  or persisted evidence;
- no target outside registered laboratories.

## 10. Deliverables

- Mobile runtime specification

## 11. Acceptance criteria

- All mobile targets are project-controlled fixtures
- Evidence includes emulator and fixture versions

## 12. Evidence and validation plan

- Fixture digest inventory

Evidence must be referenced from the delivery umbrella issue before the umbrella can
be closed, and this document must record the references in section 15.

## 13. Decisions and open questions

### Decisions taken at intent time

- Physical devices are out of scope for the first iteration

### Open questions

- Whether iOS-equivalent coverage is feasible under licensing

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
