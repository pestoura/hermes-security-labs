# TB1 Control Plane Authorization Contract

This directory implements the repository-level contract for the **Active authorization reference** crossing `TB1` from the Hermes control plane to the execution plane.

## Authority model

`ADR-0001` is authoritative: **Hermes is the only execution-authorization authority**. The gateway and runners may validate, restrict or refuse an authorization, but they may not create, expand or approve it.

The contract therefore uses a signed **authorization receipt**:

1. Hermes evaluates the active authorization/RoE context and the exact typed operation effect.
2. Hermes derives `authorization_ref` from the sanitized authorization body using domain-separated canonical JSON.
3. Hermes signs the complete receipt, including the derived reference.
4. The gateway verifies the receipt using a dedicated, purpose-bound public-key trust store.
5. The gateway independently re-evaluates the signed RoE contract and typed admission rules and requires an exact binding match.
6. Only the verified `authorization_ref` from the Hermes receipt is propagated to Runner Protocol v2.

The execution plane may recompute the expected reference **only as an integrity check**. Recomputing the digest does not create authority. A naked `authorization_ref` is never sufficient.

## Receipt contents

The receipt contains identifiers and digests only:

- authorization ID and reference;
- issue and expiry timestamps;
- campaign, run and step IDs;
- RoE contract ID and canonical payload SHA-256;
- RoE step-request ID;
- operation ID/version and capability;
- canonical SHA-256 of the validated operation parameters, never the raw parameters;
- target SHA-256 digest, never the raw target;
- intrusiveness level;
- detached signature envelope.

The parameter digest prevents a caller from changing the typed operation effect after Hermes has issued authorization. A parameter change requires a new control-plane receipt/reference even when the operation ID, target and intrusiveness level remain unchanged.

The receipt does **not** carry raw target values, operation parameters, credentials, tokens or secrets. `attempt_id` is deliberately excluded so a retry of the same logical step can reuse the same still-valid authorization receipt/reference.

Maximum receipt lifetime is **15 minutes**. Expired or not-yet-valid receipts fail closed.

## Hermes operational issuance boundary

`hermes_authorization_issuer.py` provides the repository-side issuance boundary that was previously missing.

The boundary accepts only the exact already-authorized effect fields required to bind a receipt. The caller cannot supply:

- issuer identity;
- `authorization_id`;
- `authorization_ref`;
- issue or expiry timestamps;
- signature algorithm/key metadata;
- signature bytes.

The issuer independently derives:

- the operation-parameter SHA-256 using the canonical authorization contract helper;
- the target SHA-256 using the canonical gateway target digest;
- the domain-separated authorization reference;
- the bounded validity window.

Signing is delegated through the minimal `ReceiptSigner` protocol. The Labs repository deliberately contains **no private-key loader, private-key path, seed, password or cryptographic provider credential**. A deployment may bind that protocol to an HSM, KMS, Vault transit engine or equivalent controlled signing service. The signing provider remains responsible for private-key custody and lifecycle.

The issuer remains fail-closed if:

- the effect envelope contains missing or caller-added fields;
- correlation identifiers are not canonical UUIDs;
- the RoE digest, target or operation parameters are malformed;
- the requested lifetime is outside `1..900` seconds;
- the signer key identity/algorithm is unsupported;
- signing fails or returns an invalid signature;
- the resulting receipt does not validate against the canonical receipt schema/reference contract.

The returned `IssuedAuthorization` keeps the complete signed receipt out of its default representation and exposes a sanitized summary for audit/logging. Repository implementation does **not** mean a signer, trust store or live issuance path has been deployed.

## Key-purpose separation

Authorization receipts use a dedicated trust store with:

- `domain: hex0r.tb1.authorization.v1`;
- `purpose: tb1-authorization` at store and key-entry level;
- public verification material only;
- Ed25519 or ECDSA-P256-SHA256 keys;
- key lifecycle `active`, `revoked` or `retired` plus optional validity windows.

A Rules of Engagement signing trust store does not contain this purpose/domain and therefore cannot be used as a TB1 authorization trust store. This prevents cross-protocol/key-confusion reuse.

Private keys, seeds, passphrases, tokens and credentials are rejected from trust-store inputs and are never committed to the repository.

## Deterministic refusal semantics

Version, domain and purpose mismatches have dedicated refusal codes and are checked before the generic strict-schema gate. Missing required fields remain schema-invalid. Unknown, revoked, retired, expired and not-yet-valid keys, malformed/invalid signatures, receipt validity failures and reference/body mismatches all fail closed.

## Files

- `authorization-receipt.schema.json` — strict signed receipt schema.
- `authorization-trust-store.schema.json` — strict purpose-bound public-key trust store schema.
- `authorization_receipt.py` — canonicalization/reference/parameter-digest helpers and fail-closed verifier.
- `hermes_authorization_issuer.py` — Hermes-only issuance boundary using an externally supplied purpose-bound signer.

## Runtime status

- receipt contract/schema: `CANDIDATE`;
- receipt verification logic: `CANDIDATE`;
- Hermes receipt issuance boundary: `IMPLEMENTED / GREEN-REPO-CANDIDATE`;
- production signer binding/private-key custody: `NOT_CONFIGURED / NOT_RUN`;
- deployed authorization trust store: `NOT_RUN`;
- live Hermes receipt issuance: `NOT_RUN`;
- deployed gateway validation: `NOT_RUN`;
- real runner dispatch/capability execution: `NOT_RUN`;
- runtime changes: `NO_RUNTIME_CHANGE`.

Nothing in this directory contains private-key material, dispatches work, connects to a runner, touches a target or changes runtime state. The issuer may call only an injected signer implementation when explicitly invoked by a future Hermes control-plane integration.
