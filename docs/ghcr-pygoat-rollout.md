# PyGoat GHCR rollout

## Purpose

This runbook controls publication of the project-adapted PyGoat application image to GitHub Container Registry. Publication and runtime migration are deliberately separate operations.

The publication workflow does not deploy to Hermes and does not alter the active PyGoat Compose configuration.

## Canonical package

```text
ghcr.io/pestoura/hermes-pygoat
```

## Immutable source

- repository: `https://github.com/adeyosemanputra/pygoat`;
- commit: `19d17cc8874861142b330636d068bbde54e86b85`;
- short revision: `19d17cc`;
- platform: `linux/amd64`.

The workflow initializes an isolated Git repository under `RUNNER_TEMP`, fetches only the exact commit, checks out the detached commit and verifies `HEAD` before building.

## Project build recipe

PyGoat is not published from the upstream Dockerfile. The accepted Hermes runtime uses a project-contained compatibility recipe reconstructed inside runner temporary storage.

- recipe identifier: `pygoat-python310-compat-v1`;
- Dockerfile SHA-256: `58389fedb2ec704c6e0bc1e9f899cdd07a3fdc08aac117b9da20b1cfa53d8d3d`;
- declared base: `docker.io/library/python:3.10-slim-bookworm`.

The recipe preserves the runtime previously accepted during local-build validation:

1. installs the Debian build toolchain required by legacy Python packages;
2. copies the immutable upstream source;
3. removes upstream `psycopg2==2.9.3` and `PyYAML==5.1` from the requirements pass;
4. installs `psycopg2-binary==2.9.9` and `PyYAML==6.0.2`;
5. installs the remaining upstream requirements;
6. changes only Django `ALLOWED_HOSTS` to add `0.0.0.0`, `127.0.0.1`, `localhost` and `pygoat` while retaining the upstream hostname;
7. runs `python manage.py migrate --noinput` during the build;
8. starts Gunicorn on `0.0.0.0:8000` with two workers.

The workflow verifies the expected upstream dependency pins and original `ALLOWED_HOSTS` line before building. A source change that invalidates the compatibility assumptions must fail rather than silently produce a different image.

## License metadata

No license file was found at the accepted upstream commit. The publication therefore uses:

```text
org.opencontainers.image.licenses=NOASSERTION
```

This is not a license grant or a legal conclusion. Publication scope and repository visibility remain governed by project-owner approval.

## Publication workflow

Workflow:

```text
.github/workflows/publish-pygoat-ghcr.yml
```

The workflow:

- runs only through `workflow_dispatch`;
- requires `publish=true`;
- uses GitHub-hosted `ubuntu-24.04`;
- uses `GITHUB_TOKEN` with `contents: read` and `packages: write`;
- uses the Buildx `docker-container` driver;
- pins third-party Actions by full commit SHA;
- builds only `linux/amd64`;
- enables BuildKit provenance with `mode=max`;
- attaches an SBOM;
- performs no deployment.

## Immutable tags

Expected tags:

```text
upstream-19d17cc
repo-<full repository commit SHA>
```

Prohibited tags:

```text
latest
main
develop
```

Tags are discovery metadata only. Hermes must consume the accepted OCI index digest.

## OCI metadata

The image includes:

- repository source and documentation links;
- immutable upstream revision;
- declared base image;
- project Dockerfile SHA-256;
- build recipe identifier;
- upstream repository and revision;
- license value `NOASSERTION`.

## Digest roles

A successful publication with provenance and SBOM produces an OCI index containing at least:

1. one `linux/amd64` application manifest;
2. one `unknown/unknown` attestation manifest.

The workflow records three separate digest roles:

- **OCI index/runtime digest** — the only digest allowed in Compose;
- **application manifest digest** — the `linux/amd64` image manifest;
- **attestation manifest digest** — metadata containing provenance and SBOM references.

The attestation digest must never be used as the runtime image reference.

## Manual publication

From an authenticated GitHub CLI session:

```bash
gh workflow run publish-pygoat-ghcr.yml \
  --repo pestoura/hermes-security-labs \
  --ref main \
  -f publish=true
```

Identify and watch the single created run:

```bash
gh run list \
  --repo pestoura/hermes-security-labs \
  --workflow publish-pygoat-ghcr.yml \
  --event workflow_dispatch \
  --limit 10

gh run watch <RUN_ID> \
  --repo pestoura/hermes-security-labs \
  --exit-status
```

Do not automatically dispatch a second run after failure. Capture the failed step, logs and annotations first.

## Publication acceptance

Before accepting the package, record:

- workflow run and job IDs;
- exact repository SHA used by the run;
- upstream commit;
- Dockerfile SHA-256;
- build recipe identifier;
- declared and resolved base image information;
- OCI index/runtime digest;
- application manifest digest;
- attestation manifest digest;
- package visibility;
- immutable tags;
- absence of prohibited tags;
- SBOM and provenance presence;
- confirmation that no deployment occurred.

## Anonymous validation during the current operating exception

The repository is currently public. GHCR package visibility is independent and must be confirmed after publication.

When the package is public, validate without `docker login`:

```bash
docker buildx imagetools inspect \
  ghcr.io/pestoura/hermes-pygoat@sha256:<OCI_INDEX_DIGEST>
```

A `401`, `403` or package-not-found response must not be bypassed with an unapproved PAT. Classify the result as requiring a visibility/access correction.

The intended private package and read-only authenticated Hermes pull model remains tracked under issue #34.

## Hermes digest validation gate

Before changing Compose, Hermes must validate the OCI index digest through a temporary ignored override that removes the local build.

Required checks:

- anonymous or separately approved read-only pull succeeds;
- OCI index, application and attestation digest roles are correct;
- attestation points to the application manifest;
- SBOM and provenance are present;
- image architecture is `linux/amd64`;
- labels, source revision, base and Dockerfile hash match;
- effective Compose contains no application build;
- application becomes healthy;
- host publication remains restricted to `127.0.0.1`;
- `pygoat-lab` remains the only project network;
- Kali connects only when explicitly authorized;
- Kali DNS, TCP and HTTP checks pass;
- stop, restart, reset and destroy pass without building;
- second connect, disconnect and destroy operations remain idempotent;
- unrelated containers, networks, volumes and Prometheus remain unchanged;
- final state is destroyed and the working tree is clean.

Only a result of `READY_FOR_PYGOAT_COMPOSE_MIGRATION` permits a separate migration PR.

## Runtime migration

The later migration PR must be limited to:

- replacing `build:` and `hermes/pygoat:19d17cc` with the accepted immutable GHCR index digest;
- changing lifecycle startup from `--build` to `--pull missing`;
- removing source-build/BuildKit runtime dependencies from the manifest;
- updating PyGoat documentation.

It must preserve:

- port `127.0.0.1:${PYGOAT_HOST_PORT:-8000}:8000`;
- healthcheck;
- resource limits;
- `NET_RAW` removal;
- `no-new-privileges`;
- `pygoat-lab` network and alias;
- restart behavior;
- all lifecycle ownership and Kali controls.

## Post-merge acceptance

After migration, synchronize Hermes to the exact merge SHA and execute the normal versioned lifecycle:

```bash
platform/environments/web-api/pygoat/scripts/start.sh
platform/environments/web-api/pygoat/scripts/status.sh
platform/environments/web-api/pygoat/scripts/smoke.sh
platform/environments/web-api/pygoat/scripts/connect-kali.sh
platform/environments/web-api/pygoat/scripts/disconnect-kali.sh
platform/environments/web-api/pygoat/scripts/stop.sh
platform/environments/web-api/pygoat/scripts/reset.sh
platform/environments/web-api/pygoat/scripts/destroy.sh
```

The rollout issue can close only after the normal post-merge lifecycle passes and the final host state is clean.

## Rollback

Rollback must use a previously accepted immutable OCI index digest. Never roll back by moving or consuming a mutable tag.

A rollback change requires:

1. a reviewed Compose change to the previous accepted index digest;
2. normal repository checks;
3. explicit owner authorization before merge;
4. complete post-merge lifecycle validation on Hermes.

## Scope exclusions

This rollout does not:

- modernize Python, Django or dependencies;
- change challenge/application source;
- change the compatibility wrapper;
- add PostgreSQL;
- change the SQLite persistence model embedded by the accepted build;
- publish upstream official images;
- enable automatic deployment;
- configure private/read-only registry authentication;
- modify Kali MCP;
- execute exploitation, brute force, denial of service or external scanning.

Tracking issue: #46. Parent epic: #34.
