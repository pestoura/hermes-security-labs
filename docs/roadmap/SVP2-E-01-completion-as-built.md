# SVP2-E-01 — Completion / AS_BUILT Evidence Record

## 1. Decision

`SVP2-E-01 — Security knowledge graph schema provenance and framework sync` is eligible for delivery status **`completed`** at the repository / controlled-local Knowledge Fabric boundary.

This applies to the **delivery umbrella `SVP2-E-01` only**. It does not promote `EPIC-36 — Security Knowledge Fabric` or its dependent knowledge concepts to `FINAL`. Production graph persistence, campaign snapshot pinning, external source ingestion/synchronization and source-currentness verification remain outside this completion claim.

The umbrella's declared deliverables are the canonical Knowledge Fabric architecture and the source/synchronization specification. Its three acceptance criteria are now executable in CI against a local persistence boundary.

## 2. Completion boundary

Demonstrated in repository/controlled CI:

1. canonical Knowledge Fabric entity/relation/provenance/conflict contracts;
2. raw knowledge bytes persisted content-addressed and create-only;
3. canonical knowledge-record metadata protected by SHA-256 sidecars;
4. reopen and tamper verification for raw bytes and record metadata;
5. relation publication blocked unless every provenance record exists and verifies;
6. relation confidence and rationale remain explicit;
7. source conflicts persisted in the unresolved state;
8. silent/preselected conflict resolution refused;
9. explicit precedence resolution stored separately without rewriting conflict history;
10. relation and resolution persistence carry `execution_authority=NONE`.

Outside the completion claim:

- actual NVD/CISA/KEV/EPSS/TAXII/STIX/ATT&CK/ATLAS external synchronization;
- production graph database;
- campaign snapshot service/pinning;
- production source-currentness or authority verification;
- automatic source precedence/default winner;
- WORM/storage-administrator tamper resistance;
- any execution authorization derived from knowledge.

## 3. Acceptance criteria disposition

| Acceptance criterion | Disposition | Evidence |
| --- | --- | --- |
| Nenhuma relação é publicada sem proveniência completa | `MET` at controlled-local boundary | `publish_relation` validates relation shape and refuses publication unless every `provenance_record_id` exists and passes raw + record integrity verification. |
| Conflitos entre fontes são persistidos e não resolvidos silenciosamente | `MET` at controlled-local boundary | Conflicts persist only as `unresolved` with `selected_assertion=None`; resolution requires an explicit precedence policy and creates a separate immutable resolution record without modifying original conflict bytes. |
| Dados brutos ingeridos são imutáveis | `MET` as create-only/content-addressed local integrity | Raw bytes are stored by SHA-256 and records use create-only writes plus canonical metadata sidecars; replayed identical writes are idempotent and mutation/tamper fails verification. This is not a WORM or administrator-threat claim. |

## 4. Deliverables disposition

| Deliverable | Result | Canonical source |
| --- | --- | --- |
| `docs/architecture/security-knowledge-fabric.md` mantido como canónico | `MET` | Existing canonical architecture plus repository contracts and local integrity implementation. |
| Especificação das fontes e do seu modo de sincronização | `MET` as source/sync specification | `platform/knowledge-fabric/source-policy.yaml`; external synchronization remains `NOT_RUN`. |

## 5. Key evidence

- PR #146 — initial repository-owned knowledge-record, relation, conflict and applicability contract.
- PR #226 — controlled local integrity store:
  - final clean head `28d4d2bd399e497f44a877d318001ea6138a92ff`;
  - pre-merge security `31270424217`: PASS;
  - pre-merge validate `31270424092`: PASS;
  - squash merge `3329923039970da74a8b99bd4d28ef4fbe58039c`;
  - post-merge security `31270509628`: PASS;
  - post-merge validate `31270509655`: PASS.

The #226 branch history was intentionally rewritten before merge to remove a historical synthetic fixture string that caused a Gitleaks generic-key false positive. No Gitleaks allowlist or scanner weakening was introduced; the final clean one-commit branch passed the unchanged security gate.

## 6. Definition of Done assessment

| DoD | Result | Evidence / limitation |
| --- | --- | --- |
| DOD-01 — declared deliverables merged | `PASS` | Architecture and source policy are canonical; local integrity boundary is merged. |
| DOD-02 — final-head repository/security gates | `PASS` | #226 exact clean head passed `security` and `validate`. |
| DOD-03 — post-merge validation on main | `PASS after completion merge` | #226 post-merge gates PASS; completion itself remains valid only after its own post-merge gates pass. |
| DOD-04 — positive/negative/adversarial testing | `PASS` | Reopen, idempotence, raw/metadata tamper, missing provenance, relation tamper, unresolved conflict enforcement, history rewrite refusal and no-authority assertions are covered. |
| DOD-05 — canonical documentation | `PASS with explicit boundary` | Architecture/source policy + this completion record distinguish delivery completion from production graph/sync finality. |
| DOD-06 — no committed secrets | `PASS` | Final clean head passed Gitleaks without exceptions. |
| DOD-07 — fail-safe behaviour | `PASS` | Missing/tampered provenance blocks relation publication/verification; invalid conflict transitions/resolutions fail closed. |
| DOD-08 — rollback/runtime boundary | `PASS` | Filesystem-local synthetic CI only; no external sync or deployed graph runtime. |
| DOD-09 — backlog/issue reconciliation | `PENDING UNTIL MERGE` | Completion PR must promote only `SVP2-E-01`; issue #86 closes only after post-merge GREEN. |
| DOD-10 — no false FINAL/production claim | `PASS` | EPIC-36 remains non-final; graph store/external sync/campaign snapshots stay pending. |

## 7. Finality assessment

- `SVP2-E-01`: **candidate for `completed`**;
- `EPIC-36`: **`IMPLEMENTING` / `AS_BUILT=no` / `FINAL=no`**;
- controlled local raw integrity: **`PASS_CONTROLLED_CI`**;
- relation provenance publication gate: **`PASS_CONTROLLED_CI`**;
- unresolved conflict persistence: **`PASS_CONTROLLED_CI`**;
- explicit non-rewriting resolution: **`PASS_CONTROLLED_CI`**;
- external sync: **`NOT_RUN`**;
- TAXII/NVD/KEV/EPSS sync: **`NOT_RUN`**;
- production graph store: **`NOT_IMPLEMENTED`**;
- production persistence: **`NOT_RUN`**;
- campaign snapshot pinning: **not demonstrated by this umbrella completion**;
- execution authority from knowledge: **`NONE`**.

## 8. Decision record

| Field | Value |
| --- | --- |
| Decision | Complete `SVP2-E-01` at the repository/controlled-local integrity boundary without promoting EPIC-36 to FINAL. |
| Context | Both deliverables exist and all three E-01 acceptance criteria now have executable persistence/integrity evidence. |
| Alternatives | Keep E-01 open until production graph storage and all external feeds are synchronized. |
| Justification | Those are broader concept/finality and operational synchronization concerns; the E-01 delivery criteria require provenance/conflict/raw-integrity semantics and a source/sync specification, not successful production ingestion of every listed feed. |
| Accepted risk | A production graph/backend or external source may expose consistency, scale, retention and source-currentness defects absent from the local store. |
| Mitigation | Preserve explicit external-sync/graph-store non-claims and keep EPIC-36 non-final until production evidence exists. |
| State | `Em validação` until completion PR + post-merge gates are GREEN; then `Decisão`. |
| Next action | Reconcile #86 and continue E-02 / remaining backlog. |
