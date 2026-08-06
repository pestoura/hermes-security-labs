# EPIC-08 — Network and egress policy

## 1. Metadata

| Field | Value |
| --- | --- |
| Concept epic ID | `EPIC-08` |
| Slug | `network-and-egress-policy` |
| Pillar | `B` — Runtime Foundation |
| Phase | 2 |
| Priority | P0 |
| Delivery umbrella | `SVP2-B-03` (issue [#81](https://github.com/pestoura/hermes-security-labs/issues/81)) |
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

Network posture is applied per environment without a single policy contract, so egress exposure is hard to audit and easy to widen accidentally.

## 4. Intended outcome

A declarative network policy model with default-deny egress, explicit allowlists per lab family and auditable exceptions.

## 5. Scope and non-goals

### In scope

- Default-deny egress profiles
- Per-lab network isolation
- Explicit, time-bounded exceptions with an owner
- Policy audit trail

### Non-goals

- Changing production network configuration outside labs

## 6. Intent architecture

Each lab declares a network profile; the lifecycle refuses to start a lab whose effective network posture is wider than its declared profile.

## 7. Contracts, data and capabilities

- Network profile schema
- Exception record with expiry and approver

Contracts are canonical in Git. Where this epic reuses a platform-wide contract, the
canonical definition lives in the
[reference architecture](../../architecture/security-validation-reference-architecture.md)
and in [EPIC-01](EPIC-01-architecture-and-canonical-contracts.md); this document
references it instead of restating it.

## 8. Dependencies and sequencing

- [EPIC-04 — Transactional lifecycle and isolation](EPIC-04-transactional-lifecycle-and-isolation.md)

Sequencing follows the phase model in the
[intent document](../../architecture/security-validation-platform-v2-intent.md).
This epic is planned for phase 2.

## 9. Security, risks and failure modes

- Silent widening through shared networks
- Exceptions outliving their justification

Platform-wide invariants that this epic must not weaken:

- absence of evidence never produces a `PASS` verdict;
- no execution outside an active authorization contract;
- no secrets, tokens, cookies or raw credential material in documentation, telemetry
  or persisted evidence;
- no target outside registered laboratories.

## 10. Deliverables

- Network policy specification
- Egress profile catalogue

## 11. Acceptance criteria

- No lab starts with an undeclared network profile
- Every exception has an expiry and an approver

## 12. Evidence and validation plan

- Effective network posture recorded at lab start

Evidence must be referenced from the delivery umbrella issue before the umbrella can
be closed, and this document must record the references in section 15.

## 13. Decisions and open questions

### Decisions taken at intent time

- Default posture is deny-all egress

### Open questions

- How package installation inside labs is handled without weakening default-deny

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
