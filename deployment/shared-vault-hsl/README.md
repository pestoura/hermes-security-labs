# HSL shared Hermes Vault consumer

Status: repository consumer contract for CHG-HSL-085. `NO_AUTOMATIC_ACTIVATION`; live provider evidence remains a separate gate.

## Ownership boundary

The shared Vault service is **provider-owned** by `pestoura/hermes-vault`. HSL does not start, initialize, unseal, administer, back up, restore or configure the shared Vault.

HSL consumes only the published capability:

- endpoint `https://hermes-vault:8200` on `hermes-security-plane`;
- Transit mount `hsl-transit`;
- key `hsl-signing`;
- AppRole auth mount `approle`;
- AppRole `hsl-signer`.

The canonical non-secret mapping is `consumer-contract.yaml` and is closed by `consumer-contract.schema.json`.

## Credentials and HITL

RoleID/SecretID delivery is an operator **HITL** boundary. Credential values, Vault tokens, Shamir shares, private keys and passphrases must never appear in this repository, logs, evidence or ChatGPT context.

## Activation boundary

Repository acceptance does not select a signer and does not grant trust, execution or promotion authority. The canonical state remains `NO_DECISION`, `NO_SELECTION`, trust absent/unbound, `runtime_status=NOT_RUN`, `promotion_allowed=false`, campaign `BLOCKED/HOLD`.

The existing `VaultSignerAdapter` is the consumer application path. CHG-HSL-085 introduces no automatic loader/factory and no fallback signer.

Live acceptance requires the provider-owned HSL capability, limited AppRole authentication, bounded signing observation, signer attestation, R1–R8 evidence and the separate human decision lifecycle in issue #403.

## Legacy continuity

Historical evidence produced with the former HSL-local signer remains a verification concern only. New-signature authority moves to the shared capability only after the later acceptance/cutover gates pass. No bulk re-signing is implied by this contract.

## Hardened operator consumer

`consumer/` is the canonical ephemeral Vault CLI shell for future operator HITL windows. It replaces the ad-hoc official-Vault container used during the first Secret Zero observation, which exposed unnecessary root execution and image-declared writable `/vault/file` and `/vault/logs` volumes.

The dedicated consumer runs as UID/GID 10001, inherits no Vault data/log volumes, mounts only the public CA read-only, uses its own isolated namespace on `hermes-security-plane` and requires its own fresh `/32` observation immediately before issuance. CHG-HSL-104 hardens the shell only; it does not change the signer decision, bind trust or grant runtime authority.

## Signer decision evidence bundle

CHG-HSL-105 adds `signer-evidence/`, a repository-only assembly path for the four evidence classes required by issue #403. It accepts only sanitized public provider metadata and stages output outside Git.

A bundle may become `READY_FOR_HUMAN_DECISION` only after canonical signer-attestation verification, public trust-store lifecycle review and R1–R8 assessment all pass. That readiness state does not change `NO_DECISION`, `NO_SELECTION`, trust binding, Runner authority or target authority; the explicit human decision remains a later governed change.
