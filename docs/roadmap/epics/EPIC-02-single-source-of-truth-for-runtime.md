# EPIC-02 — Single source of truth for runtime

## 1. Metadata

| Field | Value |
| --- | --- |
| Concept epic ID | `EPIC-02` |
| Slug | `single-source-of-truth-for-runtime` |
| Pillar | `A` — Governance and Architecture |
| Phase | 1 |
| Priority | P0 |
| Delivery umbrella | `SVP2-A-01` (issue [#76](https://github.com/pestoura/hermes-security-labs/issues/76)) |
| Document version | 1.1.0 |
| Document date | 2026-08-06 |
| Catalogue | [Epic catalogue 45](../epic-catalogue-45.md) |
| Lifecycle contract | [Architecture documentation lifecycle](../../architecture/architecture-documentation-lifecycle.md) |

## 2. Current status

**IMPLEMENTING** — the first implementation block is active on branch
`feat/epic-02-runtime-source-of-truth`. It formalizes and validates repository-owned runtime
intent without changing deployment or live runtime behaviour.

| Lifecycle state | Reached |
| --- | --- |
| INTENT | yes |
| IMPLEMENTING | yes |
| AS_BUILT | no |
| FINAL | no |

## 3. Problem and motivation

Runtime facts (labs, runners, images, bindings, capabilities) are declared in several places, so drift between Git, deployed state and documentation is possible and undetected.

## 4. Intended outcome

One versioned declarative source describes runtime intent; deployed state is compared against it and divergence is reported, never silently reconciled.

## 5. Scope and non-goals

### In scope

- Declarative runtime manifest inventory in Git
- Drift semantics IN_SYNC / DRIFT_DETECTED / UNKNOWN as a documented contract
- Rules for what may never be authoritative outside Git

### Non-goals

- Changing the existing deployment tracking implementation
- Automatic remediation of drift

## 6. Intent architecture

Git holds intent. A read-only comparator derives observed state and emits a tri-state verdict. Absence of evidence maps to UNKNOWN, never to IN_SYNC.

## 7. Contracts, data and capabilities

- Runtime manifest schema
- Drift verdict record with commit, inventory hashes and counters

Contracts are canonical in Git. The runtime-specific contract is defined by:

- [`platform/registry.yaml`](../../../platform/registry.yaml);
- [`platform/schemas/runtime-profile.schema.json`](../../../platform/schemas/runtime-profile.schema.json);
- [runtime source-of-truth policy](../../architecture/runtime-source-of-truth.md);
- [ADR-0009](../../architecture/adr/ADR-0009-runtime-source-of-truth-and-drift-semantics.md).

The reference architecture and [EPIC-01](EPIC-01-architecture-and-canonical-contracts.md)
remain the platform-wide authority model.

## 8. Dependencies and sequencing

- [EPIC-01 — Architecture and canonical contracts](EPIC-01-architecture-and-canonical-contracts.md) — `AS_BUILT` on `main` before this branch was created.

Sequencing follows the phase model in the
[intent document](../../architecture/security-validation-platform-v2-intent.md).
This epic is planned for phase 1.

## 9. Security, risks and failure modes

- Manifest divergence from actual container state
- Tri-state collapsing into boolean under pressure
- Generated applied state becoming an undocumented source of truth
- Orphan or duplicate runtime profiles
- Environment-level digest overrides diverging from a shared runtime release

Platform-wide invariants that this epic must not weaken:

- absence of evidence never produces a `PASS` verdict;
- no execution outside an active authorization contract;
- no secrets, tokens, cookies or raw credential material in documentation, telemetry
  or persisted evidence;
- no target outside registered laboratories.

## 10. Deliverables

- Documented source-of-truth policy
- Drift contract specification
- Schema-backed runtime profile inventory
- Read-only repository validator and positive/negative tests
- CI integration for source-of-truth validation

## 11. Acceptance criteria

- Every runtime asset has exactly one authoritative declaration
- UNKNOWN is produced whenever evidence is missing or unparsable

## 12. Evidence and validation plan

- Validate every registered runtime profile against the schema
- Reject duplicate IDs, duplicate manifest paths, ID mismatches and orphan profiles
- Reject environment references to undeclared runtimes
- Validate fail-safe drift and release identity rules
- Run repository, catalogue, security and gitleaks workflows
- Record runtime gates as `NOT_APPLICABLE` for this no-runtime-change block

Evidence must be referenced from the delivery umbrella issue before the umbrella can
be closed, and this document must record the references in section 15.

## 13. Decisions and open questions

### Decisions taken at intent time

- Git is authoritative; GitHub issues are a working view.

### Decisions taken during implementation

- `platform/registry.yaml` is the canonical catalogue root; it references authoritative
  artefacts instead of duplicating their contents.
- Applied deployment state, host observations, issues/comments and generated output are
  explicitly non-authoritative.
- Drift is strictly tri-state and missing, unparsable or unverifiable observation maps to
  `UNKNOWN`.
- Automatic reconciliation is forbidden.
- Image digest identity is pinned per immutable runtime release, not per environment.
- Host runtime profiles that do not identify an image use `NOT_APPLICABLE`; this does not
  waive digest requirements for later runner or laboratory image releases.

### Open questions

- None for this block. Runtime release manifests themselves remain a later implementation
  capability and must follow ADR-0009 when introduced.

## 14. Implementation notes

> Reserved lifecycle section. Updated during implementation with pull request references,
> deviations from intent and decisions taken while building. Do not delete this heading.

### Block 1 — canonical runtime source of truth

- Branch: `feat/epic-02-runtime-source-of-truth`
- Umbrella issue: [#76](https://github.com/pestoura/hermes-security-labs/issues/76)
- Pull request: pending creation from this branch
- Runtime declaration: `NO_RUNTIME_CHANGE`
- Normalized the five existing runtime profiles instead of creating duplicate declarations.
- Added a runtime-profile JSON Schema and a read-only source-of-truth validator.
- Added positive and negative tests and wired them into repository CI.
- Preserved `deployment/deployment_tracking.py` unchanged.

### Reconciled existing state

| Existing artefact | Classification after this block |
| --- | --- |
| `platform/registry.yaml` | canonical catalogue root |
| `platform/rollout.yaml` | authoritative rollout declaration referenced by registry |
| `platform/runtimes/*.yaml` | authoritative runtime profiles referenced one-to-one by registry |
| `platform/environments/**` | authoritative laboratory declarations for their own scope |
| `.deployment.json` | non-authoritative applied-state evidence |
| live host/container/network state | non-authoritative observation |
| GitHub issues/comments | work tracking, not configuration authority |

## 15. As-built / final architecture

> Reserved. Populate after the implementation pull request is merged. Must record what
> was actually built, evidence links, and every divergence from sections 6 to 11.
> No umbrella may be closed while this section is empty.

_Not yet merged._

## 16. Document change log

| Date | Version | Change |
| --- | --- | --- |
| 2026-08-06 | 1.0.0 | Initial intent document created from the concept epic catalogue. |
| 2026-08-06 | 1.1.0 | Set IMPLEMENTING; record canonical registry, tri-state drift, release identity decision, validator and CI plan. |
