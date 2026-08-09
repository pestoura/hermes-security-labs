# Private VAmPI pilot — reconciled current state

Date: 2026-08-09
Tracking issue: `#53`

This document reconciles the current implementation state of the private GHCR VAmPI pilot. It distinguishes controlled CI evidence from real Hermes-host runtime acceptance and does not promote either to production evidence.

## Current decision

```text
PRIVATE_VAMPI_PUBLISHED_PACKAGE_BOUNDARY_CONFIRMED_RUNTIME_ACCEPTANCE_BLOCKED_ON_EXACT_READ_PACKAGES_PAT
```

The private VAmPI package already exists and its accepted OCI index digest is immutable. The remaining implementation boundary is the real Hermes-host acceptance with a PAT classic exposing exactly `read:packages`, followed by the separate versioned Compose migration and final rollback/deployment reconciliation.

## Current repository and package state

Publisher repository:

```text
pestoura/hermes-private-registry-publisher
```

Current publisher visibility:

```text
public
```

This repository visibility is a temporary, owner-authorized implementation exception so GitHub-hosted Actions can remain usable while private-repository Actions are affected by the account billing/spending constraint. It is not evidence that the GHCR package is public and it is not the final state required by issue `#53`.

Final issue closure requires the publisher repository to return to:

```text
private
```

Private package identity:

```text
ghcr.io/pestoura/hermes-private-vampi
```

Accepted private OCI index digest:

```text
sha256:b1b66324a2d35cfe55e3edcd81f9f3c012907c71367df37f83d9ef63b500b3d3
```

Accepted public rollback image:

```text
ghcr.io/pestoura/hermes-vampi@sha256:e7b2760d586ed2b4b15a689823a07816e32308bca293f9e8c08830c7b36c7229
```

Package settings that cannot be enumerated through the current GitHub integration remain owner-confirmed rather than API-verified:

- `hermes-private-vampi` remains `private`;
- `pestoura/hermes-private-registry-publisher` is the intended authorized repository;
- `pestoura/hermes-security-labs` has no package access;
- no additional intentional repository access is present.

The source-repository deny gate independently proves that the `GITHUB_TOKEN` from `pestoura/hermes-security-labs` receives `403 Forbidden` when attempting to consume the private digest.

## Controlled CI evidence

Publisher main accepted SHA:

```text
27399211c11c4571650f7c777bc7dc428ddb7dde
```

Controlled CI evidence at that state:

| Control | State |
|---|---|
| anonymous private-package denial | `PASS` |
| private consumer preflight with publisher `GITHUB_TOKEN` | `PASS` |
| Kali MCP private VAmPI lifecycle parity | `PASS` |
| private → public rollback proof | `PASS` |
| workflow authority auto-audit | `PASS` |

The publisher consumer workflows use only `contents: read` and `packages: read`, do not execute on pull-request-controlled input, and contain no package mutation path.

This evidence is classified as:

```text
CONTROLLED_CI_PREFLIGHT_ONLY
CONTROLLED_CI_ROLLBACK_PROOF_ONLY
```

It is not `HERMES_RUNTIME_ACCEPTED`.

## Gate reconciliation

| Gate | State | Evidence / constraint |
|---|---|---|
| A — documentation/source | `PASS` | private-publisher architecture and public rollback model documented |
| B — private publisher readiness | `PASS_IMPLEMENTATION_STATE` | publisher exists and accepted package was published; repository is temporarily public by explicit owner exception |
| C — package namespace readiness | `PASS_HISTORICAL` | parallel private identity exists without mutating the accepted public package |
| D — private publication | `PASS` | exact accepted OCI index digest recorded |
| E — anonymous denial | `PASS` | controlled publisher CI repeatedly confirms anonymous denial |
| Package repository-access acceptance | `OWNER_CONFIRMED` | granular package settings cannot be enumerated by current integration; source-repo deny independently passes |
| F — authenticated read-only Hermes access | `BLOCKED_CREDENTIAL` | no dedicated PAT classic exposing exactly `read:packages` is present in the Hermes secret store |
| G — read-only authority proof | `BLOCKED_CREDENTIAL` | requires the same exact-scope PAT; proof is non-mutating and based on classic PAT scope introspection |
| H — private-digest lifecycle parity on real Hermes | `BLOCKED_CREDENTIAL` | Docker/Compose/Kali host prerequisites pass; exact private pull still requires the dedicated PAT |
| I — versioned Compose migration | `NOT_RUN` | requires F/G/H PASS first |
| real post-migration acceptance | `NOT_RUN` | requires Compose migration and exact-SHA repository validation |
| real rollback demonstration | `NOT_RUN` | follows accepted private runtime migration |
| final publisher-private boundary | `NOT_RUN` | required before issue closure |

`PASS_HISTORICAL` records a completed predecessor step and is not an instruction to republish.

## Hermes host preflight

A read-only preflight on the real Hermes host confirmed:

- Docker Engine and Docker Compose are available;
- the Kali MCP container is already running and healthy;
- the versioned VAmPI Compose reference still points to the accepted public rollback digest, as expected before migration;
- the private VAmPI image is not already present locally, as expected before authenticated pull;
- no dedicated GHCR PAT classic reference with exactly `read:packages` exists in the checked Hermes/Jarvas secret stores;
- the existing GitHub CLI credential exposes `write:packages` and `delete:packages` and is therefore explicitly unsuitable for Gate F/G;
- a pre-existing global Docker `ghcr.io` auth entry exists but is not an accepted evidence source and must not be allowed to mask the isolated credential test.

The acceptance harness uses an isolated `DOCKER_CONFIG`, reads the dedicated PAT only through stdin, and removes the isolated credential material during cleanup.

## Gate G evidence model

GHCR may return an opaque bearer token. The implementation therefore does not attempt to decode the registry bearer token and does not request `pull,push` authority as a negative-control technique.

For the real Hermes credential, Gate G is fail-closed on the classic PAT metadata exposed by GitHub:

```text
X-OAuth-Scopes = read:packages
```

In `strict` scope mode (the default and the only production-acceptable mode) the set must be exactly `read:packages`; any additional scope causes failure.

An explicit `--scope-mode dev` exists for DEV runs only. It requires an approval reference and package-read authority. GitHub does not list `read:packages` when a broader parent scope is granted, so `write:packages` or `delete:packages` are accepted in DEV as implying read. Additional scopes are tolerated, and the run records:

```text
scope_posture=DEGRADED_ACCEPTED_FOR_DEV
least_privilege_claimed=false
production_closure_blocked_until_read_packages_only=true
```

In DEV mode Gate G asserts only authority sufficiency plus `gate_g_registry_mutation_attempted=false`; it does not assert least privilege. In both modes no upload, tag mutation, manifest PUT, blob upload or delete is performed.

## Current hard blocker

The remaining external blocker is credential provisioning:

```text
PAT classic
scope: read:packages only
```

The token must not be committed, posted to GitHub, copied into issue evidence, supplied in command arguments, stored in Compose, or placed in normal shell history. It must be installed through the approved secret store / isolated stdin flow.

The current broader GitHub CLI credential must not be reused.

## Automatic continuation after credential provisioning

Once the exact-scope PAT exists in the approved secret store, continue without reopening completed decisions:

1. run `deployment/private-ghcr-vampi-acceptance.sh accept` on the real Hermes host using the dedicated credential through stdin;
2. require Gate F exact authenticated private-digest pull `PASS`;
3. require Gate G exact `read:packages` authority proof `PASS` with no registry mutation;
4. require Gate H real VAmPI lifecycle and Kali connectivity `PASS`, clean Git state and zero residue;
5. create a separate, minimal Compose PR changing only VAmPI to the accepted private package/digest plus strictly required deployment metadata;
6. run repository CI and merge only after GREEN/PASS;
7. validate the exact merged `main` SHA;
8. rerun real Hermes post-migration acceptance;
9. demonstrate real rollback to the accepted public digest and restore the accepted private state if it remains the target state;
10. update deployment tracking without recording the credential value;
11. return `pestoura/hermes-private-registry-publisher` to `private`;
12. revalidate publisher/package/source-repository access boundaries;
13. close `#53` only after all runtime, rollback, tracking, credential-cleanup and final-boundary evidence is present;
14. reconcile the final backlog and record `PROJECT DELIVERY COMPLETE` only if no safe technical work remains.

## Security boundary

This reconciliation does not:

- create or reveal a PAT;
- broaden credential scope;
- modify package visibility or permissions;
- republish or retag the package;
- modify versioned Compose;
- claim that controlled CI is real Hermes runtime acceptance;
- claim production deployment.
