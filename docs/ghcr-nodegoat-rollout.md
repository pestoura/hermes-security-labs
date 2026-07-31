# NodeGoat GHCR rollout

## Purpose

Publish the OWASP NodeGoat application image to GitHub Container Registry without changing the active Hermes runtime until the resulting OCI index digest is independently validated.

This is the third controlled rollout under issue #34, after VAmPI and DVAPI.

## Package

```text
ghcr.io/pestoura/hermes-nodegoat
```

Canonical upstream source:

```text
https://github.com/OWASP/NodeGoat
c5cb68a7084e4ae7dcc60e6a98768720a81841e8
```

Upstream Dockerfile SHA-256:

```text
564fbfee6c70cebb62279954262dc614004faabfb71f63c09cb93a1f01237810
```

Declared upstream base image:

```text
docker.io/library/node:12-alpine
```

Upstream license:

```text
Apache-2.0
```

MongoDB is not published or mirrored. The runtime continues to consume the separately pinned official image `docker.io/library/mongo:4.4.29`.

## Compatibility boundary

The accepted local NodeGoat runtime builds the exact upstream commit with its upstream Dockerfile. That Dockerfile declares Node.js 12.

This rollout preserves that behavior so publication and runtime migration can be compared against the already accepted baseline. Node.js modernization, dependency upgrades or replacement of the upstream Dockerfile are separate compatibility and security changes and are outside issue #43.

The GHCR output is consumed only by immutable OCI digest. BuildKit provenance records the concrete base layers used during publication.

## Workflow

The publication workflow is:

```text
.github/workflows/publish-nodegoat-ghcr.yml
```

It is available only through `workflow_dispatch`. The operator must explicitly set the required `publish` boolean input.

The workflow:

- runs on a GitHub-hosted `ubuntu-24.04` runner;
- grants only `contents: read` and `packages: write`;
- uses the reviewed Docker Buildx `docker-container` driver;
- fetches only the declared upstream commit into the ephemeral runner directory;
- verifies that the checked-out `HEAD` matches the declared commit;
- verifies the upstream Dockerfile against its reviewed SHA-256;
- confirms the expected application and database-reset files exist;
- builds `linux/amd64` from the verified source;
- authenticates to GHCR with the ephemeral `GITHUB_TOKEN`;
- publishes only immutable tags;
- explicitly disables `latest`;
- adds OCI source, revision, documentation, license and Hermes build metadata;
- generates BuildKit provenance with `mode=max`;
- attaches an SBOM to the OCI image index;
- verifies the OCI index structure after publication;
- records the index/runtime digest separately from the application and attestation manifests;
- does not publish MongoDB;
- does not deploy to Hermes.

## Published tags

```text
upstream-c5cb68a
repo-<full hermes-security-labs commit SHA>
```

The following tags are prohibited:

```text
latest
main
develop
```

Runtime consumption must use the accepted OCI index digest, not a tag and not the attestation manifest:

```text
ghcr.io/pestoura/hermes-nodegoat@sha256:<oci-index-digest>
```

## Digest roles

The publication produces an OCI image index containing at least:

1. one `linux/amd64` application manifest;
2. one `unknown/unknown` attestation manifest referencing the application manifest.

The workflow summary records all three values:

- OCI index/runtime digest;
- application manifest digest;
- attestation manifest digest.

Only the OCI index digest may be used in the Hermes Compose runtime reference. The attestation digest must never be used as the application image.

## Current visibility exception

The repository and rollout packages are currently public because GitHub-hosted Actions were blocked by the account billing/spending restriction while the repository was private.

Anonymous Hermes validation requires `hermes-nodegoat` to remain publicly readable during this temporary operating phase. Repository visibility and package visibility are independent and must be confirmed after first publication.

The target operating model remains tracked under issue #34:

- private repository and packages;
- package linkage to `pestoura/hermes-security-labs`;
- read-only Hermes registry authentication;
- no credential in Git, Compose, evidence or shell history.

## First publication procedure

After the publication PR is reviewed and explicitly authorised for merge:

```bash
gh workflow run publish-nodegoat-ghcr.yml \
  --repo pestoura/hermes-security-labs \
  --ref main \
  -f publish=true
```

Obtain and watch the new run:

```bash
RUN_ID="$(
  gh run list \
    --repo pestoura/hermes-security-labs \
    --workflow publish-nodegoat-ghcr.yml \
    --event workflow_dispatch \
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
- upstream commit and Dockerfile SHA-256;
- OCI index/runtime digest;
- `linux/amd64` application manifest digest;
- attestation manifest digest;
- published immutable tags;
- package visibility and repository linkage.

Do not identify the runtime digest by selecting the final `sha256` string from the log. Use the workflow summary or inspect the OCI index explicitly.

## Registry validation

When the package is intentionally public for this rollout, validation must succeed without `docker login`:

```bash
docker buildx imagetools inspect \
  ghcr.io/pestoura/hermes-nodegoat@sha256:<oci-index-digest>
```

Confirm:

- OCI index media type;
- exactly one `linux/amd64` application manifest;
- an attestation manifest with platform `unknown/unknown`;
- attestation reference pointing to the application manifest;
- expected OCI and Hermes labels;
- expected upstream Dockerfile SHA-256 label;
- Apache-2.0 license metadata;
- absence of mutable runtime tags.

## Hermes validation gate

Do not change the NodeGoat Compose before the digest is accepted.

The existing lifecycle must first be exercised through a temporary ignored Compose override that:

- removes the application `build:` definition;
- replaces only the NodeGoat application image with the exact OCI index digest;
- disables pull/build during the lifecycle exercise after the anonymous digest pull;
- preserves `mongo:4.4.29`, the internal `nodegoat-db` network and the MongoDB volume.

Required evidence:

- anonymous or approved read-only digest pull;
- image ID, RepoDigests, platform and labels;
- effective application image by exact OCI index digest;
- no local NodeGoat build;
- NodeGoat and MongoDB healthy;
- host binding restricted to `127.0.0.1`;
- MongoDB without host port bindings;
- application connected to both project networks;
- MongoDB connected only to `nodegoat-db`;
- `nodegoat-db` remains internal;
- Kali joined only to `nodegoat-lab` and never to `nodegoat-db`;
- localhost and Kali DNS/TCP/HTTP checks;
- application-to-MongoDB connectivity;
- stop, restart and reset without build;
- idempotent destroy;
- final Kali disconnection;
- MongoDB volume and both NodeGoat networks removed;
- Prometheus and unrelated Docker resources unchanged;
- previous local image unchanged;
- clean working tree.

## Runtime migration gate

Only after the complete Hermes digest validation passes may a separate PR:

- remove the NodeGoat application `build:` block;
- replace `hermes/nodegoat:c5cb68a` with the accepted GHCR OCI index digest;
- change lifecycle start/reset from local build to pull-missing behavior;
- remove the runtime Docker BuildKit dependency;
- update the NodeGoat README and manifest.

The MongoDB image, command, internal database network, volume and all isolation controls must remain unchanged.

## Rollback

If publication or Hermes validation fails:

- leave the current Compose and lifecycle unchanged;
- do not alter or remove the accepted local NodeGoat image;
- do not alter MongoDB or unrelated resources;
- do not retry publication automatically;
- do not use the attestation manifest as a runtime reference;
- document the exact failing step and evidence in issue #43;
- keep issue #43 open until a reviewed correction is accepted.
