# SVP2-B-03 — Completion / AS_BUILT Evidence Record

## 1. Decision

`SVP2-B-03 — Transactional lab lifecycle cleanup proof and network egress profiles` is eligible for delivery status **`completed`** at the repository / controlled-Docker-CI boundary.

This decision applies only to the **delivery umbrella `SVP2-B-03`**. It does not promote concept epics `EPIC-04 — Transactional lifecycle and isolation` or `EPIC-08 — Network and egress policy` to `AS_BUILT` or `FINAL`.

## 2. Completion boundary

The umbrella acceptance criteria are now directly exercised using disposable Docker resources created only for CI:

1. cleanup uncertainty/failure produces `QUARANTINED`, `reusable=false` and no zero-residue proof;
2. the controlled lab network is created with Docker `--internal`, so no default external egress route is granted by this candidate;
3. bounded periodic scans enumerate only explicitly labelled controlled-CI network/volume resources and identify untracked resources as orphans;
4. cleanup verifies ownership labels before removal and produces a zero-residue proof only after the owned resources disappear;
5. observation and cleanup remain separated from target execution: the controlled driver does not create or run containers and never contacts an external target.

Outside the completion claim:

- production Docker lifecycle service or daemon identity;
- production scanner authentication/attestation;
- state-based container attach/detach under real campaign races;
- firewall/egress exception enforcement beyond the controlled `--internal` network observation;
- orphan remediation after detection;
- real L3/L4 snapshot/rollback execution, TTL enforcement and data budgets;
- Kubernetes or other runtime drivers;
- customer or production deployment.

## 3. Acceptance criteria disposition

| Acceptance criterion | Disposition | Evidence |
| --- | --- | --- |
| Cleanup failure quarantines the laboratory and blocks reuse | `MET` at controlled-CI boundary | Lifecycle contract already fails closed; PR #231 adds `cleanup_with_state()` and a negative test proving synthetic cleanup failure returns `QUARANTINED`, `reusable=false`, `proof=None`, `cleanup_error=CLEANUP_UNVERIFIED`. |
| No laboratory obtains egress by default | `MET` for the controlled Docker candidate | PR #231 provisions the disposable lab network with Docker `network create --internal`, validates `.Internal == true`, and does not create a path that widens egress. The broader production policy remains non-final. |
| Periodic orphan-resource detection exists | `MET` at controlled-CI boundary | PR #231 adds bounded periodic scan orchestration and real Docker CI tests where controlled network/volume resources without lifecycle ownership are repeatedly classified as `ORPHANS_DETECTED`. |

## 4. Deliverables disposition

| Deliverable | Result | Canonical implementation |
| --- | --- | --- |
| Lab lifecycle and network-profile specification | `MET` | `platform/lab-lifecycle/` schemas/policy/protocol plus EPIC-04/EPIC-08 documentation. |
| Zero-residue proof contract | `MET` | `zero-residue-proof.schema.json`, lifecycle proof validation, controlled Docker cleanup/reopen tests. |

## 5. Key evidence

- PR #139 — transactional lifecycle/isolation/zero-residue contract; merge `591552d652fbff82d81f750535799380e9c643a9`; post-merge security/validate PASS.
- PR #166 — EPIC-04/08 lifecycle reconciliation; post-merge security/validate PASS.
- PR #231 — controlled Docker lifecycle + periodic orphan scanning; final validated head `1249e8a08f9c753b736ffce3f2cc34210b2cde43`; merge `53fba289687ac1b0d4a9f57dff706cc6e32dc633`.
- PR #231 exercises real disposable Docker **network and volume** resources in CI only; no containers, targets or external systems are created or contacted by this acceptance harness.
- Integrated main including B-03 and subsequent independent lanes remained GREEN through `4c6525af187f7e18f507b1a42f6ebf82a24a644d` and later `0fa1b0196388ef7be17f84fe9deebc53ba850600` subject to the completion PR's own exact-head and post-merge gates.

## 6. Definition of Done assessment

| DoD | Result | Evidence / limitation |
| --- | --- | --- |
| DOD-01 — declared deliverables merged | `PASS` | Lifecycle/network specification and zero-residue contract are in `main`. |
| DOD-02 — final-head repository/security gates | `PASS after completion validation` | Completion status is valid only after this PR's exact head has `security` + `validate` PASS. |
| DOD-03 — post-merge validation on main | `PASS after completion merge` | Completion is final only after exact integrated SHA post-merge `security` + `validate` PASS. |
| DOD-04 — positive/negative/adversarial/regression testing | `PASS` | Includes real disposable Docker network/volume observations, orphan findings, zero-residue proof, ownership checks, bounded periodic scans and fail-closed cleanup failure. |
| DOD-05 — canonical documentation | `PASS with reconciliation` | EPIC-04/08 are updated to acknowledge controlled CI observations while preserving production limitations. |
| DOD-06 — no committed secrets | `PASS` | Harness uses no customer credentials, external tokens or runtime secrets; repository security gate remains mandatory. |
| DOD-07 — failures/missing evidence fail-safe | `PASS` | Cleanup uncertainty quarantines; partial/unavailable orphan observations cannot become `CLEAR`; zero-residue proof is emitted only after verification. |
| DOD-08 — rollback / runtime boundary | `PASS with explicit limitation` | No production deployment, no target execution and no real L3/L4 rollback claim. |
| DOD-09 — issue/backlog status reconciliation | `PENDING UNTIL MERGE` | After exact-SHA post-merge GREEN, issue #81 may be reconciled to `status:completed` and closed as completed. |
| DOD-10 — no false FINAL claim | `PASS` | EPIC-04/08 remain `IMPLEMENTING / AS_BUILT=no / FINAL=no`; production adapters and advanced recovery remain non-final. |

## 7. Finality assessment

Therefore:

- `SVP2-B-03`: **candidate for `completed`**;
- `EPIC-04`: **`IMPLEMENTING / AS_BUILT=no / FINAL=no`**;
- `EPIC-08`: **`IMPLEMENTING / AS_BUILT=no / FINAL=no`**;
- controlled Docker network/volume lifecycle: **`PASS_CONTROLLED_CI`**;
- cleanup fail-closed quarantine: **`PASS_CONTROLLED_CI`**;
- zero-residue observation: **`PASS_CONTROLLED_CI`**;
- periodic orphan detection: **`PASS_CONTROLLED_CI`**;
- production Docker lifecycle/scanner: **`NOT_RUN`**;
- orphan remediation: **`NOT_IMPLEMENTED / NOT_RUN`**;
- real L3/L4 snapshot/rollback: **`NOT_RUN`**;
- customer/production runtime: **`NO_RUNTIME_CHANGE`**.

## 8. Decision record

| Field | Value |
| --- | --- |
| Decision | Complete `SVP2-B-03` at the controlled Docker CI delivery boundary without promoting EPIC-04/08 to finality. |
| Context | All three backlog acceptance criteria now have executable evidence using owned disposable network/volume resources and fail-closed lifecycle semantics. |
| Alternative considered | Keep B-03 implementing until a production Docker/Kubernetes lifecycle service exists. |
| Reason rejected | That would conflate the declared umbrella acceptance criteria with broader concept/runtime finality; DOD-10 preserves the distinction. |
| Accepted risk | Production adapters, real containers, race conditions, firewall enforcement or recovery operations may expose defects not observable in the controlled network/volume harness. |
| Mitigation | Keep EPIC-04/08 non-FINAL and require separate deployment/runtime evidence before any production readiness claim. |
| State | `Em validação` until completion PR and post-merge gates are GREEN. |
| Next action | Reconcile issue #81 only after exact integrated SHA passes both canonical gates. |
