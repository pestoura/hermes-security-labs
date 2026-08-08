# SVP2-D-01 — Completion / AS_BUILT Evidence Record

## 1. Decision

`SVP2-D-01 — Evidence Plane v2 with chain of custody retention and replay` is eligible for delivery status **`completed`** at the repository / local-controlled Evidence Plane boundary.

This decision applies to the **delivery umbrella `SVP2-D-01` only**. It does not promote `EPIC-10 — Evidence Plane` or `EPIC-12 — Redaction and data classification` to `FINAL`. Both remain **`IMPLEMENTING` / `AS_BUILT=no` / `FINAL=no`** while production object storage, encryption at rest, WORM/immutable storage, executable retention enforcement, deployed Runner handoff, production replay/redaction and customer publication remain `NOT_IMPLEMENTED` / `NOT_RUN` as applicable.

`completed` therefore means that the declared D-01 deliverables and backlog acceptance criteria are demonstrated in the controlled local boundary. It does not mean production chain-of-custody certification or production Evidence Plane readiness.

## 2. Completion boundary

The delivery has repository-backed and CI-executed evidence for:

1. canonical Evidence Plane v2 schema and policy;
2. mandatory campaign/run/step/attempt correlation identifiers;
3. SHA-256 content integrity and content-addressed local persistence;
4. canonical record-metadata digest sidecars and fail-closed tamper detection;
5. raw/restricted/sanitized/summary classification;
6. default-deny sharing for raw/restricted evidence;
7. derived parent/source-digest lineage;
8. deterministic structured redaction;
9. redaction before persistence of structured sensitive source material;
10. deterministic verified reconstruction of a stored sanitized/summary result from its evidence record and lineage.

The following remain **outside the completion claim**:

- production object/WORM storage;
- encryption-at-rest proof and key lifecycle;
- executable retention expiry/deletion scheduler;
- production Runner → Evidence Plane transport;
- production redaction/replay;
- customer export/publication workflow;
- Human-in-the-Loop publication approval;
- protection against an actor with write control over the complete local filesystem store.

## 3. Acceptance criteria disposition

| Acceptance criterion | Disposition | Evidence |
| --- | --- | --- |
| Toda a evidência tem hash, origem e identificadores de correlação | `MET` at the controlled local boundary | Evidence v2 requires origin, SHA-256 and all four correlation IDs; local persistence verifies payload digest/size and canonical record metadata. |
| Evidência bruta nunca é partilhada sem derivação sanitizada | `MET` at the controlled local boundary | Raw/restricted classes are non-exportable by default; structured safe-ingress redacts in memory before persistence and persists only a digest-only restricted manifest plus sanitized derivative. |
| Um resultado pode ser reproduzido a partir do registo de evidência | `MET` as verified stored-result reconstruction | PR #223 reconstructs the exact stored sanitized/summary payload after record, payload and parent-lineage verification and emits a deterministic receipt. It explicitly does **not** re-execute the originating operation or replay authorization. |

## 4. Deliverables disposition

| Deliverable | Result | Canonical implementation |
| --- | --- | --- |
| Especificação do Evidence Plane v2 | `MET` | `platform/evidence-plane/evidence-record.schema.json`, `evidence_plane.py`, `README.md`. |
| Política de retenção e de partilha de evidência | `MET` as policy/contract | `platform/evidence-plane/evidence-policy.yaml`; runtime retention enforcement remains `NOT_RUN`. |

## 5. Key evidence

- PR #217 — local content-addressed persistence, reopen, payload integrity, lineage and export boundary; merge `aa589bbaa6ede9192963ff2a47244ab34309c1c6`; post-merge security `31265416771` PASS; validate `31265416803` PASS.
- PR #218 — lifecycle reconciliation for local persistence; merge `e667d6d8...`; post-merge gates PASS.
- PR #219 — deterministic structured redaction; merge `383d60479f5874ac103fe3a74654e85690be19d0`; post-merge security `31266367567` PASS; validate `31266367331` PASS.
- PR #220 — structured-redaction lifecycle reconciliation; merge `724515b49f89a1b163afacc5e98c44d4b9812aeb`; post-merge security `31266841057` PASS; validate `31266841059` PASS.
- PR #221 — redaction-before-persistence safe ingress; merge `cbf88aecb9bf69ad4d7bd0164f8ac8f61f04b4aa`; post-merge security `31267199992` PASS; validate `31267199995` PASS.
- PR #222 — safe-ingress lifecycle reconciliation; merge `9ae0d0ad026595f00856c4aa727c4f51ff64ff29`; post-merge security `31267571201` PASS; validate `31267571199` PASS.
- PR #223 — verified stored-result reconstruction plus canonical record metadata integrity sidecar; validated head `38ad140426392f13e2ac361016d5ec952ddb5665`; pre-merge security `31268294121` PASS; validate `31268294124` PASS; squash merge `fa0e0eb40e0fd558b43a2bae8f411761d51f9807`; post-merge security `31268410335` PASS; validate `31268410326` PASS.

All fixtures used by these blocks are synthetic and filesystem-local to controlled CI.

## 6. Definition of Done assessment

| DoD | Result | Evidence / limitation |
| --- | --- | --- |
| DOD-01 — declared deliverables merged | `PASS` | Evidence Plane v2 specification and retention/sharing policy are canonical in `main`. |
| DOD-02 — final-head repository/security gates | `PASS` | Technical blocks were merged only after exact-head `security` + `validate` PASS. |
| DOD-03 — post-merge validation on main | `PASS after completion merge` | Technical blocks through #223 have exact-SHA post-merge PASS; completion remains valid only after its own post-merge gates pass. |
| DOD-04 — positive/negative/adversarial/regression testing | `PASS` | Reopen, idempotence, payload tamper, metadata tamper, parent tamper, invalid policy identity, non-exportable classes, sensitive canaries and safe-ingress persistence are covered. |
| DOD-05 — canonical documentation | `PASS with explicit reconciliation` | This record separates D-01 delivery completion from concept finality and production custody claims. |
| DOD-06 — no committed secrets | `PASS` | Security gates remain GREEN; all sensitive values used in tests are synthetic canaries. |
| DOD-07 — failures/missing evidence fail-safe | `PASS` | Corrupt payload, record, sidecar, lineage or policy identity prevents reconstruction/export. |
| DOD-08 — rollback / runtime boundary | `PASS with explicit limitation` | Production storage/replay/redaction remain `NOT_RUN`; no external/deployed runtime change is claimed. |
| DOD-09 — issue/backlog status reconciliation | `PENDING UNTIL MERGE` | Completion PR must promote only `SVP2-D-01` to `completed`; after post-merge GREEN, issue #84 is reconciled and closed. |
| DOD-10 — no false FINAL claim | `PASS` | EPIC-10 and EPIC-12 remain non-final; WORM/encryption/retention enforcement/production replay remain outside the completion claim. |

## 7. Finality assessment

Therefore:

- `SVP2-D-01`: **candidate for `completed`**;
- `EPIC-10`: **`IMPLEMENTING` / `AS_BUILT=no` / `FINAL=no`**;
- `EPIC-12`: **`IMPLEMENTING` / `AS_BUILT=no` / `FINAL=no`**;
- local controlled persistence: **`PASS_LOCAL_CONTROLLED_CI`**;
- redaction-before-persistence: **`PASS_CONTROLLED_CI`**;
- verified stored-result reconstruction: **`PASS_CONTROLLED_CI`**;
- encryption at rest: **`NOT_RUN`**;
- WORM/object storage: **`NOT_IMPLEMENTED` / `NOT_RUN`**;
- retention enforcement: **`NOT_IMPLEMENTED` / `NOT_RUN`**;
- production replay/redaction: **`NOT_RUN`**;
- deployed Evidence Plane: **`NO_RUNTIME_CHANGE`**.

## 8. Decision record

| Field | Value |
| --- | --- |
| Decision | Complete delivery umbrella `SVP2-D-01` without promoting EPIC-10/EPIC-12 to `FINAL`. |
| Context | Both declared deliverables exist and all three backlog acceptance criteria are demonstrated in controlled local CI. |
| Alternative considered | Keep D-01 `implementing` until WORM/encryption/retention enforcement and production replay exist. |
| Reason rejected | Those are concept/production finality concerns beyond the declared D-01 deliverables and acceptance criteria; keeping the umbrella open would conflate delivery completion with production finality. |
| Accepted risk | Production storage and transport can expose durability, key-management, retention and distributed-chain-of-custody defects not observable in the local reference store. |
| Mitigation | Preserve explicit production non-claims, keep EPIC-10/12 non-final and require separate deployment/runtime gates before any production claim. |
| State | `Em validação` until completion PR and exact-SHA post-merge gates are GREEN; then `Decisão`. |
| Next action | Reconcile issue #84 after merge and continue the remaining P0/P1 backlog. |
