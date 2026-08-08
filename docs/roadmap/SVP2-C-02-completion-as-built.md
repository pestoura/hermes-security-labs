# SVP2-C-02 — Completion / AS_BUILT Evidence Record

## 1. Decision

`SVP2-C-02 — Capability registry profiles and signed supply chain promotion` is eligible for delivery status **`completed`** at the repository / controlled-CI supply-chain boundary, subject to lifecycle reconciliation and exact-head/post-merge gates.

This delivery-level completion does not claim production image publication/promotion, production registry consumption or production revocation execution.

## 2. Completion boundary

The declared acceptance criteria are enforced by canonical contracts and controlled evidence:

1. capability usability requires `promotion=stable` plus installed, executable, functionally-tested, authorized and compatible state;
2. stable promotion fails closed unless SBOM, signature and provenance evidence are present and the scan blocker count is zero;
3. the supply-chain gate binds SBOM/signature/provenance/scan evidence to the same exact SHA-256 image subject rather than trusting unrelated references;
4. controlled CI creates an SPDX 2.3 inventory/provenance bundle and cryptographically signs/verifies the exact subject with an ephemeral Ed25519 key;
5. PR #251 builds a disposable scratch image, archives the exact image, scans that archive with pinned Trivy, binds the report digest/subject into the same evidence chain and requires HIGH/CRITICAL blockers=0 before `ELIGIBLE_CONTROLLED_CI`;
6. revocation sets the capability to `revoked`, makes it immediately unusable and prevents subsequent promotion.

Outside this completion claim:

- production image publication or stable promotion;
- production capability registry persistence/consumption by the gateway;
- production SBOM/provenance/signing service;
- production vulnerability scanning service;
- production revocation distribution/enforcement;
- campaign snapshot pinning against a deployed registry;
- use of production credentials or customer images.

## 3. Acceptance criteria disposition

| Acceptance criterion | Disposition | Evidence |
| --- | --- | --- |
| Capability is usable only when functionally-tested and authorized | `MET` | `is_usable()` requires stable promotion and `stable_gate_failures()` requires installed/executable/functionally_tested, authorized policy and compatibility. Negative tests fail closed when either functional testing or authorization is absent. |
| No image reaches stable without SBOM, signature and scan without blockers | `MET` at controlled repository/CI boundary | Stable gate requires SBOM/signature/provenance and zero scan blockers; PR #236 binds all evidence to one image identity; PR #245 provides controlled SPDX/provenance + Ed25519 verification; PR #251 performs the previously missing real controlled Trivy scan of the exact disposable image archive and requires blockers=0. Production stable promotion remains `NOT_RUN`. |
| Revocation removes image/capability from usable set immediately | `MET` in registry enforcement model | `revoke()` sets `revoked=true` and `promotion=revoked`; `is_usable()` returns false and all later promotion attempts fail closed. Production revocation distribution remains `NOT_RUN`. |

## 4. Deliverables disposition

| Deliverable | Result | Canonical implementation |
| --- | --- | --- |
| Capability registry and profile specification | `MET` | `platform/capability-registry/capability-registry.schema.json`, `capability_registry.py`, README and tests. |
| Image promotion/revocation policy | `MET` | `promotion-policy.yaml`, `supply_chain_gate.py`, controlled supply-chain evidence and image-assessment workflow. |

## 5. Key evidence

- PR #143 — repository-level capability-registry and supply-chain promotion decision logic; later lifecycle reconciliation #169 records the candidate while preserving runtime nonclaims.
- PR #236 — binds verified SBOM/signature/provenance/scan evidence to the exact same SHA-256 image subject.
- PR #245 — controlled provenance/signature evidence; head `12d98fa3c81aa617d014a41e09b79d6942997cd7`; merge `758f3617a39ae89ca721606bbd9356640b2c264a`.
- PR #251 — controlled real image assessment; head `cf9b034ea816ef2849ed8149fa536d57e9892dcf`; merge `e1b198540e097186acbca3ef0213293c5f2477e0`.
- PR #251 dedicated `controlled-image-assessment` post-merge job: PASS; exact image archive is scanned with Trivy and bound to the evidence bundle while `production_image=NOT_RUN` remains explicit.
- The eventual C-02 completion PR must independently pass exact-head and exact-SHA post-merge canonical gates.

## 6. Definition of Done assessment

| DoD | Result | Evidence / limitation |
| --- | --- | --- |
| DOD-01 — declared deliverables merged | `PASS` | Registry/profile and promotion/revocation contracts are in `main`. |
| DOD-02 — final-head repository/security gates | `PASS after completion validation` | Completion requires exact-head `security` + `validate` PASS. |
| DOD-03 — post-merge validation on main | `PASS after completion merge` | Exact integrated SHA must pass canonical gates. |
| DOD-04 — positive/negative/adversarial/regression testing | `PASS` | Missing functional/authorization/evidence/compatibility gates, non-zero scan blockers, quarantine/revocation and evidence-subject mismatches fail closed; real controlled scan evidence is mandatory. |
| DOD-05 — canonical documentation | `PASS after lifecycle reconciliation` | EPIC-07/EPIC-30 and historical runtime-status wording must be reconciled to distinguish controlled CI evidence from production `NOT_RUN`. |
| DOD-06 — no committed secrets | `PASS` | Controlled signing uses ephemeral keys; no production credentials/keys are committed. |
| DOD-07 — failures/missing evidence fail-safe | `PASS` | Missing/invalid evidence and revocation prevent usability/promotion. |
| DOD-08 — runtime boundary | `PASS with explicit limitation` | Disposable CI artefacts only; no production image publication/promotion. |
| DOD-09 — issue/backlog reconciliation | `PENDING` | Issue #83 closes only after lifecycle PR + post-merge GREEN. |
| DOD-10 — no false production claim | `PASS` | Production promotion, registry use, scanning service and revocation distribution remain `NOT_RUN`. |

## 7. Finality assessment

Therefore:

- `SVP2-C-02`: **candidate for `completed`**;
- capability usability gate: **`PASS`**;
- exact-subject supply-chain evidence binding: **`PASS_CONTROLLED_CI`**;
- controlled SPDX/provenance + Ed25519 verification: **`PASS_CONTROLLED_CI`**;
- controlled real Trivy image assessment: **`PASS_CONTROLLED_CI`**;
- revocation usability enforcement: **`PASS`**;
- production image publication/stable promotion: **`NOT_RUN`**;
- production registry consumption/revocation distribution: **`NOT_RUN`**;
- production SBOM/signing/provenance/scanning services: **`NOT_RUN`**.

## 8. Decision record

| Field | Value |
| --- | --- |
| Decision | Prepare `SVP2-C-02` for delivery completion at the controlled-CI supply-chain boundary. |
| Context | All three backlog acceptance criteria are now covered by registry enforcement plus exact-subject cryptographic/provenance and real controlled image-scan evidence. |
| Alternative considered | Keep C-02 implementing until a production registry publishes a stable image. |
| Reason rejected | That would conflate the declared supply-chain/promotion control delivery with production deployment; the completion claim keeps production explicitly `NOT_RUN`. |
| Accepted risk | Production registries/signers/scanners and revocation propagation can reveal operational integration defects absent in CI. |
| Mitigation | Preserve production `NOT_RUN` and require separate runtime/deployment acceptance before operational activation. |
| State | `Em validação` pending serial lifecycle reconciliation. |
| Next action | After the preceding lifecycle completion is merged, synchronize this record to current `main`, reconcile C-02 backlog/EPIC-07/EPIC-30/policy guards, run exact-head gates, merge only on PASS, then close #83 after post-merge GREEN. |
