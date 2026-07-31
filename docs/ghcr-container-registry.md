# GitHub Container Registry operating model

## Purpose

GitHub Container Registry (GHCR) is the canonical registry for container images built or adapted by `pestoura/hermes-security-labs`.

The repository remains the source of truth for source code, Dockerfiles, Compose files, manifests, workflows and documentation. GHCR stores the resulting Docker/OCI images. Hermes pulls accepted images and runs them locally; GitHub never deploys directly to Hermes.

This capability is a cross-cutting supply-chain improvement. It supports Web/API hardening, deployment tracking and Phase 2, but it is not a prerequisite for closing the initial Web/API implementation.

## Operational status

The initial five project-built image rollouts are complete and accepted by immutable public GHCR digest:

| Environment | Package |
|---|---|
| VAmPI | `ghcr.io/pestoura/hermes-vampi` |
| DVAPI | `ghcr.io/pestoura/hermes-dvapi` |
| OWASP NodeGoat | `ghcr.io/pestoura/hermes-nodegoat` |
| PyGoat | `ghcr.io/pestoura/hermes-pygoat` |
| Damn Vulnerable GraphQL Application | `ghcr.io/pestoura/hermes-dvga` |

These packages were made public during a temporary infrastructure and billing exception. GitHub does not allow a public package to be changed back to private. The accepted package identities therefore remain public historical artefacts and cannot directly become the private target state.

The controlled transition to parallel private package identities and read-only Hermes authentication is specified in [`ghcr-private-readonly-transition.md`](ghcr-private-readonly-transition.md) and tracked by issue `#53`.

No current public package may be deleted, overwritten, retagged or changed as part of that transition.

## Scope

### Project-built packages

The first-generation public package names above remain accepted until each replacement private package passes publication, access, digest, lifecycle, migration and post-merge gates.

Project-built Kali MCP or runtime images require a separate approval before being added.

### Upstream images

Official upstream dependencies remain in their canonical registries and are pinned by digest. This includes MariaDB, MongoDB, PostgreSQL, DVWA, WebGoat and Juice Shop.

Mirroring an upstream image into GHCR is an exception that requires a documented reason, such as upstream-retention risk, registry availability, compliance or supply-chain approval.

## Package visibility and linkage

Target-state project packages are private unless a separate public-release decision is approved.

Rules:

- a package intended to be private must be private from first publication;
- an existing public package must never be treated as capable of returning to private visibility;
- every package is linked to `pestoura/hermes-security-labs` for source traceability when appropriate;
- package visibility and access inheritance are separate controls and must both be verified;
- a private package linked to the public repository must use verified granular package access rather than assume repository inheritance provides confidentiality;
- GitHub Actions access is granted only to the publishing repository and only at the package permission level required by the workflow;
- package deletion is not part of normal lifecycle operations.

Required OCI metadata:

```text
org.opencontainers.image.source=https://github.com/pestoura/hermes-security-labs
org.opencontainers.image.revision=<source-or-repository-commit>
org.opencontainers.image.created=<RFC3339 timestamp>
org.opencontainers.image.description=<short description>
org.opencontainers.image.licenses=<SPDX identifier when known>
```

## Tag and digest policy

Tags are navigation metadata. Digests are deployment identities.

Allowed publication tags:

- immutable source/revision tag;
- repository commit tag;
- controlled release tag after acceptance.

Prohibited deployment references:

- `latest`;
- `main`;
- `master`;
- `develop`;
- any other mutable channel tag.

After local acceptance, Compose and manifests consume the exact accepted OCI index digest:

```yaml
image: ghcr.io/pestoura/<package>@sha256:<accepted-index-digest>
```

The application manifest and attestation manifest are recorded separately. The attestation digest is never used as a runtime reference.

A human-readable tag may remain in documentation and evidence, but it is not the runtime trust anchor.

## Build and publication workflow

Publication uses GitHub-hosted runners only.

Minimum workflow permissions:

```yaml
permissions:
  contents: read
  packages: write
```

Additional attestation permissions are allowed only when required by a reviewed implementation.

Rules:

- no self-hosted runner;
- no Docker socket from Hermes;
- no deployment to Hermes from GitHub Actions;
- no personal access token for publication when `GITHUB_TOKEN` is sufficient;
- third-party actions are pinned by immutable commit SHA;
- publication is triggered by explicit workflow dispatch or a controlled release event;
- pull-request validation builds without publishing unless explicitly approved;
- published output records image name, tag, OCI index digest, application digest, attestation digest, architecture, source revision and attestation result;
- a private-package workflow must verify that the new package identity is not one of the accepted public package names.

## Hermes authentication model

Hermes receives read-only package access for private packages.

GitHub Packages command-line authentication outside GitHub Actions uses a personal access token (classic).

The Hermes credential requires only:

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

Rules:

- no registry token is stored in Git, manifests, Compose files or evidence;
- authentication uses standard input, never a token in command-line arguments;
- the token owner must have read permission to the private package;
- credential creation, storage, rotation and revocation are host-operations tasks requiring explicit approval;
- runtime scripts never print the credential, authorization headers or Docker auth configuration;
- an isolated Docker configuration directory is used for Hermes registry access;
- a supported credential helper or approved host secret store is preferred;
- a plain Docker `config.json` is not encrypted and requires explicit temporary-pilot approval, restrictive file modes and a documented expiry;
- deployment verifies the expected package identity and digest before starting the laboratory.

Example login shape with placeholder values only:

```bash
printf '%s' "${GHCR_READ_TOKEN}" |
  docker --config "${HERMES_GHCR_DOCKER_CONFIG}" \
  login ghcr.io \
  --username pestoura \
  --password-stdin
```

## Private access validation

A private package is not accepted until all of the following pass:

1. anonymous metadata inspection and pull are denied;
2. authenticated exact-digest inspection and pull succeed;
3. the credential exposes `read:packages` and does not expose write, delete or repository scopes;
4. a non-destructive registry authorization check confirms push authority is denied or omitted;
5. no manifest, blob, tag or package version is uploaded by the negative-control test;
6. OCI index, application and attestation roles remain valid;
7. SBOM and provenance remain present;
8. lifecycle acceptance passes on Hermes using a temporary ignored override;
9. the credential is absent from evidence and shell history;
10. final Docker and Git state is clean.

## Supply-chain controls

Each published image must provide:

- immutable source commit;
- reproducible build instructions where practical;
- OCI source and revision metadata;
- accepted architecture;
- OCI index digest;
- application and attestation manifest digests;
- dependency and base-image references;
- vulnerability scan result or documented exception;
- build provenance attestation when supported;
- lifecycle acceptance on Hermes;
- rollback digest.

The registry does not replace source review, lifecycle validation or local isolation testing.

## Rollout model

### Completed public rollout

The five initial public packages have passed controlled publication, independent digest validation, Compose migration and post-merge lifecycle acceptance.

### Private read-only pilot

VAmPI is the first private-access pilot because it is a single project-built service with an accepted lifecycle and no external database dependency.

The proposed parallel pilot identity is:

```text
ghcr.io/pestoura/hermes-private-vampi
```

The package name, credential provisioning and first publication require explicit owner authorization.

Pilot sequence:

1. confirm private-package billing and budget readiness;
2. review and merge the private transition documentation;
3. explicitly authorize the package identity and credential creation;
4. publish the new package privately through a separately reviewed workflow;
5. verify package visibility, linkage and granular Actions access;
6. prove anonymous denial;
7. provision and validate the read-only Hermes credential;
8. pull and validate the exact private digest through a temporary override;
9. migrate Compose in a separate PR;
10. perform post-merge acceptance;
11. demonstrate rollback to the accepted public digest;
12. update deployment tracking and drift detection;
13. decide the namespace model for the remaining packages.

Only one package migration is active at a time.

## Billing and quota gate

Private package storage and data transfer are metered.

Before private publication:

- confirm available storage and transfer allowance;
- confirm a valid budget/payment configuration where required;
- record only non-sensitive quota readiness evidence;
- stop with `BLOCKED_GHCR_PRIVATE_BILLING` when GitHub blocks usage;
- do not bypass the block with a self-hosted runner or exposed Hermes Docker socket.

## Integration with deployment tracking

Issue `#7` must eventually record, for each deployed laboratory:

- Git commit;
- effective Compose hash;
- registry visibility class;
- GHCR package identity;
- accepted OCI index digest;
- local image ID;
- architecture;
- authentication mode;
- credential rotation identifier without secret material;
- SBOM and provenance verification result;
- rollback digest.

Drift is reported when the effective package identity or image digest differs from the identity and digest declared by the accepted Git commit.

## Rollback policy

Rollback is a reviewed change to a previously accepted immutable OCI index digest.

During the private pilot, the current public VAmPI digest remains the rollback target:

```text
ghcr.io/pestoura/hermes-vampi@sha256:e7b2760d586ed2b4b15a689823a07816e32308bca293f9e8c08830c7b36c7229
```

Rollback never:

- moves a tag;
- deletes the private package;
- bypasses post-change acceptance;
- reuses the read-only credential for publication;
- changes unrelated laboratories.

## Phase relationship

- **Phase 1 Web/API:** closed for the scoped initial implementation.
- **Public GHCR rollout:** complete for the five project-built images.
- **Private read-only transition:** tracked by issue `#53` under epic `#34`.
- **Deployment tracking and drift:** tracked by issue `#7`.
- **Phase 2:** uses the same registry, provenance, digest and least-privilege principles.

## Acceptance criteria

The GHCR epic can close only when:

- the five initial image rollouts remain accepted and immutable;
- the irreversible public-package constraint is documented;
- a private package identity is published without altering its public predecessor;
- package visibility, linkage and granular permissions are verified;
- Hermes authenticates with a `read:packages`-only credential;
- anonymous private-package access is denied;
- authenticated exact-digest pull succeeds;
- absence of write/delete authority is proven without destructive operations;
- lifecycle acceptance passes using the private digest;
- a separate migration PR and post-merge acceptance pass;
- rollback to a previous accepted digest is demonstrated;
- deployment tracking records package identity, digest and authentication mode;
- no automatic deployment path to Hermes exists;
- no credentials or sensitive logs are committed.