# LAB_L1 signer target direction — VAULT with deferred implementation

**Status:** architecture direction approved; operational signer decision remains pending  
**Date:** 2026-08-15  
**Change:** CHG-HSL-073  
**Campaign:** `VAL-HSL-RUNNER-L1-LIVE-PROMOTION`

## Decision

`VAULT` is the preferred future custody architecture for the LAB_L1 external signer.

This is **not** an operational provider/candidate selection and does not satisfy the CHG-HSL-062 human-decision evidence contract. The Hermes environment does not yet expose an operational Vault capability, so implementation, provider evidence, trust installation and runtime binding are deliberately deferred.

The machine-readable signer state therefore remains unchanged:

```text
human decision      NO_DECISION
supplier selection  NO_SELECTION
selected class      null
human decision id   null
trust binding        disabled / absent
provider attestation NOT_OBSERVED
promotion_allowed    false
runtime_status       NOT_RUN
campaign             BLOCKED / HOLD
```

No endpoint, credential, token, key, private material or trust-store content is created by this direction.

## Why this state is deliberate

The existing human-decision contract treats `APPROVED` as an evidence-bearing operational decision. It requires canonical evidence references and is intentionally stronger than an architectural preference. Reusing `APPROVED` to mean "preferred but not implemented" would collapse architecture intent into an assurance claim that the repository cannot currently prove.

Likewise, moving the signer baseline to `PENDING` or `SELECTED` would be invalid before an evidence-verified custody candidate exists and is bound to an explicit human decision.

## Provider-neutral software boundary that may proceed now

CHG-HSL-073 introduces a provider-neutral `SigningService` contract. It accepts only an already-computed SHA-256 digest plus bounded purpose, domain and correlation metadata and returns only signature/public identity/audit metadata.

The boundary performs no provider access and grants no execution authority.

A deterministic Ed25519 `TestSignerAdapter` exists only to exercise the contract in CI. Its outputs are hard-marked:

```text
signer_class=TEST
authority=CI_ONLY/NON_AUTHORITATIVE
admissible_for_lab_l1=false
```

The LAB_L1 envelope guard rejects that adapter and also rejects `PKCS11` as a standalone custody class. Only structurally admissible `VAULT`, `KMS` or `HSM` envelopes can pass the preliminary guard.

Passing that preliminary guard still proves **none** of the following:

- actual provider custody;
- non-exportability of the real private key;
- provider/source evidence authenticity;
- R1-R8 compliance;
- approved trust-store binding;
- runtime signer freshness/identity;
- campaign promotion authority.

Those properties remain separately fail-closed behind `runtime_signer_attestation`, the injected `EvidenceVerifier`, the signer human-decision/selection contracts and the public trust-store verification path.

## Explicitly forbidden temporary shortcuts

Until Vault exists, LAB_L1 must not fall back to:

- a repository PEM/private-key file;
- an operator-owned private key on the Hermes host;
- an OpenSSL-generated local promotion key;
- the CI-only test adapter;
- `PKCS11` without a separately proven custody backend;
- automatic KMS/HSM/provider selection merely to clear the gate.

An unavailable real signer remains a deterministic HOLD condition.

## Next implementation layers

Provider-neutral work may continue in this order without changing the operational signer state:

1. trust-manifest/SPKI binding contract;
2. rotation/revocation state contract;
3. signing audit-event schema and EvidenceVerifier binding;
4. authenticated receipt-delivery integration;
5. future Vault capability/adaptor provisioning under a separate governed change;
6. real provider/candidate evidence and R1-R8 review;
7. explicit operational human decision and later selection transition;
8. trust installation/binding;
9. remaining PRE_PROMOTION gates and request-bound HITL.

The first real Vault observation remains a later SAFE-LIVE evidence event, not something inferred from repository CI.
