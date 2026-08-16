# Authorization audit evidence custody

## Purpose

CHG-HSL-079 / ADR-0016 adds a repository-level custody path for the sanitized `authorization-receipt-audit/v1` object produced by the canonical Runner authorization audit contract.

The purpose is narrow: persist the exact sanitized authorization-decision audit object through the **existing Evidence Plane**, verify its integrity through the **existing EvidenceVerifier contract**, and bind that verified custody to the existing authorization `AuditSink` / EvidenceChain.

This capability does **not** issue authorization, enable receipt delivery, install trust, select a signer/provider, dispatch Runner work, contact a target or promote LAB_L1.

## Authority boundary

Hermes remains the execution-authorization authority. The custody bridge is an evidence component only.

It may receive only an already-built, schema-valid and sanitized authorization audit object. It cannot accept caller-provided trust, verification, promotion or execution authority and it cannot reconstruct authorization from evidence.

The committed custody policy remains:

```yaml
state: DISABLED
default: deny
runtime_status: NOT_RUN
execution_authority: none
```

Repository support therefore does not imply a live enabled custody path.

## Canonical flow

```text
verified authorization decision / refusal
        |
        v
build_authorization_audit_record()
        |
        | authorization-receipt-audit/v1
        | sanitized public audit object only
        v
AuthorizationAuditCustody.persist(...)
        |
        +--> validate closed JSON schema before store use
        +--> validate trusted correlation before store use
        +--> validate RFC3339 UTC recorded_at before store use
        +--> canonical JSON serialization
        +--> SHA-256 content identity
        +--> existing injected Evidence Plane store.put(...)
        +--> existing store.verify(evidence_id)
        |
        v
Evidence Plane record + immutable content object
        |
        +--> LocalEvidenceVerifier / EvidenceVerifier
        |
        v
CanonicalAuthorizationAuditAdapter
        |
        +--> AuditSink.append(...)
        |
        v
existing EvidenceChain / seal / verify
```

No second datastore, EvidenceChain, seal or verifier is introduced.

## Object identity versus custody identity

CHG-HSL-079 deliberately keeps two identities separate.

### Content identity

The AuditSink `object_ref` identifies the exact sanitized authorization audit object by its canonical content digest:

```text
evidence://authorization-receipt-audit/<payload_sha256>
```

The AuditSink also records the same SHA-256 and canonical payload size.

This identity remains stable regardless of the Evidence Plane backend used to hold the object.

### Custody binding

The AuditSink `evidence_ref` binds the event to the canonical Evidence Plane record that holds the object:

```text
ev_<32 lowercase hex>
```

The custody bridge may internally return `evidence://ev_<id>`, but the authorization adapter normalizes and validates it before AuditSink append. The returned `evidence_id` and `evidence_ref` must identify the same canonical Evidence Plane record.

The two values are not interchangeable:

- `object_ref` answers **which exact object?**;
- `evidence_ref` answers **which Evidence Plane custody record holds it?**.

## Data minimization

The payload persisted to the Evidence Plane is exactly the closed `authorization-receipt-audit/v1` object.

The contract permits only bounded audit metadata such as:

- event type and phase;
- decision and machine-readable reason code;
- SHA-256 of a canonical authorization reference when valid;
- duplicate marker;
- bounded capability and intrusiveness metadata;
- fixed non-authority fields `promotion_allowed=false`, `runtime_status=NOT_RUN`, `execution_authority=NONE`.

The custody path must never persist:

- raw receipt JSON;
- raw authorization references;
- receipt signatures;
- public/private signing key material;
- raw target locators;
- raw operation parameters;
- credentials or secrets;
- tokens, cookies or headers;
- backend exception text;
- caller-provided verification or authority flags.

The closed JSON schema rejects additional fields before any Evidence Plane write.

## Validation before write

The bridge fails before touching the Evidence Plane store when any of the following is invalid:

1. the authorization audit event schema;
2. the exact trusted correlation field set;
3. a correlation identifier;
4. the UTC `recorded_at` timestamp;
5. the custody policy;
6. the injected store contract.

Correlation is validated through the canonical Evidence Plane correlation contract before projection so malformed trusted context cannot be reclassified as a generic backend failure.

## Persistence and verification

For an enabled test/runtime composition, the bridge:

1. canonicalizes the sanitized JSON with deterministic key order and separators;
2. computes SHA-256 and payload size independently;
3. builds an Evidence Plane v2 record using the existing contract;
4. stores the Evidence Plane record and content object through the injected store;
5. requires `store.verify(evidence_id)` to succeed;
6. returns the canonical custody identity only after successful post-write verification.

A store write followed by failed verification is a failure. Backend exception messages are not exposed through the public custody error contract.

## AuditSink linkage

When optional custody is configured in `CanonicalAuthorizationAuditAdapter`, custody completes before the AuditSink append.

The adapter requires:

- persisted SHA-256 equals the independently calculated audit-record SHA-256;
- persisted payload size equals the independently calculated canonical size;
- `evidence_ref` is a canonical `ev_<32 lowercase hex>` value or its `evidence://` URI form;
- returned `evidence_id` and `evidence_ref` identify the same custody record.

Only then does the adapter append:

```text
object_ref            = evidence://authorization-receipt-audit/<sha256>
object_digest_sha256  = <same sha256>
object_size_bytes     = <same canonical size>
evidence_ref          = ev_<canonical Evidence Plane ID>
```

If required custody fails, a positive authorization audit result is not reported and no AuditSink entry is appended.

A refusal remains a refusal even when its audit path fails; evidence failure can never convert a denial into authorization.

## EvidenceVerifier integrity

The existing `LocalEvidenceVerifier` / `EvidenceVerifier` contract remains the verification authority for the stored object.

`EvidenceVerifierChainResolver` is only an interface adapter between the EvidenceChain resolver signature and `EvidenceVerifier.verify(ref, digest)`. It implements no independent trust or digest decision.

An intact stored object verifies successfully. A tampered object, missing object, wrong digest, malformed reference or verifier exception fails closed.

## Idempotency and retry semantics

Two existing properties are combined:

- the Evidence Plane store is content-addressed;
- the authorization audit adapter suppresses an exact event identity after a successful AuditSink append.

An exact duplicate therefore creates neither a second custody object nor a second chain event.

If custody succeeds but AuditSink append fails, the immutable Evidence Plane object is **not deleted**. The adapter preserves the chosen `recorded_at` for the event identity. A deterministic retry reuses the same Evidence Plane record and can complete one final AuditSink append.

This avoids mutating evidence history to hide a partial failure and prevents retry-driven evidence proliferation.

## Committed policy state

`platform/evidence-plane/authorization-audit-custody-policy.yaml` is committed fail-closed:

```text
state                = DISABLED
default              = deny
runtime_status       = NOT_RUN
execution_authority  = none
classification       = restricted
retention            = default-30d / 30 days
raw receipt          = forbidden
raw authorization ref= forbidden
```

Tests may construct an explicitly enabled temporary policy in isolated test storage. That test composition is not evidence that the committed runtime path is enabled.

## Failure semantics

Stable failures cover, among others:

- disabled or invalid policy;
- invalid event schema;
- invalid correlation or timestamp;
- unavailable Evidence Plane store;
- projection/write failure;
- failed post-write integrity verification;
- custody digest/size/reference mismatch;
- AuditSink append failure.

Lower-layer exception strings are not propagated. A failure creates no execution or promotion authority.

## Runtime and promotion non-claims

Repository acceptance of CHG-HSL-079 proves only that the custody contract and its integration are implemented and regression-tested.

It does **not** prove that:

- a live receipt-delivery AF_UNIX endpoint exists;
- resolver or delivery policies are enabled;
- Runner trust material is configured;
- a VAULT/KMS/HSM/PKCS11 signer/provider is operational;
- a live authorization audit object has been persisted by an enabled runtime composition;
- LAB_L1 has valid Human-in-the-Loop promotion approval;
- a Runner action or target effect is authorized or executed;
- production WORM storage or tenant isolation exists.

Until those independent gates have their own evidence, `promotion_allowed=false`, `runtime_status=NOT_RUN`, `execution_authority=NONE`, and `VAL-HSL-RUNNER-L1-LIVE-PROMOTION` remains `BLOCKED / HOLD`.

## Related records

- `ADR-0015` — authorization receipt audit evidence and canonical AuditSink integration;
- `ADR-0016` — selected authorization audit Evidence Plane custody architecture;
- `CHG-HSL-078` — repository authorization decision audit trail;
- `CHG-HSL-079` — repository custody and EvidenceVerifier linkage;
- `VAL-HSL-RUNNER-L1-LIVE-PROMOTION` — independent live-promotion acceptance campaign.
