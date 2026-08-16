# VAULT LAB_L1 operational implementation design

Date: 2026-08-16
Status: Proposed operational implementation design — owner selected Option A; implementation requires spec review before coding
Scope: Hermes Security Labs LAB_L1 external signer custody lane for `VAL-HSL-RUNNER-L1-LIVE-PROMOTION`

## Context

ADR-0014 selected `VAULT` as the target signer custody architecture while deliberately deferring implementation. The owner has now selected Option A: begin the operational VAULT implementation lane for LAB_L1.

This authorization starts implementation work but **does not** satisfy the evidence-bearing signer decision in issue #403 and does not move `platform/assurance/signer-human-decision.yaml` from `NO_DECISION` to `APPROVED`.

The current fail-closed operational source of truth therefore remains:

- human signer decision: `NO_DECISION`;
- supplier selection: `NO_SELECTION`;
- `selected_class: null`;
- `human_decision_id: null`;
- trust store: absent/unbound;
- provider attestation: not observed;
- `promotion_allowed=false`;
- `runtime_status=NOT_RUN`;
- `execution_authority=NONE`;
- campaign: `BLOCKED / HOLD`.

The repository already exposes a provider-neutral `SigningService` that accepts a canonical TB1 digest-only request and returns public signature/identity metadata. Provider-specific behavior must remain behind this boundary.

## Decision

Implement the first operational LAB_L1 VAULT capability using a **Vault Transit-backed signer adapter** behind the existing provider-neutral `SigningService` contract.

The first slice is intentionally narrow:

1. add a `VaultSignerAdapter` that can authenticate to a configured Vault service and request signing through a Transit signing key;
2. add typed, bounded configuration with no secrets in Git;
3. add deterministic fail-closed error mapping and timeouts;
4. add provider-observation/public-metadata extraction needed by later signer attestation and EvidenceVerifier work;
5. add unit/contract tests using an injected transport/fake Vault boundary;
6. optionally add an isolated non-authoritative integration harness for a disposable Vault instance only after the adapter contract is green;
7. do **not** bind trust, mark the signer selected, enable runtime policy, execute a Runner target effect or promote LAB_L1.

## Implementation approaches considered

### Approach A — direct Vault Transit adapter behind `SigningService` — selected

The application owns a small provider-specific adapter that calls the Vault HTTP API and maps the response into the existing `SigningResult` contract.

Advantages:

- smallest change to the current architecture;
- preserves the existing provider-neutral Runner boundary;
- simple to unit-test with an injected transport;
- allows precise timeout/error and evidence metadata handling;
- no extra sidecar/service solely for LAB_L1.

Limitations:

- the adapter must handle authentication, token lifetime and Vault-specific response validation correctly;
- a small amount of Vault-specific code enters `platform/assurance`, albeit behind a clear boundary.

### Approach B — dedicated signer sidecar/service

Add a separate service that owns all Vault interaction and exposes a bespoke local signing API to Hermes.

Advantages:

- strongest process/network separation;
- easier future multi-provider implementation.

Limitations:

- unnecessary deployment/API/health/observability complexity for the first LAB_L1 slice;
- duplicates controls already represented by `SigningService`;
- increases operational burden before commercial/runtime need exists.

Decision: defer until multiple provider backends or stronger process isolation justify it.

### Approach C — Vault-specific calls directly in Runner/authorization flow

Advantages: fastest initial wiring.

Limitations: violates the accepted provider-neutral architecture, couples Runner behavior to Vault transport/auth details, and makes later KMS/HSM migration harder.

Decision: rejected.

## Vault capability boundary

The target flow is:

```text
TB1 authorization workflow
        |
        | canonical digest + purpose/domain + correlation_id
        v
SigningService
        |
        v
VaultSignerAdapter
        |
        | authenticated, bounded request
        v
Vault Transit signing endpoint
        |
        | signature + public/provider metadata
        v
VaultSignerAdapter validation
        |
        +--> SigningResult
        |
        +--> signer-operation audit metadata
        |
        +--> provider observation/evidence input
```

Vault Transit is used only for cryptographic signing. Raw commands, target data, credentials, evidence payloads and arbitrary application content do not cross the signing contract.

## Components

### `VaultSignerConfig`

Immutable configuration object containing only non-secret operational configuration and secret *references* where needed.

Expected bounded fields:

- Vault address/endpoint;
- Transit mount path;
- signing key name;
- expected Vault namespace only if the selected deployment uses one;
- authentication mode;
- RoleID source/reference when AppRole is used;
- SecretID source/reference when AppRole is used;
- connect/read timeout values within repository-defined limits;
- expected signer algorithm;
- optional CA bundle path/reference for TLS verification.

Secrets/tokens must never be serialized into logs, evidence, `SigningResult`, repository files or exception strings.

### `VaultTransport`

Small injectable HTTP boundary used by `VaultSignerAdapter`.

Responsibilities:

- perform only the explicitly allowed Vault API requests;
- enforce connect/read timeout;
- require TLS verification except in an explicitly CI-only disposable harness;
- return parsed response objects or stable transport errors;
- never log request authentication headers or secret-bearing response data.

Unit tests inject a fake transport. Provider integration tests may use the real transport against an isolated disposable Vault.

### `VaultAuthSession`

Authentication/token lifecycle boundary.

Initial LAB implementation supports AppRole for machine authentication, with least-privilege Vault policy restricted to the exact Transit signing path. The adapter must not require a static root/admin token.

The auth session:

- obtains a short-lived client token from configured credential sources;
- caches it only in process memory;
- never persists it to repository/evidence/logs;
- may re-authenticate once on an authentication-expiry response;
- fails closed after bounded retry;
- cannot create or modify policies, auth methods, mounts or keys.

A future platform-native trusted identity method may replace AppRole without changing `SigningService`.

### `VaultSignerAdapter`

Implements `SigningService`.

Responsibilities:

1. call `validate_signing_request()` before any network action;
2. authenticate through `VaultAuthSession`;
3. submit only the validated digest to the configured Transit sign path;
4. reject responses that do not match the configured key/algorithm/provider expectations;
5. return `SigningResult` with `signer_class="VAULT"` only when the provider response is structurally valid;
6. set `admissible_for_lab_l1` only as a structural envelope property; it never proves R1–R8, trust or custody on its own;
7. attach an `audit_ref` only after the canonical signer-operation audit/evidence path has accepted the public audit event;
8. expose no private key material or Vault token.

## Signing semantics

The adapter uses Vault Transit signing rather than exporting or loading a private key into Hermes. HashiCorp documents Transit as a cryptographic service that supports signing/verification, and the Transit HTTP API exposes a dedicated sign endpoint for a named key. The implementation plan must pin the exact supported Vault image/release by immutable digest before any integration harness is accepted.

For the initial LAB_L1 slice:

- canonical TB1 `digest_sha256` remains the only message material accepted by `SigningService`;
- canonical purpose remains `tb1-authorization`;
- canonical domain remains `hex0r.tb1.authorization.v1`;
- the initial key algorithm must be one already accepted by the repository LAB_L1 envelope guard (`Ed25519` or `ECDSA-P256-SHA256`);
- the exact mapping between repository algorithm identifier and Vault key/sign operation must be explicit and tested;
- no implicit algorithm downgrade/fallback is allowed.

## Authentication and authorization

AppRole is selected for the first machine-to-Vault LAB integration because the Vault documentation explicitly supports it for machine/application authentication. The Vault policy attached to this identity must be minimal and allow only the required signing operation for the exact Transit key path plus the minimum read capability required to produce public attestation metadata, if any.

The implementation must preserve these boundaries:

- no root token in runtime configuration;
- no Vault management capability from the signer adapter;
- no key creation, deletion, rotation, policy mutation or auth-method configuration from the adapter;
- credential bootstrap/provisioning is a separate operator/governed action;
- RoleID/SecretID or resulting Vault token are never evidence payloads.

## Evidence and audit flow

A successful cryptographic signature is not sufficient for LAB_L1 promotion.

The adapter must feed only sanitized public metadata into the existing evidence contracts. Later gates must independently prove:

- provider/capability observation;
- active key identity;
- signing enabled;
- private key non-exportability as supported/proven by the deployed backend;
- exact algorithm;
- public-key SPKI SHA-256;
- signer-operation audit attribution;
- trust-store manifest agreement;
- R1–R8 review;
- canonical EvidenceVerifier acceptance.

The evidence identity/binding distinction established by ADR-0016 remains unchanged.

## Fail-closed behavior

The adapter must map provider failures to stable internal errors without exposing secrets.

Minimum failure classes:

- configuration invalid/missing;
- Vault unreachable/timeout;
- TLS verification failure;
- authentication refused/expired;
- authorization denied;
- Transit key missing/disabled/incompatible;
- malformed provider response;
- signature missing/invalid encoding;
- algorithm/key identity mismatch;
- audit/evidence custody failure.

Rules:

- no local/test signer fallback;
- no retry loop beyond a small bounded retry policy;
- no automatic key creation or provider repair;
- any evidence/audit failure after signing prevents the result from becoming LAB_L1-acceptable;
- no provider failure changes `NO_DECISION`, `NO_SELECTION`, trust state or campaign HOLD.

## Network and isolation

The operational Vault endpoint must not be exposed to the target lab network.

For the first Hermes deployment:

- Vault resides on a dedicated/internal Docker network or equivalent isolated service segment;
- only the component hosting `VaultSignerAdapter` receives egress to Vault;
- Runner target containers do not receive Vault network reachability;
- no Docker socket is exposed to Vault or the signer adapter;
- Vault management/API exposure to the host is limited to the operator path required for provisioning/observation;
- production/Hermes network placement is validated separately from CI disposable integration tests.

## Key lifecycle

Key provisioning, rotation and revocation are separate governed operations from signing.

The adapter itself can:

- identify the configured key and observed key version/public identity;
- refuse revoked/disabled/incompatible state;
- detect a key/public identity change and force re-attestation/trust reconciliation.

The adapter cannot:

- create a new key;
- rotate the key;
- delete a key;
- change minimum versions;
- silently accept a new public SPKI digest.

A key change invalidates previous trust binding for future signatures until the new public identity is independently observed, evidence-verified and accepted through the trust lifecycle.

## First implementation slice

### In scope

- `VaultSignerConfig` contract;
- injectable `VaultTransport` boundary;
- `VaultAuthSession` AppRole flow;
- `VaultSignerAdapter` implementing `SigningService`;
- stable error model and sanitization;
- provider response parsing/validation;
- audit-event handoff into the existing signer audit adapter;
- fake-transport unit tests;
- negative tests for missing config/auth denied/timeout/malformed response/key mismatch/algorithm mismatch/audit failure;
- documentation and governance change record;
- optional disposable Vault Transit integration test after unit/contract GREEN.

### Explicitly out of scope

- changing `signer-human-decision.yaml` to `APPROVED`;
- changing `supplier_selection` to `PENDING`/`SELECTED`;
- trust-store installation;
- runtime signer policy enablement;
- receipt-delivery policy enablement;
- PRE_PROMOTION completion;
- HITL approval;
- Runner/Kali/WebGoat target effect;
- POST_EFFECT package;
- production Vault HA/storage/unseal design.

## Testing strategy

### Unit/contract

Must prove:

- canonical request validation happens before transport;
- exact endpoint/path construction is deterministic and bounded;
- AppRole/token handling never leaks secrets;
- timeout/auth/permission/provider errors fail closed;
- only one bounded re-authentication attempt is possible;
- no fallback to `TestSignerAdapter`;
- expected key/algorithm/signature response is enforced;
- sanitized public metadata only;
- audit failure blocks LAB_L1 acceptance;
- `require_lab_l1_admissible()` remains a preliminary envelope guard, not provider evidence.

### Disposable provider integration

After unit/contract tests pass, an isolated Vault integration harness may prove:

- AppRole authentication to a least-privilege role;
- Transit signing succeeds with the configured test key;
- the client cannot create/rotate/delete keys or modify Vault configuration;
- invalid credentials and revoked/expired access fail closed;
- a key identity/version change is observable and does not silently update trust;
- logs/evidence contain no Vault token, SecretID or private key material.

This integration evidence is **LAB implementation evidence**, not yet sufficient R1–R8 promotion evidence unless the exact Hermes deployment and custody conditions are separately verified.

## Acceptance for this implementation slice

The first slice is acceptable when:

1. repository tests and Exact-SHA gates are GREEN;
2. no secret appears in Git/diff/tests/evidence logs;
3. the adapter cannot perform Vault administration/key lifecycle operations;
4. provider outage/auth failure/mismatch all return deterministic fail-closed outcomes;
5. `SigningService` provider-neutral API remains unchanged unless a separately justified contract version is required;
6. signer operation audit handoff is preserved;
7. current governance remains `NO_DECISION + NO_SELECTION` and campaign `BLOCKED/HOLD`;
8. any disposable integration harness is isolated, deterministic and tear-down verified;
9. no live Runner target effect occurs.

## Subsequent stages

After the first slice is accepted:

1. provision the actual Hermes Vault capability under a separate governed deployment change;
2. provision the exact LAB_L1 Transit signing key and least-privilege identity;
3. capture provider/capability evidence and live signer attestation;
4. generate and verify the public trust manifest/SPKI binding;
5. complete the R1–R8 evidence review;
6. only then record the human decision as `APPROVED + NO_SELECTION`;
7. separately transition the baseline to `PENDING/SELECTED` with the exact decision ID and verified candidate;
8. separately bind/install trust;
9. finish remaining delivery/custody/PRE gates;
10. request explicit HITL before any live effect;
11. produce POST_EFFECT evidence and reset proof.

## Risks and controls

### Credential compromise

Control: least-privilege AppRole, short-lived in-memory token, secret references outside Git, sanitized error/logging, no admin/key-management permissions.

### Vault outage blocks signing

Accepted for LAB_L1. Control: deterministic HOLD; no local fallback.

### False inference that a successful signature proves custody

Control: envelope validation remains separate from runtime attestation, EvidenceVerifier, trust manifest and R1–R8 review.

### Key rotation creates trust drift

Control: exact key identity/SPKI/version observation; no silent trust update; re-attestation required.

### Premature production complexity

Control: no HA cluster, auto-unseal, external storage or production tenancy design in this slice. Those belong to a later capability deployment design.

## Decision record

- Decision: begin operational VAULT implementation for LAB_L1 using a Vault Transit-backed adapter behind the existing `SigningService`.
- Context: Option A explicitly selected by the owner after CHG-HSL-080 completed.
- Alternatives considered: dedicated signer sidecar; direct Vault calls from Runner.
- Justification: smallest safe implementation that preserves provider-neutral contracts, isolation and fail-closed governance.
- Risks accepted: Vault becomes an availability dependency for signer operations; real custody evidence remains unavailable until the Hermes deployment exists.
- State: design prepared for owner spec review; no implementation code written by this change.
- Next action after approval: write the implementation plan and execute it test-first in a separate change/PR.