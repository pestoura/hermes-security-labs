# Rules of Engagement Contract v1

This directory contains the contract-only implementation for `EPIC-28 — Rules of Engagement as Code` / issue #77.

## Delivered boundary

The implementation validates a machine-readable engagement contract and produces a deterministic allow/refuse decision for a proposed step. It does not dispatch, execute, schedule or cancel any runtime operation.

The contract covers:

- customer and provider identities;
- campaign and contract identifiers;
- validity and execution windows;
- target allowlists and explicit exclusions;
- capability allowlists and prohibitions;
- an intrusiveness ceiling from `L0` to `L4`;
- approvers, emergency contacts and stop conditions;
- request-rate, concurrency, data and duration limits;
- explicit treatment of credential use, lateral movement, persistence, evasion, destructive actions, data exfiltration, denial of service and mass data access;
- a detached signature envelope with canonical payload digest.

## Fail-closed rules

- An active contract is unusable without an external signature verifier.
- A payload digest mismatch is rejected before scope evaluation.
- Exclusions override broader allow rules.
- Only a `RUNNING` campaign may authorize a step.
- The kill switch and any active stop condition block execution.
- `L2` and above require step approval; `L3` and `L4` require rollback plans; `L4` requires two approvals from distinct sides.
- High-risk actions are denied unless explicitly allowed at a sufficient level.
- Unknown properties and secret-bearing field names are rejected.
- A decision contains identifiers and stable codes only; it does not copy the signature or raw contract.

## Signature boundary

The repository deliberately does not embed any private key or secret. Trust material is loaded at runtime from an **operator-provided file outside version control**, containing only SPKI-encoded public keys.

`roe_trust_store.py` implements:

- `TrustStore.load(path)` — schema-validated, fail-closed load of the key file. Missing, unreadable, oversized, malformed, schema-invalid, duplicate-`key_id`, invalid-validity or unparsable-key files all refuse deterministically.
- `TrustStore.resolve(key_id, algorithm, moment)` — a `key_id` resolves to exactly one key; unknown, revoked, out-of-validity or algorithm-mismatched keys refuse with `TRUST_STORE_KEY_UNKNOWN`, `TRUST_STORE_KEY_REVOKED`, `TRUST_STORE_KEY_EXPIRED` and `TRUST_STORE_ALGORITHM_MISMATCH`.
- `verify_with_trust_store(...)` — real cryptographic verification for the algorithms already declared by the schema: `Ed25519` and `ECDSA-P256-SHA256` (SHA-256, DER signature), via `cryptography`.

`authorize_step()` keeps its original caller-supplied `verifier` contract. It additionally accepts `trust_store_path=`; when no explicit verifier is supplied, the file-backed store becomes the verifier. With neither, the decision still fails closed with `SIGNATURE_VERIFIER_UNAVAILABLE`.

Key file layout is defined by `roe-trust-store.schema.json`; `examples/trust-store.example.json` shows the shape with a placeholder public key only.

## External kill switch

`authorize_step()` accepts `kill_switch_path=`. When configured, the file-backed state is consulted on every decision:

- `state: armed` — no effect;
- `state: engaged` without scope — blocks every campaign (`KILL_SWITCH_ENGAGED`);
- `state: engaged` with `scope.campaign_id` — blocks only that campaign;
- missing, unreadable, malformed or schema-invalid file — refuses with `KILL_SWITCH_UNAVAILABLE`, `KILL_SWITCH_MALFORMED` or `KILL_SWITCH_SCHEMA_INVALID`.

The state file carries no commands, tokens or secrets: only a state, a timestamp, an optional campaign scope and an optional uppercase reason code. The reason code is never copied into the decision.

When `kill_switch_path` is not supplied the behaviour is unchanged, preserving backwards compatibility with the request-level `kill_switch` boolean, which continues to apply independently.

## Files

- `roe-contract.schema.json` — RoE document schema.
- `roe-step-request.schema.json` — proposed-step decision input.
- `roe-trust-store.schema.json` — trust store key file schema.
- `roe-kill-switch.schema.json` — external kill-switch state schema.
- `intrusiveness-policy.yaml` — canonical L0-L4 approval and rollback matrix.
- `roe_contract.py` — structural, semantic, signature-boundary and authorization decision logic.
- `roe_trust_store.py` — file-backed trust store, real signature verification and kill-switch state.
- `examples/trust-store.example.json` — non-secret example key file.
- `examples/kill-switch.example.json` — non-secret example kill-switch state.
- `../tests/test_roe_contract.py` — positive, negative and adversarial tests.
- `../tests/test_roe_trust_store.py` — trust store and kill-switch unit tests.
- `../tests/test_roe_trust_store_authorization.py` — end-to-end authorization tests with real signatures.

## Dependencies

`cryptography` is required for signature verification and is pinned in the `validate` workflow. The base contract module imports the trust store lazily, so structural validation and caller-supplied verifiers keep working without it; a trust store load without `cryptography` refuses with `TRUST_STORE_CRYPTO_UNAVAILABLE`.

## Current status

- Contract and decision logic: `CANDIDATE`.
- Trust store and signature verification logic: `CANDIDATE`.
- Gateway enforcement: `NOT_RUN`.
- Hermes trust-store integration: `NOT_IMPLEMENTED`.
- Production signature verification: `NOT_RUN`.
- Real deployment of a trust store or kill switch: `NOT_RUN`.
- Runtime changes: `NO_RUNTIME_CHANGE`.
