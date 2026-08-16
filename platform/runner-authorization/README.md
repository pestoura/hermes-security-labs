# Runner authorization reference resolver

This directory provides the execution-plane lookup boundary for TB1 `authorization_ref` values. It does **not** issue or approve authorization.

## Authority model

Hermes remains the only execution-authorization authority. The resolver has one trusted ingest path:

1. receive a signed TB1 receipt through a trusted composition boundary;
2. call the canonical verifier in `platform/authorization-contract/authorization_receipt.py`;
3. cache only the returned sanitized `VerifiedAuthorization` metadata;
4. resolve a Runner `authorization_ref` only while that verified metadata remains in memory and inside its validity window.

A naked `authorization_ref` cannot populate the cache and resolves to nothing.

## Canonical policy

The committed resolver policy is deliberately non-operational:

- `state: DISABLED`;
- `default: deny`;
- `runtime_status: NOT_RUN`;
- `execution_authority: none`;
- `trust_store_path: NOT_CONFIGURED`;
- cache is `memory-only` with no persistence.

Repository merge therefore cannot create a live authorization path.

## Cached data

The cache stores the canonical `VerifiedAuthorization` object only. It does not retain:

- receipt signatures;
- public/private key material;
- raw target locators;
- raw operation parameters;
- credentials, tokens or cookies.

The safe inventory intentionally omits even target and parameter digests. It exposes only reference/correlation/operation/capability/intrusiveness/expiry metadata needed for operational observability.

## Fail-closed restart semantics

The cache is intentionally volatile in this first candidate. Process restart produces an empty cache; previously valid references therefore become locally unresolvable until a signed receipt is verified again. This is safer than adding persistence before the trusted ingest and revocation model are settled.

The resolver also rechecks `issued_at`/`expires_at` on every lookup and removes stale or future-dated cached entries.

## Trusted receipt delivery boundary

`receipt_delivery.py` is the smallest trusted composition path that answers *how a verified receipt reaches the Runner process*. It sits in front of the resolver and never bypasses it.

- **Sole issuer.** The delivery envelope issuer must equal the canonical contract issuer (`hermes-control-plane`); anything else is refused before verification.
- **No caller-controlled trust.** Envelope and receipt are rejected if they carry `verified`, `trusted`, `trust_level`, `execution_authority`, `verification_source`, `bypass` or similar fields. Trust is produced only by the canonical verifier.
- **No private key in the Runner.** Secret-shaped fields (`private_key`, `signing_key`, `token`, `passphrase`, ...) fail closed, and the module itself never signs or loads key material.
- **Authenticated local composition.** Delivery is authenticated by AF_UNIX peer credentials (`uid` + principal) against the policy, not by any field inside `runner.step.request` and not by a network claim.
- **Replay discipline.** Sequences must be monotonic; an exact duplicate sequence is idempotent and does not re-register, while an out-of-order sequence is refused.
- **Fail-closed restart.** Nothing is persisted. A restarted Runner has an empty resolver cache and no sequence baseline, so it resolves nothing until Hermes redelivers.

The committed `receipt-delivery-policy.yaml` is `DISABLED` / `deny` / `NOT_RUN` / `execution_authority: none` with `socket_path: NOT_CONFIGURED`, so merging cannot create a live delivery path.

## Authorization decision audit evidence

CHG-HSL-078 / ADR-0015 adds repository-only audit evidence for authorization decisions through `authorization_audit_adapter.py` and the existing canonical LAB_L1 `AuditSink` / EvidenceChain.

The closed event model covers:

- successful verified receipt registration (`REGISTERED`);
- live lookup (`LOOKUP_HIT`);
- unknown or invalid lookup (`LOOKUP_MISS`);
- expired/future-invalid cached authorization (`LOOKUP_EXPIRED`);
- delivery or registration refusal (`REFUSED`).

Security properties:

- trusted audit correlation is supplied by the local composition or schema-validated Runner request, never copied from an unverified receipt;
- canonical authorization references are represented in the public event only by SHA-256; malformed/unbounded references are recorded as `null`;
- raw receipt, signature, key, target, parameters, credentials and secrets are not included;
- exact duplicate delivery does not create a second registration event;
- with an observer configured, a registration or lookup hit that cannot be audited fails closed;
- post-registration audit failure removes local resolvability through `resolver.forget()` before acceptance is returned;
- refusal-audit failure cannot turn a denial into success;
- the canonical AuditSink replay/hash-link/seal controls are reused unchanged.

The first WebGoat L1 adapter already performs full request binding against verified authorization metadata and now supplies request-bound audit context when the resolver supports audited lookup. Legacy resolver doubles that expose only `resolve(ref)` remain supported for repository compatibility.

### Optional Evidence Plane custody

CHG-HSL-079 / ADR-0016 adds optional repository support for persisting the **same sanitized authorization audit record** through the existing Evidence Plane before it is linked to the AuditSink.

The custody dependency and Evidence Plane store are injected into `CanonicalAuthorizationAuditAdapter`; the adapter does not create a datastore, verifier, EvidenceChain or seal.

When custody is configured:

1. the closed `authorization-receipt-audit/v1` object is validated before storage;
2. trusted campaign/run/step/attempt correlation and `recorded_at` are validated before any store write;
3. the exact canonical JSON object is content-addressed and persisted through the injected Evidence Plane store;
4. post-write integrity verification is mandatory;
5. the returned digest and size must match the independently calculated audit-record digest and size;
6. the returned Evidence Plane identity must be canonical and internally consistent;
7. only after those checks does the existing AuditSink append the event.

The two references have intentionally different semantics:

```text
object_ref   = evidence://authorization-receipt-audit/<payload_sha256>
evidence_ref = ev_<canonical Evidence Plane ID>
```

`object_ref` identifies the exact sanitized content. `evidence_ref` binds that content to its canonical Evidence Plane custody record. One must not be substituted for the other.

Exact replay remains idempotent. If Evidence Plane custody succeeds but AuditSink append fails, the immutable evidence object is retained and a deterministic retry reuses the same custody record rather than deleting evidence or creating repeated copies.

The committed `platform/evidence-plane/authorization-audit-custody-policy.yaml` remains `DISABLED / deny / NOT_RUN / execution_authority: none`. Tests may enable an isolated temporary policy, but repository support is **not** evidence that live authorization-audit persistence is enabled or operational.

This remains **GREEN-REPO evidence only**. It does not mean the delivery socket, resolver, trust store, signer or live custody composition is operational.

## Remaining runtime blockers

Delivery composition, authorization decision auditing and repository-level Evidence Plane custody support now exist, but the live path remains disabled and has no demonstrated enabled runtime custody composition.

Before live promotion we still need:

1. an enabled delivery policy bound to a real socket path, peer uid and control-plane principal, provisioned by deployment;
2. configured and evidenced TB1 trust store on the Runner side;
3. real external signer/provider evidence consistent with the approved custody decision;
4. an enabled runtime authorization-audit custody composition with live persistence and verification evidence;
5. lifecycle/revocation behaviour for already-cached authorizations where required by live operation;
6. live negative tests for forged, expired, unknown, revoked and mismatched references;
7. explicit request-bound Human-in-the-Loop promotion approval after the remaining PRE_PROMOTION evidence is complete.

## Non-goals

This block does not implement real receipt issuance, private-key loading, socket provisioning, provider selection, trust installation, target traffic or runtime enablement. Repository audit/custody success is not execution or promotion authority.