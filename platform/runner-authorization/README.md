# Runner authorization reference resolver

This directory provides the execution-plane lookup boundary for TB1 `authorization_ref` values. It does **not** issue or approve authorization.

## Authority model

Hermes remains the only execution-authorization authority. The resolver has one trusted ingest path:

1. receive a signed TB1 receipt through a future trusted composition boundary;
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

## Remaining runtime blocker

Delivery composition now exists in the repository, but it is not enabled and not wired to a real socket.

Before live promotion we still need:

1. an enabled delivery policy bound to a real socket path, peer uid and control-plane principal, provisioned by deployment;
2. configured TB1 trust store on the Runner side;
3. lifecycle/revocation behaviour for cached authorizations;
4. audit evidence for receipt registration and lookup decisions;
5. integration with the target-bound adapter so it checks the full `VerifiedAuthorization` binding against the Runner request;
6. live negative tests for forged, expired, unknown and mismatched references.

## Non-goals

This block does not implement receipt issuance, private-key loading, routing, transport identity, adapter execution, Evidence Plane persistence, target traffic or runtime enablement.
