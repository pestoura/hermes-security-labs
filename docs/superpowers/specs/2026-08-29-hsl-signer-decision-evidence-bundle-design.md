# HSL signer decision evidence bundle — design

**Status:** Em validação — CHG-HSL-105.
**Scope:** repository preparation for issue #403 `APPROVED + NO_SELECTION`.
**Non-goal:** this change does not issue credentials, select a runtime candidate, bind trust, promote Runner execution or touch a target.

## Context

CHG-HSL-103 recorded sanitized Secret Zero `OBSERVED_PASS`; CHG-HSL-104 hardened the future operator consumer. Issue #403 still requires four evidence classes before the human signer record can move from `NO_DECISION` to `APPROVED`: capability evidence, signer attestation, trust-store manifest and an R1–R8 review.

The current repository has canonical verifiers for signer attestation, trust-store lifecycle and signer/trust composition, but no single fail-closed assembly path for a real shared-Vault observation. CHG-HSL-105 adds that path while preserving every authority boundary.

## Decision

Use one **sanitized decision-evidence bundle** built from a public provider observation. The live operator window supplies only an already-authorized AppRole session; repository tooling receives no RoleID, SecretID, wrapping token or Vault token as persisted input.
## Inputs and outputs

The live input is a normalized Vault Transit key observation containing only public/non-secret data: endpoint class, mount/key name, active key version, Ed25519 public key, exportability/plaintext-backup flags, signing support, observation time and sanitized capability/audit results.

The assembler produces four content-addressed artifacts:

1. `capability_evidence` — exact Vault capability and auditability observation;
2. `signer_attestation` — canonical TB1 observed signer envelope bound to the capability evidence digest;
3. `trust_store_manifest` — public key generation + signer/trust manifest with `trust_binding_allowed=false`;
4. `r1_r8_review` — deterministic requirement-by-requirement assessment referencing the first three artifacts and existing repository controls.

A fifth bundle manifest binds the four refs/digests and reports only `READY_FOR_HUMAN_DECISION` or `HOLD`. `READY_FOR_HUMAN_DECISION` is not a signer decision and grants no authority.

## Identity model

For the shared Vault lane the canonical signer identity is derived, never hand-entered:

- `provider_kind = VAULT`;
- `provider_ref = https://hermes-vault:8200/hsl-transit/hsl-signing`;
- `key_id = vault:hsl-transit:hsl-signing:v<observed-version>`;
- `algorithm = Ed25519`;
- `public_key_spki_sha256 = SHA-256(DER SubjectPublicKeyInfo)`.
## Fail-closed rules

The observation/bundle code must reject:

- any token, password, SecretID, RoleID, wrapping token, private key, passphrase or generic credential field;
- a non-Ed25519 key, inactive key, disabled signing, exportable key, plaintext backup enabled or missing public key;
- an observation without successful key-read/sign-verify/negative capability checks;
- missing or failed audit attribution evidence;
- stale/future timestamps outside the canonical signer-attestation freshness window;
- mismatched provider/key/SPKI identity across artifacts;
- missing/duplicate R1–R8 results or any failed requirement;
- any artifact that sets trust binding, automatic activation, promotion or execution authority.

The assembler must reuse the existing canonical `runtime_signer_attestation`, `trust_store_lifecycle` and `signer_trust_manifest` code rather than duplicating those security decisions.

## HITL boundary

Credential issuance, wrapping, unwrap, RoleID/SecretID handling and AppRole login remain operator-only. The operator consumer may execute the public-metadata observation after login, but the emitted file must contain only sanitized public metadata and booleans. No raw Vault response is committed automatically.

The future operator sequence must first start the hardened CHG-HSL-104 consumer, observe its fresh IPv4 `/32`, and bind any new SecretID/token to that consumer address. The historical CHG-HSL-103 `172.25.0.3/32` is evidence of that execution only and must not be reused as a future assumed consumer address.
## R1–R8 mapping

- **R1:** Vault Transit service-mediated signing; key metadata proves `exportable=false` and plaintext backup disabled.
- **R2:** provider ref, key version, domain and purpose are explicit and must match the generated TB1 descriptor.
- **R3:** only the public SPKI is used to build the explicit trust-store generation; no trust is installed.
- **R4:** the live capability observation requires a successful bounded sign/verify challenge; adapter fail-closed semantics remain canonical.
- **R5:** capability evidence requires a sanitized provider audit attribution result for the bounded sign operation.
- **R6:** the review binds existing fail-closed rotation/revocation lifecycle contracts and exact key-version identity.
- **R7:** the shared software Vault lane is reproducible from non-secret descriptors and requires no hardware procurement for LAB_L1.
- **R8:** schemas reject secret/private material and all generated evidence remains separated from authorization/promotion effects.

## State transitions

CHG-HSL-105 itself leaves:

- `signer-human-decision = NO_DECISION`;
- `supplier_selection = NO_SELECTION`;
- `selected_class = null`;
- trust absent/unbound;
- `promotion_allowed = false`;
- `execution_authority = NONE`;
- `runtime_status = NOT_RUN`.

After a later live bundle is `READY_FOR_HUMAN_DECISION`, a separate governed change may record the explicit human `APPROVED + NO_SELECTION` decision. Candidate binding, trust binding and live promotion remain later independent transitions.
