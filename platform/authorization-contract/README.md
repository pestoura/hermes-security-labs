# TB1 Control Plane Authorization Contract

This directory implements the repository-level contract for the **Active authorization reference** crossing `TB1` from the Hermes control plane to the execution plane.

## Authority model

`ADR-0001` is authoritative: **Hermes is the only execution-authorization authority**. The gateway and runners may validate, restrict or refuse an authorization, but they may not create, expand or approve it.

The contract therefore uses a signed **authorization receipt**:

1. Hermes evaluates the active authorization/RoE context.
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
- target SHA-256 digest, never the raw target;
- intrusiveness level;
- detached signature envelope.

It does **not** carry raw target values, operation parameters, credentials, tokens or secrets. `attempt_id` is deliberately excluded so a retry of the same logical step can reuse the same authorization receipt/reference.

Maximum receipt lifetime is **15 minutes**. Expired or not-yet-valid receipts fail closed.

## Key-purpose separation

Authorization receipts use a dedicated trust store with:

- `domain: hex0r.tb1.authorization.v1`;
- `purpose: tb1-authorization` at store and key-entry level;
- public verification material only;
- Ed25519 or ECDSA-P256-SHA256 keys;
- key lifecycle `active`, `revoked` or `retired` plus optional validity windows.

A Rules of Engagement signing trust store does not contain this purpose/domain and therefore cannot be used as a TB1 authorization trust store. This prevents cross-protocol/key-confusion reuse.

Private keys, seeds, passphrases, tokens and credentials are rejected from trust-store inputs and are never committed to the repository.

## Files

- `authorization-receipt.schema.json` — strict signed receipt schema.
- `authorization-trust-store.schema.json` — strict purpose-bound public-key trust store schema.
- `authorization_receipt.py` — canonicalization/reference helpers and fail-closed verifier.

## Runtime status

- receipt contract/schema: `CANDIDATE`;
- receipt verification logic: `CANDIDATE`;
- Hermes operational receipt issuance: `NOT_IMPLEMENTED` / `NOT_RUN`;
- deployed authorization trust store: `NOT_RUN`;
- deployed gateway validation: `NOT_RUN`;
- real runner dispatch/capability execution: `NOT_RUN`;
- runtime changes: `NO_RUNTIME_CHANGE`.

Nothing in this directory signs with or loads a private key, dispatches work, connects to a runner, touches a target or changes runtime state.
