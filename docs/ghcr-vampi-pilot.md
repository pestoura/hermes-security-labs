# VAmPI GHCR pilot

## Purpose

Publish the project-built VAmPI laboratory image to GitHub Container Registry without changing the active Hermes runtime until the package is independently validated.

## Package

```text
ghcr.io/pestoura/hermes-vampi
```

Canonical upstream source:

```text
https://github.com/erev0s/VAmPI
f16052dce83f05847133ec98f01c5193a41de7d8
```

## Workflow

The publication workflow is:

```text
.github/workflows/publish-vampi-ghcr.yml
```

It is available only through `workflow_dispatch`. The operator must explicitly enable the `publish` boolean input.

The workflow:

- runs on a GitHub-hosted runner;
- authenticates to `ghcr.io` with the ephemeral `GITHUB_TOKEN`;
- grants only `contents: read` and `packages: write`;
- builds directly from the immutable upstream Git commit;
- publishes only immutable tags;
- does not publish `latest`, `main` or `develop`;
- adds OCI and Hermes upstream metadata;
- generates BuildKit provenance with `mode=max`;
- attaches an SBOM;
- prints the immutable image digest in the workflow summary;
- does not deploy to Hermes.

## Published tags

The pilot publishes:

```text
upstream-f16052d
repo-<full hermes-security-labs commit SHA>
```

Runtime consumption must use the digest, not either tag:

```text
ghcr.io/pestoura/hermes-vampi@sha256:<digest>
```

## Action pinning

The Docker login, metadata and build actions are pinned to reviewed commit SHAs. Updating any action requires a separate reviewed change.

## Provenance model

GitHub artifact attestations for private repositories require GitHub Enterprise Cloud. This private repository therefore uses the OCI attestations produced by Docker BuildKit:

```yaml
provenance: mode=max
sbom: true
```

These attestations are attached to the image index in GHCR. No build argument or secret is passed to the upstream build.

## First publication procedure

1. Merge the reviewed workflow PR.
2. Open **Actions → Publish VAmPI to GHCR**.
3. Choose **Run workflow** on `main`.
4. Enable the `publish` input.
5. Wait for the build, push and digest verification steps.
6. Record the workflow run URL and immutable digest.
7. Open **Packages → hermes-vampi**.
8. Confirm that the package is private and linked to `pestoura/hermes-security-labs`.
9. Confirm the source, documentation, upstream revision and repository labels.

## Registry validation

From an authenticated workstation:

```bash
docker buildx imagetools inspect \
  ghcr.io/pestoura/hermes-vampi@sha256:<digest>
```

Confirm:

- media type is OCI-compatible;
- the published platform is `linux/amd64`;
- the manifest digest matches the workflow summary;
- provenance and SBOM attestation manifests are present;
- no mutable deployment reference is introduced.

## Hermes validation

Do not store credentials in the repository, Compose files or shell history.

After creating a read-only package credential outside the repository, authenticate interactively or through the Hermes secret-management mechanism and pull the immutable reference:

```bash
docker pull \
  ghcr.io/pestoura/hermes-vampi@sha256:<digest>
```

Before changing the VAmPI Compose file, record:

```bash
docker image inspect \
  ghcr.io/pestoura/hermes-vampi@sha256:<digest>
```

Required evidence:

- configured image reference;
- image ID;
- repository digest;
- architecture;
- OCI labels;
- successful localhost-only lifecycle;
- Kali isolation;
- final destroyed state;
- no unrelated Docker drift.

## Runtime migration gate

The existing VAmPI Compose build remains canonical until all of the following pass:

1. package publication;
2. package privacy and repository linkage;
3. digest and metadata verification;
4. Hermes read-only pull;
5. complete VAmPI lifecycle using the digest;
6. comparison with the already accepted local-build behavior.

Only then may a follow-up PR replace:

```yaml
build:
  context: https://github.com/erev0s/VAmPI.git#f16052dce83f05847133ec98f01c5193a41de7d8
image: hermes/vampi:f16052d
```

with the immutable GHCR digest reference.

## Rollback

If package validation fails, leave the current Compose file unchanged and delete or supersede only the invalid package version. Do not delete accepted local images or alter unrelated laboratory resources.
