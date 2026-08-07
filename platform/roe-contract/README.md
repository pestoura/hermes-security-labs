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

The repository deliberately does not embed any private key, seed or other
secret material, and no key material of any kind is committed to Git.
`validate_contract_for_execution()` requires a caller-supplied verifier and
fails closed when no verifier is available.

`trust_store.py` provides a **file-backed trust store** holding public
verification material only, plus real cryptographic verification for the two
algorithms in the schema (`Ed25519` and `ECDSA-P256-SHA256`, via
`cryptography`). Deployments point the store at a path outside the repository.

Trust-store document (`schema_version: 1.0.0`):

```json
{
  "schema_version": "1.0.0",
  "keys": [
    {
      "key_id": "roe-signing-ed25519-001",
      "algorithm": "Ed25519",
      "state": "active",
      "public_key": "<base64 SubjectPublicKeyInfo DER>",
      "not_before": "2026-08-01T00:00:00Z",
      "not_after": "2027-08-01T00:00:00Z"
    }
  ]
}
```

Deterministic refusal codes: `SIGNATURE_KEY_UNKNOWN`, `SIGNATURE_KEY_REVOKED`,
`SIGNATURE_KEY_NOT_ACTIVE`, `SIGNATURE_KEY_EXPIRED`,
`SIGNATURE_KEY_NOT_YET_VALID`, `SIGNATURE_ALGORITHM_MISMATCH`,
`SIGNATURE_MALFORMED`, `SIGNATURE_INVALID`, `TRUST_STORE_UNAVAILABLE`,
`TRUST_STORE_INVALID`, `TRUST_STORE_SCHEMA_UNSUPPORTED`,
`TRUST_STORE_DUPLICATE_KEY_ID`, `TRUST_STORE_ALGORITHM_UNSUPPORTED`,
`TRUST_STORE_KEY_ALGORITHM_MISMATCH`, `TRUST_STORE_SECRET_MATERIAL`,
`CRYPTO_BACKEND_UNAVAILABLE`.

An entry carrying a field named like secret material (`private_key`, `seed`,
`passphrase`, ...) is rejected outright, so a leaked private key can never be
loaded silently.

The legacy callable-verifier interface is unchanged: any
`(payload, signature) -> bool` remains accepted, and test scaffolding verifiers
are still test scaffolding, not a production mechanism.

## External kill switch

`kill_switch.py` implements an operator-controlled switch that lives **outside**
the step request, so execution can be halted without cooperation from the
requesting component. It is opt-in through
`authorize_step(..., kill_switch_path=...)`; omitting the argument preserves the
previous behaviour exactly.

```json
{
  "schema_version": "1.0.0",
  "state": "engaged",
  "scope": "global",
  "reason_code": "operator-halt",
  "updated_at": "2026-08-10T09:30:00Z"
}
```

- `state: engaged` refuses every step with `KILL_SWITCH_ACTIVE`.
- `scope: campaign` additionally requires a matching `campaign_id`.
- Missing, unreadable, malformed or unsupported documents refuse with
  `KILL_SWITCH_UNAVAILABLE` / `KILL_SWITCH_INVALID` /
  `KILL_SWITCH_SCHEMA_UNSUPPORTED`. Absence of evidence is never read as
  "released".
- The switch is evaluated **before** contract validation, so an engaged switch
  halts execution even when the contract itself is untrustworthy.

## Deployment

1. Generate the signing key pair outside this repository, on the signing host.
2. Export only the public key as base64 SubjectPublicKeyInfo DER into the trust
   store file; never copy the private key anywhere near the repository.
3. Store the trust store and kill-switch documents outside Git, readable by the
   authorizing process only.
4. Pass both paths explicitly:
   `authorize_step(contract, request, build_trust_store_verifier(store_path),
   kill_switch_path=switch_path)`.
5. Revocation is a state change to `revoked` in the trust store; engaging the
   kill switch is a state change to `engaged` in the switch document.

Runtime status of this deployment procedure: `NOT_RUN`.

## Files

- `roe-contract.schema.json` — RoE document schema.
- `roe-step-request.schema.json` — proposed-step decision input.
- `intrusiveness-policy.yaml` — canonical L0-L4 approval and rollback matrix.
- `roe_contract.py` — structural, semantic, signature-boundary and authorization decision logic.
- `trust_store.py` — file-backed public-key trust store and cryptographic verifier.
- `kill_switch.py` — external file-backed kill switch.
- `../tests/test_roe_contract.py` — positive, negative and adversarial tests.
- `../tests/test_roe_trust_store.py` — trust store and kill-switch tests.

## Canonical admission path

`authorize_step()` is the RoE decision function; it is **not** the enforcement
boundary by itself. The canonical admission/enforcement API is
[`platform/gateway-protocol/admission.py`](../gateway-protocol/admission.py)
(`authorize_admission()`), which derives the RoE decision internally from the
signed contract, this step request, the trust store and the external kill
switch, and refuses any caller-supplied RoE decision. Runtime gateway
integration: `NOT_RUN`.

## Current status

- Contract and decision logic: `CANDIDATE`.
- Trust store and cryptographic verification: `CANDIDATE`.
- External kill switch: `CANDIDATE`.
- Gateway enforcement: `NOT_RUN`.
- Hermes trust-store integration: `NOT_IMPLEMENTED`.
- Production signature verification: `NOT_RUN`.
- Runtime deployment of the trust store or kill switch: `NOT_RUN`.
- Runtime changes: `NO_RUNTIME_CHANGE`.

