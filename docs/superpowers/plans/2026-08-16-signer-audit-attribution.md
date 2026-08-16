# Signer Audit Attribution Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a provider-neutral signer-operation audit adapter that emits a closed public event and appends it to the existing canonical LAB_L1 `AuditSink` / evidence chain without creating a second ledger or granting runtime authority.

**Architecture:** Add a dedicated adapter under `platform/assurance` following the existing runner-transport audit-adapter pattern. The adapter validates a canonical `SigningRequest` and a bounded `SigningResult`, produces a deterministic `signer-operation-audit/v1` public record containing only public metadata and digests, and appends that record as `evidence_record` to the existing `platform/evidence-plane/audit_sink.py`. The Audit Sink remains the sole chain/seal implementation.

**Tech Stack:** Python 3.13, dataclasses, hashlib/base64/json, JSON Schema 2020-12, pytest, jsonschema, existing provider-neutral signing-service and LAB_L1 AuditSink contracts.

## Global Constraints

- No Vault/KMS/HSM/PKCS11 client, provider call, network I/O, subprocess, filesystem write, private key, credential, token, secret or trust installation.
- `NO_DECISION / NO_SELECTION` remains unchanged; VAULT remains architecture target only.
- `promotion_allowed=false`, `runtime_status=NOT_RUN`, `execution_authority=NONE` remain invariant.
- No Runner or target effect.
- Reuse the existing canonical `AuditSink`; do not implement a second chain, seal, persistence layer or ledger.
- The signer audit record may contain only public signing metadata, attribution labels, evidence references and SHA-256 digests; it must never include raw payload or raw signature bytes/base64.
- The adapter fails closed if request/result types are invalid, request validation fails, required attribution is missing/unsafe, or the result envelope is malformed for public audit use.
- CI/test signer events are permitted only when explicitly marked `test_only=true`, `promotion_allowed=false`, `runtime_status=NOT_RUN`, and cannot satisfy LAB_L1 custody evidence.

---

### Task 1: Freeze the public signer-operation audit schema

**Files:**
- Create: `platform/schemas/signer-operation-audit.schema.json`
- Create: `platform/tests/test_signer_operation_audit_schema.py`

**Interfaces:**
- Consumes: public fields from `SigningRequest` and `SigningResult`.
- Produces: closed JSON Schema `signer-operation-audit/v1` with `additionalProperties=false`.

- [ ] Write a failing schema test that validates one canonical event and rejects unknown/secret fields, authority elevation, invalid SHA-256 digests, unsupported signer classes/algorithms, and missing attribution.
- [ ] Run `pytest -q platform/tests/test_signer_operation_audit_schema.py`; expected RED because the schema file does not exist.
- [ ] Implement the minimal closed schema. Required fields: `schema_version`, `operation`, `request_digest_sha256`, `purpose`, `domain`, `request_correlation_id`, `signature_sha256`, `key_id`, `algorithm`, `public_key_spki_sha256`, `signer_class`, `authority`, `audit_ref`, `principal`, `provider_ref`, `test_only`, `promotion_allowed`, `runtime_status`, `execution_authority`. Constrain `operation="SIGN"`, signer class to `VAULT|KMS|HSM|TEST`, algorithms to `Ed25519|ECDSA-P256-SHA256`, boolean authority fields to the locked values, and evidence/provider refs to bounded non-control-character strings.
- [ ] Run the schema test; expected PASS.

### Task 2: Implement deterministic signer audit record construction

**Files:**
- Create: `platform/assurance/signer_audit_adapter.py`
- Create: `platform/tests/test_signer_audit_adapter.py`

**Interfaces:**
- Consumes: `SigningRequest`, `SigningResult`, `SignerAuditAttribution(principal, provider_ref, test_only)`.
- Produces: `build_signer_audit_record(request, result, attribution) -> dict[str, object]` and deterministic canonical JSON digest/size.

- [ ] Write failing tests for canonical record construction, request validation, required/unsafe principal/provider reference, deterministic signature SHA-256 from decoded public signature, no raw `signature_b64`, no raw payload, no secret-like fields, and test-only classification.
- [ ] Run `pytest -q platform/tests/test_signer_audit_adapter.py`; expected RED because the adapter does not exist.
- [ ] Implement dynamic loading of sibling `signing_service.py`, canonical request validation, bounded public-result validation, `SignerAuditAttribution`, signature digest derivation, and deterministic canonical JSON encoding.
- [ ] Set locked authority fields in every record: `promotion_allowed=false`, `runtime_status="NOT_RUN"`, `execution_authority="NONE"`.
- [ ] Set `test_only=true` for signer class `TEST` or explicit test attribution; reject inconsistent `test_only=false` with signer class `TEST`.
- [ ] Run adapter tests; expected PASS.

### Task 3: Funnel signer audit events into the canonical AuditSink

**Files:**
- Modify: `platform/assurance/signer_audit_adapter.py`
- Modify: `platform/tests/test_signer_audit_adapter.py`

**Interfaces:**
- Consumes: existing `AuditSink`, `AuditContext`, signer audit record.
- Produces: `CanonicalSignerAuditAdapter.record_signing(...)` which appends exactly one `evidence_record` to the existing AuditSink.

- [ ] Write failing tests proving one signer operation creates one AuditSink entry, sealed verification succeeds, object digest equals the canonical signer record digest, replay fails closed, and no second chain/seal implementation exists.
- [ ] Implement standalone dynamic loading of `platform/evidence-plane/audit_sink.py` following `platform/runner-transport/audit_adapter.py`.
- [ ] Map campaign/run/step/attempt to `AuditContext`, map `principal` directly, use decision `SIGN`, use request correlation ID as `correlation_id`, and use `recorded` outcome for external custody or `observed` for test-only events.
- [ ] Append only `object_kind="evidence_record"`, `object_ref="evidence://signer-operation/<sha256>"`, `object_media_type="application/json"`, and the deterministic digest/size.
- [ ] Run adapter tests plus `platform/tests/test_audit_sink.py`; expected PASS.

### Task 4: Add static safety and regression guards

**Files:**
- Modify: `platform/tests/test_signer_audit_adapter.py`

**Interfaces:**
- Produces: AST/static guards for provider neutrality and absence of authority side effects.

- [ ] Add AST tests forbidding imports/calls for `hvac`, `boto3`, `pkcs11`, `requests`, `httpx`, `socket`, `subprocess`, filesystem persistence, or duplicate chain/seal logic.
- [ ] Add assertions that the adapter never exposes `private_key`, `secret`, `token`, `credential`, raw payload, or raw signature fields.
- [ ] Run `pytest -q platform/tests/test_signer_operation_audit_schema.py platform/tests/test_signer_audit_adapter.py platform/tests/test_signing_service.py platform/tests/test_audit_sink.py`; expected PASS.

### Task 5: Record governance without changing signer decision state

**Files:**
- Create: `changes/CHG-HSL-075.yaml`
- Create: `docs/architecture/signer-operation-audit-attribution.md`
- Modify only if required by repository reconciliation tests: `docs/roadmap/current-walking-skeleton-status.md`

**Interfaces:**
- Produces: auditable decision record for option A and explicit unchanged runtime/signer authority state.

- [ ] Record decision: dedicated signer audit adapter feeding the existing AuditSink/evidence chain.
- [ ] Record alternatives rejected: extending generic AuditSink schema with signer-specific fields; placing audit attribution inside `SignatureEnvelope`; creating a second ledger.
- [ ] State invariants explicitly: provider selection `NO_SELECTION`, human decision `NO_DECISION`, no trust installation, no key provisioning, no runtime effect, no promotion.
- [ ] Document MVP boundary and post-#403 follow-on for real provider audit attestation.
- [ ] Run repository governance/source-of-truth tests relevant to change records and current walking skeleton.

### Task 6: PR, exact-SHA CI, review, merge, post-merge verification

**Files:**
- No new implementation files beyond Tasks 1-5.

**Interfaces:**
- Produces: merged CHG-HSL-075 with exact-SHA evidence.

- [ ] Open a draft PR from `chg-hsl-075/signer-audit-attribution` to `main`.
- [ ] Run/observe all repository workflows on the exact PR head SHA; diagnose and fix any RED without weakening gates.
- [ ] Review PR diff for authority drift, provider coupling, secrets, duplicate chain/seal code, stale docs and unresolved review threads.
- [ ] Mark ready and squash-merge only after all required workflows are GREEN on the exact head SHA.
- [ ] Verify all required post-merge workflows are GREEN on the exact new `main` SHA.
- [ ] Update/close any CHG-HSL-075 tracking issue if its acceptance criteria are fully satisfied; leave #403 open and unchanged except for an informational progress comment if useful.
