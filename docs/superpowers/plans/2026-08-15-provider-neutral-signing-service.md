# Provider-Neutral Signing Service Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the first provider-neutral signer execution contract that can later be backed by Vault, while proving fail-closed behavior now with a mechanically inadmissible CI-only test adapter.

**Architecture:** Add a small `SigningService` boundary under `platform/assurance/` that accepts only canonical digest/domain requests and returns public verification metadata plus a signature envelope. Provider-specific Vault behavior remains absent. A deterministic CI-only Ed25519 adapter will implement the same interface but carry explicit `CI_ONLY / NON_AUTHORITATIVE / NOT_ADMISSIBLE_FOR_LAB_L1_PROMOTION` provenance so no LAB_L1 acceptance path can mistake test signatures for custody evidence. Existing public-only trust verification and runtime signer-attestation contracts remain authoritative and unchanged.

**Tech Stack:** Python 3.13, dataclasses/protocols, `cryptography` (already used by the canonical RoE trust-store verifier), pytest, repository change-record/source-of-truth validation.

## Global Constraints

- `VAULT` is the preferred target custody architecture; its implementation is deferred.
- Do not provision or contact Vault/KMS/HSM/PKCS11.
- Do not create endpoint, credential, token, private-key file or trust-store binding.
- `signer-human-decision.yaml` remains `NO_DECISION` and `supplier_selection` remains `NO_SELECTION`.
- `promotion_allowed=false`, `runtime_status=NOT_RUN`, `execution_authority=none` and campaign `BLOCKED/HOLD` remain invariant.
- No local/private-key fallback is admissible for LAB_L1 promotion.
- A CI-only signer must be mechanically marked `CI_ONLY`, `NON_AUTHORITATIVE`, `NOT_ADMISSIBLE_FOR_LAB_L1_PROMOTION`.
- Signing input is bounded to an already-computed SHA-256 digest plus explicit purpose/domain metadata; raw evidence, commands, credentials and arbitrary payload bytes are not accepted by the provider-neutral contract.
- All failures at the signer boundary are deterministic and fail closed.

---

### Task 1: Provider-neutral SigningService contract

**Files:**
- Create: `platform/assurance/signing_service.py`
- Test: `platform/tests/test_signing_service.py`

**Interfaces:**
- Produces: `SigningRequest`, `SigningResult`, `SigningService`, `SigningServiceError`, `validate_signing_request()`.
- `SigningRequest`: immutable dataclass with `digest_sha256: str`, `purpose: str`, `domain: str`, `correlation_id: str`.
- `SigningResult`: immutable dataclass with `signature_b64: str`, `key_id: str`, `algorithm: str`, `public_key_spki_sha256: str`, `signer_class: str`, `authority: str`, `admissible_for_lab_l1: bool`, `audit_ref: str`.
- `SigningService`: protocol exposing `sign(request: SigningRequest) -> SigningResult`.
- Stable failure codes: `SIGNING_REQUEST_INVALID`, `SIGNER_UNAVAILABLE`, `SIGNER_RESPONSE_INVALID`, `SIGNER_NOT_ADMISSIBLE`.

- [ ] **Step 1: Write failing request-validation tests**

Add tests that reject: non-64-lowercase-hex digest, blank/oversized purpose, blank/oversized domain, blank/oversized correlation id, and values containing line breaks/control characters. Add a positive test for a bounded canonical request.

```python
request = SigningRequest(
    digest_sha256="a" * 64,
    purpose="tb1-authorization-receipt",
    domain="hermes-security-labs/lab-l1",
    correlation_id="corr-001",
)
assert validate_signing_request(request) is request
```

- [ ] **Step 2: Run the focused test and confirm RED**

Run: `PYTHONPATH=platform/runner-protocol/src pytest -q platform/tests/test_signing_service.py`

Expected: FAIL because `platform.assurance.signing_service` does not exist.

- [ ] **Step 3: Implement the minimal provider-neutral contract**

Implement immutable dataclasses/protocol and validation only. Do not import networking, subprocess, provider SDKs, filesystem private-key handling or Vault libraries. `SigningResult` must expose only signature/public metadata and audit reference; it must have no private/secret field.

- [ ] **Step 4: Add source-level safety tests**

Assert the module contains none of: `hvac`, `boto3`, `pkcs11`, `requests`, `httpx`, `socket`, `subprocess`, `private_key`, `secret_key`, `password`, `token`, `credential` as executable/imported behavior. Permit the literal failure-code wording only where necessary by checking the AST/imports rather than naive unrestricted substring matching.

- [ ] **Step 5: Run focused tests and confirm GREEN**

Run: `PYTHONPATH=platform/runner-protocol/src pytest -q platform/tests/test_signing_service.py`

Expected: all PASS.

- [ ] **Step 6: Commit**

Commit message: `feat(chg-hsl-073): add provider-neutral signing service contract`

---

### Task 2: CI-only deterministic Ed25519 adapter

**Files:**
- Create: `platform/assurance/test_signer_adapter.py`
- Test: `platform/tests/test_test_signer_adapter.py`
- Consume: `platform/assurance/signing_service.py`

**Interfaces:**
- Produces: `TestSignerAdapter` implementing `SigningService`.
- Constructor: `TestSignerAdapter(seed: bytes, *, key_id: str = "ci-test-ed25519")`.
- `sign(request)` returns `SigningResult` with:
  - `algorithm="Ed25519"`;
  - `signer_class="TEST"`;
  - `authority="CI_ONLY/NON_AUTHORITATIVE"`;
  - `admissible_for_lab_l1=False`;
  - deterministic `audit_ref="ci-test://<correlation_id>/<digest-prefix>"`.
- Produces helper `verification_payload(request: SigningRequest) -> bytes` using a stable domain-separated canonical byte representation.

- [ ] **Step 1: Write failing deterministic-signature tests**

Cover: identical request+seed => identical signature; changed digest/purpose/domain/correlation id => different verification payload/signature; returned SPKI SHA-256 matches the DER public key; `admissible_for_lab_l1` is always false.

- [ ] **Step 2: Run focused test and confirm RED**

Run: `PYTHONPATH=platform/runner-protocol/src pytest -q platform/tests/test_test_signer_adapter.py`

Expected: FAIL because the adapter does not exist.

- [ ] **Step 3: Implement only the CI adapter**

Use `cryptography.hazmat.primitives.asymmetric.ed25519.Ed25519PrivateKey.from_private_bytes(seed)` in memory. Never read/write a key file. Reject seeds that are not exactly 32 bytes. Build a deterministic public SPKI DER digest with `serialization.Encoding.DER` + `PublicFormat.SubjectPublicKeyInfo`. Sign only `verification_payload(request)` after `validate_signing_request()`.

- [ ] **Step 4: Prove signatures verify with the existing cryptography backend**

In tests, reconstruct the public key from the adapter's public DER helper/result fixture and verify the signature against `verification_payload(request)`. A mutated payload must fail verification.

- [ ] **Step 5: Add mechanical inadmissibility tests**

Assert every result has `signer_class == "TEST"`, `authority == "CI_ONLY/NON_AUTHORITATIVE"`, `admissible_for_lab_l1 is False`, and that the module exports no function that turns those flags true. Assert no filesystem/network/provider imports exist.

- [ ] **Step 6: Run focused tests and confirm GREEN**

Run: `PYTHONPATH=platform/runner-protocol/src pytest -q platform/tests/test_test_signer_adapter.py platform/tests/test_signing_service.py`

Expected: all PASS.

- [ ] **Step 7: Commit**

Commit message: `test(chg-hsl-073): add inadmissible CI-only signer adapter`

---

### Task 3: LAB_L1 admission guard for signer results

**Files:**
- Modify: `platform/assurance/signing_service.py`
- Test: `platform/tests/test_signing_service.py`

**Interfaces:**
- Produces: `require_lab_l1_admissible(result: SigningResult) -> SigningResult`.
- The guard must reject any result where `admissible_for_lab_l1 is not True`, `signer_class not in {"VAULT", "KMS", "HSM"}`, authority is CI/test/non-authoritative, required public metadata is malformed, or `audit_ref` is absent.
- This guard validates only the result envelope; it does **not** replace `runtime_signer_attestation.verify_signer_attestation`, EvidenceVerifier, R1-R8 evidence or trust binding.

- [ ] **Step 1: Write failing admission-guard tests**

Use a real `TestSignerAdapter` result and assert:

```python
with pytest.raises(SigningServiceError) as exc:
    require_lab_l1_admissible(ci_result)
assert exc.value.code == "SIGNER_NOT_ADMISSIBLE"
```

Add table tests for malformed algorithm/key/SPKI/audit metadata and a synthetic structurally valid `VAULT` result that passes this envelope-only guard.

- [ ] **Step 2: Run focused tests and confirm RED**

Run: `PYTHONPATH=platform/runner-protocol/src pytest -q platform/tests/test_signing_service.py platform/tests/test_test_signer_adapter.py`

Expected: FAIL because the guard is absent.

- [ ] **Step 3: Implement the minimal guard**

No evidence verification, no trust installation and no selection mutation. Return the unchanged result only when its envelope is structurally admissible; otherwise raise stable `SIGNER_NOT_ADMISSIBLE`/`SIGNER_RESPONSE_INVALID` errors.

- [ ] **Step 4: Add an integration assertion against current signer state**

Load the current `platform/assurance/signer-human-decision.yaml` and `platform/assurance/signer-baseline.yaml` through existing canonical loaders and assert the new guard does not mutate or reinterpret `NO_DECISION + NO_SELECTION`.

- [ ] **Step 5: Run focused tests and confirm GREEN**

Run: `PYTHONPATH=platform/runner-protocol/src pytest -q platform/tests/test_signing_service.py platform/tests/test_test_signer_adapter.py platform/tests/test_signer_selection.py platform/tests/test_signer_selection_transition.py`

Expected: all PASS.

- [ ] **Step 6: Commit**

Commit message: `harden(chg-hsl-073): reject CI signer at LAB_L1 boundary`

---

### Task 4: Governance record and documentation reconciliation

**Files:**
- Create: `changes/CHG-HSL-073.yaml`
- Modify: `docs/architecture/lab-assurance-signer-decision-packet.md`
- Modify: `docs/roadmap/current-walking-skeleton-status.md`
- Test: `deployment/tests/test_change_record_observation_consistency.py`
- Test: relevant signer/source-of-truth reconciliation tests discovered from current main.

**Interfaces:**
- Records the provider-neutral signing contract as repository-only hardening.
- Explicitly records `VAULT target / implementation deferred` as architecture direction only.
- Leaves `platform/assurance/signer-human-decision.yaml`, `signer-baseline.yaml`, runtime deployment trust binding and the promotion campaign unchanged.

- [ ] **Step 1: Add the CHG-HSL-073 record using an existing campaign observation**

Use the canonical signer/promotion observation already defined by the repository; do not invent a new observation solely for this change. Record `NO_RUNTIME_CHANGE`, `promotion_allowed=false`, `runtime_status=NOT_RUN`, and the CI signer's explicit inadmissibility.

- [ ] **Step 2: Reconcile signer decision documentation**

Document these distinct states:

```text
architecture target: VAULT
implementation: DEFERRED
human operational decision: NO_DECISION
supplier selection: NO_SELECTION
trust binding: DISABLED/ABSENT
CI signer: NON_AUTHORITATIVE and NOT_ADMISSIBLE_FOR_LAB_L1_PROMOTION
```

- [ ] **Step 3: Update walking-skeleton status**

State that the signer software boundary can now be developed/tested provider-neutrally, but the campaign remains HOLD because real provider attestation, verified trust and receipt/live-effect gates are still missing.

- [ ] **Step 4: Run reconciliation/static tests**

Run at minimum:

```bash
PYTHONPATH=platform/runner-protocol/src pytest -q \
  platform/tests/test_signing_service.py \
  platform/tests/test_test_signer_adapter.py \
  platform/tests/test_signer_selection.py \
  platform/tests/test_signer_selection_transition.py \
  deployment/tests/test_runtime_signer_attestation.py \
  deployment/tests/test_change_record_observation_consistency.py
python3 platform/scripts/validate_source_of_truth.py
python3 platform/scripts/jds_static_gate.py
python3 security/tools/securityctl.py validate
```

Expected: all PASS / `SOURCE_OF_TRUTH_OK` / `JDS_STATIC_GATE_OK` / zero security warnings.

- [ ] **Step 5: Run repository-wide gates**

Run the repository's normal lint/validate suite used by current main, including `make lint`, `make validate`, `git diff --check`, and shell syntax checks where applicable.

Expected: GREEN. If a failure reproduces on clean main, record it as baseline rather than hiding it; otherwise fix the branch before PR.

- [ ] **Step 6: Commit**

Commit message: `docs(chg-hsl-073): record deferred Vault target and signer boundary`

---

### Task 5: PR, Exact-SHA CI and post-merge verification

**Files:** no additional product files unless a CI-discovered branch defect requires correction.

**Interfaces:**
- Produces a merged governed change only after exact-head checks are GREEN.

- [ ] **Step 1: Open PR from a clean implementation branch based on the latest accepted `main`**

PR must state that no provider, key, trust binding, runtime policy or campaign authority changes.

- [ ] **Step 2: Require all repository workflows on the exact PR head**

Required families: `validate`, `security`, `Release governance`, `Private VAmPI deny` plus Exact-SHA/source-of-truth checks used by current main.

- [ ] **Step 3: Diagnose/fix any RED and rerun**

Do not merge around a failed gate. Preserve fail-closed semantics.

- [ ] **Step 4: Merge only when all exact-head checks are GREEN**

Use the repository's normal squash-merge pattern.

- [ ] **Step 5: Verify post-merge workflows on the new exact `main` SHA**

Do not consider CHG-HSL-073 accepted until post-merge `validate`, `security`, release-governance and private-VAmPI-deny workflows are GREEN on that exact SHA.

## Plan self-review

- Spec coverage: covers the first independently testable sub-project from the approved VAULT-deferred spec: provider-neutral signer boundary, CI-only adapter, fail-closed LAB_L1 inadmissibility, governance and exact-SHA delivery. Trust-manifest lifecycle, rotation/revocation integration, audit-event schema and real Vault adapter are intentionally separate later plans because each is independently reviewable and does not need to be coupled to this first software boundary.
- Placeholder scan: no TBD/TODO/fill-later steps.
- Type consistency: `SigningRequest`, `SigningResult`, `SigningService`, `TestSignerAdapter`, `verification_payload()` and `require_lab_l1_admissible()` are defined once and consumed consistently.
