# Vault LAB_L1 Operational Capability Design

Date: 2026-08-16
Status: Approved for autonomous implementation under owner global authorization
Change: CHG-HSL-082
Issue: #426
Parent decision/evidence issue: #403
Base: `737472d4dbd303c212f5d099d2a871fa04039312`

## Goal

Provision the first real, isolated Hermes LAB_L1 Vault capability that can support the already-merged `VaultSignerAdapter`, while preserving the fail-closed governance boundary: no signer selection, no trust installation, no runtime promotion and no Runner target effect.

## Facts and constraints

- CHG-HSL-081 already provides the provider-neutral Vault Transit Ed25519 signer adapter.
- `signer-human-decision.yaml` remains `NO_DECISION`.
- supplier selection remains `NO_SELECTION`.
- trust remains unbound.
- campaign remains `BLOCKED / HOLD`.
- `promotion_allowed=false`, `runtime_status=NOT_RUN`, `execution_authority=NONE` must remain unchanged.
- Real bootstrap creates sensitive Shamir shares, an initial root token and AppRole SecretID material. None may enter Git, logs or repository evidence.

## Approved architecture

### Vault runtime

- HashiCorp Vault Community `1.21.4`, pinned by multi-platform index digest:
  `hashicorp/vault:1.21.4@sha256:4e33b126a59c0c333b76fb4e894722462659a6bec7c48c9ee8cea56fccfd2569`.
- single node;
- Integrated Storage / Raft;
- TLS mandatory;
- no development mode;
- no HA;
- no auto-unseal;
- Shamir initialization with 3 shares and threshold 2.

### Network boundary

- dedicated Docker network `vault-signer-internal` with `internal: true`;
- Vault API exposed on host loopback only for operator bootstrap/health;
- no `0.0.0.0` host publication;
- no host publication for cluster port `8201`;
- signer-side component may join `vault-signer-internal`;
- Runner, Kali, Juice Shop, WebGoat and other target environments must not join this network;
- TLS is mandatory both over loopback and the internal network.

### Storage and container hardening

- dedicated persistent Raft volume;
- read-only root filesystem where compatible with Vault runtime needs, with explicit writable mounts for data/log/tmp only;
- `no-new-privileges:true`;
- drop all Linux capabilities, adding only capabilities demonstrably required by the pinned Vault image/runtime;
- no Docker socket;
- bounded CPU, memory and PID resources;
- no privileged container;
- no host network mode.

## TLS model

Repository contains configuration contracts and certificate path conventions only. Private CA keys and server private keys are generated/installed by the operator path outside Git.

Expected runtime paths:

- `/vault/tls/ca.pem` — public CA certificate;
- `/vault/tls/server.pem` — Vault server certificate;
- `/vault/tls/server-key.pem` — Vault server private key, mounted read-only from an operator-managed secret path;
- server certificate SANs must include the internal service name used by the signer and the loopback/operator name chosen by deployment tooling.

TLS verification may not be disabled in the operational compose path.

## Bootstrap lifecycle

The bootstrap script is intentionally split into non-secret preparation and secret-bearing operator execution.

1. Start Vault sealed with Raft storage and TLS.
2. Verify health endpoint and expected `initialized=false` state.
3. Operator initializes once with `key-shares=3`, `key-threshold=2`.
4. Shamir shares are delivered only to the operator output channel and never persisted by repository tooling.
5. Operator supplies two shares to unseal.
6. Initial root token is used only for bootstrap.
7. Enable Transit at `transit/`.
8. Create exact Ed25519 key `hermes-lab-l1-signer` with:
   - `derived=false`;
   - `exportable=false`;
   - `allow_plaintext_backup=false`.
9. Enable AppRole at `approle/`.
10. Install signer policy granting only:
    - read of metadata for `transit/keys/hermes-lab-l1-signer`;
    - update to `transit/sign/hermes-lab-l1-signer`.
11. Create signer AppRole with bounded token TTL/max TTL, bounded token uses where supported, and no default broad policy inheritance.
12. Create SecretID through response wrapping with single use and short TTL.
13. Create a separate limited operator identity/policy for health/observation tasks needed after root revocation.
14. Prove the signer identity cannot create/rotate/delete keys, alter auth methods, alter policies, mount engines or access unrelated paths.
15. Revoke the initial root token.
16. Repeat health/capability checks using limited identities.

## Secret handling

Repository automation must never:

- accept Shamir shares as command-line arguments;
- write shares/root token/SecretID/client tokens to files;
- echo those values;
- serialize them into JSON/YAML evidence;
- include them in exceptions;
- commit generated TLS private keys.

Secret-bearing operator commands consume values from stdin, ephemeral file descriptors or external secret references only. Any repository evidence contains only hashes/identifiers of public capability facts, never credential material.

## Policy boundary

The signer policy is exact-path and deny-by-absence. It contains no wildcard granting management capability.

Allowed paths:

- `transit/keys/hermes-lab-l1-signer` — `read`;
- `transit/sign/hermes-lab-l1-signer` — `update`.

Explicit validation must prove signer denial for:

- `sys/mounts/*`;
- `sys/auth/*`;
- `sys/policies/*`;
- `transit/keys/*` creation/update/delete operations except read of the exact key;
- `transit/keys/hermes-lab-l1-signer/rotate`;
- unrelated Transit keys;
- token/root administration.

## Repository components

Create a focused deployment slice under `deployment/vault-lab-l1/`:

- `compose.yaml` — hardened single-node runtime, loopback publication and internal network;
- `config/vault.hcl` — Raft + TLS server config;
- `policies/signer.hcl` — exact least-privilege signer policy;
- `policies/operator-observer.hcl` — post-bootstrap observation-only policy;
- `bootstrap/bootstrap.sh` — fail-closed operator bootstrap that never persists secrets;
- `bootstrap/verify-capability.sh` — public/sanitized capability checks;
- `README.md` — operator procedure and HITL boundaries.

Create repository tests under `deployment/tests/` to statically validate the compose/config/policies/scripts and governance invariants. Tests must not require a live Vault service in normal CI.

## Evidence contract for CHG-HSL-082

Repository/static evidence may assert only deployment design facts. Live capability evidence is emitted only after execution on Hermes and includes sanitized facts such as:

- Vault version and build revision;
- initialized/sealed state transitions;
- TLS peer identity/fingerprint;
- storage type `raft`;
- Transit mount enabled;
- key name/type/version;
- `derived=false`;
- `exportable=false`;
- `allow_plaintext_backup=false`;
- public Ed25519 key / SPKI SHA-256;
- signer policy hash;
- negative authorization checks;
- root-token revocation result;
- signing and local cryptographic verification result.

These observations are capability evidence only. They do not independently change #403 to APPROVED and do not install trust.

## Fail-closed rules

- no dev-mode fallback;
- no plaintext HTTP fallback;
- no `latest` or floating image tag;
- no automatic initialization if Vault is already initialized;
- no automatic root-token regeneration;
- no automatic trust-store mutation;
- no signer selection mutation;
- no live target execution;
- any ambiguity in bootstrap/capability checks results in HOLD.

## Testing strategy

### Static/TDD acceptance

Tests must fail before the new deployment slice exists and then prove:

1. image is pinned by tag and immutable digest;
2. no `-dev` command or dev environment variables are present;
3. only `127.0.0.1` publishes Vault API;
4. port 8201 is not host-published;
5. dedicated network is `internal: true`;
6. compose has no privileged/host-network/Docker-socket access;
7. Raft storage and TLS are mandatory in `vault.hcl`;
8. TLS disable flags are absent/false;
9. signer policy contains only the two exact allowed paths/capabilities;
10. bootstrap uses 3/2 Shamir and response wrapping with single-use SecretID;
11. scripts reject unsafe environment/config and do not write secret-bearing outputs;
12. governance files remain `NO_DECISION + NO_SELECTION + BLOCKED/HOLD`.

### Live acceptance on Hermes

Live acceptance is a later execution gate in the same change when the Hermes runtime tool is available. It must prove startup, initialization, unseal, least privilege, Transit signature verification, sanitized evidence and initial root revocation.

## Definition of done

CHG-HSL-082 may be repository-accepted when static/TDD/CI/Exact-SHA are green and the deployment package is safe to execute. It may be marked operationally complete only after the real Hermes capability evidence is captured.

Until live execution occurs, the authoritative status is `GREEN-REPO / RUNTIME NOT_RUN`, not live-ready.

## Decision record

- **Decision:** deploy Vault LAB_L1 as single-node Raft + TLS + manual Shamir 3/2.
- **Network:** loopback-only host operator API plus dedicated internal signer network.
- **Credential model:** ephemeral bootstrap root, then revocation; signer AppRole with response-wrapped single-use SecretID.
- **Alternatives rejected:** dev mode, LAN exposure, HA and auto-unseal for this LAB_L1 stage.
- **Risks accepted:** manual unseal and single-node availability are acceptable for LAB_L1; they are not the production target architecture.
- **State:** owner approved autonomous implementation; no additional micro-approval required before repository execution.