# CHG-HSL-073 — provider-neutral signer boundary status

**Date:** 2026-08-15  
**Campaign:** `VAL-HSL-RUNNER-L1-LIVE-PROMOTION`  
**Effect:** repository-only hardening; no runtime/provider/trust mutation

## What is now implemented

CHG-HSL-073 establishes the first provider-neutral software boundary for a future external custody signer:

- immutable bounded `SigningRequest` and `SigningResult` contracts;
- `SigningService` protocol with a single `sign()` operation;
- strict digest/purpose/domain/correlation validation;
- deterministic in-memory Ed25519 CI signer for contract testing only;
- canonical domain-separated signing payload;
- public SPKI SHA-256 binding in the test result;
- LAB_L1 envelope guard that rejects CI/test/non-authoritative output and standalone `PKCS11`;
- no networking, subprocess, provider SDK, private-key file or trust installation in the provider-neutral boundary.

The CI-only signer is mechanically labelled:

```text
CI_ONLY=true
NON_AUTHORITATIVE=true
NOT_ADMISSIBLE_FOR_LAB_L1_PROMOTION=true
```

and every result carries:

```text
signer_class=TEST
authority=CI_ONLY/NON_AUTHORITATIVE
admissible_for_lab_l1=false
```

## TDD evidence

The implementation was developed fail-closed through explicit RED/GREEN cycles:

1. contract tests first failed because `signing_service.py` did not exist;
2. the minimal provider-neutral contract made that suite GREEN;
3. adapter tests first failed because `test_signer_adapter.py` did not exist;
4. the in-memory CI adapter made that contract GREEN;
5. a module-identity test-harness defect was isolated and corrected without weakening `SigningRequest` type checking;
6. LAB_L1 guard tests then produced a clean RED consisting only of the missing guard;
7. the minimal envelope guard restored the full `platform/tests` contract suite to GREEN.

No RED was bypassed by loosening signer type/custody semantics.

## Architecture direction

`VAULT` is recorded as the preferred future LAB_L1 custody architecture, but its implementation is deferred because no operational Vault capability exists yet in Hermes.

This does **not** alter the canonical operational state:

- `signer-human-decision.yaml`: `NO_DECISION`;
- `supplier_selection`: `NO_SELECTION`;
- `selected_class`: `null`;
- `human_decision_id`: `null`;
- trust store: absent;
- provider attestation: not observed;
- `promotion_allowed=false`;
- `runtime_status=NOT_RUN`;
- campaign: `BLOCKED / HOLD`.

Issue #403 remains open because actual operational signer selection still requires evidence that cannot exist until a real custody implementation is available.

## What this does not prove

A structurally admissible external signer envelope is not provider evidence. The following remain required later and are not satisfied by CHG-HSL-073:

- real external signer/provider observation;
- non-exportable real private key proof;
- active/signing-enabled key attestation;
- independently verified source evidence;
- exact public trust-store binding;
- R1-R8 review evidence;
- real authenticated receipt delivery;
- complete PRE_PROMOTION package;
- request-bound HITL approval;
- live Runner effect/audit/outcome/reset evidence;
- POST_EFFECT acceptance.

## Updated continuation path

Work may now continue without waiting for Vault on provider-neutral capabilities:

1. trust-manifest and SPKI binding lifecycle;
2. rotation/revocation contract;
3. signer audit-event and EvidenceVerifier linkage;
4. authenticated receipt-delivery contract/integration;
5. other non-signer PRE_PROMOTION evidence lanes.

The real Vault adapter/provisioning and the evidence-bearing operational decision remain separate later changes. No target-interacting action becomes authorized because this repository boundary is GREEN.
