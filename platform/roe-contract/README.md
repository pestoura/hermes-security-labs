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

The repository deliberately does not embed a private key, trust store or cryptographic implementation. `validate_contract_for_execution()` requires a caller-supplied verifier and fails closed when no verifier is available. Production trust-store integration remains `NOT_IMPLEMENTED`.

The test verifier is deterministic test scaffolding only and is not a production signature mechanism.

## Files

- `roe-contract.schema.json` — RoE document schema.
- `roe-step-request.schema.json` — proposed-step decision input.
- `intrusiveness-policy.yaml` — canonical L0-L4 approval and rollback matrix.
- `roe_contract.py` — structural, semantic, signature-boundary and authorization decision logic.
- `../tests/test_roe_contract.py` — positive, negative and adversarial tests.

## Current status

- Contract and decision logic: `CANDIDATE`.
- Gateway enforcement: `NOT_RUN`.
- Hermes trust-store integration: `NOT_IMPLEMENTED`.
- Production signature verification: `NOT_RUN`.
- Runtime changes: `NO_RUNTIME_CHANGE`.
