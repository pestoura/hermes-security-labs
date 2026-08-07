# EPIC-38 — CWE/CAPEC/ATT&CK Semantic Chain

## 1. Metadata

| Field | Value |
| --- | --- |
| Concept epic ID | `EPIC-38` |
| Slug | `cwe-capec-attack-semantic-chain` |
| Pillar | `E` — Security Knowledge Fabric |
| Phase | 5 |
| Priority | P1 |
| Delivery umbrella | `SVP2-E-01` (issue [#86](https://github.com/pestoura/hermes-security-labs/issues/86)) |
| Document version | 1.1.0 |
| Document date | 2026-08-07 |
| Catalogue | [Epic catalogue 45](../epic-catalogue-45.md) |
| Lifecycle contract | [Architecture documentation lifecycle](../../architecture/architecture-documentation-lifecycle.md) |

## 2. Current status

**INTENT** — this concept remains intentionally unpromoted. PR #146 implements generic provenance-aware relation derivation, but not the deterministic vulnerability → CWE → CAPEC → ATT&CK chain resolver required by EPIC-38.

| Lifecycle state | Reached |
| --- | --- |
| INTENT | yes |
| IMPLEMENTING | no |
| AS_BUILT | no |
| FINAL | no |

The following EPIC-38-specific capabilities remain `NOT_IMPLEMENTED` / `NOT_RUN`:

- typed hop rules for vulnerability-to-weakness, weakness-to-pattern and pattern-to-technique resolution;
- deterministic chain record and ordered hop model;
- first-class missing-link/gap semantics;
- per-hop confidence aggregation and chain-quality policy;
- ambiguity handling specific to semantic-chain resolution;
- planning integration using a frozen knowledge snapshot.

Generic `derive_relation()` support from PR #146 cannot establish that the required semantic chain exists or that any external mapping has been validated.

## 3. Problem and motivation

Moving from a specific vulnerability to the adversary behaviour that exercises it is a manual, inconsistent reasoning step.

## 4. Intended outcome

An explicit semantic chain resolving vulnerability to weakness to attack pattern to technique, with confidence at each hop.

## 5. Scope and non-goals

### In scope

- Chain resolution rules and hop confidence
- Handling of missing or ambiguous links
- Chain outputs consumed by planning
- Chain quality metrics

### Non-goals

- Fabricating links where upstream data provides none

## 6. Intent architecture

Resolution is deterministic given a snapshot: same input plus same snapshot yields the same chain, including explicit gaps.

## 7. Contracts, data and capabilities

- Chain record with hops, confidence and gaps

Contracts are canonical in Git. Where this epic reuses a platform-wide contract, the canonical definition lives in the [reference architecture](../../architecture/security-validation-reference-architecture.md) and in [EPIC-01](EPIC-01-architecture-and-canonical-contracts.md); this document references it instead of restating it.

## 8. Dependencies and sequencing

- [EPIC-36 — Security Knowledge Fabric](EPIC-36-security-knowledge-fabric.md)
- [EPIC-37 — Vulnerability Intelligence Synchronization](EPIC-37-vulnerability-intelligence-synchronization.md)

Sequencing follows the phase model in the [intent document](../../architecture/security-validation-platform-v2-intent.md). This epic is planned for phase 5.

## 9. Security, risks and failure modes

- Low-confidence chains driving campaign content
- Ambiguity collapsed into a single arbitrary path
- Generic relations being mistaken for validated framework semantics

Platform-wide invariants that this epic must not weaken:

- absence of evidence never produces a `PASS` verdict;
- no execution outside an active authorization contract;
- no secrets, tokens, cookies or raw credential material in documentation, telemetry or persisted evidence;
- no target outside registered laboratories.

## 10. Deliverables

- Semantic chain specification

## 11. Acceptance criteria

- Every chain reports per-hop confidence and gaps
- Missing links are represented explicitly, never inferred silently

No dedicated semantic-chain resolver or chain evidence exists yet.

## 12. Evidence and validation plan

- Chain samples with explicit gap reporting
- Determinism tests against pinned knowledge snapshots
- Ambiguous/low-confidence mapping cases

## 13. Decisions and open questions

### Decisions taken

- Gaps are first-class output, not failures.
- PR #146 is shared relation substrate only and does not promote EPIC-38.

### Open questions

- Minimum confidence for automatic planning inclusion

## 14. Implementation notes

> Reserved. Populate during implementation with pull request references, deviations from intent, and decisions taken while building. Do not delete this heading.

- PR #146 supplies generic provenance-aware relation construction only.
- No CWE/CAPEC/ATT&CK chain resolver is implemented.
- `NO_RUNTIME_CHANGE`.

## 15. As-built / final architecture

> Reserved. Populate when the delivery umbrella reaches completion. Must record what was actually built, evidence links, and every divergence from sections 6 to 11. No umbrella may be closed while this section is empty.

_Not started. EPIC-38 remains INTENT._

## 16. Document change log

| Date | Version | Change |
| --- | --- | --- |
| 2026-08-06 | 1.0.0 | Initial intent document created from the concept epic catalogue. |
| 2026-08-07 | 1.1.0 | Clarified that generic relations from PR #146 do not implement the semantic-chain resolver; lifecycle remains INTENT. |
