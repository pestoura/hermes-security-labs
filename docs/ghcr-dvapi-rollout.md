# DVAPI GHCR rollout

## Purpose

Publish the project-built DVAPI application image to GitHub Container Registry without changing the active Hermes runtime until the package digest is independently validated.

This is the second rollout under issue #34 and follows the accepted VAmPI publication model.

## Package

```text
ghcr.io/pestoura/hermes-dvapi
```

Canonical upstream source:

```text
https://github.com/payatu/DVAPI
bde30d295aa8bc7f5516396fbae19d9630c11600
```

Reviewed base image:

```text
docker.io/library/node:20-bookworm-slim
```

MongoDB is not published or mirrored. The runtime continues to consume the separately pinned official MongoDB image.

## Workflow

The publication workflow is:

```text
.github/workflows/publish-dvapi-ghcr.yml
```

It is available only through `workflow_dispatch`. The operator must explicitly enable the required `publish` boolean input.

The workflow:

- runs on a GitHub-hosted `ubuntu-24.04` runner;
- grants only `contents: read` and `packages: write`;
- uses the accepted Docker Buildx `docker-container` driver;
- fetches only the declared upstream commit into the ephemeral runner directory;
- verifies that the checked-out `HEAD` exactly matches the declared commit;
- writes the reviewed Hermes Dockerfile only in the ephemeral workspace;
- builds `linux/amd64` from the verified source;
- authenticates to GHCR with the ephemeral `GITHUB_TOKEN`;
- publishes only immutable tags;
- explicitly disables `latest`;
- adds OCI and Hermes upstream/base-image metadata;
- generates BuildKit provenance with `mode=max`;
- attaches an SBOM to the OCI image index;
- exposes the immutable digest in the workflow summary;
- does not publish MongoDB;
- does not deploy to Hermes.

## Reviewed build recipe

```dockerfile
FROM node:20-bookworm-slim
WORKDIR /app
COPY src /app
RUN npm install && npm install --global pm2
CMD ["pm2-runtime", "start", "npm", "--", "start"]
```

This recipe replaces the upstream mutable Node base while preserving the source and runtime command already accepted by the DVAPI lifecycle campaign.

## Published tags

```text
upstream-bde30d2
repo-<full hermes-security-labs commit SHA>
```

Runtime consumption must use the accepted digest, not either tag:

```text
ghcr.io/pestoura/hermes-dvapi@sha256:<digest>
```

## Action pinning

The Docker setup, login, metadata and build actions are pinned to reviewed full commit SHAs. Updating an action requires a separate reviewed change.

## Current visibility exception

The repository and pilot package are currently public because GitHub-hosted Actions were blocked by the account billing/spending restriction while the repository was private.

This is a temporary operating exception. The target model remains:

- private repository and packages;
- package linkage to `pestoura/hermes-security-labs`;
- read-only Hermes registry authentication;
- no credential in Git, Compose, evidence or shell history.

That target model remains tracked under issue #34.

## First publication procedure

After the workflow PR is reviewed and explicitly authorised for merge:

```bash
gh workflow run publish-dvapi-ghcr.yml \
  --repo pestoura/hermes-security-labs \
  --ref main \
  -f publish=true
```

Obtain and watch the latest run:

```bash
RUN_ID="$(
  gh run list \
    --repo pestoura/hermes-security-labs \
    --workflow publish-dvapi-ghcr.yml \
    --limit 1 \
    --json databaseId \
    --jq '.[0].databaseId'
)"

gh run watch "${RUN_ID}" \
  --repo pestoura/hermes-security-labs \
  --exit-status
```

Record:

- workflow run and job IDs;
- publication repository SHA;
- immutable package digest;
- application manifest digest;
- SBOM/provenance attestation manifest digest;
- published immutable tags.

## Registry validation

While the package remains public, validation must succeed without `docker login`:

```bash
docker buildx imagetools inspect \
  ghcr.io/pestoura/hermes-dvapi@sha256:<digest>
```

Confirm:

- OCI-compatible image index;
- `linux/amd64` application manifest;
- canonical digest matching the workflow summary;
- provenance and SBOM attestation manifests;
- expected OCI and Hermes labels;
- absence of a `latest` runtime tag.

## Hermes validation gate

Do not change the DVAPI Compose before the digest is accepted.

The existing lifecycle must be exercised using a temporary, ignored Compose override that replaces only the application image and disables local builds. MongoDB must continue to use `mongo:4.4.29` on the internal `dvapi-db` network.

Required evidence:

- anonymous or read-only digest pull;
- image ID, RepoDigests, platform and labels;
- effective application image by exact digest;
- no local application build;
- application and MongoDB healthy;
- host binding restricted to `127.0.0.1`;
- MongoDB without host port bindings;
- Kali joined only to `dvapi-lab` and never to `dvapi-db`;
- localhost and Kali DNS/TCP/HTTP checks;
- reset and idempotent destroy;
- final Kali disconnection;
- MongoDB volume and both DVAPI networks removed;
- Prometheus and unrelated Docker resources unchanged;
- clean working tree.

## Runtime migration gate

Only after the complete Hermes digest validation passes may a separate PR:

- remove the DVAPI application `build:` block;
- replace `hermes/dvapi:bde30d2` with the accepted GHCR digest;
- change lifecycle start/reset from local build to pull-missing behavior;
- remove the runtime Docker BuildKit dependency;
- update the DVAPI README and manifest.

The MongoDB image, internal network and lifecycle isolation controls must remain unchanged.

## Rollback

If publication or Hermes validation fails:

- leave the current Compose and lifecycle unchanged;
- do not delete the accepted local image;
- do not alter MongoDB or unrelated resources;
- delete or supersede only an invalid package version after a documented decision;
- keep issue #40 open with the exact failure evidence.
