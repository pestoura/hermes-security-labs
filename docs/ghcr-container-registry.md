# GitHub Container Registry operating model

## Purpose

GitHub Container Registry (GHCR) is the canonical registry for container images built or adapted by `pestoura/hermes-security-labs`.

The public repository remains the source of truth for source code, Compose files, manifests, accepted digests and operating documentation. GHCR stores the resulting Docker/OCI artefacts. Hermes pulls accepted images and runs them locally; GitHub never deploys directly to Hermes.

## Operational status

The initial five project-built image rollouts are complete and accepted by immutable public GHCR digest:

| Environment | Package |
|---|---|
| VAmPI | `ghcr.io/pestoura/hermes-vampi` |
| DVAPI | `ghcr.io/pestoura/hermes-dvapi` |
| OWASP NodeGoat | `ghcr.io/pestoura/hermes-nodegoat` |
| PyGoat | `ghcr.io/pestoura/hermes-pygoat` |
| Damn Vulnerable GraphQL Application | `ghcr.io/pestoura/hermes-dvga` |

These package identities were made public during a temporary operating exception. A public package cannot be changed back to private. They therefore remain immutable accepted artefacts and rollback references.

The transition to private packages and read-only Hermes authentication is tracked by issue `#53` and specified in [`ghcr-private-readonly-transition.md`](ghcr-private-readonly-transition.md).

## Visibility and access are separate controls

GHCR Container packages support granular visibility and access permissions.

A package intended to remain private must:

- be private from first publication;
- never reuse an accepted public package identity;
- avoid inheriting access from a public repository;
- expose Actions access only to an approved private publisher repository;
- remain inaccessible through anonymous pulls;
- be consumed by Hermes only through a dedicated read-only credential.

A private package linked before first publication can inherit access permissions from its linked repository even though package visibility remains private. GitHub also warns that giving a public repository access to a private package can extend access through forks. The current public source repository must therefore not be the publisher or inherited-permission boundary for a private package.

Official references:

- [Configuring package access control and visibility](https://docs.github.com/en/packages/learn-github-packages/configuring-a-packages-access-control-and-visibility)
- [Connecting a repository to a package](https://docs.github.com/en/packages/learn-github-packages/connecting-a-repository-to-a-package)

## Private publisher boundary

The target architecture uses two repositories with different responsibilities.

### Public canonical source repository

`pestoura/hermes-security-labs`

Responsibilities:

- source and configuration review;
- accepted source commits and recipe hashes;
- public Compose and manifest definitions;
- accepted public and private runtime digests;
- lifecycle validation evidence references;
- deployment tracking and drift policy.

This repository must not receive inherited access to private packages.

### Private publisher repository

Proposed pilot identity:

`pestoura/hermes-private-registry-publisher`

Responsibilities:

- reviewed publication workflows only;
- immutable source checkout from the canonical public repository or upstream source;
- Dockerfile or generated recipe verification;
- GHCR publication with its own `GITHUB_TOKEN`;
- SBOM and provenance generation;
- package settings and Actions access limited to the private publisher.

Creation of this repository requires explicit owner authorization. It must be private before any workflow or package publication occurs.

## Package identities

The first private pilot package is proposed as:

```text
ghcr.io/pestoura/hermes-private-vampi
```

The current public runtime and rollback reference remains:

```text
ghcr.io/pestoura/hermes-vampi@sha256:e7b2760d586ed2b4b15a689823a07816e32308bca293f9e8c08830c7b36c7229
```

No public package, tag or digest is deleted, overwritten or moved during the transition.

## OCI metadata and repository linkage

For private packages, `org.opencontainers.image.source` points to the approved private publisher repository so that package linkage and inherited permissions remain private:

```text
org.opencontainers.image.source=https://github.com/pestoura/hermes-private-registry-publisher
```

The canonical public source and immutable revision are recorded separately:

```text
io.hermes.canonical-source=https://github.com/pestoura/hermes-security-labs
io.hermes.canonical-source.revision=<full-source-commit>
io.hermes.build.recipe=<reviewed-recipe-id>
io.hermes.build.dockerfile-sha256=<reviewed-sha256>
```

Required standard OCI metadata also includes:

```text
org.opencontainers.image.revision=<publisher-repository-commit>
org.opencontainers.image.created=<RFC3339 timestamp>
org.opencontainers.image.description=<short description>
org.opencontainers.image.licenses=<SPDX identifier when known>
```

## Tag and digest policy

Tags are navigation metadata. Digests are deployment identities.

Allowed publication tags:

- immutable source or recipe revision tag;
- immutable publisher-repository commit tag;
- controlled release tag after acceptance.

Prohibited runtime references:

- `latest`;
- `main`;
- `master`;
- `develop`;
- any other mutable channel tag.

Compose and manifests consume only the accepted OCI index digest:

```yaml
image: ghcr.io/pestoura/<private-package>@sha256:<accepted-index-digest>
```

The application and attestation manifests are recorded separately. The attestation digest is never used as a runtime reference.

## Publication workflow

Publication uses a GitHub-hosted runner in the private publisher repository.

Minimum permissions:

```yaml
permissions:
  contents: read
  packages: write
```

Additional attestation permissions are allowed only when required by the reviewed implementation.

Rules:

- `GITHUB_TOKEN` only for publication;
- no personal access token in Actions secrets when `GITHUB_TOKEN` is sufficient;
- no self-hosted runner;
- no Hermes Docker socket;
- no automatic deployment;
- manual dispatch or controlled release only;
- third-party Actions pinned by full commit SHA;
- immutable source and dependency verification;
- immutable tags only;
- SBOM and provenance retained;
- package visibility verified as private after first publication;
- inherited access verified to reference only the private publisher repository.

## Hermes authentication model

Hermes uses a dedicated personal access token classic with only:

```text
read:packages
```

Forbidden scopes include:

```text
write:packages
delete:packages
repo
workflow
admin:org
```

The existing GitHub CLI OAuth token on Hermes is operationally overprivileged and must not be reused as the registry consumer credential.

Credential rules:

- create, rotate and revoke only through an owner-authorized host operation;
- store outside Git, Compose, manifests, evidence and agent memory;
- authenticate through standard input;
- use a dedicated Docker configuration directory;
- prefer an approved credential helper or host secret store;
- never print token values, authorization headers or Docker `auth` fields;
- remove or rotate temporary pilot credentials after validation.

Example shape with placeholders only:

```bash
printf '%s' "${GHCR_READ_TOKEN}" |
  docker --config "${HERMES_GHCR_DOCKER_CONFIG}" \
  login ghcr.io \
  --username pestoura \
  --password-stdin
```

## Billing and execution readiness

GitHub currently documents Container registry image storage and bandwidth as free, with advance notice before any policy change. General private GitHub Packages quotas and budgets still apply to other package types.

The private pilot must nevertheless verify:

- the private publisher repository can execute GitHub-hosted Actions;
- no Actions spending or quota block prevents the publication workflow;
- the package remains private after publication;
- no payment or budget change is made without explicit authorization.

A failed legacy billing API endpoint does not by itself prove a Container registry block. UI or supported API evidence is required for any claim that billing is ready or blocked.

Official reference:

- [GitHub Packages billing](https://docs.github.com/en/billing/concepts/product-billing/github-packages)

## Private access validation

A private package is accepted only when all gates pass:

1. private publisher repository is approved and private;
2. package is private from first publication;
3. inherited access references only the private publisher repository;
4. anonymous metadata inspection and pull fail;
5. authenticated exact-digest inspection and pull succeed;
6. the Hermes credential exposes only `read:packages`;
7. a non-destructive authorization check confirms push authority is denied or omitted;
8. no manifest, blob, tag or version is uploaded by the negative-control test;
9. OCI index, application and attestation roles are valid;
10. SBOM and provenance are present;
11. lifecycle parity passes through a temporary ignored override;
12. evidence contains no credential material;
13. Docker and Git finish clean.

## Pilot sequence

1. merge the corrected private-publisher architecture;
2. verify private-repository Actions readiness;
3. explicitly authorize creation of the private publisher repository;
4. create it as private with minimal contents;
5. prepare and review a VAmPI publication workflow there;
6. explicitly authorize the first private publication;
7. publish `hermes-private-vampi` once;
8. verify visibility, linkage and inherited access;
9. provision the dedicated `read:packages` credential;
10. prove anonymous denial and authenticated digest pull;
11. validate lifecycle parity through a temporary override;
12. migrate Compose in a separate PR;
13. perform post-merge acceptance;
14. demonstrate rollback to the accepted public digest;
15. update deployment tracking and drift detection under `#7`.

Only one package migration is active at a time.

## Rollback policy

Rollback is a reviewed change to a previously accepted immutable OCI index digest.

For the VAmPI pilot, the rollback target is:

```text
ghcr.io/pestoura/hermes-vampi@sha256:e7b2760d586ed2b4b15a689823a07816e32308bca293f9e8c08830c7b36c7229
```

Rollback never moves a tag, deletes a package, changes unrelated laboratories or reuses the read-only credential for publication.

## Deployment tracking

Issue `#7` must record:

- canonical source commit;
- publisher repository and commit;
- effective Compose hash;
- registry visibility class;
- package identity;
- accepted OCI index digest;
- application and attestation digests;
- local image ID and architecture;
- authentication mode;
- credential rotation identifier without secret material;
- SBOM and provenance verification;
- rollback digest.

Drift exists when the effective package identity or digest differs from the accepted Git commit.

## Completion criteria

The GHCR epic can close only when:

- all five accepted public images remain immutable;
- the private publisher boundary is implemented;
- a private package is published without inheriting from the public repository;
- anonymous access is denied;
- Hermes pulls by exact digest using a `read:packages`-only credential;
- absence of write/delete authority is proven safely;
- lifecycle parity and private Compose migration pass;
- rollback to the accepted public digest is demonstrated;
- deployment tracking records source, publisher, package, digest and authentication mode;
- no automatic deployment or committed credential exists.