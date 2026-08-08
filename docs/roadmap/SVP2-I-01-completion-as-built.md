# SVP2-I-01 — Completion / AS_BUILT Evidence Record

## 1. Decision

`SVP2-I-01 — Lab Schema v2 families isolation and deterministic reset` is eligible for delivery status **`completed`** at the repository / controlled-Docker-CI boundary, subject to its own lifecycle reconciliation and exact-head/post-merge gates.

This delivery-level completion does not claim that every historical laboratory has been migrated to Lab Schema v2, nor that Kubernetes, VM, cloud, identity, mobile or external-hardware laboratories have been activated.

## 2. Completion boundary

The declared acceptance criteria are now directly supported by contract and controlled runtime evidence:

1. Lab Schema v2 fixes isolation to `privileged=false`, `host_network=false`, `docker_socket=false`, `host_mounts=false`; generated/untrusted labs require isolated build;
2. every conforming family manifest must define exactly `VULNERABLE`, `MITIGATED` and `FIXED`, each with both positive and negative controls;
3. deterministic reset identity is content-derived from family/variant/reset seed and is independently attested across repeated observations;
4. controlled filesystem reset evidence mutates state between runs and proves convergence to the same canonical post-reset digest;
5. controlled Docker CI evidence creates a disposable internal network/owned volume, runs a non-root read-only-rootfs fixture with all capabilities dropped, deliberately mutates state, destroys/recreates the fixture and proves the repeated post-reset attestation is identical;
6. the dedicated Docker gate verifies zero residue for owned network/volume resources and cannot pass through a skip path.

Outside this completion claim:

- migration/compliance attestation for every existing historical lab family;
- production container lab runtime;
- Kubernetes/VM/identity/cloud/mobile/IoT-OT lab activation;
- external hardware interaction;
- production Lab Registry selection/placement service;
- production reset scheduler or repair/remediation service;
- customer assets or production infrastructure.

## 3. Acceptance criteria disposition

| Acceptance criterion | Disposition | Evidence |
| --- | --- | --- |
| No laboratory runs with privileged, host network or Docker socket | `MET` for the Lab Schema v2 contract and controlled Docker candidate | `validate_isolation()` and schema tests fail closed on privileged/host-network/socket/mount state. PR #253 exercises a real disposable Docker fixture with `privileged=false`, `host_network=false`, no Docker socket or host mounts, read-only rootfs, `cap-drop=ALL`, `no-new-privileges` and UID 10001. |
| Each family supports the three states and positive/negative controls | `MET` at the Lab Schema v2 family-contract boundary | Manifest construction/schema require exactly `VULNERABLE`, `MITIGATED`, `FIXED`; each state requires non-empty positive and negative controls. This does not claim all legacy labs have been migrated. |
| Reset produces an identical verifiable state between executions | `MET` at controlled-local and controlled-Docker-CI boundaries | PR #237 defines deterministic reset attestation; PR #248 proves repeated filesystem reset convergence after deliberate drift; PR #253 performs destructive Docker reset/recreation and requires identical post-reset attestation plus zero residue. |

## 4. Deliverables disposition

| Deliverable | Result | Canonical implementation |
| --- | --- | --- |
| Lab Schema v2 and Lab Registry specification | `MET` | `platform/lab-registry-v2/lab-manifest.schema.json`, `lab_registry.py`, README and selection/isolation tests. |
| Isolation and laboratory-maturity policy | `MET` | `platform/lab-registry-v2/lab-policy.yaml`, schema constraints and controlled Docker evidence workflow. |

## 5. Key evidence

- Initial I-01 contract implementation defines the Lab Schema v2 family/state/isolation/selection model and fail-closed policy constraints.
- PR #237 — deterministic reset attestation; head `854791ab67986595535bc73eeb96e5eb35d87402`; merge `3b802f1e9af1140c5f295eb94a885582d3b784c8`.
- PR #248 — controlled filesystem reset convergence evidence; head `797b6210560b48d9b1eaad296d8566d5666957f5`; merge `cb2bf746943644cca0d20e99bdede3b109c77e49`.
- PR #253 — mandatory controlled Docker reset/zero-residue evidence; head `a2edb6f05b181619e8875ad9d23e1ae25312bb09`; merge `ffc89b5d8e57292b7bc321b4c9fdf1b495a3918f`.
- PR #253 post-merge security `31281724007`: PASS; validate `31281724018`: PASS; dedicated `svp2-i01-controlled-docker-reset` `31281724017`: PASS.
- The eventual I-01 completion PR must independently pass exact-head and exact-SHA post-merge canonical gates on the then-current `main`.

## 6. Definition of Done assessment

| DoD | Result | Evidence / limitation |
| --- | --- | --- |
| DOD-01 — declared deliverables merged | `PASS` | Lab Schema/Registry and isolation/maturity policy are in `main`. |
| DOD-02 — final-head repository/security gates | `PASS after completion validation` | Completion requires exact-head `security` + `validate` PASS. |
| DOD-03 — post-merge validation on main | `PASS after completion merge` | Exact integrated SHA must pass both canonical gates. |
| DOD-04 — positive/negative/adversarial/regression testing | `PASS` | Isolation violations, missing states/controls, divergent reset state, sensitive snapshot fields, controlled drift, Docker mutation/recreation and residue are covered. |
| DOD-05 — canonical documentation | `PASS after lifecycle reconciliation` | Backlog/guard status will be reconciled only after H-01 shared-file completion is integrated. |
| DOD-06 — no committed secrets | `PASS` | Controlled fixtures use no customer secrets or credentials; security gate remains mandatory. |
| DOD-07 — failures/missing evidence fail-safe | `PASS` | Isolation violations fail validation; divergent reset cannot attest deterministic convergence; Docker workflow fails if reset/residue checks fail. |
| DOD-08 — rollback/runtime boundary | `PASS with explicit limitation` | Only disposable controlled CI resources are used; production lab runtimes and external domains remain `NOT_RUN`. |
| DOD-09 — issue/backlog reconciliation | `PENDING` | Issue #92 is reconciled only after its completion PR and post-merge gates are GREEN. |
| DOD-10 — no false production/domain claim | `PASS` | Completion does not activate or certify production/Kubernetes/VM/cloud/identity/mobile/IoT-OT/hardware labs or claim migration of all legacy labs. |

## 7. Finality assessment

Therefore:

- `SVP2-I-01`: **candidate for `completed`**;
- Lab Schema v2 isolation contract: **`PASS`**;
- three-state + positive/negative control family contract: **`PASS`**;
- deterministic reset attestation: **`PASS_CONTROLLED_CI`**;
- controlled Docker reset/recreation: **`PASS_CONTROLLED_CI`**;
- controlled zero-residue verification: **`PASS_CONTROLLED_CI`**;
- migration of every legacy lab: **`NOT_CLAIMED`**;
- production container/Kubernetes/VM/cloud/mobile/identity/IoT-OT/hardware labs: **`NOT_RUN`**;
- production lab orchestration/remediation: **`NOT_RUN`**.

## 8. Decision record

| Field | Value |
| --- | --- |
| Decision | Prepare `SVP2-I-01` for delivery completion at the Lab Schema v2 / controlled-Docker-CI boundary. |
| Context | All three backlog acceptance criteria have direct schema/tests and controlled reset evidence, including a mandatory real-Docker gate. |
| Alternative considered | Keep I-01 implementing until every historical lab and every runtime family is migrated/activated. |
| Reason rejected | That would conflate the declared Lab Schema v2 delivery acceptance criteria with broader migration and domain-runtime finality. |
| Accepted risk | Legacy lab migration, real service/container behavior and additional runtime drivers may reveal compatibility issues outside the controlled fixture. |
| Mitigation | Keep legacy migration and all production/domain activations outside the completion claim; require separate runtime/domain gates. |
| State | `Em validação` pending H-01 shared-file reconciliation and I-01 completion gates. |
| Next action | After H-01 closes, synchronize this record to current `main`, apply only I-01 backlog/guard reconciliation, run exact-head gates, merge on PASS, then close #92 after post-merge GREEN. |
