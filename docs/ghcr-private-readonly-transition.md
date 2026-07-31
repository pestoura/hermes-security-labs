# GHCR private read-only transition

## Status

This document defines the transition from the accepted public GHCR packages to private package consumption by Hermes.

It is an architecture and operations specification only. It does not create a package, token, repository, organization, workflow run, visibility change or deployment.

Tracking issue: `#53`.
Parent epic: `#34`.
Related deployment tracking: `#7`.

## Decision drivers

The transition must:

- preserve every accepted public runtime digest;
- avoid deleting, replacing or retagging accepted artefacts;
- keep the public source repository canonical;
- prevent private package access from inheriting through the public repository;
- publish through GitHub-hosted Actions only;
- give Hermes download-only registry access;
- keep credentials outside Git and evidence;
- prove anonymous denial and authenticated exact-digest access;
- demonstrate rollback to an accepted public digest;
- migrate one laboratory at a time.

## Accepted public baseline

| Environment | Public package | Accepted OCI index digest |
|---|---|---|
| VAmPI | `ghcr.io/pestoura/hermes-vampi` | `sha256:e7b2760d586ed2b4b15a689823a07816e32308bca293f9e8c08830c7b36c7229` |
| DVAPI | `ghcr.io/pestoura/hermes-dvapi` | `sha256:18d9175aa8031568c95e5bd9dcd9597a0b575aec7a742d81c7f34973c506c872` |
| NodeGoat | `ghcr.io/pestoura/hermes-nodegoat` | `sha256:0e0cbd8b0c82db51b1dfff9c58a391653774fa3b7b4c68ad10e6cda4c173ab6c` |
| PyGoat | `ghcr.io/pestoura/hermes-pygoat` | `sha256:3df04f28225c1b9a7a888edbb724540364c3d88967578fc688d47632272069a9` |
| DVGA | `ghcr.io/pestoura/hermes-dvga` | `sha256:6e5fcb0bca47ac75fc218d2a62858673964d8703341bb6387841a84b7409d2d4` |

These packages remain immutable accepted artefacts, current runtimes until replacement and rollback references throughout the private migration.

The transition must not delete a public package or version, move a tag, overwrite an accepted digest, attempt to return a public package to private visibility or migrate all five runtimes in one operation.

## Confirmed platform constraints

GitHub Container Registry supports granular visibility and access permissions.

A newly published package is private by default. A private package can be made public, but a public package cannot be made private again.

Package visibility and package access are separate. A private package linked before first publication can inherit access from its linked repository. GitHub warns that granting a public repository access to private packages can extend access through forks.

GitHub Packages command-line authentication outside GitHub Actions requires a personal access token classic. Hermes needs only `read:packages` and the token owner must have read access to the package.

A GitHub Actions publisher should use its repository `GITHUB_TOKEN`, not a long-lived personal token.

GitHub currently documents Container registry image storage and bandwidth as free. Actions execution readiness and any applicable account budget remain separate preconditions.

## Audit result — 2026-08-01

The first read-only precondition audit returned:

```text
GHCR_PRIVATE_PRECONDITIONS_NOT_PROVEN
```

Confirmed:

- canonical main was synchronized and clean;
- five public packages remained present and public;
- `hermes-private-vampi` appeared absent;
- existing GHCR publication workflows used GitHub-hosted runners and `GITHUB_TOKEN`;
- no live credential was found in versioned files.

Unproven or unsuitable:

- legacy billing API endpoints returned `404` and did not prove readiness or blockage;
- no isolated Docker credential storage existed;
- the current Hermes GitHub CLI OAuth token exposed broad scopes including `write:packages`, `delete:packages`, `repo` and `workflow`;
- local `labctl` could not run because PyYAML was absent from that host Python environment.

The current OAuth token is not an acceptable Hermes runtime credential and must not be reused for private GHCR pulls.

The missing PyYAML dependency is a local validation-environment limitation. It does not authorize package creation and is not treated as repository drift.

## Corrected architecture

### Public canonical source repository

```text
pestoura/hermes-security-labs
```

This repository remains public and canonical for source, manifests, accepted recipes, Compose definitions, digests and lifecycle policy.

It must not receive inherited, Actions or repository read access to private packages.

### Private publisher repository

Proposed identity:

```text
pestoura/hermes-private-registry-publisher
```

This repository must:

- be private before any package publication;
- contain only reviewed publisher workflows, minimum runbooks and required configuration;
- use GitHub-hosted runners;
- publish with its own `GITHUB_TOKEN`;
- fetch immutable source or recipes from the canonical public repository or approved upstream source;
- generate SBOM and provenance;
- link the package permission boundary only to itself;
- perform no deployment to Hermes.

Repository creation requires separate explicit owner authorization.

### Private pilot package

```text
ghcr.io/pestoura/hermes-private-vampi
```

The package must remain private from first publication and inherit access only from the private publisher repository.

The current public package remains unchanged:

```text
ghcr.io/pestoura/hermes-vampi@sha256:e7b2760d586ed2b4b15a689823a07816e32308bca293f9e8c08830c7b36c7229
```

## Metadata model

The private package uses the private publisher repository as the standard OCI source linkage:

```text
org.opencontainers.image.source=https://github.com/pestoura/hermes-private-registry-publisher
org.opencontainers.image.revision=<publisher-commit>
```

Canonical source traceability is retained through separate labels:

```text
io.hermes.canonical-source=https://github.com/pestoura/hermes-security-labs
io.hermes.canonical-source.revision=<full-source-commit>
io.hermes.build.recipe=<reviewed-recipe-id>
io.hermes.build.dockerfile-sha256=<reviewed-sha256>
```

The workflow records the OCI index, application manifest and attestation manifest separately. Only the OCI index digest is a runtime reference.

## Publisher access model

Minimum workflow permissions:

```yaml
permissions:
  contents: read
  packages: write
```

Publication rules:

- GitHub-hosted runner only;
- private publisher repository only;
- `GITHUB_TOKEN` only;
- explicit `workflow_dispatch` boolean gate;
- immutable source and dependency revisions;
- immutable tags;
- no `latest`, `main`, `master` or `develop` tag;
- SBOM and provenance retained;
- no self-hosted runner or Hermes Docker socket;
- no deployment;
- no PAT stored in Actions secrets for publication;
- no linkage or inherited access from the public source repository.

## Package settings gate

After first publication and before any Hermes login:

- visibility is exactly `private`;
- the package is linked to the private publisher repository;
- inherited access references only the private publisher repository;
- the public source repository has no package Actions, read, write or admin access;
- no unapproved repository, user or team has package access;
- immutable tags and all manifest digests are recorded;
- no troubleshooting step changes the package to public.

Any public visibility result permanently rejects that package identity for the private target state.

## Hermes consumer model

Hermes uses a distinct personal access token classic with only:

```text
read:packages
```

Forbidden scopes:

```text
write:packages
delete:packages
repo
workflow
admin:org
```

The credential must not reuse the existing GitHub CLI OAuth token, a publication token or another operator credential.

## Credential storage

Credential creation, installation, rotation and revocation require explicit owner authorization.

The token must never appear in Git history, Compose, manifests, command-line arguments, process listings, shell tracing, screenshots, evidence, agent memory or issue comments.

Authentication uses standard input and an isolated Docker configuration:

```bash
printf '%s' "${GHCR_READ_TOKEN}" |
  docker --config "${HERMES_GHCR_DOCKER_CONFIG}" \
  login ghcr.io \
  --username pestoura \
  --password-stdin
```

Preferred storage is an approved credential helper or host secret store. A plain Docker `config.json` requires explicit temporary-pilot approval, directory mode `0700`, file mode `0600`, documented expiry and immediate rotation after the test.

Evidence may record the Docker config path, ownership, modes, helper name, token scope names, creation/expiry dates and rotation identifier. It must never record the token, Docker `auth`, Basic/Bearer headers or decoded credential material.

## Precondition gates

### Gate A — documentation and source state

- corrected private-publisher architecture merged;
- public source repository clean and canonical;
- all five accepted public package digests preserved;
- no live secret versioned;
- local validation environment capable of running the canonical manifest validator, or equivalent GitHub CI validation explicitly recorded.

### Gate B — private publisher readiness

Before repository creation:

- owner approves `pestoura/hermes-private-registry-publisher`;
- repository name is available;
- repository will be created private;
- GitHub-hosted Actions usage is not blocked for the account;
- no self-hosted fallback is proposed;
- creation procedure has no source-code or secret migration.

Failure decision:

```text
BLOCKED_PRIVATE_PUBLISHER_ACTIONS
```

### Gate C — package namespace readiness

Before publication:

- `hermes-private-vampi` is absent under the target namespace;
- first publication defaults to private;
- no existing public or private package identity will be overwritten;
- the public VAmPI digest remains available as rollback.

### Gate D — private publication

Publish exactly once through a reviewed workflow in the private publisher repository.

Required result:

- new private package;
- immutable source and publisher tags;
- OCI index, application and attestation digests;
- SBOM and provenance;
- no deployment;
- no mutation of the public package.

Decision:

```text
READY_FOR_PRIVATE_GHCR_ACCESS_VALIDATION
```

### Gate E — anonymous denial

Using a Docker configuration without GHCR credentials:

- metadata inspection by exact private digest fails;
- pull by exact private digest fails;
- the sanitized error proves authentication or authorization denial;
- no fallback to the public package occurs.

### Gate F — authenticated read-only access

Using the isolated read-only Docker configuration:

- login succeeds through standard input;
- exact-digest metadata inspection and pull succeed;
- OCI topology, labels, SBOM and provenance remain valid;
- no mutable tag is consumed.

### Gate G — safe negative control

Do not upload a manifest, blob or tag and do not call a delete endpoint.

Prove absence of write/delete authority by:

1. confirming the PAT classic has `read:packages` and lacks forbidden scopes;
2. requesting registry authorization for a push-capable scope without uploading content and confirming push authority is denied or omitted.

All authorization headers and bearer tokens are redacted before evidence is written.

### Gate H — lifecycle parity

Before any versioned Compose change, use a temporary ignored override with the private OCI index digest and repeat the accepted VAmPI lifecycle:

- start without build;
- health and smoke;
- localhost-only binding;
- hardening;
- temporary Kali DNS, TCP and HTTP access;
- idempotent connect/disconnect;
- stop and restart;
- reset;
- destroy and second destroy;
- no external drift;
- clean working tree.

Decision:

```text
READY_FOR_PRIVATE_VAMPI_COMPOSE_MIGRATION
```

### Gate I — versioned migration

A separate PR may replace only the public VAmPI package identity and digest with the accepted private identity and digest.

The PR must preserve application behavior, ports, healthcheck, resource limits, hardening, network isolation, Kali controls and other package workflows.

Merge requires explicit owner authorization and post-merge Hermes acceptance.

## Billing clarification

Current GitHub documentation states that Container registry image storage and bandwidth are presently free. A `404` from unsupported or obsolete billing endpoints does not prove a GHCR block.

The actionable financial precondition for this pilot is that GitHub-hosted Actions can execute in the proposed private publisher repository without an account-level spending or usage block. Any payment, budget or plan change requires separate explicit authorization.

## Rollback boundary

Rollback is a reviewed Compose change back to:

```text
ghcr.io/pestoura/hermes-vampi@sha256:e7b2760d586ed2b4b15a689823a07816e32308bca293f9e8c08830c7b36c7229
```

Rollback uses the exact digest, preserves lifecycle controls, runs complete post-change acceptance, updates deployment tracking and leaves the private package untouched for diagnosis.

## Deployment tracking integration

Issue `#7` must distinguish:

- public canonical source repository and commit;
- private publisher repository and commit;
- package visibility;
- package identity;
- OCI index, application and attestation digests;
- local image ID and architecture;
- effective Compose hash;
- authentication mode;
- credential rotation identifier without secret material;
- SBOM/provenance verification;
- rollback digest.

Drift exists when the running package identity or digest differs from the accepted Git state.

## Evidence requirements

Use ignored directories under `.runtime/evidence/`.

Allowed evidence includes package identities, digests, sanitized status/errors, workflow IDs, OCI metadata, token scope names without values, file modes, lifecycle results and drift comparisons.

Forbidden evidence includes token values, authorization headers, Docker `auth`, cookies, private keys, unredacted environment dumps and shell history containing credentials.

## Implementation sequence

1. merge the private-publisher correction through an authorized PR;
2. verify Actions readiness for a private repository;
3. explicitly authorize creation of the private publisher repository;
4. create it as private with minimal contents;
5. prepare and review the VAmPI private publication workflow there;
6. explicitly authorize first publication;
7. publish once and verify private package settings;
8. explicitly authorize and provision the `read:packages` credential;
9. run anonymous-deny, authenticated-read and negative-control gates;
10. validate the private digest through a temporary override;
11. open a separate private-runtime migration PR;
12. obtain explicit merge authorization;
13. run post-merge acceptance;
14. demonstrate rollback to the public digest;
15. update deployment tracking and drift detection;
16. decide whether remaining packages stay in the personal namespace or move to an organization.

## Completion criteria

Issue `#53` can close only when:

- the private publisher boundary is implemented;
- the private package is published without granting access to the public repository;
- anonymous access is denied;
- authenticated exact-digest pull succeeds using a `read:packages`-only credential;
- absence of write/delete authority is proven safely;
- VAmPI lifecycle passes from the private digest;
- a separate Compose migration is merged and accepted;
- rollback to the accepted public digest is demonstrated;
- deployment tracking records source, publisher, package, digest and authentication mode;
- final Git, Docker and credential state is clean.

Until then, the five accepted public packages remain canonical runtimes.