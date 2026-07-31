# GHCR private read-only transition

## Status

This document defines the transition from the temporary public GHCR operating model to private package consumption by Hermes.

It is an architecture and operations specification only. It does not create a package, token, organization, repository, workflow run, visibility change or deployment.

Tracking issue: `#53`.
Parent epic: `#34`.
Related deployment tracking: `#7`.

## Decision drivers

The transition must:

- preserve every accepted public runtime digest;
- avoid deleting, replacing or retagging accepted artefacts;
- give Hermes download-only access;
- keep credentials outside Git and evidence;
- retain GitHub-hosted publication and prohibit deployment from GitHub to Hermes;
- prove that anonymous access is denied for the private package;
- prove that authenticated access can pull only the accepted digest;
- allow rollback to an already accepted public digest;
- migrate only one laboratory at a time.

## Confirmed platform constraints

GitHub Container Registry supports granular visibility and access permissions for packages scoped to a personal account or organization.

A newly published package is private by default. A private package can later be made public, but a package that has been made public cannot be changed back to private.

GitHub Packages command-line authentication outside GitHub Actions requires a personal access token (classic). A download-only credential needs `read:packages` and the token owner must have read access to the package. The credential must not include `write:packages`, `delete:packages` or repository write permission.

A repository workflow should publish with its ephemeral `GITHUB_TOKEN`, not a long-lived personal token. The package must explicitly permit the workflow repository through package Actions access or the verified repository-linkage model.

Private package storage and data transfer are metered. The account or organization must have sufficient included allowance and a usable budget/payment configuration before publication.

## Existing public baseline

The first-generation package identities are public and cannot become the private target state.

| Environment | Public package | Accepted OCI index digest |
|---|---|---|
| VAmPI | `ghcr.io/pestoura/hermes-vampi` | `sha256:e7b2760d586ed2b4b15a689823a07816e32308bca293f9e8c08830c7b36c7229` |
| DVAPI | `ghcr.io/pestoura/hermes-dvapi` | `sha256:18d9175aa8031568c95e5bd9dcd9597a0b575aec7a742d81c7f34973c506c872` |
| NodeGoat | `ghcr.io/pestoura/hermes-nodegoat` | `sha256:0e0cbd8b0c82db51b1dfff9c58a391653774fa3b7b4c68ad10e6cda4c173ab6c` |
| PyGoat | `ghcr.io/pestoura/hermes-pygoat` | `sha256:3df04f28225c1b9a7a888edbb724540364c3d88967578fc688d47632272069a9` |
| DVGA | `ghcr.io/pestoura/hermes-dvga` | `sha256:6e5fcb0bca47ac75fc218d2a62858673964d8703341bb6387841a84b7409d2d4` |

These packages remain:

- historical accepted artefacts;
- current runtime references until a private replacement passes every gate;
- rollback references during the private migration;
- immutable by policy.

The transition must not:

- delete a public package or version;
- move an existing tag;
- overwrite an accepted digest;
- attempt to change a public package back to private;
- change all five runtimes in one operation.

## Namespace model

### Stage 1: personal-account pilot

The proposed first pilot uses a new package identity under the existing personal namespace:

```text
ghcr.io/pestoura/hermes-private-vampi
```

This name is deliberately different from `hermes-vampi`. It prevents accidental mutation of the accepted public package and makes the access boundary visible in logs and evidence.

The package must remain private from first publication.

The package may be linked to `pestoura/hermes-security-labs` for source metadata, but access inheritance from the public repository must not be relied on for confidentiality. Package access must be verified in granular mode. The workflow repository receives only the package Actions permission needed to publish and validate the package.

### Stage 2: organization decision

Before migrating all five packages, review whether a dedicated GitHub organization is required.

An organization is preferred when the project needs:

- teams and read-only human roles;
- a machine-user lifecycle independent of the repository owner;
- centralized package policies and billing;
- separation between owner administration and runtime consumption;
- future contributors without write access to the personal repository.

Organization creation, repository transfer or package publication in another namespace requires a separate explicit owner decision.

## Package access model

### Publisher

The publication workflow uses:

```yaml
permissions:
  contents: read
  packages: write
```

Additional permissions are allowed only when required by the reviewed attestation implementation.

Publication rules:

- GitHub-hosted runner only;
- `GITHUB_TOKEN` only;
- explicit `workflow_dispatch` approval gate;
- immutable source and dependency revisions;
- immutable package tags;
- no `latest`, `main`, `master` or `develop` tag;
- SBOM and provenance retained;
- no deployment to Hermes;
- no personal token stored in Actions secrets for publication when `GITHUB_TOKEN` is sufficient.

### Package settings

After the first publication and before any Hermes authentication test, verify:

- visibility is `private`;
- the package has the intended source repository link;
- the package does not unintentionally expose access through inherited permissions from the public repository;
- `pestoura/hermes-security-labs` has only the required GitHub Actions package access;
- no unapproved user, repository or team has package access;
- package deletion is not part of the workflow;
- package versions and immutable tags are recorded.

Do not make the package public as a troubleshooting step. That decision is irreversible for the package identity.

### Hermes consumer

Hermes uses a dedicated personal access token (classic) with:

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

The token owner must have read access to the private package. The token is for registry consumption only and must not be reused by GitHub Actions publication workflows.

## Credential handling

Credential creation, installation, rotation and revocation are host-operations changes and require explicit owner authorization.

The credential must never appear in:

- Git history;
- Compose files;
- manifests;
- documentation examples with a real value;
- command-line arguments;
- process listings;
- shell tracing;
- screenshots;
- evidence files;
- Hermes agent memory;
- issue or pull request comments.

Authentication must use standard input:

```bash
printf '%s' "${GHCR_READ_TOKEN}" |
  docker --config "${HERMES_GHCR_DOCKER_CONFIG}" \
  login ghcr.io \
  --username pestoura \
  --password-stdin
```

The implementation must use an isolated Docker configuration directory, not the general operator configuration.

Preferred storage is a supported Docker credential helper or another approved host secret store. A plain Docker `config.json` is not encrypted; using it for a pilot requires explicit approval, directory mode `0700`, file mode `0600`, a documented expiry and immediate rotation after the test.

The evidence process may record:

- login success or failure;
- Docker config directory path;
- file ownership and modes;
- credential-helper name;
- token creation and expiry dates;
- token scope names;
- rotation identifier.

It must not record the token, authorization headers, Docker auth value or decoded credential material.

## Validation gates

### Gate A: billing and package preconditions

Confirm before publication:

- private package storage allowance is available;
- data-transfer allowance is available;
- billing and budget configuration will not block the test;
- the package name does not already exist;
- the package will be created private;
- the repository remains public unless a separate decision changes it;
- no self-hosted runner or Hermes Docker socket is used.

Failure decision:

```text
BLOCKED_GHCR_PRIVATE_BILLING
```

### Gate B: private publication

Publish exactly once through the reviewed GitHub-hosted workflow.

Required result:

- new private package identity;
- immutable source tag;
- repository-SHA tag;
- OCI index, application manifest and attestation manifest recorded separately;
- SBOM and provenance present;
- no deployment;
- no mutation of `ghcr.io/pestoura/hermes-vampi`.

Decision:

```text
READY_FOR_PRIVATE_GHCR_ACCESS_VALIDATION
```

### Gate C: anonymous denial

From a Docker configuration directory with no GHCR credentials:

- metadata inspection by the private digest must fail;
- pull by the private digest must fail;
- the failure must be an authentication or authorization denial;
- no fallback to the public package is allowed.

Evidence must contain only the sanitized error and package identity.

### Gate D: authenticated read-only access

Using the isolated read-only Docker configuration:

- login succeeds through standard input;
- exact-digest metadata inspection succeeds;
- exact-digest pull succeeds;
- OCI topology, labels, SBOM and provenance remain valid;
- the pulled image ID and architecture are recorded;
- no mutable tag is consumed.

### Gate E: safe negative control

Do not upload a manifest, blob or tag and do not call a delete endpoint.

Prove the absence of write/delete authority through both of the following:

1. inspect the authenticated token scope metadata and confirm `read:packages` is present while `write:packages`, `delete:packages` and `repo` are absent;
2. request registry authorization for a push-capable scope without uploading content and confirm that push authority is denied or omitted.

Authorization headers and bearer tokens must be redacted before evidence is written.

A destructive push/delete test is prohibited.

### Gate F: lifecycle parity

Before a versioned Compose change, use a temporary ignored override to consume the private OCI index digest.

Repeat the complete accepted VAmPI lifecycle:

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

### Gate G: versioned migration

A separate PR may replace only the public VAmPI package identity and digest with the independently accepted private package identity and digest.

The PR must not change:

- application behavior;
- ports;
- healthcheck;
- resource limits;
- hardening;
- network and Kali controls;
- publication workflows for the other packages.

Merge requires explicit owner authorization and post-merge Hermes acceptance.

## Rollback boundary

During the pilot, rollback is a reviewed Compose change back to:

```text
ghcr.io/pestoura/hermes-vampi@sha256:e7b2760d586ed2b4b15a689823a07816e32308bca293f9e8c08830c7b36c7229
```

Rollback must:

- use the exact accepted public digest;
- never use a mutable tag;
- preserve lifecycle and hardening controls;
- run the complete post-change acceptance;
- update deployment tracking under `#7`;
- leave the private package untouched for diagnosis.

The public package may be retired from active use only after the private pilot, rollback test and deployment tracking are accepted. It is not deleted.

## Deployment tracking integration

The future deployment record under `#7` must distinguish:

- registry visibility class: `public` or `private`;
- package identity;
- accepted OCI index digest;
- local image ID;
- architecture;
- Git commit;
- effective Compose hash;
- authentication mode: `anonymous` or `read-only-token`;
- credential rotation identifier, not the secret;
- SBOM/provenance verification result;
- rollback digest.

Drift is present when the running package identity or digest differs from the accepted Git commit, even when the local image ID points to equivalent layers.

## Evidence requirements

Use an ignored directory under `.runtime/evidence/`.

Allowed evidence:

- package names and digests;
- sanitized HTTP status and registry errors;
- workflow run and job identifiers;
- image metadata and OCI topology;
- token scope names without token value;
- file modes and owners;
- lifecycle results;
- drift comparison.

Forbidden evidence:

- token values;
- Basic or Bearer authorization headers;
- Docker `auth` fields;
- cookies;
- private key material;
- unredacted environment dumps;
- shell history containing credentials.

## Implementation sequence

1. Merge this documentation through an explicitly authorized PR.
2. Confirm account billing/quota readiness.
3. Explicitly authorize the pilot package name and credential creation.
4. Add a separate private VAmPI publication workflow or a safely parameterized reviewed workflow.
5. Publish once and verify private package settings.
6. Provision the read-only credential outside the repository.
7. Execute anonymous-deny, authenticated-read and safe negative-control gates.
8. Validate the exact private digest through a temporary override.
9. Open a separate VAmPI private-runtime migration PR.
10. Obtain explicit merge authorization.
11. Run post-merge acceptance.
12. Demonstrate rollback to the accepted public digest.
13. Update deployment tracking and drift detection.
14. Decide whether the remaining packages use the personal namespace or a dedicated organization.

## Completion criteria

Issue `#53` can close only when:

- the architecture document is merged;
- the owner has selected and authorized the pilot namespace;
- billing/quota readiness is proven;
- the private package is published without changing the public package;
- anonymous pull is denied;
- authenticated exact-digest pull succeeds;
- absence of write/delete authority is proven safely;
- VAmPI lifecycle passes from the private digest;
- a separate Compose migration is merged and accepted;
- rollback to the accepted public digest is demonstrated;
- deployment tracking records the private runtime without secrets;
- final state is clean.

Until then, the five accepted public packages remain the canonical runtimes.