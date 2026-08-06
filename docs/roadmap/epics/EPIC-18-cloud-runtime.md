# EPIC-18 — Cloud Runtime

## 1. Metadata

| Field | Value |
| --- | --- |
| Concept epic ID | `EPIC-18` |
| Slug | `cloud-runtime` |
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

Cloud control-plane misconfiguration is a major risk class with no validation runtime and no safe emulation strategy.

## 4. Intended outcome

A cloud runtime family based on emulated or strictly scoped disposable environments with explicit cost and blast-radius controls.

## 5. Scope and non-goals

### In scope

- Emulated cloud control plane as the default
- Scoped disposable accounts as an exception path
- Blast radius and cost guardrails
- Cloud-specific capabilities

### Non-goals

- Using real production cloud tenants
- Incurring uncontrolled cost

## 6. Intent architecture

Default is local emulation; any real-provider path requires an explicit authorization contract with spend and scope limits.

## 7. Contracts, data and capabilities

- Cloud lab manifest
- Guardrail record with scope and spend limits

Contracts are canonical in Git. Where this epic reuses a platform-wide contract, the
canonical definition lives in the
[reference architecture](../../architecture/security-validation-reference-architecture.md)
and in [EPIC-01](EPIC-01-architecture-and-canonical-contracts.md); this document
references it instead of restating it.

## 8. Dependencies and sequencing

- [EPIC-04 — Transactional lifecycle and isolation](EPIC-04-transactional-lifecycle-and-isolation.md)
- [EPIC-07 — Capability Registry](EPIC-07-capability-registry.md)
- [EPIC-08 — Network and egress policy](EPIC-08-network-and-egress-policy.md)

Sequencing follows the phase model in the
[intent document](../../architecture/security-validation-platform-v2-intent.md).
This epic is planned for phase 8.

## 9. Security, risks and failure modes

- Emulation fidelity gaps producing false confidence
- Accidental use of a non-disposable tenant

Platform-wide invariants that this epic must not weaken:

- absence of evidence never produces a `PASS` verdict;
- no execution outside an active authorization contract;
- no secrets, tokens, cookies or raw credential material in documentation, telemetry
  or persisted evidence;
- no target outside registered laboratories.

## 10. Deliverables

- Cloud runtime specification

## 11. Acceptance criteria

- Real-provider execution is refused without an explicit contract
- Every cloud lab declares a blast radius

## 12. Evidence and validation plan

- Guardrail configuration recorded per campaign

Evidence must be referenced from the delivery umbrella issue before the umbrella can
be closed, and this document must record the references in section 15.

## 13. Decisions and open questions

### Decisions taken at intent time

- Emulation first; real providers are an audited exception

### Open questions

- Which fidelity gaps must be documented as known limitations

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
