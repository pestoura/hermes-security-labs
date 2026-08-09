# EPIC-06 — Kali Image Factory

## 1. Metadata

| Field | Value |
| --- | --- |
| Concept epic ID | `EPIC-06` |
| Slug | `kali-image-factory` |
| Pillar | `C` — Image and Capability Factory |
| Phase | 3 |
| Priority | P1 |
| Delivery umbrella | `SVP2-C-01` (issue [#82](https://github.com/pestoura/hermes-security-labs/issues/82)) |
| Document version | 1.2.0 |
| Document date | 2026-08-08 |
| Catalogue | [Epic catalogue 45](../epic-catalogue-45.md) |
| Lifecycle contract | [Architecture documentation lifecycle](../../architecture/architecture-documentation-lifecycle.md) |

## 2. Current status

**IMPLEMENTING** — PR #142 integrated the repository-owned minimal non-root runtime policy candidate. PR #215 subsequently added the first controlled disposable image build and runtime observation harness in CI. The candidate is built from a base image pinned by digest and is actually started with a read-only root filesystem, non-root UID/GID, all Linux capabilities dropped, `no-new-privileges`, no network and bounded resources. Production image publication, supply-chain attestations, promotion/retirement and Hermes deployment remain `NOT_RUN`.

| Lifecycle state | Reached |
| --- | --- |
| INTENT | yes |
| IMPLEMENTING | yes |
| AS_BUILT | no |
| FINAL | no |

## 3. Problem and motivation

Execution images built ad hoc increase attack surface, weaken provenance and make runtime behaviour hard to reproduce. The repository therefore needs an explicit minimal base contract and controlled runtime evidence before image publication and promotion can be activated.

## 4. Intended outcome

A factory that produces minimal, non-root, pinned and attested execution images with a defined promotion lifecycle, while keeping browser/heavy-tool layers separated from the core runtime.

## 5. Scope and non-goals

### In scope

- Minimal non-root runtime policy
- Read-only root filesystem requirement
- Immutable runner code under `/opt/hermes/runners`
- Explicit bounded writable state paths
- Default capability drop and explicit elevated capability profiles
- TCP-connect / `nmap -sT` core network semantics
- Separation of browser and heavy-tool layers
- Controlled disposable core candidate build and runtime observation in CI
- Future digest publication, build provenance and promotion lifecycle

### Non-goals for the current controlled candidate

- Publishing an execution image to a registry
- Adding offensive/security tooling to the base image
- Connecting the candidate to Hermes or customer environments
- Establishing network connectivity or target access
- Claiming SBOM, signing, provenance or promotion evidence that has not been produced

## 6. Intent architecture

The base runtime is a small core layer with immutable runner code and explicit writable state. Capability-heavy or browser tooling belongs in dedicated layers/profiles. Elevated Linux capabilities are not inherited by the core profile.

```mermaid
flowchart LR
  POLICY[Repository runtime policy]
  CORE[Controlled minimal core candidate]
  LAYER[Dedicated capability layers]
  RUNNER[/opt/hermes/runners immutable]
  STATE[Explicit writable state]
  CI[Controlled CI observation]
  PROMOTE[Future supply-chain promotion]

  POLICY --> CORE
  POLICY --> LAYER
  CORE --> RUNNER
  CORE --> STATE
  CORE --> CI
  CI -. no automatic promotion .-> PROMOTE
```

## 7. Contracts, data and capabilities

Canonical repository components include:

- `platform/runtime-base/runtime-base-policy.yaml`;
- `platform/runtime-base/runtime_policy.py`;
- `platform/runtime-base/README.md`;
- `platform/runtime-base/candidate/Dockerfile`;
- `platform/runtime-base/candidate/runtime_probe.py`;
- `platform/runtime-base/candidate/validate_candidate_runtime.sh`;
- regression and runtime acceptance tests under `platform/tests/`.

The contract requires non-root UID, read-only root filesystem, immutable `/opt/hermes/runners`, bounded writable paths, no host mounts or Docker socket, capabilities dropped by default, no privileged runtime, `nmap -sT` by default and explicit justification for `NET_RAW`.

The controlled candidate additionally observes the effective runtime identity, filesystem write boundary, effective Linux capabilities, `NoNewPrivs`, raw-socket denial and ordinary TCP socket availability. It runs with `--network none`; socket creation is not a network connection or target interaction.

## 8. Dependencies and sequencing

- [EPIC-03 — Typed Kali MCP](EPIC-03-typed-kali-mcp.md)

The runtime-base contract and controlled candidate can be validated before publication. SBOM, signing, provenance, registry promotion/revocation and accepted-image supply-chain lifecycle remain owned by C-02 and related concept epics; C-01 evidence must not be treated as those controls.

## 9. Security, risks and failure modes

- Image bloat re-introducing unaudited tooling
- Pinning drift between manifest and registry
- Tools silently assuming root or raw sockets
- Writable paths expanding beyond declared state
- Privileged/capability exceptions becoming the default path
- Treating controlled CI evidence as production deployment evidence
- Treating a pinned base-image digest as provenance for the built candidate

Platform-wide invariants that this epic must not weaken:

- absence of evidence never produces a `PASS` verdict;
- no execution outside an active authorization contract;
- no secrets, tokens, cookies or raw credential material in documentation, telemetry or persisted evidence;
- no target outside registered laboratories;
- elevated network capabilities require an explicit profile and justification;
- controlled CI candidate evidence never authorizes publication or deployment.

## 10. Deliverables

Repository/runtime candidate delivered:

- minimal non-root runtime policy and validator;
- persistent runner-layout contract;
- capability/network-profile restrictions;
- fail-closed regression coverage;
- reproducible Dockerfile candidate with pinned base digest;
- controlled CI build/start/observation harness;
- observed non-root, read-only-root and zero-effective-capability core runtime boundary.

Still pending for the broader concept epic:

- published immutable image digest;
- SBOM/signing/provenance evidence for the produced image;
- registry promotion/retirement execution;
- browser/heavy-tool production layers;
- Hermes runtime deployment and operational observation.

## 11. Acceptance criteria

Repository-level and controlled-runtime criteria now demonstrated:

- core policy cannot declare root execution;
- controlled core candidate actually runs as UID/GID `10001:10001`;
- controlled candidate root filesystem and runner code root are not writable;
- declared state paths remain writable through bounded tmpfs mounts;
- effective Linux capabilities are zero in the controlled core candidate;
- raw sockets are unavailable;
- `NET_RAW` remains available only through an explicit, justified policy profile;
- privileged mode and Docker socket/host mounts are forbidden;
- core scanning semantics remain TCP connect / `nmap -sT` by policy.

Broader concept completion / `FINAL` still requires evidence that:

- accepted/published images have immutable digest and complete provenance/SBOM/signing evidence;
- promotion/retirement controls are exercised against built artefacts;
- production/Hermes runtime instances preserve the declared boundary;
- additional runtime layers do not weaken the core invariants.

## 12. Evidence and validation plan

Current evidence:

- PR #142 — runtime-base contract implementation;
- PR #168 — lifecycle reconciliation of the contract candidate;
- PR #215 — controlled non-root runtime-base candidate;
- PR #215 validated head `2559a5644809e7e849007c92fa2439bf2bf5fc18`;
- PR #215 `security` run `31264264119`: success;
- PR #215 `validate` run `31264264113`: success, including the Docker candidate build/start/runtime probe;
- PR #215 squash merge `75208c271e9e2a2caa836e4c4a9385d290ff2e07`;
- post-merge `security` run `31264361798`: success;
- post-merge `validate` run `31264361702`: success, including repeated controlled runtime observation on the integrated SHA.

Observed controlled-CI state:

- image build: `PASS_CONTROLLED_CI`;
- container start: `PASS_CONTROLLED_CI`;
- non-root observation: `PASS_CONTROLLED_CI`;
- read-only root observation: `PASS_CONTROLLED_CI`;
- capability-drop observation: `PASS_CONTROLLED_CI`;
- image publication: `NOT_RUN`;
- SBOM/signing/provenance promotion: `NOT_RUN`;
- Hermes deployment: `NOT_RUN`.

## 13. Decisions and open questions

### Decisions

- Core runtimes are non-root and read-only by contract.
- Runner code is immutable under `/opt/hermes/runners`.
- Writable state is explicit and bounded.
- Core Linux capabilities are dropped by default.
- `nmap -sT` is the default network scanning mode; `NET_RAW` is exceptional and profile-bound.
- Browser and heavy-tool layers stay separate from the core base.
- The first runtime candidate is disposable, has `--network none`, and exists only to observe the security boundary in CI.
- A successful controlled candidate does not automatically become a publishable or promoted runtime image.

### Open questions

- Cadence for rebuilding to absorb upstream security updates
- Final production base image/distribution and pinning strategy
- Registry publication policy and immutable candidate digest recording
- Operational promotion evidence jointly owned with C-02

## 14. Implementation notes

> Reserved lifecycle section. It is populated progressively while the epic is `IMPLEMENTING`; retaining the `Reserved` marker is required by the architecture documentation lifecycle contract.

- PR #142 introduced the minimal non-root runtime contract and validator.
- PR #168 reconciled the original contract-only implementation state.
- PR #215 added a fixed controlled runtime candidate and permanent CI acceptance test.
- The candidate executes only its repository-owned observation probe; no security tooling, target, credential or customer environment is involved.
- This lifecycle block changes the evidence declaration only; it does not deploy Hermes or publish an image.

## 15. As-built / final architecture

> Reserved lifecycle section. This section records the current implementation boundary but remains non-final until supply-chain promotion and deployed-runtime evidence satisfy the broader concept criteria.

Current factual boundary:

- runtime-base policy/schema/validator: `IMPLEMENTED`;
- disposable controlled core candidate: `AS_BUILT_CI_CANDIDATE`;
- base image reference: pinned by immutable digest;
- image build: `PASS_CONTROLLED_CI`;
- container start: `PASS_CONTROLLED_CI`;
- non-root UID/GID observation: `PASS_CONTROLLED_CI`;
- read-only-root observation: `PASS_CONTROLLED_CI`;
- runner-root immutability observation: `PASS_CONTROLLED_CI`;
- capability-drop observation: `PASS_CONTROLLED_CI`;
- `NoNewPrivs` observation: `PASS_CONTROLLED_CI`;
- raw-socket denial: `PASS_CONTROLLED_CI`;
- network target execution: `NOT_RUN`;
- security-tool execution: `NOT_RUN`;
- image publication: `NOT_RUN`;
- digest/provenance/SBOM/signing promotion: `NOT_RUN`;
- Hermes deployment: `NOT_RUN`;
- deployed runtime changes: `NO_DEPLOYED_RUNTIME_CHANGE`.

`AS_BUILT` for the complete concept and `FINAL` remain false. The controlled candidate evidence is narrower than publication/promotion readiness.


_Lifecycle unchanged: EPIC-06 is `IMPLEMENTING`; `AS_BUILT` and `FINAL` remain no. The record below states exactly what was merged and where the evidence lives, so that a future promotion decision is not made from memory or by association._
### Exact evidence

| Evidence | Value |
| --- | --- |
| Technical pull request | [#142](https://github.com/pestoura/hermes-security-labs/pull/142) |
| Validated PR head | `c718177d098b0d72fe329637af229a189d4cd892` |
| Integrated `main` merge commit | `c6e672cb8c02ed55e63b521fcad04d5e8e97fdc6` |
| Pre-merge `validate` | success — run `31170174973` |
| Pre-merge `security` | success — run `31170174910` |
| Post-merge `main` `validate` | success — run `31170352666` |
| Post-merge `main` `security` | success — run `31170352690` |

The merge commit is an ancestor of `main`.

### Evidence that is missing for promotion

`AS_BUILT` is withheld because the epic's target state is not satisfied by repository-level contract integration alone:

- image build/publication, runtime non-root/read-only/capability observations, provenance promotion and Hermes deployment: NOT_RUN.

`NO_RUNTIME_CHANGE`.

## 16. Document change log

| Date | Version | Change |
| --- | --- | --- |
| 2026-08-06 | 1.0.0 | Initial intent document created from the concept epic catalogue. |
| 2026-08-07 | 1.1.0 | Reconciled EPIC-06 to `IMPLEMENTING` after PR #142 while preserving all image/runtime observations as `NOT_RUN`. |
| 2026-08-08 | 1.2.0 | Record PR #215 controlled CI image build/start and non-root/read-only/capability observations while preserving publication, supply-chain promotion and Hermes deployment as `NOT_RUN`. |
