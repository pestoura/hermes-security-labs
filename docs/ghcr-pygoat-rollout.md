# PyGoat GHCR rollout

## Purpose

This runbook controls publication and later runtime migration of the project-adapted PyGoat image. Publication, digest validation and Compose migration are separate gates.

The publication workflow does not deploy to Hermes and does not alter the active PyGoat Compose runtime.

## Canonical package

```text
ghcr.io/pestoura/hermes-pygoat
```

## Immutable source

- repository: `https://github.com/adeyosemanputra/pygoat`;
- commit: `19d17cc8874861142b330636d068bbde54e86b85`;
- platform: `linux/amd64`;
- upstream license metadata: `NOASSERTION`.

The workflow fetches only the exact commit into runner temporary storage and verifies the detached `HEAD` before building.

## Recipe history

### Rejected recipe v1

The first publication used:

- recipe: `pygoat-python310-compat-v1`;
- Dockerfile SHA-256: `58389fedb2ec704c6e0bc1e9f899cdd07a3fdc08aac117b9da20b1cfa53d8d3d`;
- OCI index: `sha256:20616206188704f51cb1123083722531e13a84c19ac65ff721dfb8691acfe8da`.

The OCI object, provenance, SBOM, health, Kali separation and lifecycle tests passed. It was rejected for Compose migration because runtime inspection returned:

```text
ALLOWED_HOSTS=['*']
```

The cause was ordering inside upstream `settings.py`: the recipe replaced the declared list, but the later call `django_heroku.settings(locals())` configured `ALLOWED_HOSTS` again.

The rejected digest and its existing tags are historical evidence. They must not be used at runtime, deleted, overwritten or retagged as accepted.

### Corrected recipe v2

The corrected recipe uses:

- recipe: `pygoat-python310-compat-v2`;
- Dockerfile SHA-256: `be97d7312173241fdffd709ba9532d6c602b7780cc03d90c0a353fa216d835e6`;
- declared base: `docker.io/library/python:3.10-slim-bookworm`;
- immutable discovery tag: `upstream-19d17cc-recipe-v2`.

The recipe:

1. installs the Debian native build toolchain required by historical dependencies;
2. copies the immutable upstream source;
3. excludes upstream `psycopg2==2.9.3` and `PyYAML==5.1` from the requirements pass;
4. installs `psycopg2-binary==2.9.9` and `PyYAML==6.0.2`;
5. installs the remaining upstream requirements;
6. verifies exactly one original `ALLOWED_HOSTS` declaration and exactly one original django-heroku settings call;
7. sets the authorised host list to:

   ```text
   ['pygoat.herokuapp.com', '0.0.0.0', '127.0.0.1', 'localhost', 'pygoat']
   ```

8. changes `django_heroku.settings(locals())` to `django_heroku.settings(locals(), allowed_hosts=False)` so django-heroku cannot replace the authorised list;
9. runs `python manage.py migrate --noinput` during the build;
10. starts Gunicorn on `0.0.0.0:8000` with two workers.

The workflow hash-verifies the complete reconstructed Dockerfile and fails when either upstream source assumption changes.

## Dependency observation

`django-heroku==0.3.1` can install `psycopg2` transitively even though the project explicitly installs `psycopg2-binary==2.9.9`. Digest validation must record both installed distributions and compare the imported module behavior with the accepted local image.

This rollout does not modernize Python, Django or application dependencies.

## Publication workflow

Workflow:

```text
.github/workflows/publish-pygoat-ghcr.yml
```

The workflow:

- runs only through `workflow_dispatch` with `publish=true`;
- uses GitHub-hosted `ubuntu-24.04`;
- grants `contents: read` and `packages: write` only;
- pins third-party Actions by full commit SHA;
- uses Buildx with the `docker-container` driver;
- builds only `linux/amd64`;
- publishes with SBOM and provenance `mode=max`;
- executes no deployment.

## Immutable tags

The corrected publication must create:

```text
upstream-19d17cc-recipe-v2
repo-<full corrected repository commit SHA>
```

The previous `upstream-19d17cc` tag must not be moved. Prohibited mutable tags remain:

```text
latest
main
develop
```

Tags are discovery metadata only. Hermes must consume an independently accepted OCI index digest.

## Runtime configuration gate inside publication

After pushing the image, the workflow starts a temporary network-isolated container from the exact published digest and imports Django settings. Publication succeeds only when the effective value is exactly:

```text
['pygoat.herokuapp.com', '0.0.0.0', '127.0.0.1', 'localhost', 'pygoat']
```

This gate prevents a structurally valid package with a wildcard host policy from being reported as accepted.

## OCI digest roles

A successful publication contains:

1. one `linux/amd64` application manifest;
2. one `unknown/unknown` attestation manifest;
3. one OCI index referencing both.

Record separately:

- **OCI index/runtime digest** — the only digest allowed in Compose;
- **application manifest digest** — the executable `linux/amd64` manifest;
- **attestation manifest digest** — provenance and SBOM metadata.

The attestation digest must never be used as a runtime reference.

## Manual publication

```bash
gh workflow run publish-pygoat-ghcr.yml \
  --repo pestoura/hermes-security-labs \
  --ref main \
  -f publish=true
```

Dispatch exactly once. On failure, capture the run, job, failed step, annotations and logs before changing anything. Do not automatically repeat the workflow.

## Publication acceptance

Record:

- exact main SHA;
- workflow run and job IDs;
- upstream commit;
- recipe identifier and Dockerfile hash;
- declared and resolved base image;
- immutable tags;
- OCI index, application and attestation digests;
- attestation reference to the application manifest;
- anonymous package inspection;
- runtime `ALLOWED_HOSTS` gate;
- SBOM and provenance;
- confirmation that no deployment occurred.

A `401`, `403` or package-not-found result must not be bypassed with an unapproved PAT. Private/read-only registry access remains tracked under issue #34.

## Hermes digest validation gate

Before changing Compose, Hermes must use a temporary ignored override that removes the local build and pins the exact new OCI index digest.

Required checks include:

- anonymous pull and OCI topology;
- labels, source revision, recipe and Dockerfile hash;
- exact runtime `ALLOWED_HOSTS`;
- Django, PyYAML, Gunicorn and psycopg2 observations;
- applied migrations and Django system check;
- effective Compose without `build:`;
- healthy application and localhost-only binding;
- `NET_RAW` removal and `no-new-privileges`;
- temporary Kali DNS, TCP and HTTP access only to the application;
- idempotent connect, disconnect and destroy;
- stop, restart and reset without build;
- no drift in unrelated containers, networks, volumes or Prometheus;
- unchanged prior local image;
- destroyed final state and clean working tree.

Only `READY_FOR_PYGOAT_COMPOSE_MIGRATION` permits a separate migration PR.

## Runtime migration

The later migration PR must be limited to:

- replacing the local PyGoat build and image tag with the accepted immutable GHCR index digest;
- changing lifecycle startup from `--build` to `--pull missing`;
- removing runtime BuildKit/source-build dependencies from the manifest;
- updating PyGoat documentation.

It must preserve:

- `127.0.0.1:${PYGOAT_HOST_PORT:-8000}:8000`;
- healthcheck and restart behavior;
- resource limits;
- `NET_RAW` removal;
- `no-new-privileges`;
- `pygoat-lab` and its alias;
- lifecycle ownership and Kali controls.

No migration merge is allowed without explicit owner authorization.

## Post-merge acceptance

After migration, synchronize Hermes to the exact merge SHA and execute the normal versioned lifecycle. The rollout issue can close only after the complete post-merge test passes and the final host state is clean.

## Rollback

Rollback must reference a previously accepted immutable OCI index digest through a reviewed Compose change. Never roll back by moving or consuming a mutable tag.

Tracking issue: #46. Parent epic: #34.
