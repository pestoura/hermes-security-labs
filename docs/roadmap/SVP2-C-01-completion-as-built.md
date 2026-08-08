# SVP2-C-01 — Completion / AS_BUILT Evidence Record

## 1. Decision

`SVP2-C-01 — Minimal non-root runtime base and persistent runner layout` is eligible for delivery status **`completed`** at the controlled core-runtime candidate boundary.

This completion applies to the **delivery umbrella `SVP2-C-01` only**. `EPIC-06 — Kali Image Factory` remains **`IMPLEMENTING` / `AS_BUILT=no` / `FINAL=no`** because image publication, SBOM generation, signing/provenance, promotion/retirement, browser/heavy-tool production layers and Hermes deployment are broader factory/finality concerns and remain `NOT_RUN`.

Those supply-chain and registry controls are primarily owned by `SVP2-C-02`; they are not additional acceptance criteria of C-01.

## 2. Completion boundary

The delivery has repository-backed and CI-executed evidence for:

1. minimal non-root core runtime policy;
2. fixed non-root UID/GID in the controlled candidate;
3. persistent immutable runner layout under `/opt/hermes/runners`;
4. explicit bounded writable state paths;
5. read-only root filesystem;
6. default drop of Linux capabilities;
7. `NoNewPrivs` enforcement;
8. raw socket denial in the core profile;
9. ordinary TCP socket availability for TCP-connect semantics;
10. explicit `raw-network` profile with both `requires_explicit_profile=true` and `requires_justification=true` for `NET_RAW`;
11. prohibition of privileged mode, Docker socket and host mounts;
12. actual Docker image build and container observation in canonical CI.

Outside the completion claim:

- image publication to a registry;
- SBOM, signing or build provenance;
- image promotion/retirement and revocation;
- browser/heavy-tool production layers;
- Hermes deployment or client connectivity;
- security-tool execution;
- production/runtime readiness beyond the controlled CI candidate.

## 3. Acceptance criteria disposition

| Acceptance criterion | Disposition | Evidence |
| --- | --- | --- |
| Nenhum perfil core corre como root | `MET` | Policy forbids UID 0 and PR #215 builds/starts the core candidate as `10001:10001`, with runtime assertion of UID/GID 10001. |
| Capacidades de rede elevadas exigem perfil explícito e justificação | `MET` | Core drops all capabilities; `NET_RAW` is available only in the `raw-network` policy profile, which requires explicit selection and justification. Controlled core runtime observes zero effective capabilities and raw-socket denial. |

## 4. Deliverables disposition

| Deliverable | Result | Canonical implementation |
| --- | --- | --- |
| Especificação da base runtime e do layout de runners | `MET` | `platform/runtime-base/runtime-base-policy.yaml`, `runtime_policy.py`, candidate Dockerfile/probe/harness and README. |
| Política de capacidades de rede por perfil | `MET` | Core `-sT`/TCP-connect semantics, drop-all default, explicit justified `raw-network` profile, privileged=false. |

## 5. Key evidence

- PR #142 — repository-owned runtime-base contract and policy candidate.
- PR #215 — controlled candidate build/runtime observation; validated head `2559a5644809e7e849007c92fa2439bf2bf5fc18`.
  - pre-merge security `31264264119`: PASS;
  - pre-merge validate `31264264113`: PASS;
  - squash merge `75208c271e9e2a2caa836e4c4a9385d290ff2e07`;
  - post-merge security `31264361798`: PASS;
  - post-merge validate `31264361702`: PASS.
- PR #216 — lifecycle/source-of-truth reconciliation of the controlled runtime evidence; merged as `b4257e8e...` with post-merge GREEN gates.

No target, network connection, scanner, pentest operation, credential, client environment or deployed Hermes runtime was involved.

## 6. Definition of Done assessment

| DoD | Result | Evidence / limitation |
| --- | --- | --- |
| DOD-01 | `PASS` | Both declared C-01 deliverables are merged into main. |
| DOD-02 | `PASS` | #215 exact final-head `security` and `validate` PASS. |
| DOD-03 | `PASS after completion merge` | #215/#216 post-merge gates are GREEN; completion remains valid only after its own post-merge gates pass. |
| DOD-04 | `PASS` | Policy validation plus actual Docker build/start/runtime observations cover positive and negative capability/filesystem/runtime cases. |
| DOD-05 | `PASS with explicit reconciliation` | EPIC-06 and this completion record separate C-01 delivery completion from broader Image Factory finality. |
| DOD-06 | `PASS` | Canonical security gate GREEN; no secrets or credentials used. |
| DOD-07 | `PASS` | Runtime harness uses assertions and fails the canonical `validate` gate on root/writable-root/capability/raw-socket regressions. |
| DOD-08 | `PASS` | Candidate exists only in controlled CI and is removed by test cleanup; deployed runtime remains `NO_DEPLOYED_RUNTIME_CHANGE`. |
| DOD-09 | `PENDING UNTIL MERGE` | Completion PR must reconcile backlog and issue #82 after post-merge GREEN. |
| DOD-10 | `PASS` | EPIC-06 remains non-final while publication/SBOM/signing/provenance/promotion/Hermes deployment remain `NOT_RUN`. |

## 7. Finality assessment

- `SVP2-C-01`: **candidate for `completed`**;
- `EPIC-06`: **`IMPLEMENTING` / `AS_BUILT=no` / `FINAL=no`**;
- controlled core image build: **`PASS_CONTROLLED_CI`**;
- controlled container start: **`PASS_CONTROLLED_CI`**;
- non-root observation: **`PASS_CONTROLLED_CI`**;
- read-only root observation: **`PASS_CONTROLLED_CI`**;
- capability-drop observation: **`PASS_CONTROLLED_CI`**;
- image publication: **`NOT_RUN`**;
- SBOM/signing/provenance: **`NOT_RUN`**;
- promotion/retirement: **`NOT_RUN`**;
- Hermes deployment: **`NOT_RUN`**;
- deployed runtime change: **`NO_DEPLOYED_RUNTIME_CHANGE`**.

## 8. Decision record

| Field | Value |
| --- | --- |
| Decision | Complete delivery umbrella `SVP2-C-01` without promoting EPIC-06 to `FINAL`. |
| Context | The two declared C-01 acceptance criteria and both deliverables are demonstrated by policy plus an actually built/started candidate in canonical CI. |
| Alternatives considered | Keep C-01 implementing until image supply-chain publication is complete. |
| Justification | Publication, SBOM/signing/provenance and promotion are broader Image Factory/C-02 concerns and are not C-01 acceptance criteria. |
| Risks accepted | The controlled candidate does not prove registry or Hermes deployment behaviour. |
| Impact | C-01 delivery can close while C-02 and EPIC-06 finality remain open. |
| State | `Em validação` until completion PR + post-merge gates are GREEN; then `Decisão`. |
| Next action | Reconcile #82 and continue C-02/P0 backlog. |
