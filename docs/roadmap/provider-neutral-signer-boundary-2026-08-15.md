# Provider-neutral signer boundary status — CHG-HSL-073 through CHG-HSL-076

**Baseline date:** 2026-08-15  
**Reconciled:** 2026-08-16  
**Campaign:** `VAL-HSL-RUNNER-L1-LIVE-PROMOTION`  
**Effect:** repository-only hardening; no runtime/provider/trust mutation

## What is now implemented

### CHG-HSL-073 — provider-neutral signing boundary

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

### CHG-HSL-074 — trust-manifest composition/provenance hardening

CHG-HSL-074 hardens provider-neutral trust-manifest composition and requires exact verified attestation provenance before composition may succeed. It does not select a provider, install a trust store, create keys or enable runtime policy.

### CHG-HSL-075 — signer operation audit attribution

CHG-HSL-075 adds a dedicated `signer-operation-audit/v1` adapter that feeds the existing canonical AuditSink/evidence chain:

- closed public event schema;
- deterministic content addressing;
- request digest/purpose/domain/correlation binding;
- signature represented only by SHA-256 of decoded public signature bytes;
- public key id, algorithm and SPKI SHA-256 attribution;
- principal/provider reference and provider audit reference attribution;
- CI signer events mechanically `test_only=true`;
- no raw signing payload, raw signature/base64, private key, credential, token or secret in the event;
- no second ledger, evidence chain or seal.

Every event remains mechanically non-authoritative for promotion:

```text
promotion_allowed=false
runtime_status=NOT_RUN
execution_authority=NONE
```

### CHG-HSL-076 — signer audit EvidenceVerifier linkage

CHG-HSL-076 completes the provider-neutral `signer audit-event -> EvidenceVerifier` linkage:

- canonical signer-audit custody policy is `DISABLED / deny / NOT_RUN`;
- public signer audit event can be projected into an injected existing Evidence Plane store under a disposable test-only enabled copy of the policy;
- Evidence Plane classification remains `restricted` and excludes original signing payload/raw signature;
- Evidence Plane `storage_ref` and AuditSink `object_ref` use the same content address `evidence://signer-operation/<sha256>`;
- the EvidenceChain metadata `evidence_ref` remains the frozen raw `ev_<32hex>` identifier;
- existing `LocalEvidenceVerifier` proves exact local evidence integrity and digest binding;
- a thin `EvidenceVerifierChainResolver` only translates the existing EvidenceChain callable interface into the existing `EvidenceVerifier.verify(ref, sha256)` interface;
- the resolver adds no independent verification, persistence, provider, chain or seal semantics;
- missing objects, tamper, digest mismatch, malformed references and backend errors fail closed.

This closes the provider-neutral audit-event/EvidenceVerifier software linkage only. It is not real provider/custody evidence.

## TDD / validation evidence

The signer boundary has been developed through fail-closed repository gates rather than by weakening contracts.

For CHG-HSL-073:

1. contract tests first failed because `signing_service.py` did not exist;
2. the minimal provider-neutral contract made that suite GREEN;
3. adapter tests first failed because `test_signer_adapter.py` did not exist;
4. the in-memory CI adapter made that contract GREEN;
5. a module-identity test-harness defect was isolated and corrected without weakening `SigningRequest` type checking;
6. LAB_L1 guard tests then produced a clean RED consisting only of the missing guard;
7. the minimal envelope guard restored the full `platform/tests` contract suite to GREEN.

For CHG-HSL-075 and CHG-HSL-076, observed failures were corrected at their actual interface boundaries:

- invalid provisional JDS validation states were replaced with canonical states rather than weakening release governance;
- duplicate Python module identity in tests was fixed in the test loader, not by weakening production type validation;
- public `evidence://ev_...` references are normalized to the frozen raw `ev_...` EvidenceChain identifier at the signer boundary;
- the EvidenceChain resolver contract was not modified: a thin interface adapter delegates to the existing LocalEvidenceVerifier;
- Evidence Plane storage reference and AuditSink object reference were aligned to the same content-addressed signer audit object.

No RED was bypassed by loosening signer custody, provider, trust, evidence or execution semantics.

## Architecture direction

`VAULT` remains recorded only as the preferred future LAB_L1 custody architecture direction. No operational custody class/provider has been approved or selected by these software-hardening lanes.

The canonical operational state remains:

- `signer-human-decision.yaml`: `NO_DECISION`;
- `supplier_selection`: `NO_SELECTION`;
- `selected_class`: `null`;
- `human_decision_id`: `null`;
- trust store: absent;
- provider attestation: not observed;
- signer-audit custody policy: `DISABLED`;
- `promotion_allowed=false`;
- `runtime_status=NOT_RUN`;
- campaign: `BLOCKED / HOLD`.

Issue #403 remains open because actual operational signer/custody selection and evidence still require an explicit human decision and real provider evidence.

## What this does not prove

Provider-neutral signer software being GREEN does not constitute external custody evidence. The following remain required later:

- real external signer/provider observation;
- non-exportable real private key proof;
- active/signing-enabled key attestation;
- independently verified source evidence;
- exact operational public trust-store binding;
- rotation/revocation evidence;
- R1-R8 review evidence;
- real authenticated receipt delivery;
- complete PRE_PROMOTION package;
- request-bound HITL approval;
- live Runner effect/audit/outcome/reset evidence;
- POST_EFFECT acceptance.

The LAB_L1 hash seal remains integrity/tamper-evidence only. It does not assert external authenticity or durable/WORM custody.

## Updated continuation path

Completed provider-neutral signer lanes:

- [x] provider-neutral signing boundary;
- [x] trust-manifest composition/provenance hardening;
- [x] signer operation audit-event attribution;
- [x] signer audit-event -> Evidence Plane -> EvidenceVerifier -> AuditSink/EvidenceChain linkage.

Remaining lanes that may still be developed without selecting a real provider, subject to each lane preserving `NO_DECISION / NO_SELECTION`:

1. trust-manifest/SPKI lifecycle contract where not already covered by CHG-HSL-074;
2. rotation/revocation contract;
3. authenticated receipt-delivery contract/integration;
4. other non-signer PRE_PROMOTION evidence lanes.

The real Vault adapter/provisioning, operational custody decision, trust installation and evidence-bearing live signer observation remain separate later changes. No target-interacting action becomes authorized because these repository boundaries are GREEN.
