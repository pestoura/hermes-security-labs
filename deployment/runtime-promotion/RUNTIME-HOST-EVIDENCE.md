# Runtime host evidence — read-only acceptance boundary

`runtime_host_evidence.py` converts deployment declarations into **observed host evidence** without changing the host.

It consumes:

- the canonical Runner identity/socket descriptor;
- the canonical TB1 signer/trust-store descriptor;
- an explicit trust-store ownership/mode expectation.

## What it observes

Using Python standard-library read operations only, the collector checks:

- gateway service account exists with exact name/UID/GID/nologin shell;
- Runner service account exists with exact name/UID/GID/nologin shell;
- dispatch group exists with exact GID and required members;
- socket parent directory exists, is not a symlink and has exact owner/group/mode;
- Runner AF_UNIX socket exists, is actually a socket, is not a symlink and has exact owner/group/mode;
- installed Runner authorization trust store exists as a regular non-symlink file with exact owner/group/mode;
- the installed trust-store JSON canonically hashes to the exact public trust-store document approved in the TB1 deployment descriptor;
- the trust-store owner is independent from the gateway and Runner execution identities.

The output contains only account IDs/names, file/socket metadata and trust-store SHA-256 values. It never emits public-key contents or any private/secret material.

## Canonical command

```bash
python3 deployment/runtime-promotion/runtime_host_evidence.py \
  --descriptor deployment/runtime-promotion/templates/runtime-host-evidence-descriptor.example.yaml \
  --json check
```

The committed example is inert and is **not expected to pass on arbitrary hosts**. A live run must use a reviewed descriptor whose UID/GID/mode expectations correspond to the authorized deployment.

## Fail-closed model

The collector returns non-zero when any in-scope observation differs from the approved declaration. It does not:

- create users/groups;
- run `sudo`;
- create or connect sockets;
- call `chmod`, `chown`, `mkdir` or other mutators;
- install or modify a trust store;
- contact KMS/HSM/Vault/PKCS#11;
- read a private key;
- invoke Docker, scanners, target tools or network clients;
- promote any Runner policy.

Even when all host checks pass, `promotion_allowed` remains `false` and `runtime_status` remains `NOT_RUN`.

## Deliberate remaining evidence

A PASS does **not** close these live-promotion requirements:

- `USER_NAMESPACE_MAPPING_NOT_OBSERVED` — prove host/container UID/GID mapping for the actual processes;
- `SIGNER_PROVIDER_ATTESTATION_NOT_OBSERVED` — prove the external signer reference resolves to the intended protected key;
- `UNAUTHORIZED_PEER_NEGATIVE_TEST_NOT_RUN` — attempt the real socket from a non-allowed UID/GID and prove fail-closed refusal;
- `LIVE_AUDIT_SINK_NOT_OBSERVED` — observe the authenticated-principal audit event in the selected durable backend;
- `LIVE_RUNNER_EFFECT_NOT_RUN` — execute and evidence the bounded WebGoat L1 effect only after explicit promotion.

This collector is therefore **host evidence**, not promotion authority.
