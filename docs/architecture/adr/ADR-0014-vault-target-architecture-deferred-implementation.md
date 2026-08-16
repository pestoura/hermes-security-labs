# ADR-0014 — VAULT as target signer custody architecture with deferred implementation

- **Status:** Accepted architectural direction — implementation deferred
- **Date:** 2026-08-16
- **Decision source:** CHG-HSL-073 design direction / issue #403 remains open
- **Supersedes:** none
- **Superseded by:** none

## Context

The LAB_L1 signer requirements require external custody, non-exportable private key material, purpose/domain binding, fail-closed provider availability, public trust binding, auditability and rotation/revocation semantics. The repository currently has no operational Hermes Vault capability, no selected signer provider, no installed trust store and no evidence-bearing live signer observation.

The architectural question was whether to implement or select a custody backend immediately to unblock the promotion campaign, use a temporary local signer, switch to a cloud KMS, choose HSM, or record a preferred architecture while keeping operational selection and provisioning separate.

Conflating architecture preference with operational custody evidence would make the repository state false. The design therefore separates target architecture from the later human/provider selection workflow.

## Decision

**Selected architectural target:** `VAULT` for the future LAB_L1 external signer custody implementation.

**Implementation is deferred.** No Vault endpoint, token, credential, key, provider binding, trust installation or runtime policy is created by this decision.

The operational source of truth remains:

```text
human decision = NO_DECISION
supplier/provider selection = NO_SELECTION
selected_class = null
human_decision_id = null
trust store = ABSENT
provider attestation = NOT_OBSERVED
promotion_allowed = false
runtime_status = NOT_RUN
campaign = BLOCKED / HOLD
```

Issue #403 remains the separate human decision/evidence gate. A future operational choice must still satisfy the canonical R1–R8 evidence requirements and does not become valid merely because this ADR prefers VAULT architecturally.

## Positive consequences

- Gives the software boundary a stable target without pretending infrastructure exists.
- Avoids a temporary provider decision that would create migration and cloud-dependency debt solely to unblock a gate.
- Preserves provider-neutral interfaces so KMS/HSM remain technically possible if requirements change.
- Keeps private-key material outside the repository and prevents a local fallback from being mistaken for admissible custody.
- Allows signer contracts, EvidenceVerifier, trust manifest and audit paths to progress independently of Vault provisioning.

## Negative consequences

- LAB_L1 signer promotion remains blocked until the actual Vault capability and evidence exist.
- A later Vault implementation may expose constraints not visible in provider-neutral contracts.
- The project carries an explicit deferred infrastructure dependency that must be tracked rather than forgotten.
- If cloud or hardware custody becomes mandatory, this direction may need supersession.

## Security implications

- No local PEM/OpenSSL/private-key-file fallback is admissible for LAB_L1 custody proof.
- Standalone `PKCS11` is an interface, not a custody class, and cannot satisfy R1 on its own.
- Provider-neutral CI signers remain `CI_ONLY / NON_AUTHORITATIVE / NOT_ADMISSIBLE_FOR_LAB_L1_PROMOTION`.
- Any future Vault implementation must fail closed on provider unavailability and must produce independently verifiable evidence of active signing, non-exportability, auditability and trust binding.
- Architecture preference never grants selection, trust, authorization, execution or promotion authority.

## Alternatives considered

### A. VAULT target architecture with implementation deferred — **Selected**

Chosen because it fits the intended Hermes platform direction, can satisfy the external custody model server-side, avoids premature hardware procurement and does not force a cloud-specific dependency before the Vault capability exists.

### B. Managed KMS as the immediate or future custody backend — **Deferred / admissible alternative**

KMS remains an admissible custody class and may offer strong non-exportability, audit and lifecycle controls with relatively low implementation friction. It was not selected as the target now because adopting it only to unblock LAB_L1 would create a cloud/tenancy dependency and later migration work without a current business or technical requirement for that dependency.

Reconsider if cloud tenancy becomes an accepted platform dependency, an existing managed KMS is already available with required evidence, or Vault cannot satisfy R1–R8 operationally.

### C. HSM as the custody backend — **Not selected for MVP**

HSM offers the strongest custody boundary but introduces higher procurement, integration and operational complexity than is proportionate for the first LAB_L1 slice.

Reconsider if an HSM is already available as a shared service, regulatory/contractual requirements mandate hardware-backed custody, or PROD assurance requires guarantees that Vault/KMS cannot satisfy.

### D. Local PEM/OpenSSL signer — **Rejected for LAB_L1 custody proof**

A local private key would undermine the external/non-exportable custody requirement and create a dangerous false-positive path to promotion. It may be used only for explicitly non-authoritative CI/testing where mechanically barred from LAB_L1 evidence.

### E. Standalone PKCS11 — **Rejected as a custody class**

PKCS11 describes an interface. Without independently verified evidence of the actual token/module and its custody guarantees, it does not prove external custody and cannot be selected on its own.

## Evidence and validation

The provider-neutral signer boundary, test-only signer, trust manifest composition, audit attribution and EvidenceVerifier linkage have been implemented and validated without changing the operational signer decision. Those software-hardening changes demonstrate that the target can remain deferred without blocking unrelated contract development.

No real Vault/KMS/HSM provider evidence is claimed by this ADR.

## Review triggers

Review this decision when:

- the Hermes Vault capability becomes operational and can be tested against R1–R8;
- Vault cannot provide required non-exportability, audit, availability or rotation/revocation evidence;
- cloud tenancy/dependency becomes formally accepted, making KMS strategically preferable;
- an existing HSM service becomes available with materially lower integration cost;
- PROD requirements introduce hardware-backed or jurisdictional custody constraints;
- provider availability, cost or operational complexity changes materially;
- #403 receives an explicit evidence-bearing human custody decision that conflicts with this target direction.
