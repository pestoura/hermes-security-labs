# DVGA GHCR rollout

## Purpose

This runbook controls publication and later runtime migration of the project-adapted Damn Vulnerable GraphQL Application image. Publication, digest validation and Compose migration are separate gates.

The publication workflow does not deploy to Hermes and does not alter the active GraphQL/DVGA Compose runtime.

## Canonical package

```text
ghcr.io/pestoura/hermes-dvga
```

## Immutable sources

Primary application source:

- repository: `https://github.com/dolevf/Damn-Vulnerable-GraphQL-Application`;
- commit: `a961308c02d1fb462b192681c336b0739e432da7`;
- application version: `2.2.0`;
- platform: `linux/amd64`;
- license: MIT (`LICENSE.md`).

Pinned VCS dependency:

- repository: `https://github.com/dolevf/flask-sockets`;
- commit: `513caf69a053a53c35110a389c9b0d83b2a9d99b`;
- installed distribution: `Flask-Sockets 0.2.1.1`.

The workflow fetches both repositories by exact commit and verifies each fetched object before building.

## Discovery evidence

The accepted local image is:

```text
hermes/dvga:a961308
```

Read-only inspection of that image proved that the upstream requirement:

```text
git+https://github.com/dolevf/flask-sockets@master
```

had resolved to:

```text
513caf69a053a53c35110a389c9b0d83b2a9d99b
```

The proof came from the installed `Flask-Sockets` distribution `direct_url.json`, not from the current remote branch position alone. The same commit remained fetchable by immutable SHA and matched the remote `master` during discovery.

Publication must never depend on `master`, even while it happens to reference the same commit.

## Accepted local baseline

The local image discovery recorded:

- image ID: `sha256:91445839524e5acf21213ef840cd88b7c368604964b46aa345dead7dd18e2167`;
- Python: `3.10.20`;
- runtime user: `dvga`;
- working directory: `/opt/dvga`;
- command: `python app.py`;
- internal HTTP: `200`;
- SQLite database initialized;
- upload directory initialized.

Critical dependency versions:

- Flask `2.2.2`;
- Flask-Sockets `0.2.1.1`;
- Flask-GraphQL `2.0.1`;
- Flask-GraphQL-Auth `1.3.3`;
- Flask-SocketIO `5.3.2`;
- Flask-SQLAlchemy `3.0.2`;
- SQLAlchemy `1.4.44`;
- graphene `2.1.9`;
- graphene-sqlalchemy `2.3.0`;
- graphql-core `2.3.2`;
- gevent `22.10.2`;
- gevent-websocket `0.10.1`;
- greenlet `2.0.1`;
- Werkzeug `2.2.2`;
- PyJWT `2.0.1`.

These values form the later digest-validation baseline.

## Publication recipe

Recipe identifier:

```text
dvga-python310-vcs-pin-v1
```

Dockerfile SHA-256:

```text
9bce8097d8b8e2ed32c86cfa335cb8e3bc9f914f9e998e1f296a2e668c428e5d
```

Declared base:

```text
docker.io/library/python:3.10-slim-bookworm
```

The recipe:

1. starts from Python 3.10 slim Bookworm;
2. installs `git`, required by the historical VCS dependency;
3. creates the non-login `dvga` user;
4. copies the exact primary upstream source;
5. verifies exactly one mutable Flask-Sockets requirement;
6. replaces only `flask-sockets@master` with the proven immutable commit;
7. installs all remaining upstream requirements without version modernization;
8. executes `python setup.py` to initialize application state;
9. transfers ownership of `/opt/dvga` to `dvga`;
10. runs `python app.py` as `dvga`.

The workflow hash-verifies the complete reconstructed Dockerfile and fails if the upstream requirement assumption changes.

## Publication workflow

Workflow:

```text
.github/workflows/publish-dvga-ghcr.yml
```

The workflow:

- runs only through `workflow_dispatch` with `publish=true`;
- uses GitHub-hosted `ubuntu-24.04`;
- grants `contents: read` and `packages: write` only;
- pins third-party Actions by full commit SHA;
- uses Buildx with the `docker-container` driver;
- builds only `linux/amd64`;
- publishes SBOM and BuildKit provenance `mode=max`;
- performs no deployment.

## Immutable tags

The publication must create:

```text
upstream-a961308-flask-sockets-513caf6
repo-<full repository commit SHA>
```

Prohibited mutable tags:

```text
latest
main
develop
```

Tags are discovery metadata only. Hermes must consume an independently accepted OCI index digest.

## Runtime gates inside publication

After pushing, the workflow pulls and validates the exact published digest.

Required checks include:

- image user is `dvga`;
- command is `python app.py`;
- `Flask-Sockets 0.2.1.1` contains `direct_url.json`;
- VCS `commit_id` and `requested_revision` both equal the immutable commit;
- all critical dependency versions match the accepted baseline;
- DVGA version is `2.2.0`;
- a network-isolated temporary container starts;
- `NET_RAW` is removed;
- `no-new-privileges` is active;
- internal HTTP responds successfully;
- SQLite database and uploads directory exist.

The temporary validation container is removed through a shell trap.

## OCI metadata

Required labels include:

- repository source and documentation;
- primary upstream repository and revision;
- Flask-Sockets repository and revision;
- declared base image;
- recipe identifier;
- Dockerfile SHA-256;
- MIT license.

## OCI digest roles

A successful publication contains:

1. one `linux/amd64` application manifest;
2. one `unknown/unknown` attestation manifest;
3. one OCI index referencing both.

Record separately:

- **OCI index/runtime digest** — the only digest allowed in Compose;
- **application manifest digest** — executable `linux/amd64` object;
- **attestation manifest digest** — provenance and SBOM metadata.

The attestation digest must never be used as a runtime reference.

## Manual publication

```bash
gh workflow run publish-dvga-ghcr.yml \
  --repo pestoura/hermes-security-labs \
  --ref main \
  -f publish=true
```

Dispatch exactly once. On failure, capture the run, job, failed step, annotations and logs before changing anything. Do not automatically repeat the workflow.

## Publication acceptance

Record:

- exact main SHA;
- workflow run and job IDs;
- primary upstream commit;
- Flask-Sockets commit;
- recipe and Dockerfile hash;
- declared and resolved base image;
- immutable tags;
- OCI index, application and attestation digests;
- attestation reference to the application manifest;
- anonymous package inspection;
- runtime dependency and application gates;
- SBOM and provenance;
- confirmation that no deployment occurred.

A `401`, `403` or package-not-found result must not be bypassed with an unapproved PAT. Private/read-only registry access remains tracked under issue #34.

## Hermes digest validation gate

Before changing Compose, Hermes must use a temporary ignored override that removes the local build and pins the exact accepted OCI index digest.

Required checks include:

- anonymous pull and OCI topology;
- labels, source revisions, recipe and Dockerfile hash;
- dependency parity with `hermes/dvga:a961308`;
- exact Flask-Sockets `direct_url.json`;
- non-root `dvga` runtime;
- DVGA 2.2.0, SQLite initialization and uploads directory;
- effective Compose without `build:`;
- healthy application and localhost-only binding;
- `NET_RAW` removal and `no-new-privileges`;
- temporary Kali DNS, TCP and HTTP access only to the application;
- idempotent connect, disconnect and destroy;
- stop, restart and reset without build;
- no drift in unrelated containers, networks, volumes or Prometheus;
- unchanged local historical image;
- destroyed final state and clean working tree.

Only `READY_FOR_DVGA_COMPOSE_MIGRATION` permits a separate migration PR.

## Runtime migration

The later migration PR must be limited to:

- replacing the local DVGA build and image tag with the accepted immutable GHCR index digest;
- changing lifecycle startup from any build behavior to `--pull missing` when required;
- removing runtime BuildKit/source-build dependencies from the manifest;
- updating GraphQL/DVGA documentation.

It must preserve:

- `127.0.0.1:${GRAPHQL_LAB_HOST_PORT:-5013}:5013`;
- healthcheck and restart behavior;
- resource limits;
- non-root runtime supplied by the image;
- `NET_RAW` removal;
- `no-new-privileges`;
- `graphql-vulnerable-lab` network and alias;
- lifecycle ownership and Kali controls.

No migration merge is allowed without explicit owner authorization.

## Post-merge acceptance

After migration, synchronize Hermes to the exact merge SHA and execute the versioned lifecycle from the repository. The rollout issue can close only after the complete post-merge test passes and the final host state is clean.

## Rollback

Rollback must reference a previously accepted immutable OCI index digest through a reviewed Compose change. Never roll back by moving or consuming a mutable tag.

Tracking issue: #50. Parent epic: #34.
