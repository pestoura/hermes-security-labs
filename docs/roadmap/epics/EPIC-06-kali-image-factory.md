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
| Document version | 1.1.0 |
| Document date | 2026-08-07 |
| Catalogue | [Epic catalogue 45](../epic-catalogue-45.md) |
| Lifecycle contract | [Architecture documentation lifecycle](../../architecture/architecture-documentation-lifecycle.md) |

## 2. Current status

**IMPLEMENTING** — PR #142 integrated the repository-owned minimal non-root runtime policy candidate. The contract defines the core non-root/read-only/capability/layout invariants, but no execution image has been built, started, promoted or observed against a real runtime.

| Lifecycle state | Reached |
| --- | --- |
| INTENT | yes |
| IMPLEMENTING | yes |
| AS_BUILT | no |
| FINAL | no |

## 3. Problem and motivation

Execution images built ad hoc increase attack surface, weaken provenance and make runtime behaviour hard to reproduce. The repository therefore needs an explicit minimal base contract before image build and promotion are activated.

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
- Future digest pinning, build provenance and promotion lifecycle

### Non-goals

- Publishing new public packages in this block
- Adding offensive tooling to the base image
- Starting containers or deploying Hermes runtimes
- Claiming runtime observations that have not been executed

## 6. Intent architecture

The base runtime is a small core layer with immutable runner code and explicit writable state. Capability-heavy or browser tooling belongs in dedicated layers/profiles. Elevated Linux capabilities are not inherited by the core profile.

```mermaid
flowchart LR
  POLICY[Repository runtime policy]
  CORE[Minimal core image]
  LAYER[Dedicated capability layers]
  RUNNER[/opt/hermes/runners immutable]
  STATE[Explicit writable state]
  RUNTIME[Future runtime observation]

  POLICY --> CORE
  POLICY --> LAYER
  CORE --> RUNNER
  CORE --> STATE
  CORE -. build/start NOT_RUN .-> RUNTIME
```

## 7. Contracts, data and capabilities

Canonical repository components currently include:

- `platform/runtime-base/runtime-policy.schema.json`;
- `platform/runtime-base/runtime-policy.yaml`;
- `platform/runtime-base/runtime_policy.py`;
- `platform/runtime-base/README.md`;
- regression tests under `platform/tests/`.

The current contract requires non-root UID, read-only root filesystem, immutable `/opt/hermes/runners`, bounded writable paths, no host mounts or Docker socket, capabilities dropped by default, no privileged runtime, `nmap -sT` by default and explicit justification for `NET_RAW`.

## 8. Dependencies and sequencing

- [EPIC-03 — Typed Kali MCP](EPIC-03-typed-kali-mcp.md)

The repository-level policy can be validated before any image is built. Actual image build/promotion must follow the supply-chain and capability-registry controls owned by C-02.

## 9. Security, risks and failure modes

- Image bloat re-introducing unaudited tooling
- Pinning drift between manifest and registry
- Tools silently assuming root or raw sockets
- Writable paths expanding beyond declared state
- Privileged/capability exceptions becoming the default path
- Treating a policy candidate as runtime evidence

Platform-wide invariants that this epic must not weaken:

- absence of evidence never produces a `PASS` verdict;
- no execution outside an active authorization contract;
- no secrets, tokens, cookies or raw credential material in documentation, telemetry or persisted evidence;
- no target outside registered laboratories;
- elevated network capabilities require an explicit profile and justification.

## 10. Deliverables

Repository-level candidate delivered:

- minimal non-root runtime policy and validator;
- persistent runner-layout contract;
- capability/network-profile restrictions;
- fail-closed regression coverage.

Still pending:

- concrete reproducible image build;
- digest/provenance/SBOM/signing evidence;
- runtime non-root/read-only/capability observations;
- promotion/retirement execution;
- Hermes runtime deployment.

## 11. Acceptance criteria

Repository-level criteria currently demonstrated:

- core policy cannot declare root execution;
- privileged mode and Docker socket/host mounts are forbidden;
- elevated capabilities are absent from the default core profile;
- `NET_RAW` requires an explicit justified profile;
- core scanning semantics default to TCP connect / `nmap -sT`.

Umbrella completion still requires operational evidence that:

- no core execution image runs as root;
- the selected image actually has a read-only root filesystem and expected capability drop;
- every accepted image has immutable digest and provenance evidence;
- promotion/retirement controls are exercised against built artefacts.

## 12. Evidence and validation plan

Current evidence is repository/CI only:

- PR #142 runtime-base contract implementation;
- runtime-policy regression tests;
- full repository `security` and `validate` gates.

Runtime/image evidence remains `NOT_RUN` and must be recorded in issue #82 before the umbrella can close.

## 13. Decisions and open questions

### Decisions

- Core runtimes are non-root and read-only by contract.
- Runner code is immutable under `/opt/hermes/runners`.
- Writable state is explicit and bounded.
- Core Linux capabilities are dropped by default.
- `nmap -sT` is the default network scanning mode; `NET_RAW` is exceptional and profile-bound.
- Browser and heavy-tool layers stay separate from the core base.

### Open questions

- Cadence for rebuilding to absorb upstream security updates
- Concrete base image/distribution and pinning strategy
- Build system and registry used for the first reproducible candidate
- Operational promotion evidence required jointly with C-02

## 14. Implementation notes

> Reserved lifecycle section. It is populated progressively while the epic is `IMPLEMENTING`; retaining the `Reserved` marker is required by the architecture documentation lifecycle contract.

- PR #142 introduced the minimal non-root runtime contract and validator.
- Issue #82 and master tracker #97 already classify the delivery umbrella as `implementing`.
- This reconciliation removes the stale `INTENT / not started` claim without promoting runtime state.

## 15. As-built / final architecture

> Reserved lifecycle section. This section records the current implementation boundary but remains non-final until deployed/runtime evidence satisfies the umbrella acceptance criteria.

Current factual boundary:

- runtime-base policy/schema/validator: `CANDIDATE`;
- non-root policy requirement: repository validated;
- read-only root requirement: repository validated;
- default capability drop / explicit `NET_RAW` profile: repository validated;
- immutable runner layout: repository validated;
- image build/publication: `NOT_RUN`;
- container start: `NOT_RUN`;
- real non-root observation: `NOT_RUN`;
- real read-only-root observation: `NOT_RUN`;
- real capability-drop observation: `NOT_RUN`;
- digest/provenance/SBOM/signing promotion: `NOT_RUN`;
- Hermes deployment: `NOT_RUN`;
- runtime changes: `NO_RUNTIME_CHANGE`.

`AS_BUILT` and `FINAL` remain false.

## 16. Document change log

| Date | Version | Change |
| --- | --- | --- |
| 2026-08-06 | 1.0.0 | Initial intent document created from the concept epic catalogue. |
| 2026-08-07 | 1.1.0 | Reconciled EPIC-06 to `IMPLEMENTING` after PR #142 while preserving all image/runtime observations as `NOT_RUN`. |
