# HSL Shared Vault Live Provider Probe Design

- **Change:** CHG-HSL-086
- **Status:** Approved direction / implementation pending
- **Base:** CHG-HSL-085 / ADR-0018
- **Scope:** first bounded live observation lane for the shared Hermes Vault consumer

## Goal

Establish a disposable HSL consumer process on `hermes-security-plane`, verify DNS and TLS to the provider-owned shared Vault, and expose only the probe's own `/32` network identity before any AppRole credential is issued. The same running network namespace is retained across the later operator HITL so a CIDR-bound SecretID can be issued to exactly that consumer identity.

## Non-goals

This change does not issue, unwrap, read, persist or transmit RoleID, SecretID, wrapping tokens or Vault tokens. It does not select the signer, install trust, create provider evidence claiming acceptance, promote a campaign, run a target effect, administer Vault, or reactivate the legacy HSL Vault.

## Architecture

`deployment/shared-vault-hsl/probe/` adds a purpose-built non-root container. It attaches only to the external `hermes-security-plane`, exposes no ports, receives no Docker socket, drops all capabilities, uses a read-only root filesystem and mounts only the public Vault CA certificate read-only.

The probe performs a bounded pre-credential sequence:

1. validate the exact HTTPS endpoint supplied by the accepted consumer contract;
2. resolve `hermes-vault` inside the security plane;
3. establish a TLS connection with hostname and CA validation enabled;
4. derive its own source IPv4 address from the connected socket;
5. emit a sanitized readiness record containing only the endpoint, provider peer IP, consumer `/32`, TLS state and explicit no-authority markers;
6. remain alive without a shell workflow so the network namespace/IP stays stable for the subsequent HITL.

## Source-of-truth and drift

The accepted consumer descriptor remains canonical. Tests require the probe compose endpoint, external network and security boundaries to remain exactly aligned with `deployment/shared-vault-hsl/consumer-contract.yaml`. The probe is observation only and cannot become a parallel desired-state source.

## Secret-zero boundary

The probe deliberately stops before credential use. After a fresh `PRE_SECRET_ZERO_NETWORK_READY` observation, the Vault operator may issue a wrapped, single-use, short-TTL SecretID bound to the observed `/32`. RoleID and response-wrapping delivery remain out-of-band HITL and are never handled by this change or ChatGPT.

A later controlled command may share the already-running probe network namespace to execute the existing `VaultSignerAdapter`; that credential-bearing execution is a separate HITL/runtime gate and is not performed by the pre-secret probe.

## Output contract

The sanitized readiness record is closed and contains only:

- `schema_version=hsl.shared-vault-pre-secret-zero/v1`;
- `provider=hermes-shared-vault`;
- `vault_addr=https://hermes-vault:8200`;
- `peer_ip`;
- `consumer_cidr=<ipv4>/32`;
- `dns_resolved=true`;
- `tls_verified=true`;
- negotiated TLS version;
- `credential_stage=NOT_RUN`;
- `runtime_status=OBSERVED_PRE_SECRET_ZERO`;
- `promotion_allowed=false`;
- `execution_authority=NONE`.

No certificate private material, credential, token, secret reference value or target data is emitted.

## Fail-closed behavior

The probe exits non-zero and emits no readiness PASS when the endpoint differs from the accepted contract, CA material is unavailable, DNS fails, the source address is not IPv4, TLS verification fails, hostname verification fails, or the resolved provider cannot be reached.

## Runtime lifecycle

The container is disposable and may remain running only while waiting for the explicit Secret Zero HITL. It uses a deterministic name and `restart: "no"`; it is never a permanent service. Stop/removal after the evidence lane is an explicit cleanup step. No automatic fallback to the legacy signer exists.

## Acceptance

Repository acceptance requires targeted tests, canonical validation, security/lint gates, exact-SHA CI and no changes to signer human-decision/baseline/trust state. Live pre-secret acceptance additionally requires the running probe to report TLS verified and a single `/32` while Vault remains healthy. `SECRETID_ISSUANCE` remains `NOT_RUN` at this boundary.
