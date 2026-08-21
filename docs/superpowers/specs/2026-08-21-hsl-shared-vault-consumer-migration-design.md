# HSL Shared Vault Consumer Migration — Design

- **Status:** Approved direction, implementation pending
- **Date:** 2026-08-21
- **Change:** CHG-HSL-085
- **Architecture decision:** ADR-0018

## Purpose

Replace the future-new-signature dependency on the HSL-owned isolated Vault package with a consumer-only contract to the shared `pestoura/hermes-vault` service, without changing signer selection, trust binding, campaign promotion or execution authority.

This change is repository-side only. Live Vault capability bootstrap and credential handoff remain operator/HITL work owned by `hermes-vault`.

## Known facts

- `VaultSignerAdapter` already accepts configurable Vault endpoint, Transit mount, key name, AppRole mount and secret references.
- `hermes-security-plane` exists and is Docker-internal; `vault-vault-1` is attached under the `hermes-vault` alias.
- Shared Vault runtime is healthy and its real isolated restore drill is accepted.
- HSL issue #403 already authorizes the VAULT operational implementation lane but still requires evidence before an evidence-bearing human signer decision.
- HSL `origin/main` remains `NO_DECISION / NO_SELECTION / trust ABSENT / BLOCKED-HOLD`.

## Selected approach

Add one closed, non-secret HSL consumer descriptor. It describes the shared Vault capability but grants no authority and contains only references, never credential values.

Canonical values:

```yaml
provider: hermes-shared-vault
vault_addr: https://hermes-vault:8200
transit_mount: hsl-transit
key_name: hsl-signing
approle_mount: approle
approle_name: hsl-signer
role_id_ref: secretref://hermes-vault/hsl-signer/role-id
secret_id_ref: secretref://hermes-vault/hsl-signer/secret-id
```

The descriptor is not automatically loaded by production runtime in CHG-HSL-085. It is a versioned handoff contract for the already-existing adapter and for the later live observation/configuration lane.

## Ownership

`hermes-vault` owns Vault deployment, TLS server identity, mount/key lifecycle, AppRole policy, credential issuance, audit, backup and recovery. HSL owns application consumption, signer observation, evidence composition and the human/trust transition after evidence is accepted.

## Security and lifecycle constraints

- No SecretID, Vault token, private key, Shamir share, passphrase or recovery locator in Git, logs or evidence.
- No HSL code may enable mounts/auth methods, create keys, create policies or issue credentials in the shared Vault.
- No automatic fallback from shared signer failure to the legacy HSL signer.
- TLS verification is mandatory; `VAULT_SKIP_VERIFY`/equivalents are forbidden.
- The consumer identity must be least privilege: sign, verify and key-metadata read only for `hsl-transit/hsl-signing`.
- The descriptor must preserve provider-neutral application code: the adapter remains configurable and no shared-service values are hard-coded into `vault_signer_adapter.py`.
- Legacy `deployment/vault-lab-l1` remains non-authoritative for new signatures. Historical verification continuity is preserved until a later explicit retirement change.

## State invariants

CHG-HSL-085 must not modify the operational decision state:

```text
signer-human-decision = NO_DECISION
supplier_selection = NO_SELECTION
selected_class = null
human_decision_id = null
trust = ABSENT / UNBOUND
provider attestation = NOT_OBSERVED
promotion_allowed = false
runtime_status = NOT_RUN
execution_authority = NONE
campaign = BLOCKED / HOLD
```

## Repository artefacts

CHG-HSL-085 will add:

- `deployment/shared-vault-hsl/consumer-contract.schema.json` — closed schema for the non-secret consumer handoff;
- `deployment/shared-vault-hsl/consumer-contract.yaml` — canonical shared-Vault HSL descriptor;
- `deployment/shared-vault-hsl/README.md` — ownership, credential and activation boundaries;
- `deployment/tests/test_shared_vault_hsl_consumer.py` — schema, exact-value, adapter-compatibility and invariant tests;
- `changes/CHG-HSL-085.yaml` — honest repository change record.

It will update `deployment/vault-lab-l1/README.md` to mark the package as legacy/non-authoritative for new signatures after shared capability acceptance. No destructive removal occurs in this change.

## Acceptance criteria

1. Descriptor validates against a closed schema and contains no unknown fields.
2. Endpoint is exactly `https://hermes-vault:8200`; mount/key/AppRole names match the provider contract.
3. Credential fields are references only and use the approved `secretref://` scheme.
4. An instance of `VaultSignerConfig` can be built from the descriptor's adapter-facing values without changing `vault_signer_adapter.py`.
5. Tests prove no shared-Vault administrative commands are introduced in HSL consumer artefacts.
6. Legacy package documentation explicitly forbids automatic fallback/new signing authority.
7. Existing signer decision/baseline files are byte-unchanged.
8. `promotion_allowed=false`, `runtime_status=NOT_RUN`, `execution_authority=NONE` and campaign HOLD remain true.

## Live handoff after repository acceptance

The next live lane is provider evidence, not automatic activation:

1. `hermes-vault` creates/verifies `hsl-transit/hsl-signing`, policy and `hsl-signer` AppRole under short-lived JIT administration.
2. RoleID/SecretID delivery is HITL and remains outside the model/repository.
3. HSL performs a bounded live key observation and fixed signing probe through `VaultSignerAdapter`.
4. Public/sanitized evidence is converted into signer attestation, provider evidence and R1–R8 review inputs.
5. Issue #403 may then move to the explicit human `APPROVED + NO_SELECTION` state if evidence passes.
6. Selection, trust installation and live promotion remain later, independent governed changes.

## Out of scope

- changing target scope or the CHG-HSL-084 S2 refusal;
- enabling live Runner/WebGoat effects;
- changing `signer-human-decision.yaml` or `signer-baseline.yaml`;
- issuing or persisting credentials;
- deleting the legacy Vault package;
- production HA, auto-unseal or Enterprise Vault features.

## Recommendation

Proceed with the descriptor-only migration contract first. It removes topology ambiguity immediately without pretending that live provider evidence or signer selection already exists. Then perform the operator-gated shared-Vault bootstrap and evidence lane.
