# EPIC-20 — IoT/OT and external hardware

## 1. Metadata

| Field | Value |
| --- | --- |
| Concept epic ID | `EPIC-20` |
| Slug | `iot-ot-and-external-hardware` |
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

IoT and OT protocols and devices require validation approaches that container labs cannot represent, and physical hardware breaks the isolation model.

## 4. Intended outcome

A documented approach for protocol simulation first, with a strictly bounded and separately authorized path for external hardware.

## 5. Scope and non-goals

### In scope

- Protocol simulation labs for OT/IoT protocols
- Hardware-in-the-loop boundary and prohibitions
- Additional authorization requirements for physical assets

### Non-goals

- Any action against live industrial systems

## 6. Intent architecture

Simulation labs behave like standard labs; hardware paths are declared as a distinct trust boundary with mandatory dual approval.

## 7. Contracts, data and capabilities

- Simulation lab manifest
- Hardware engagement authorization record

Contracts are canonical in Git. Where this epic reuses a platform-wide contract, the
canonical definition lives in the
[reference architecture](../../architecture/security-validation-reference-architecture.md)
and in [EPIC-01](EPIC-01-architecture-and-canonical-contracts.md); this document
references it instead of restating it.

## 8. Dependencies and sequencing

- [EPIC-04 — Transactional lifecycle and isolation](EPIC-04-transactional-lifecycle-and-isolation.md)
- [EPIC-08 — Network and egress policy](EPIC-08-network-and-egress-policy.md)
- [EPIC-09 — Exploitation safety](EPIC-09-exploitation-safety.md)

Sequencing follows the phase model in the
[intent document](../../architecture/security-validation-platform-v2-intent.md).
This epic is planned for phase 8.

## 9. Security, risks and failure modes

- Simulation fidelity gaps
- Physical safety implications of OT actions

Platform-wide invariants that this epic must not weaken:

- absence of evidence never produces a `PASS` verdict;
- no execution outside an active authorization contract;
- no secrets, tokens, cookies or raw credential material in documentation, telemetry
  or persisted evidence;
- no target outside registered laboratories.

## 10. Deliverables

- IoT/OT approach specification

## 11. Acceptance criteria

- Hardware execution is refused without dual approval
- Simulation limitations are documented per protocol

## 12. Evidence and validation plan

- Authorization records for any hardware path

Evidence must be referenced from the delivery umbrella issue before the umbrella can
be closed, and this document must record the references in section 15.

## 13. Decisions and open questions

### Decisions taken at intent time

- Simulation is the default and only unattended path

### Open questions

- Which protocols justify first-wave simulation coverage

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
