# Shared Vault pre-Secret-Zero live probe

Status: CHG-HSL-086 disposable network/TLS observation harness. This is not signer activation and not provider acceptance.

## Purpose

The probe joins only `hermes-security-plane`, verifies the exact accepted endpoint `https://hermes-vault:8200` with the operator-supplied public CA, derives its own IPv4 source identity and emits one sanitized `PRE_SECRET_ZERO_NETWORK_READY` record. It then remains alive so that exact network namespace can be used for the later operator HITL.

The probe exposes no ports, receives no Docker socket, runs as UID/GID 10001, has a read-only root filesystem, drops all Linux capabilities and uses `no-new-privileges`.

## Boundary

`SECRETID_ISSUANCE=NOT_RUN`

No RoleID, SecretID, wrapping token, Vault token, private key or passphrase is accepted or processed by this probe. `promotion_allowed=false` and `execution_authority=NONE` remain invariant.

There is `NO_AUTOMATIC_FALLBACK` to the historical `deployment/vault-lab-l1` signer. The container is disposable (`restart: "no"`) and is retained only long enough to preserve its `/32` through the explicit Secret Zero HITL.

## Operator input

The external named volume `hsl-shared-vault-ca` contains only the public CA PEM used to verify the shared Vault TLS listener. The operator populates that volume outside Compose before launch. The CA certificate is public trust material, not a workload credential. No credential value is supplied through Compose environment variables, files or command arguments.

## Acceptance

A valid observation has TLS verification enabled, a single IPv4 `/32`, `credential_stage=NOT_RUN`, `runtime_status=OBSERVED_PRE_SECRET_ZERO`, `promotion_allowed=false` and `execution_authority=NONE`.

Any DNS, endpoint, CA, TLS or network-identity failure is fail-closed and must not be treated as readiness.
