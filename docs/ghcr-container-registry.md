# GitHub Container Registry operating model

## Purpose

GitHub Container Registry (GHCR) is the canonical registry for container images built or adapted by `pestoura/hermes-security-labs`.

The repository remains the source of truth for source code, Dockerfiles, Compose files, manifests, workflows and documentation. GHCR stores the resulting Docker/OCI images. Hermes pulls accepted images and runs them locally; GitHub never deploys directly to Hermes.

This capability is a cross-cutting supply-chain improvement. It supports Web/API hardening, deployment tracking and Phase 2, but it is not a prerequisite for closing the initial Web/API implementation.

## Scope

### Initial project-built packages

| Environment | Package |
|---|---|
| VAmPI | `ghcr.io/pestoura/hermes-vampi` |
| DVAPI | `ghcr.io/pestoura/hermes-dvapi` |
| OWASP NodeGoat | `ghcr.io/pestoura/hermes-nodegoat` |
| PyGoat | `ghcr.io/pestoura/hermes-pygoat` |
| Damn Vulnerable GraphQL Application | `ghcr.io/pestoura/hermes-dvga` |

Project-built Kali MCP or runtime images require a separate approval before being added.

### Upstream images

Official upstream dependencies remain in their canonical registries and are pinned by digest. This includes MariaDB, MongoDB, PostgreSQL, DVWA, WebGoat and Juice Shop.

Mirroring an upstream image into GHCR is an exception that requires a documented reason, such as upstream-retention risk, registry availability, compliance or supply-chain approval.

## Package visibility and linkage

- Packages are private unless a separate public-release decision is approved.
- Every package is linked to `pestoura/hermes-security-labs`.
- Packages inherit repository access whenever supported.
- OCI source metadata is added before the first publication so package linkage is established at publication time.
- Package deletion is not part of normal lifecycle operations.

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

- immutable source/revision tag, for example `f16052d`;
- repository commit tag, for example `sha-<short-commit>`;
- controlled release tag after acceptance, for example `0.1.0`.

Prohibited deployment references:

- `latest`;
- `main`;
- `develop`;
- any other mutable channel tag.

After local acceptance, Compose and manifests must consume the exact accepted digest:

```yaml
image: ghcr.io/pestoura/hermes-vampi@sha256:<accepted-digest>
```

A human-readable tag may remain in documentation and evidence, but it is not the runtime trust anchor.

## Build and publication workflow

Publication uses GitHub-hosted runners only.

Minimum workflow permissions:

```yaml
permissions:
  contents: read
  packages: write
```

When provenance attestations are enabled:

```yaml
permissions:
  contents: read
  packages: write
  id-token: write
  attestations: write
```

Rules:

- no self-hosted runner;
- no Docker socket from Hermes;
- no deployment to Hermes from GitHub Actions;
- no personal access token for publication when `GITHUB_TOKEN` is sufficient;
- third-party actions are pinned by immutable commit SHA;
- publication is triggered by explicit workflow dispatch or a controlled release event;
- pull-request validation builds without publishing unless explicitly approved;
- published output records image name, tag, digest, architecture, source revision and attestation result.

## Hermes authentication model

Hermes receives read-only package access.

- No registry token is stored in Git, manifests, Compose files or evidence.
- Authentication uses standard input, never a token in command-line arguments.
- For private GHCR pulls outside GitHub Actions, use a dedicated package-read-only credential with `read:packages` and no repository write permission.
- Credential creation, storage and rotation are host-operations tasks and require explicit approval.
- Runtime scripts never print the credential or Docker auth configuration.
- Deployment verifies the expected digest before starting the laboratory.

Example login pattern:

```bash
echo "${GHCR_READ_TOKEN}" | docker login ghcr.io -u pestoura --password-stdin
```

The variable value must be supplied outside the repository and cleared according to the host credential procedure.

## Supply-chain controls

Each published image must provide:

- immutable source commit;
- reproducible build instructions where practical;
- OCI source and revision metadata;
- accepted architecture;
- repository digest;
- dependency and base-image references;
- vulnerability scan result or documented exception;
- build provenance attestation when supported;
- lifecycle acceptance on Hermes;
- rollback digest.

The registry does not replace source review, lifecycle validation or local isolation testing.

## Pilot rollout

VAmPI is the preferred pilot because it is a single project-built service with an already accepted lifecycle.

1. Add and review the publication workflow.
2. Build VAmPI from its immutable upstream commit.
3. Publish `ghcr.io/pestoura/hermes-vampi:<revision>`.
4. Record the GHCR repository digest and architecture.
5. Verify package linkage and private permissions.
6. Authenticate Hermes with read-only access.
7. Pull the image by digest.
8. Replace the pilot local-build reference with the GHCR digest on a dedicated branch.
9. Repeat the complete VAmPI lifecycle acceptance.
10. Demonstrate rollback to the previous accepted image or build path.
11. Promote the remaining images one at a time.

Only one package migration is active at a time.

## Integration with deployment tracking

Issue `#7` must eventually record, for each deployed laboratory:

- Git commit;
- effective Compose hash;
- GHCR image name;
- accepted digest;
- local image ID;
- architecture;
- attestation verification result where available.

Drift is reported when the effective image digest differs from the digest declared by the accepted Git commit.

## Phase relationship

- **Phase 1 Web/API:** closes when all scoped environments are accepted, merged and verified on `main`; GHCR migration is not a blocking criterion.
- **GHCR adoption:** tracked independently by issue `#34` as supply-chain hardening.
- **Phase 2:** uses the same registry, provenance and digest policy for DevSecOps, supply-chain and AI/MCP images.

## Acceptance criteria

GHCR adoption is complete when:

- this policy is merged;
- a reviewed GitHub-hosted publication workflow exists;
- the VAmPI pilot package is private and linked to the repository;
- OCI metadata and immutable digest are present;
- provenance evidence is recorded when supported;
- Hermes pulls with read-only access;
- lifecycle acceptance passes using the GHCR digest;
- rollback is demonstrated;
- no automatic deployment path to Hermes exists;
- no credentials or sensitive logs are committed.
