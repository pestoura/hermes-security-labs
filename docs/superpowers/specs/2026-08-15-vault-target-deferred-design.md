# VAULT target architecture with deferred implementation

Date: 2026-08-15
Status: Approved architecture direction; implementation deferred
Scope: LAB_L1 external signer custody path for `VAL-HSL-RUNNER-L1-LIVE-PROMOTION`

## Context

The LAB_L1 signer contract requires an external custody backend that can satisfy the accepted R1-R8 baseline. The current repository deliberately separates human choice, provider/candidate evidence, trust binding and live promotion.

The Hermes environment does not yet have an operational Vault capability. Selecting or provisioning a concrete Vault instance now only to unblock the LAB_L1 signer gate would create premature infrastructure coupling and could lead to a false claim that custody, trust and attestation have already been proven.

The current machine-readable human-decision contract supports only `NO_DECISION` and `APPROVED`. An `APPROVED` record requires evidence references and represents an operationally admissible human decision, not merely a preferred future architecture. Therefore this design must not overload `APPROVED` to mean "preferred but not implemented".

## Decision

Adopt `VAULT` as the preferred target custody architecture for the LAB_L1 external signer, while explicitly deferring implementation, candidate binding, trust installation and provider attestation until a Vault capability exists in Hermes.

This is an architecture-target decision, not an operational supplier/candidate selection.

The authoritative operational state remains:

- `signer-human-decision.yaml`: `NO_DECISION`;
- `supplier_selection`: `NO_SELECTION`;
- baseline `selected_class`: `null`;
- `human_decision_id`: `null`;
- trust store: absent;
- provider attestation: not observed;
- `promotion_allowed=false`;
- `runtime_status=NOT_RUN`;
- campaign: `BLOCKED / HOLD`.

## Why VAULT is the target

For the current LAB_L1/MVP stage, VAULT provides the preferred balance of:

- service-mediated signing with non-exportable-key semantics when correctly deployed;
- compatibility with on-premises, hybrid and later cloud deployments;
- lower bring-up friction than a dedicated HSM estate;
- less architectural dependence on a single cloud provider than choosing KMS only to satisfy a temporary blocker;
- a clean path to audited signing, rotation and revocation without placing private key material in the Runner or repository.

This does not prove that a future Vault deployment satisfies R1-R8. The actual deployment must still be independently attested and evidence-verified before it can become an admissible signer candidate.

## Alternatives considered

### KMS

Advantages: strong managed custody primitives, mature auditability and straightforward non-exportability evidence in many providers.

Limitations: introduces an external cloud/provider dependency before the Hermes deployment model requires one; using KMS only as a temporary LAB_L1 unblocker would create migration work and weaken provider neutrality.

Decision: admissible future alternative, not the preferred current target.

### HSM

Advantages: strongest dedicated custody boundary and mature assurance model.

Limitations: procurement, operational complexity and cost are disproportionate for the first isolated LAB_L1 effect.

Decision: retain for later higher-assurance/production profiles where justified.

### Local software key / PEM / OpenSSL fallback

Advantages: trivial to deploy and useful for unit tests.

Limitations: does not satisfy the custody goal and risks creating an accidental production fallback.

Decision: prohibited as LAB_L1 promotion evidence. A test signer may exist only under explicit CI-only, non-authoritative controls.

## Architecture boundary

The signer integration must remain provider-neutral at the Runner boundary:

```text
Runner / assurance workflow
        |
        v
SigningService contract
        |
        +-- VaultSignerAdapter        future LAB_L1 target
        |
        +-- TestSignerAdapter         CI-only, non-authoritative
```

The Runner must never depend directly on Vault-specific transport details. Provider-specific behavior belongs behind the adapter boundary.

### `SigningService` responsibilities

- accept a bounded signing request containing only approved digest/domain data;
- return a signature plus public identity metadata required for verification;
- fail closed when the external signer is unavailable, stale, mis-bound or unverifiable;
- never expose private key material;
- emit auditable operation metadata suitable for later EvidenceVerifier validation.

### `VaultSignerAdapter` future responsibilities

- call a configured Vault signing capability only after a separate governed provisioning change;
- bind an approved key identity and algorithm;
- expose provider/source evidence without secrets;
- preserve non-exportable-key semantics;
- support rotation/revocation and fail-closed behavior.

No endpoint, credential, token, key or trust material is part of this design decision.

### `TestSignerAdapter` constraints

If implemented for CI, it must be mechanically prevented from satisfying LAB_L1 promotion evidence. It must be explicitly marked:

- `CI_ONLY`;
- `NON_AUTHORITATIVE`;
- `NOT_ADMISSIBLE_FOR_LAB_L1_PROMOTION`.

It may test serialization, signature verification, domain binding, timeout/error behavior, simulated rotation/revocation and trust-manifest parsing. It must not create an accepted custody attestation.

## State model

This design adds a conceptual distinction that must remain visible in governance:

1. `TARGET_ARCHITECTURE_SELECTED` — VAULT is the preferred future custody class;
2. `IMPLEMENTATION_DEFERRED` — no Vault capability is yet deployed;
3. `NO_DECISION + NO_SELECTION` — authoritative operational signer state remains unchanged;
4. future `APPROVED + NO_SELECTION` — only after the repository-required evidence plan is actually satisfiable;
5. future candidate `PENDING/SELECTED` — separate governed evidence-bound transition;
6. trust binding — separate governed transition;
7. live promotion/HITL — separate final transition.

No automatic transition is permitted between these states.

## Work that may proceed before Vault exists

The following provider-neutral work is allowed and recommended:

- define/strengthen the signer abstraction contract;
- add fail-closed behavior for unavailable or unverifiable signer responses;
- define trust-store manifest lifecycle and SPKI SHA-256 binding contracts;
- define rotation and revocation contract tests;
- integrate signer evidence with EvidenceVerifier interfaces;
- define audit-event schemas for signing operations;
- add a CI-only test signer that is explicitly inadmissible for LAB_L1 promotion;
- create a separate Hermes Vault capability lane for later infrastructure provisioning.

## Work that remains blocked until Vault exists

The following must not be claimed or executed yet:

- real Vault endpoint/configuration;
- real non-exportable signing key;
- provider/candidate capability attestation;
- accepted R1-R8 operational review;
- public trust-store installation/binding;
- signer candidate `SELECTED` state;
- PRE_PROMOTION completion dependent on signer/trust evidence;
- LAB_L1 live Runner effect or promotion based on signer evidence.

## Fail-closed rules

- absence of Vault must never fall back to a local private key;
- an unavailable signer must produce a deterministic HOLD/blocked outcome;
- test-signing evidence must never be accepted by the production/LAB_L1 EvidenceVerifier path;
- missing or mismatched key identity, algorithm, SPKI hash, evidence digest or freshness proof must fail closed;
- no trust-store content may be generated or installed implicitly from a signer response.

## Testing strategy

Before a future Vault deployment, CI should prove:

- provider-neutral signer contract behavior;
- deterministic refusal on unavailable signer;
- no local-key fallback;
- domain/purpose binding;
- rejection of stale or mismatched signer metadata;
- rejection of CI-only signer evidence by LAB_L1 acceptance paths;
- trust-manifest parser/validator behavior without installing trust;
- rotation/revocation state transitions at the contract level.

After Vault deployment, a separate governed evidence campaign must prove:

- non-exportable private key;
- active key and signing enabled;
- exact key identity and algorithm;
- public SPKI SHA-256 binding;
- auditability and attribution;
- rotation/revocation behavior;
- independent EvidenceVerifier validation;
- complete R1-R8 evidence set.

## Risks accepted

- LAB_L1 promotion remains blocked on signer/trust evidence until Vault is implemented.
- Some provider-specific integration details cannot be validated yet.
- A later Vault deployment may reveal operational constraints that require adapter changes.

These risks are preferable to prematurely introducing a cloud KMS dependency, procuring an HSM for an MVP lab, or weakening custody with a local-key workaround.

## Decision record

- Decision: VAULT is the preferred LAB_L1 external signer target architecture.
- Context: Hermes Vault capability is not yet implemented.
- Alternatives: KMS, HSM, local software key.
- Justification: provider neutrality, proportional cost/complexity and future on-prem/hybrid compatibility.
- Risks accepted: signer-dependent LAB_L1 promotion remains HOLD until real Vault evidence exists.
- Impact: architecture can progress provider-neutrally; operational signer state remains unchanged.
- State: Architecture direction approved; implementation deferred.
- Next actions: record the target in governance, keep #403 operational selection unapproved, then implement only provider-neutral signer/trust/evidence contracts until the Vault capability lane is ready.
