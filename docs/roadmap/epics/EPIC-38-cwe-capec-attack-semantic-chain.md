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
| Document version | 1.2.0 |
| Document date | 2026-08-08 |
| Catalogue | [Epic catalogue 45](../epic-catalogue-45.md) |
| Lifecycle contract | [Architecture documentation lifecycle](../../architecture/architecture-documentation-lifecycle.md) |

## 2. Current status

**IMPLEMENTING** — PR #186 integrated the dedicated repository-level semantic-chain contract for deterministic `CVE → CWE → CAPEC → ATT&CK` resolution over explicitly supplied, immutable knowledge snapshots.

| Lifecycle state | Reached |
| --- | --- |
| INTENT | yes |
| IMPLEMENTING | yes |
| AS_BUILT | no |
| FINAL | no |

Implemented at repository-contract level:

- fixed typed hop rules: `VULNERABILITY_TO_CWE`, `CWE_TO_CAPEC`, `CAPEC_TO_ATTACK`;
- strict semantic-relation and semantic-chain JSON Schemas;
- canonical CVE/CWE/CAPEC/ATT&CK identifier validation;
- deterministic relation IDs bound to `knowledge_snapshot_id`;
- per-hop provenance records, rationale and confidence;
- deterministic ordered chain resolution independent of input relation order;
- first-class `GAP` output when a mapping is absent;
- first-class `AMBIGUOUS` output when multiple mappings exist, with no silent winner;
- duplicate semantic assertions fail closed until reconciled;
- conservative chain confidence equal to the weakest completed hop;
- bounded relation/provenance sets;
- confidence thresholds produce advisory/review metadata only;
- chain outputs are always non-executable with `execution_authority = NONE`.

The following capabilities remain explicitly `NOT_IMPLEMENTED` / `NOT_RUN`:

- authoritative external CWE/CAPEC/ATT&CK mapping acquisition: `NOT_RUN`;
- mapping curation/approval workflow: `NOT_IMPLEMENTED`;
- external mapping-version synchronization/migration: `NOT_IMPLEMENTED` / `NOT_RUN`;
- production Knowledge Fabric graph persistence/query integration: `NOT_IMPLEMENTED`;
- production campaign-planner consumption of semantic-chain outputs: `NOT_IMPLEMENTED` / `NOT_RUN`;
- automatic planning inclusion based on confidence: `NOT_IMPLEMENTED`.

The repository contract therefore supports `IMPLEMENTING`, but it does not justify `AS_BUILT` or `FINAL`.

## 3. Problem and motivation

Moving from a specific vulnerability to the adversary behaviour that exercises it is a manual, inconsistent reasoning step.

## 4. Intended outcome

An explicit semantic chain resolving vulnerability to weakness to attack pattern to technique, with confidence at each hop.

## 5. Scope and non-goals

### In scope

- Chain resolution rules and hop confidence
- Handling of missing or ambiguous links
- Chain outputs suitable for advisory planning consumption
- Chain quality metrics

### Non-goals

- Fabricating links where upstream data provides none
- Treating supplied mappings as authoritative merely because they validate structurally
- Granting or expanding execution authorization

## 6. Intent architecture

Resolution is deterministic given a snapshot: same input plus same snapshot yields the same chain, including explicit gaps and ambiguities.

PR #186 implements this as a pure repository contract under `platform/knowledge-fabric/semantic_chain.py`. It consumes supplied snapshot-scoped relations only. It does not fetch framework data or query a production graph.

## 7. Contracts, data and capabilities

Canonical implementation paths from PR #186:

- `platform/knowledge-fabric/semantic_chain.py`;
- `platform/knowledge-fabric/semantic-relation.schema.json`;
- `platform/knowledge-fabric/semantic-chain.schema.json`;
- `platform/tests/test_semantic_chain.py`;
- `platform/tests/test_semantic_chain_schema_guards.py`.

A semantic relation requires:

- one immutable `knowledge_snapshot_id`;
- the fixed typed relation kind and compatible source/destination entity types;
- per-hop confidence in `[0,1]`;
- one or more canonical Knowledge Fabric provenance-record IDs;
- explicit rationale;
- no authority-, execution- or secret-shaped fields.

The resolver never collapses multiple candidate targets into a silent winner. An ambiguous stage remains `AMBIGUOUS` even when one candidate has a higher confidence value.

Contracts are canonical in Git. Where this epic reuses a platform-wide contract, the canonical definition lives in the [reference architecture](../../architecture/security-validation-reference-architecture.md) and in [EPIC-01](EPIC-01-architecture-and-canonical-contracts.md); this document references it instead of restating it.

## 8. Dependencies and sequencing

- [EPIC-36 — Security Knowledge Fabric](EPIC-36-security-knowledge-fabric.md)
- [EPIC-37 — Vulnerability Intelligence Synchronization](EPIC-37-vulnerability-intelligence-synchronization.md)

Sequencing follows the phase model in the [intent document](../../architecture/security-validation-platform-v2-intent.md). This epic is planned for phase 5.

## 9. Security, risks and failure modes

- Low-confidence chains driving campaign content automatically
- Ambiguity collapsed into a single arbitrary path
- Generic relations being mistaken for validated framework semantics
- Relations from different snapshots being mixed
- Duplicate assertions masking unresolved conflicts
- Supplied external mappings being mistaken for curated/authoritative mappings

Platform-wide invariants that this epic must not weaken:

- absence of evidence never produces a `PASS` verdict;
- no execution outside an active authorization contract;
- no secrets, tokens, cookies or raw credential material in documentation, telemetry or persisted evidence;
- no target outside registered laboratories;
- semantic-chain outputs remain `ADVISORY_ONLY`;
- semantic-chain outputs are never executable and have `execution_authority = NONE`;
- Hermes / Control Plane remains the sole execution-authorization authority.

## 10. Deliverables

- Semantic chain specification — implemented repository-side
- Strict relation/chain schemas — implemented repository-side
- Deterministic resolver with gap/ambiguity semantics — implemented repository-side
- External mapping acquisition/curation and production planner integration — not implemented / not run

## 11. Acceptance criteria

- Every completed hop reports confidence, provenance and rationale — covered by contract/tests.
- Missing links are represented explicitly, never inferred silently — covered by `GAP` tests.
- Multiple mappings are represented explicitly, never silently selected — covered by `AMBIGUOUS` tests.
- Same input/snapshot yields the same chain independent of relation order — covered by determinism tests.
- Chain quality uses the weakest completed hop rather than an optimistic average — covered by contract/tests.
- Confidence thresholds do not authorize execution or automatically include campaign content — covered by authority-boundary tests.

Operational acceptance remains incomplete because authoritative external mappings and production planner consumption have not been validated.

## 12. Evidence and validation plan

Repository evidence integrated by PR #186:

- PR head `13e91cbab2972f6f18f8d134b2b6b2b0094e0657`;
- pre-merge `security = PASS` (`31228824176`);
- pre-merge `validate = PASS` (`31228824154`);
- integrated `main` `54220a8c83402f8d8c36d3addbb293269a6f8a45`;
- post-merge `security = PASS` (`31228937926`);
- post-merge `validate = PASS` (`31228937937`).

Future operational evidence required before `AS_BUILT`:

- controlled authoritative CWE/CAPEC/ATT&CK mapping datasets with version/provenance evidence;
- mapping curation/conflict-resolution evidence against real framework content;
- production snapshot persistence/query evidence where applicable;
- demonstrated planner consumption that preserves `GAP`, `AMBIGUOUS`, confidence and authorization boundaries;
- migration evidence when upstream framework mappings/identifiers change.

## 13. Decisions and open questions

### Decisions taken

- Gaps are first-class output, not failures.
- Ambiguities are first-class output and are never resolved solely by highest confidence.
- Chain confidence is the minimum confidence of completed hops.
- A confidence threshold only changes advisory/review metadata; it does not authorize execution.
- PR #146 is shared relation substrate only.
- PR #151 is consumer-side vulnerability resolution/proposal substrate only and does not replace the EPIC-38 resolver.
- PR #186 promotes EPIC-38 only to `IMPLEMENTING` after post-merge validation.

### Open questions

- Controlled source/curation process for authoritative CWE/CAPEC/ATT&CK mappings.
- Policy for confidence thresholds when a production planner eventually consumes the chain.
- How semantic-chain migration will consume EPIC-39 ATT&CK version/deprecation reports.

## 14. Implementation notes

> Reserved. Populate during implementation with pull request references, deviations from intent, and decisions taken while building. Do not delete this heading.

- PR #146 supplies generic provenance-aware relation construction.
- PR #151 supplies a caller-provided vulnerability-resolution object and provider/proposal contract; it does not perform semantic-chain graph resolution.
- PR #186 supplies the dedicated deterministic repository-level semantic-chain resolver, schemas and adversarial tests.
- External CWE/CAPEC/ATT&CK acquisition/curation remains `NOT_RUN` / `NOT_IMPLEMENTED`.
- Production planner/graph integration remains `NOT_IMPLEMENTED` / `NOT_RUN`.
- `NO_RUNTIME_CHANGE`.

## 15. As-built / final architecture

> Reserved. Populate when the delivery umbrella reaches completion. Must record what was actually built, evidence links, and every divergence from sections 6 to 11. No umbrella may be closed while this section is empty.

_Not populated. EPIC-38 is IMPLEMENTING; AS_BUILT and FINAL remain no._

## 16. Document change log

| Date | Version | Change |
| --- | --- | --- |
| 2026-08-06 | 1.0.0 | Initial intent document created from the concept epic catalogue. |
| 2026-08-07 | 1.1.0 | Clarified that generic relations from PR #146 do not implement the semantic-chain resolver; lifecycle remains INTENT. |
| 2026-08-08 | 1.2.0 | Reconciled PR #186 deterministic semantic-chain contract to `IMPLEMENTING`; recorded exact pre/post-merge gates and preserved external mapping/planner non-claims. |
