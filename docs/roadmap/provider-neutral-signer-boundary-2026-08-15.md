# Provider-neutral signer boundary status — CHG-HSL-073 through CHG-HSL-082

**Baseline date:** 2026-08-15  
**Reconciled:** 2026-08-16  
**Campaign:** `VAL-HSL-RUNNER-L1-LIVE-PROMOTION`  
**Effect:** repository-only hardening and deployable Vault capability package; no live runtime/provider/trust mutation

## What is now implemented

### CHG-HSL-073 — provider-neutral signing boundary

- immutable bounded `SigningRequest` and `SigningResult` contracts;
- one-operation `SigningService` protocol;
- canonical TB1 domain/purpose binding;
- CI-only deterministic Ed25519 signer with no key file/network/provider SDK;
- LAB_L1 envelope guard rejects test/non-authoritative output and standalone `PKCS11`;
- no provider, trust or promotion authority.

The CI-only signer remains mechanically:

```text
CI_ONLY=true
NON_AUTHORITATIVE=true
NOT_ADMISSIBLE_FOR_LAB_L1_PROMOTION=true
```

### CHG-HSL-074 — signer ↔ trust-generation evidence composition

- composes only already-verified signer provenance with an already-reviewed trust generation;
- requires exact key id, algorithm and SPKI SHA-256 agreement;
- reuses the canonical trust-store lifecycle validator;
- emits a closed public `signer-trust-manifest/v1` with no-authority flags;
- installs no trust and selects no provider.

### CHG-HSL-075 — signer operation audit attribution

- dedicated `signer-operation-audit/v1` adapter;
- feeds the existing canonical AuditSink/EvidenceChain;
- deterministic content addressing and request/correlation attribution;
- no raw payload, raw signature/base64, private key, token, credential or secret;
- no second ledger, EvidenceChain or seal.

ADR-0012 preserves the selected adapter design and the alternatives that were not selected for the MVP.

### CHG-HSL-076 — signer audit EvidenceVerifier linkage

- canonical signer-audit custody policy remains `DISABLED / deny / NOT_RUN`;
- public signer audit event may be projected into an injected existing Evidence Plane store in disposable tests;
- `LocalEvidenceVerifier` proves exact reference + digest;
- AuditSink/EvidenceChain and Evidence Plane identify the same content-addressed audit object;
- `EvidenceVerifierChainResolver` is only an interface adapter and implements no second verifier;
- tamper, missing object, digest/ref mismatch and backend errors fail closed.

### CHG-HSL-077 — signer trust manifest custody

- dedicated minimal custody bridge for the existing public `signer-trust-manifest/v1`;
- canonical policy is `DISABLED / deny / NOT_RUN / execution_authority=none`;
- closed schema is validated before any write;
- `manifest_id` is independently recomputed from canonical manifest content before custody;
- schema-valid mutation with a stale/reused `manifest_id` is refused fail-closed;
- exact canonical public manifest JSON is projected through an injected existing Evidence Plane store;
- Evidence Plane classification is `restricted` with `default-30d` / 30-day retention;
- storage reference is content-addressed as `evidence://signer-trust-manifest/<sha256>`;
- post-write canonical store integrity verification is mandatory;
- the existing `LocalEvidenceVerifier` proves exact `evidence_ref + payload_sha256` and detects tamper/ref/digest mismatch;
- identical replay is content-addressed/idempotent under the existing store semantics;
- no second store, verifier, AuditSink, EvidenceChain, seal or ledger;
- no Vault/KMS/HSM/PKCS11 call, key provisioning, trust installation, Runner effect or promotion authority.

ADR-0013 preserves the selected minimal custody design and explicitly defers immediate chain linkage and a generic custody framework until concrete review triggers are met.

### CHG-HSL-081 — LAB_L1 Vault Transit signer adapter (`GREEN-REPO`)

- keeps the existing provider-neutral `SigningService` protocol unchanged;
- centralizes the exact domain-separated TB1 signing payload so CI and external providers sign identical bytes;
- adds a bounded certificate-verifying HTTPS/JSON Vault transport restricted to `GET`/`POST` and `/v1/...` paths;
- adds AppRole machine authentication using injected secret references with short-lived token material held only in memory;
- supports only Ed25519 in this first LAB_L1 slice;
- requires the observed Transit key to be `ed25519`, signing-capable, non-derived, non-exportable and without plaintext backup;
- pins the exact observed key version into the Transit sign request and rejects a mismatched returned `vault:vN:` version;
- derives the public SPKI SHA-256 from the observed Ed25519 public key;
- cryptographically verifies every returned signature against that exact observed public key and the canonical TB1 payload before producing a `SigningResult`;
- allows at most one bounded re-authentication attempt and has no local/test signer fallback;
- exposes no Vault administration/key-lifecycle endpoints and cannot create, rotate, delete, import/export or reconfigure keys;
- returns a sanitized content-addressed `evidence://vault-sign-operation/<sha256>` operation identity, explicitly not Evidence Plane custody proof or trust binding;
- proves compatibility with the existing `signer-operation-audit/v1` path without leaking AppRole credentials or Vault tokens;
- leaves provider live attestation, R1-R8 evidence, operational trust installation and human supplier binding untouched.

Repository acceptance evidence for CHG-HSL-081 on exact candidate `0b7511f6c38034414b7bf8ad152af86955aa114b`:

```text
platform/tests = 2367 passed, 7 skipped
docs/tests = 1114 passed
roadmap/tests = 146 passed
deployment/tests = 560 passed
validate = GREEN, including Exact-SHA
security = GREEN
Release governance = GREEN
Private VAmPI source-repo access deny = GREEN
```

This is `GREEN-REPO` capability evidence only. No real Vault service, AppRole, Transit key, provider attestation, public trust-store installation or Runner target effect was provisioned by CHG-HSL-081.

### CHG-HSL-082 — isolated Hermes LAB_L1 Vault operational package (`GREEN-REPO`)

CHG-HSL-082 converts the approved Vault custody design into a controlled deployment package without claiming that the Hermes runtime has already been provisioned.

Implemented repository controls:

- Vault Community `1.21.4` pinned by immutable multi-platform digest;
- single-node Integrated Storage/Raft design;
- mandatory TLS and no dev-mode fallback;
- API published only to host loopback, with no host publication of cluster port `8201`;
- dedicated `vault-signer-internal` Docker network with `internal: true`;
- target/Kali/Runner environments remain outside the Vault network;
- read-only root filesystem, `no-new-privileges`, `cap_drop: ALL`, bounded CPU/memory/PID resources and no Docker socket;
- `disable_mlock=true` plus `SKIP_SETCAP=1`, avoiding a new Linux capability requirement for the pinned LAB deployment;
- Raft state is the only service volume and uses a named Docker volume;
- Vault HCL and policy material are delivered through Compose `configs` rather than general host bind mounts;
- TLS CA/certificate/private-key material is granted through Compose `secrets`, with source material remaining operator-managed outside Git;
- explicit Shamir initialization contract with 3 shares / threshold 2;
- initialization refuses already-initialized storage;
- unseal shares are read silently and never placed in command-line arguments;
- one-time bootstrap root is checked before management operations and has an explicit self-revocation gate;
- Transit key contract is Ed25519, non-derived, `exportable=false`, `allow_plaintext_backup=false`;
- signer policy has only exact metadata-read and sign-update paths for `hermes-lab-l1-signer`;
- AppRole signer/observer identities use no default broad policy and bounded token/SecretID TTLs;
- SecretID generation uses response wrapping with `secret_id_num_uses=1`;
- capability verifier emits only sanitized/public facts and safe signature identity hashes;
- safe negative checks prove the signer session cannot read management surfaces or unrelated Transit keys;
- no Shamir share, root credential, SecretID, wrapping token or Vault client token is a repository evidence field.

The first implementation attempt deliberately did **not** receive a hardening exception when the canonical Compose baseline rejected new host binds. Instead, the package was changed to Compose `configs`/`secrets` while retaining a named Raft volume. This preserves the repository-wide hardening invariant rather than weakening it for Vault.

Tests-first and first GREEN evidence are recorded in `docs/superpowers/checkpoints/CHG-HSL-082-tests-first.md`.

First complete GREEN candidate `fe5f79613d62068ec330325e50fcc3ffe79545d2`:

```text
YAML files = 660 parsed
docs/tests = 1123 passed
platform/tests = 2367 passed, 7 skipped
roadmap/tests = 146 passed
deployment/tests = 570 passed
validate 31960587747 = GREEN
Exact-SHA job 95198213156 = GREEN
security 31960587758 = GREEN
Release governance 31960587752 = GREEN
Private VAmPI source-repo access deny 31960587756 = GREEN
```

This remains **repository capability evidence only**. CHG-HSL-082 has not, in this repository execution, produced real Shamir shares, an initial root token, a real AppRole SecretID, a real Transit key, live provider attestation, live signer SPKI evidence or root-revocation evidence from the Hermes host. Those facts remain `runtime_status=NOT_RUN` until the controlled Hermes execution occurs.

## Architecture decision history

The canonical ADR register preserves material alternatives using explicit dispositions:

```text
Selected
Deferred
Not selected for MVP
Rejected
Superseded
```

Each material alternative records why that disposition applies and review triggers where reconsideration may become appropriate.

Recent decisions captured include:

- **ADR-0012:** dedicated signer-operation audit attribution adapter;
- **ADR-0013:** minimal dedicated signer-trust-manifest custody bridge;
- **ADR-0014:** VAULT as preferred future custody architecture, with operational provider/candidate selection separated from repository capability work.

ADR-0014 does not alter the signer decision source of truth. KMS remains an admissible deferred alternative; HSM is not selected for the MVP; local PEM/OpenSSL is rejected for LAB_L1 custody proof; standalone PKCS11 remains an interface rather than a custody class.

## Existing trust lifecycle capability — not a remaining implementation gap

The repository already contains a provider-neutral trust-store lifecycle contract covering:

- content-addressed generations;
- freshness and future/stale refusal;
- monotonic sequence and predecessor binding;
- anti-rollback checks;
- safe `active → retired/revoked` transitions;
- refusal of retired/revoked key resurrection;
- key material, algorithm and validity-window mutation refusal;
- refusal of unsafe active-key removal;
- safe rotation with a new active key;
- explicit `automatic_activation=false`, `activation_effect=NONE`, `authorization_effect=NONE`, `execution_authority=NONE`.

CHG-HSL-074 already consumes this lifecycle assessment. Rotation/revocation is therefore **not** listed as an unimplemented provider-neutral signer lane. Real provider-side propagation/attestation remains later operational evidence.

## TDD / validation evidence

The signer boundary continues to be developed through fail-closed repository gates rather than by weakening contracts.

For CHG-HSL-077:

1. the tests-first head produced a clean RED: **20 failures, 2214 passes, 7 skipped**, all caused by the custody module being absent;
2. the minimal disabled-policy custody bridge and Evidence Plane integration were implemented;
3. the first implementation run produced **1 failure, 2233 passes, 7 skipped** because the new test expected `content.size` while the canonical Evidence Plane contract uses `content.size_bytes`;
4. the defect was corrected in the test only; production/store contracts were not weakened;
5. the corrected functional head passed the full `platform/tests`/source-of-truth suite and Exact-SHA, while `security`, `Release governance` and `Private VAmPI source-repo access deny` were also GREEN.

For CHG-HSL-081:

1. tests-first head `492d2281667a7b391f12d113ef45d6c316d7b408` produced **34 failures, 2329 passes, 7 skipped**, limited to the deliberately absent Vault adapter/transport and canonical payload helper;
2. two full-suite-only dynamic-module identity defects were isolated and fixed without weakening type or transport error contracts;
3. a gitleaks false positive caused by a credential-looking synthetic fixture was removed and the PR history was rewritten so the flagged literal no longer exists in scanned branch history;
4. hardening head `a889c2537d5540a839774aff7eb8887c8fea2b96` proved that a structurally valid but cryptographically invalid 64-byte provider signature was incorrectly accepted;
5. the adapter was hardened to verify the signature against the exact observed Ed25519 public key and canonical TB1 payload;
6. exact head `0b7511f6c38034414b7bf8ad152af86955aa114b` then passed the full repository gates and Exact-SHA with **2367 platform passes, 7 skips**.

For CHG-HSL-082:

1. tests-first head `16142317f8fdea3c15e3e0414c74fcdf0815a5c1` produced **9 failures, 561 passes** in deployment tests, all caused by the deliberately absent Vault deployment artefacts;
2. first implementation head `7c590004208578139720b265528eb856ab0dfef3` exposed a single canonical platform hardening failure because configuration/policy/TLS were initially represented as new service bind mounts;
3. no exception was added to `ALLOWED_BIND_MOUNTS`;
4. the delivery model was corrected to Compose `configs` and `secrets`, leaving only the named Raft volume;
5. exact candidate `fe5f79613d62068ec330325e50fcc3ffe79545d2` then passed the complete repository gates, including **570 deployment passes** and the existing **2367 platform passes / 7 skips**.

No RED was bypassed by loosening signer custody, trust, evidence, container-hardening or execution semantics.

## Canonical operational state

The following remains authoritative and unchanged:

```text
signer-human-decision = NO_DECISION
supplier_selection = NO_SELECTION
selected_class = null
human_decision_id = null
trust store = ABSENT
provider attestation = NOT_OBSERVED
signer-audit custody policy = DISABLED
signer-trust-manifest custody policy = DISABLED
promotion_allowed = false
runtime_status = NOT_RUN
execution_authority = none
campaign = BLOCKED / HOLD
```

Issue #403 remains open because live custody/provider evidence and the evidence-bearing operational human decision are still absent.

## What the repository does not yet prove

The following remain unresolved for actual LAB_L1 promotion:

- successful startup of the CHG-HSL-082 package on the real Hermes host;
- real Shamir initialization/unseal custody;
- real bootstrap-root revocation after limited identities authenticate;
- real AppRole/SecretID issuance and consumption;
- real Transit key creation and exact public identity/SPKI observation;
- live non-exportability/signing-enabled provider attestation;
- independently verified provider/source evidence;
- operational public trust-store binding and installation;
- provider-side rotation/revocation propagation evidence;
- complete R1-R8 operational review evidence;
- real authenticated receipt delivery;
- remaining PRE_PROMOTION evidence;
- request-bound HITL approval;
- live Runner effect/audit/outcome/reset evidence;
- POST_EFFECT acceptance.

The LAB_L1 hash seal remains integrity/tamper evidence only; it does not assert external authenticity or durable/WORM custody.

## Updated continuation path

Completed repository signer lanes:

- [x] provider-neutral signing boundary;
- [x] trust-generation lifecycle/rotation/revocation contract;
- [x] signer ↔ trust-generation manifest composition and exact provenance binding;
- [x] signer operation audit attribution;
- [x] signer audit -> Evidence Plane -> EvidenceVerifier -> AuditSink/EvidenceChain linkage;
- [x] signer trust manifest -> Evidence Plane -> EvidenceVerifier custody linkage;
- [x] fail-closed Vault Transit Ed25519 adapter behind the provider-neutral boundary;
- [x] isolated single-node Raft/TLS Vault deployment package with Shamir/AppRole/bootstrap controls;
- [x] ADR preservation of recent alternatives and future review triggers.

Next operational lane:

1. execute the merged CHG-HSL-082 package on Hermes through the controlled operator path;
2. initialize/unseal without exposing Shamir/root material to Git/chat/evidence;
3. configure Transit/AppRole and consume wrapped single-use SecretIDs;
4. validate limited signer and observer identities;
5. revoke the initial root credential;
6. capture sanitized provider/capability evidence and exact public signer identity;
7. perform R1-R8 review;
8. only then allow issue #403 to reach the separate evidence-backed human decision stage;
9. supplier binding, trust installation, remaining PRE_PROMOTION, HITL and live Runner effect stay separate governed stages.

No target-interacting action becomes authorized because CHG-HSL-082 is GREEN in the repository.