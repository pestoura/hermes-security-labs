# EPIC-06 — Kali Image Factory

## 1. Metadata

| Field | Value |
| --- | --- |
| Concept epic ID | `EPIC-06` |
| Slug | `kali-image-factory` |
| Pillar | `C` — Image and Capability Factory |
| Phase | 3 |
| Priority | P1 |
| Delivery umbrella | `SVP2-C-01` (issue [#82](https://github.com/pestoura/hermes-security-labs/issues/82)) |
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

Execution images are built ad hoc, without a minimal non-root base, without reproducible layers and without a documented promotion path.

## 4. Intended outcome

A factory that produces minimal, non-root, pinned and attested execution images with a defined promotion lifecycle.

## 5. Scope and non-goals

### In scope

- Minimal non-root base image
- Digest pinning and reproducible build inputs
- Persistent runner layout separated from ephemeral state
- Promotion candidate to accepted to retired

### Non-goals

- Publishing new public packages in this task
- Adding offensive tooling to the base image

## 6. Intent architecture

Base image plus capability layers; each layer declares the capabilities it enables so the capability registry can be derived from the image manifest.

## 7. Contracts, data and capabilities

- Image manifest with digest, base, layers and capabilities
- Promotion record

Contracts are canonical in Git. Where this epic reuses a platform-wide contract, the
canonical definition lives in the
[reference architecture](../../architecture/security-validation-reference-architecture.md)
and in [EPIC-01](EPIC-01-architecture-and-canonical-contracts.md); this document
references it instead of restating it.

## 8. Dependencies and sequencing

- [EPIC-03 — Typed Kali MCP](EPIC-03-typed-kali-mcp.md)

Sequencing follows the phase model in the
[intent document](../../architecture/security-validation-platform-v2-intent.md).
This epic is planned for phase 3.

## 9. Security, risks and failure modes

- Image bloat re-introducing unaudited tooling
- Pinning drift between manifest and registry

Platform-wide invariants that this epic must not weaken:

- absence of evidence never produces a `PASS` verdict;
- no execution outside an active authorization contract;
- no secrets, tokens, cookies or raw credential material in documentation, telemetry
  or persisted evidence;
- no target outside registered laboratories.

## 10. Deliverables

- Image factory specification
- Promotion lifecycle definition

## 11. Acceptance criteria

- No execution image runs as root by default
- Every accepted image has a digest and provenance record

## 12. Evidence and validation plan

- Build provenance attestation references

Evidence must be referenced from the delivery umbrella issue before the umbrella can
be closed, and this document must record the references in section 15.

## 13. Decisions and open questions

### Decisions taken at intent time

- Images are referenced by digest, not by mutable tag

### Open questions

- Cadence for rebuilding to absorb upstream security updates

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
