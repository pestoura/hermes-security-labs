# Private VAmPI pilot — reconciled current state

Date: 2026-08-09
Tracking issue: `#53`

This document reconciles the implementation state of the private GHCR VAmPI pilot with evidence that was produced after `docs/ghcr-private-readonly-transition.md` was originally written. It does not grant new authority and does not replace the security gates in that specification.

## Current decision

```text
PRIVATE_VAMPI_PUBLISHED_MANUAL_ACCESS_LIST_CONFIRMATION_IS_ONLY_PRE_CREDENTIAL_GATE
```

The private publisher and first private VAmPI publication are no longer future work. They already exist and were executed through an owner-triggered, manually gated workflow.

No new package, token, package permission, Compose reference or Hermes runtime change is authorized by this reconciliation.

## Confirmed implementation

### Private publisher

Repository:

```text
pestoura/hermes-private-registry-publisher
```

Confirmed properties:

- repository exists;
- repository visibility is `private`;
- publication workflow is `.github/workflows/publish-private-vampi.yml`;
- workflow is manually dispatched;
- workflow requires `publish=true`;
- workflow uses a GitHub-hosted runner;
- workflow publisher authentication uses that repository's ephemeral `GITHUB_TOKEN`;
- workflow permissions are limited to `contents: read` and `packages: write`;
- no Hermes deployment is performed.

Publisher commit used for the accepted publication:

```text
1ce1b1c72c20cf9267fbdc460f40fcfe1d310d08
```

### Controlled private publication

Owner-triggered workflow run:

```text
30680647184
```

The run completed successfully with `publish=true`.

Published identity:

```text
ghcr.io/pestoura/hermes-private-vampi
```

Recorded OCI evidence:

| Evidence | Digest / state |
|---|---|
| OCI index | `sha256:b1b66324a2d35cfe55e3edcd81f9f3c012907c71367df37f83d9ef63b500b3d3` |
| `linux/amd64` application manifest | `sha256:1e208a27f3e02c04cc81b1331d6bd5f18a9a42e60e11aa18b7ece8ded741c499` |
| attestation manifest | `sha256:e0f7c71cad1cf2b06e6d8a0f5c4d18b34c7667555d3e32a6b60f3fcd2d3ab14e` |
| provenance | BuildKit `mode=max` |
| SBOM | generated |
| package visibility | recorded as `private` in prior owner evidence |
| anonymous access | denial recorded as confirmed in prior owner evidence |
| Hermes runtime mutation | none |
| Hermes credential provisioning | none |

Immutable publication tags recorded by the workflow:

```text
upstream-f16052d
publisher-1ce1b1c72c20cf9267fbdc460f40fcfe1d310d08
```

The accepted public rollback remains:

```text
ghcr.io/pestoura/hermes-vampi@sha256:e7b2760d586ed2b4b15a689823a07816e32308bca293f9e8c08830c7b36c7229
```

## Gate reconciliation

| Gate | State | Evidence / constraint |
|---|---|---|
| A — documentation/source | `PASS` | private-publisher architecture and public rollback model are documented |
| B — private publisher readiness | `PASS` | private publisher exists and its GitHub-hosted workflow executed successfully |
| C — package namespace readiness | `PASS_HISTORICAL` | first publication completed under the new parallel private identity without mutating the accepted public package |
| D — private publication | `PASS` | run `30680647184`; exact OCI index/application/attestation digests recorded |
| E — anonymous denial | `PASS_RECORDED` | prior owner evidence records anonymous access denial as confirmed |
| Package repository-access acceptance | `BLOCKED_MANUAL_CONFIRMATION` | current integration cannot obtain the complete Packages repository-access list |
| F — authenticated read-only Hermes access | `NOT_RUN` | blocked until repository-access confirmation and separately authorized `read:packages` credential provisioning |
| G — safe negative control | `NOT_RUN` | requires the read-only credential after Gate F prerequisites |
| H — private-digest lifecycle parity | `NOT_RUN` | requires authenticated exact-digest pull on Hermes |
| I — versioned Compose migration | `NOT_RUN` | requires H PASS and a separately reviewed/authorized migration |
| rollback demonstration | `NOT_RUN` | follows accepted private runtime migration |

`PASS_HISTORICAL` means the precondition was satisfied by the already completed owner-controlled publication sequence. It is not an instruction to repeat publication.

## Current hard blocker

Before any Hermes registry credential is created or installed, manually inspect the GitHub Package settings for `hermes-private-vampi` and record that:

1. `pestoura/hermes-private-registry-publisher` is the intended linked/authorized repository;
2. `pestoura/hermes-security-labs` has no package Actions/read/write/admin access;
3. no other unapproved repository, user or team has access;
4. package visibility remains exactly `private`.

The current GitHub integration receives:

```text
403 Resource not accessible by integration
```

when querying the Packages REST resource required to enumerate these settings. Therefore the access list cannot be truthfully inferred from repository visibility, workflow success or the package name.

## Post-confirmation continuation

Once the manual package-access confirmation is recorded, resume automatically in this order:

1. separately authorize creation/provisioning of a PAT classic limited to `read:packages`;
2. store it outside Git through the approved isolated Docker credential model;
3. validate authenticated metadata inspection and pull by exact OCI index digest;
4. run the non-destructive negative control proving absence of write/delete authority;
5. validate VAmPI lifecycle using a temporary ignored override;
6. prove isolated Kali connectivity and zero unrelated drift;
7. open and validate a separate Compose migration PR;
8. merge only after its explicit owner gate;
9. run post-merge acceptance;
10. demonstrate rollback to the accepted public digest;
11. update deployment tracking and close `#53` only when all completion criteria are satisfied.

## Security boundary

This reconciliation intentionally does not:

- create or rotate a PAT;
- modify GitHub Package permissions or visibility;
- republish the image;
- expose package credentials;
- modify Compose;
- pull the private image on Hermes;
- contact customer or external targets;
- relax any Human-in-the-Loop or explicit owner authorization gate.
