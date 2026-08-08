# SVP2-E-02 — Completion / AS_BUILT Evidence Record

## 1. Decision

`SVP2-E-02 — Security Knowledge API queries and per-campaign snapshots` is eligible for delivery status **`completed`** at the repository / controlled-local Knowledge API boundary.

This applies to the **delivery umbrella `SVP2-E-02` only**. It does not promote `EPIC-43 — Knowledge-Driven Campaign Planner`, `EPIC-44 — Knowledge Quality and Conflict Resolution` or `EPIC-45 — Operational Query and Discovery` to `FINAL`. Production HTTP/database/graph services, external synchronization, production temporal ingestion, production planner execution and Control Plane runtime integration remain outside this completion claim.

`SVP2-C-02` remains an unresolved dependency for later production capability/supply-chain operation; E-02 completion does not claim C-02 completion or production readiness.

## 2. Completion boundary

Demonstrated in repository/controlled CI:

1. immutable content-addressed Knowledge API snapshots;
2. snapshot persistence only when every E-01 source record exists and verifies;
3. canonical create-only snapshot records with integrity sidecars;
4. create-only campaign-to-snapshot bindings;
5. campaign rebind to a different snapshot refused;
6. EPSS/KEV/VEX temporal entries persisted append-only/content-addressed with verified provenance;
7. operational queries bound to one exact persisted snapshot;
8. explicit minimum-confidence filtering;
9. cross-snapshot query/index mixing fails closed;
10. campaign proposals persist only for the campaign's pinned snapshot;
11. persisted proposals remain `PROPOSAL_ONLY`, `executable=false`, `dispatch_available=false`, `execution_authority=NONE` and `authorization_source=CONTROL_PLANE_ONLY`;
12. nested execution, target, secret and authorization-shaped fields fail closed.

Outside the completion claim:

- HTTP/API service deployment;
- persistent production database or graph-query engine;
- external knowledge synchronization;
- production temporal ingestion;
- production campaign planner execution;
- Control Plane runtime calls or authorization receipts;
- production identity/RBAC integration;
- customer-facing query or planning service.

## 3. Acceptance criteria disposition

| Acceptance criterion | Disposition | Evidence |
| --- | --- | --- |
| Toda a query aceita filtro por snapshot do Knowledge Fabric e confiança mínima | `MET` at controlled-local boundary | Existing canonical `knowledge_api.py` and `operational_query.py` require immutable snapshot and minimum confidence; PR #228 executes queries against a persisted snapshot, filters low-confidence records and fails closed on cross-snapshot mixing. |
| Toda a campanha regista o snapshot exato usado | `MET` at controlled-local boundary | PR #228 persists create-only campaign bindings to one verified snapshot and refuses later rebind to a different snapshot, including across store reopen. |
| Propostas baseadas em conhecimento não são executáveis sem autorização do Control Plane | `MET` | Canonical proposals are `PROPOSAL_ONLY` / `executable=false` / `authorization_source=CONTROL_PLANE_ONLY`; PR #228 persists them only for the pinned campaign snapshot with `execution_authority=NONE` and `dispatch_available=false`. |

## 4. Deliverables disposition

| Deliverable | Result | Canonical source |
| --- | --- | --- |
| Especificação da Knowledge API e snapshots | `MET` | `platform/knowledge-api/knowledge_api.py`, `knowledge-snapshot.schema.json`, `operational_query.py`, query schemas and `local_api_store.py`. |
| Política de mapeamento entre frameworks e conhecimento interno | `MET` at repository contract level | Canonical Knowledge Fabric/crosswalk contracts and `platform/knowledge-api/knowledge-api-policy.yaml`; production synchronization remains `NOT_RUN`. |

## 5. Key evidence

- PR #148 — immutable snapshots, snapshot-bound query validation, minimum-confidence filtering, temporal series and proposal non-executability contract.
- PR #196 — canonical operational question catalogue, snapshot-scoped deterministic read-only queries, exact access/index/evidence scope and fail-closed snapshot mixing.
- PR #228 — controlled-local snapshot/campaign/temporal/proposal persistence:
  - final head `a3d09e8673235e9d5d0cdfe4cce62e330915bd87`;
  - pre-merge security `31271574068`: PASS;
  - pre-merge validate `31271574069`: PASS;
  - squash merge `79ad05837b6bbe7c26787be31c2ff2229aa97438`;
  - post-merge security `31271675263`: PASS;
  - post-merge validate `31271675287`: PASS.
- E-01 dependency #86 is completed at the controlled-local provenance/integrity boundary; PR #228 verifies E-01 records before admitting snapshots and temporal observations.

All fixtures are synthetic and filesystem-local to controlled CI.

## 6. Definition of Done assessment

| DoD | Result | Evidence / limitation |
| --- | --- | --- |
| DOD-01 — declared deliverables merged | `PASS` | API/snapshot/query contracts, Knowledge Fabric/crosswalk contracts and controlled persistence are canonical in main. |
| DOD-02 — exact-head security and repository gates | `PASS` | PR #228 exact head passed `security` and `validate`. |
| DOD-03 — post-merge validation | `PASS after completion merge` | #228 post-merge gates are GREEN; completion remains valid only after its own merge gates pass. |
| DOD-04 — positive/negative/adversarial testing | `PASS` | Snapshot provenance, reopen/tamper, campaign pinning/rebind, temporal provenance, confidence filtering, cross-snapshot denial, proposal mismatch/injection/tamper are covered. |
| DOD-05 — canonical documentation | `PASS with explicit boundary` | Policy and this completion record distinguish local delivery completion from production API/planner finality. |
| DOD-06 — no committed secrets | `PASS` | Security gate GREEN; fixtures are synthetic. |
| DOD-07 — fail-safe behaviour | `PASS` | Missing/tampered provenance, unknown snapshot, rebind, cross-snapshot query and execution-shaped proposal input fail closed. |
| DOD-08 — rollback/runtime boundary | `PASS` | Filesystem-local temporary CI only; no external/deployed runtime change. |
| DOD-09 — backlog/issue reconciliation | `PENDING UNTIL MERGE` | Completion PR must promote only `SVP2-E-02`; #87 closes only after exact-SHA post-merge GREEN. |
| DOD-10 — no false FINAL/production claim | `PASS` | EPIC-43/44/45 remain non-final; HTTP/database/graph/query/planner/runtime integrations remain pending. |

## 7. Finality assessment

- `SVP2-E-02`: **candidate for `completed`**;
- `EPIC-43`: **`IMPLEMENTING` / `AS_BUILT=no` / `FINAL=no`**;
- `EPIC-44`: **`IMPLEMENTING` / `AS_BUILT=no` / `FINAL=no`**;
- `EPIC-45`: **`IMPLEMENTING` / `AS_BUILT=no` / `FINAL=no`**;
- controlled snapshot persistence: **`PASS_CONTROLLED_CI`**;
- campaign snapshot pinning: **`PASS_CONTROLLED_CI`**;
- campaign rebind: **`FORBIDDEN`**;
- temporal append-only persistence: **`PASS_CONTROLLED_CI`**;
- operational snapshot/confidence filtering: **`PASS_CONTROLLED_CI`**;
- proposal execution authority: **`NONE`**;
- proposal dispatch: **`false`**;
- HTTP API/database/graph query engine: **`NOT_IMPLEMENTED`**;
- external sync/production planner/temporal ingestion: **`NOT_RUN`**;
- production snapshot/campaign stores: **`NOT_RUN`**;
- Control Plane runtime integration: **`NOT_RUN`**;
- deployed runtime: **`NO_RUNTIME_CHANGE`**.

## 8. Decision record

| Field | Value |
| --- | --- |
| Decision | Complete `SVP2-E-02` at the repository/controlled-local Knowledge API boundary without promoting EPIC-43/44/45 to FINAL. |
| Context | The three umbrella acceptance criteria are now executable and persistent in controlled CI, while existing query contracts already enforce read-only snapshot/confidence semantics. |
| Alternatives | Keep E-02 open until an HTTP/database production service and Control Plane integration exist. |
| Justification | Those are concept/production finality concerns beyond the declared E-02 delivery criteria; retaining the umbrella as implementing would conflate delivery completion with deployment readiness. |
| Accepted risk | Production persistence, identity/RBAC, distributed consistency and planner integration may expose defects not observable in the local store. |
| Mitigation | Preserve explicit production non-claims and keep EPIC-43/44/45 non-final until operational evidence exists. |
| State | `Em validação` until completion PR + post-merge gates are GREEN; then `Decisão`. |
| Next action | Reconcile #87 after merge and continue the remaining P0/P1 backlog. |
