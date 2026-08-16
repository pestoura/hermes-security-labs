# Hermes LAB_L1 Vault capability

Status: repository deployment package for CHG-HSL-082. Repository GREEN is not live-provider evidence.

## Security boundary

This package provisions one HashiCorp Vault node for LAB_L1 with Integrated Storage/Raft and mandatory TLS. It is deliberately not a production HA design.

- Vault image: `hashicorp/vault:1.21.4@sha256:4e33b126a59c0c333b76fb4e894722462659a6bec7c48c9ee8cea56fccfd2569`.
- No dev mode.
- Manual Shamir initialization: **3 shares**, **threshold 2**.
- No auto-unseal.
- Host API publication is **loopback** only: `127.0.0.1:${VAULT_LAB_L1_HOST_PORT:-18200}`.
- Vault joins only `vault-signer-internal`, a Docker network with `internal: true`.
- Port 8201 is not published to the host.
- Kali, Runner and target environments must never join `vault-signer-internal`.
- The initial **root token** exists only for bootstrap and must be revoked after limited AppRole authentication is proven.
- Signer SecretID delivery uses **response wrapping**, single use and a short TTL.

## Governance invariants

CHG-HSL-082 does not grant execution authority. Until the later evidence and decision lifecycle completes, the canonical state remains:

```text
signer-human-decision = NO_DECISION
supplier_selection = NO_SELECTION
trust = UNBOUND
campaign = BLOCKED / HOLD
promotion_allowed=false
runtime_status=NOT_RUN
execution_authority=NONE
```

A successful Vault signature or a GREEN repository gate does not change those values.

## TLS prerequisites

Private TLS material is operator-managed and must never be committed to this repository. Set `VAULT_LAB_L1_TLS_DIR` to a directory outside the repository containing:

```text
ca.pem
server.pem
server-key.pem
```

The server certificate must be valid for the names actually used by the two approved access paths. For the initial Hermes deployment, include at least:

- DNS SAN `vault` for the internal Docker service name;
- DNS SAN `localhost`;
- IP SAN `127.0.0.1` for loopback operator access.

Do not disable TLS verification. `VAULT_SKIP_VERIFY` must be unset.

## Operator CLI prerequisite

The bootstrap package deliberately uses the Vault CLI on the Hermes host so credentials do not have to be injected through Docker command arguments or container environment metadata. The operator CLI must be Vault `1.21.4` and must trust the LAB_L1 CA.

Example non-secret environment:

```bash
export VAULT_LAB_L1_HOST_PORT=18200
export VAULT_LAB_L1_TLS_DIR=/secure/operator-managed/hermes-vault-lab-l1-tls
export VAULT_ADDR=https://127.0.0.1:18200
export VAULT_CACERT="$VAULT_LAB_L1_TLS_DIR/ca.pem"
```

## Start sealed Vault

From `deployment/vault-lab-l1`:

```bash
docker compose config --quiet
docker compose up -d vault
```

The healthcheck deliberately treats both Vault exit code `0` and sealed exit code `2` as service liveness. Being sealed is expected before operator bootstrap and does not mean signing is ready.

## Bootstrap sequence

### 1. Preflight

```bash
./bootstrap/bootstrap.sh preflight
```

This validates HTTPS, CA availability and the exact operator CLI version.

### 2. Initialize exactly once

```bash
./bootstrap/bootstrap.sh init
```

Vault generates the 3 Shamir shares and initial root credential directly to the operator terminal. The repository tooling does not redirect, serialize or persist these values. Transfer the three shares to the approved custody holders outside Git/chat/log/evidence. Any two shares are required because the threshold is 2.

Re-running `init` against initialized storage is refused.

### 3. Unseal

```bash
./bootstrap/bootstrap.sh unseal
```

The script asks for two shares using silent input and sends each value to `vault operator unseal` through stdin. Shares are never placed in command-line arguments.

### 4. Authenticate with the bootstrap root credential

Load the initial root credential only into the current operator Vault CLI session/environment using the approved secret channel. Do not paste it into Git, shell history, tickets, evidence or chat.

### 5. Configure Transit, policies and AppRole

```bash
./bootstrap/bootstrap.sh configure
```

This one-time bootstrap creates:

- Transit mount `transit/`;
- Ed25519 key `hermes-lab-l1-signer`;
- `derived=false`;
- `exportable=false`;
- `allow_plaintext_backup=false`;
- exact signer policy allowing only key metadata read and signing update;
- observation-only policy;
- signer AppRole with no default policy, 10-minute token TTL, 30-minute maximum TTL, single-use 10-minute SecretID;
- observer AppRole with no default policy and bounded credentials.

The signer policy contains no Vault administration or key-lifecycle permission.

### 6. Retrieve non-secret RoleID references

```bash
./bootstrap/bootstrap.sh show-role-id signer
./bootstrap/bootstrap.sh show-role-id observer
```

RoleIDs are identifiers, not authentication by themselves. Store their references according to Hermes runtime configuration; they do not replace SecretID custody.

### 7. Issue wrapped SecretIDs

```bash
./bootstrap/bootstrap.sh issue-wrapped-secret-id signer
./bootstrap/bootstrap.sh issue-wrapped-secret-id observer
```

Each command returns a five-minute response-wrapping token rather than the underlying SecretID. The receiving component/operator must validate the wrapping token creation path, unwrap it once, and authenticate through AppRole before the initial root credential is revoked.

The signer SecretID is single-use. Do not record either the wrapped token or the unwrapped SecretID in repository evidence.

### 8. Verify the signer identity

After AppRole login, run the capability verifier using the limited signer session:

```bash
./bootstrap/verify-capability.sh
```

The verifier:

- requires TLS verification;
- verifies initialized/sealed/storage state;
- verifies exact Ed25519 key properties;
- emits only sanitized/public key identity hashes and signature identity hashes;
- proves safe read denials for management surfaces and unrelated Transit keys;
- performs a harmless fixed signing probe.

The existing `VaultSignerAdapter` remains the canonical application path for full Ed25519 verification over the TB1 canonical payload.

### 9. Verify observer authentication

Authenticate the observer AppRole and confirm it can read only the observation paths documented in `policies/operator-observer.hcl`. It must not be used for signing or management.

### 10. Revoke the initial root credential

Only after both limited AppRole paths have authenticated successfully:

```bash
export HERMES_VAULT_LAB_L1_ROOT_REVOKE_CONFIRM=OPERATIONAL_APPROLE_AUTH_VERIFIED
./bootstrap/bootstrap.sh revoke-root
unset HERMES_VAULT_LAB_L1_ROOT_REVOKE_CONFIRM
```

The command first verifies that the active credential actually has the root policy, then invokes self-revocation. If operational authentication has not been independently verified, stop and keep the campaign on HOLD rather than bypassing this gate.

## Evidence allowed from this change

Live CHG-HSL-082 evidence may contain only sanitized facts such as:

- Vault version/build;
- TLS peer/certificate fingerprint;
- initialized and sealed state transitions;
- storage type `raft`;
- Transit mount identity;
- key name/type/version;
- `derived=false`;
- `exportable=false`;
- `allow_plaintext_backup=false`;
- public-key/SPKI hash produced by the canonical adapter/evidence path;
- policy file hashes;
- safe negative authorization results;
- fixed signing probe result;
- initial root revocation outcome.

It must not contain Shamir shares, the initial root credential, SecretIDs, wrapping tokens or Vault client tokens.

## Reset and emergency HOLD

A reset is destructive to this capability and is not an automatic test cleanup action once real Raft data exists. If bootstrap state is ambiguous, credentials appear exposed, TLS validation fails, policy validation fails or key identity changes unexpectedly:

1. stop signer consumption;
2. retain `BLOCKED / HOLD`;
3. do not install/update trust;
4. do not change `NO_DECISION` or `NO_SELECTION`;
5. preserve sanitized audit/evidence;
6. investigate under a separate governed recovery/change procedure.

Deleting `hermes-vault-lab-l1-data` destroys the LAB_L1 Vault state and must therefore be an explicit operator action, never an implicit CI teardown.

## Definition of repository acceptance

Repository acceptance proves that the deployment package is structurally safe, testable and ready for controlled execution. It does **not** prove that the Hermes Vault instance has been initialized, that the real signing key exists, that AppRole credentials have been issued, or that root revocation has happened.

Those are `runtime_status=NOT_RUN` until actual Hermes execution evidence exists. The human signer decision in issue #403 remains separate.
