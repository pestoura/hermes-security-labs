# EPIC-07 — Capability Registry

## 1. Metadata

| Field | Value |
| --- | --- |
| Concept epic ID | `EPIC-07` |
| Slug | `capability-registry` |
| Pillar | `C` — Image and Capability Factory |
| Phase | 3 |
| Priority | P0 |
| Delivery umbrella | `SVP2-C-02` (issue [#83](https://github.com/pestoura/hermes-security-labs/issues/83)) |
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

There is no registry declaring which capabilities exist, which image provides them, their intrusiveness and their authorization requirements.

## 4. Intended outcome

A versioned capability registry that the gateway consults to authorize, route and bound every typed operation.

## 5. Scope and non-goals

### In scope

- Capability record: id, provider image, intrusiveness, inputs, outputs, prerequisites
- Capability profiles per runtime and per campaign
- Registry versioning and deprecation

### Non-goals

- Runtime discovery of undeclared capabilities

## 6. Intent architecture

Registry is declarative and versioned in Git; the gateway loads a pinned registry snapshot per campaign so behaviour is reproducible.

## 7. Contracts, data and capabilities

- Capability record schema
- Capability profile schema
- Registry snapshot reference

Contracts are canonical in Git. Where this epic reuses a platform-wide contract, the
canonical definition lives in the
[reference architecture](../../architecture/security-validation-reference-architecture.md)
and in [EPIC-01](EPIC-01-architecture-and-canonical-contracts.md); this document
references it instead of restating it.

## 8. Dependencies and sequencing

- [EPIC-03 — Typed Kali MCP](EPIC-03-typed-kali-mcp.md)
- [EPIC-06 — Kali Image Factory](EPIC-06-kali-image-factory.md)

Sequencing follows the phase model in the
[intent document](../../architecture/security-validation-platform-v2-intent.md).
This epic is planned for phase 3.

## 9. Security, risks and failure modes

- Registry drift versus actual image content
- Profiles silently widening intrusiveness

Platform-wide invariants that this epic must not weaken:

- absence of evidence never produces a `PASS` verdict;
- no execution outside an active authorization contract;
- no secrets, tokens, cookies or raw credential material in documentation, telemetry
  or persisted evidence;
- no target outside registered laboratories.

## 10. Deliverables

- Capability registry schema
- Profile definitions per runtime family

## 11. Acceptance criteria

- Every typed operation resolves to exactly one capability record
- Campaign evidence records the registry snapshot used

## 12. Evidence and validation plan

- Registry snapshot hash recorded per campaign

Evidence must be referenced from the delivery umbrella issue before the umbrella can
be closed, and this document must record the references in section 15.

## 13. Decisions and open questions

### Decisions taken at intent time

- Capabilities absent from the registry are refused

### Open questions

- Whether capability deprecation blocks replay of historical campaigns

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
