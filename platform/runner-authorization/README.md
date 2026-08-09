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

## Remaining runtime blocker

This candidate still does not define **how a verified receipt reaches the Runner process**. That must be supplied by an authenticated, purpose-bound composition path; it must not be added as caller-controlled fields inside `runner.step.request`.

Before live promotion we still need:

1. trusted receipt delivery/population from the control plane;
2. configured TB1 trust store on the Runner side;
3. lifecycle/revocation behaviour for cached authorizations;
4. audit evidence for receipt registration and lookup decisions;
5. integration with the target-bound adapter so it checks the full `VerifiedAuthorization` binding against the Runner request;
6. live negative tests for forged, expired, unknown and mismatched references.

## Non-goals

This block does not implement receipt issuance, private-key loading, routing, transport identity, adapter execution, Evidence Plane persistence, target traffic or runtime enablement.
