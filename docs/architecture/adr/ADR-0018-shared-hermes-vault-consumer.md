# ADR-0018 — HSL consumes the shared Hermes Vault

- **Status:** Accepted
- **Date:** 2026-08-21
- **Decision owners:** HSL architecture owner / Hermes Vault service owner
- **Related:** ADR-0014, CHG-HSL-081, CHG-HSL-082, shared Vault ADR-018..023

## Context

CHG-HSL-081 implemented a provider-neutral Vault Transit signer adapter. CHG-HSL-082 then added a repository-safe isolated `vault-lab-l1` deployment package, while deliberately leaving live provisioning `NOT_RUN`.

The shared `pestoura/hermes-vault` service is now operational on HermesJarvas with TLS, Raft, Shamir 3/2, audit, JIT administration and a verified isolated restore drill. HSL is its first consumer.

Running a second HSL-owned Vault for new signatures would duplicate custody, recovery, audit and operational controls. It would also conflict with the approved shared-service ownership model.

## Decision

HSL will consume the shared Hermes Vault for new LAB_L1 signer capability. The canonical consumer contract is:

- endpoint: `https://hermes-vault:8200` on `hermes-security-plane`;
- Transit mount: `hsl-transit`;
- key: `hsl-signing` (Ed25519);
- AppRole auth mount: `approle`;
- AppRole: `hsl-signer`;
- credentials referenced only through secret references, never stored in this repository.

The existing `VaultSignerAdapter` remains the application adapter. No HSL-specific Vault client is introduced and no provider values are hard-coded into the adapter.

The HSL-owned `deployment/vault-lab-l1` package is retained only as historical implementation provenance and, after shared-signer acceptance, as legacy verification continuity. It is not the authority for new signatures and must not be started as an automatic fallback.

## Governance boundary

This ADR does **not** itself move the signer decision or promotion state. Until separate evidence-bearing transitions complete:

```text
signer-human-decision = NO_DECISION
supplier_selection = NO_SELECTION
selected_class = null
trust = ABSENT / UNBOUND
promotion_allowed = false
runtime_status = NOT_RUN
execution_authority = NONE
campaign = BLOCKED / HOLD
```

Shared Vault bootstrap, RoleID/SecretID delivery, live signer observation, R1–R8 review, human decision, trust installation and live promotion are separate gates. No missing gate may be inferred from repository acceptance.

## Consequences

### Positive

- HSL reuses one shared operational Vault instead of duplicating custody, recovery, audit and lifecycle controls.
- The existing provider-neutral `VaultSignerAdapter` remains unchanged and testable against a non-secret descriptor.
- New-signing authority and legacy verification continuity stay explicitly separated.

### Negative

- HSL now depends on the availability and consumer contract of the shared Vault service.
- Consumer onboarding still requires a separate live identity handoff and capability acceptance before any signing authority can be enabled.
- The legacy HSL Vault package must remain clearly non-authoritative until a later retirement decision removes it.

## Security implications

- HSL receives no Vault administration capability.
- The shared Vault owns mount/key/AppRole lifecycle and audit/recovery controls.
- HSL gets only sign/verify/key-metadata capabilities through `hsl-signer`.
- There is no automatic fallback to the legacy signer.
- Existing historical signatures remain verifiable under the legacy public identity until a later retirement decision.

## Alternatives considered

1. **Shared Vault consumer descriptor + existing adapter — selected.** Minimal duplication, explicit ownership, fail-closed and testable without credentials.
2. **Hard-code shared Vault values in `VaultSignerAdapter` — rejected.** Couples application code to one deployment and weakens provider-neutrality.
3. **Keep a dedicated HSL Vault as the primary signer — rejected.** Duplicates recovery/audit/custody and conflicts with the approved shared-service model.

## Evidence and validation

Repository acceptance requires a closed, non-secret consumer descriptor, tests proving exact endpoint/mount/key/AppRole references and explicit assertions that signer decision, trust, runtime and promotion remain inactive.

Live acceptance additionally requires the shared Vault HSL capability, limited identity proof, signer observation/attestation, R1–R8 evidence, historical verification continuity and the separate human decision lifecycle in issue #403.

No SecretID, Vault token, Shamir share, private key, passphrase or recovery location may appear in repository evidence.


## Review triggers

Revisit this decision if the shared Vault service ownership model changes, the HSL signer no longer uses Transit/AppRole semantics, consumer isolation cannot be maintained, or the human signer-selection lifecycle rejects the shared-Vault provider. Repository acceptance alone is not a trigger to enable runtime authority.
