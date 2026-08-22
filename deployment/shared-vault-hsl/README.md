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
