# Typed Security Gateway Protocol candidate

This directory contains the contract-only first block for `SVP2-B-01` / issue #79.

## Boundary

The implementation validates a typed operation request and returns a deterministic allow/refuse decision. It does not dispatch, execute, schedule, cancel or connect to Kali MCP, Hermes, a runner, a laboratory, a network or a target.

## Fail-closed checks

- every operation is declared in a versioned registry;
- every request and operation parameter set validates against JSON Schema;
- generic execution, command, shell, argv, cwd and environment fields are forbidden;
- the `normal` profile exposes only explicit L0/L1 operations;
- capabilities must be attested;
- an exact RoE ALLOW decision must bind the campaign, operation and target digest;
- the operation intrusiveness level cannot exceed the RoE ceiling;
- runtime state must be `IN_SYNC`;
- observed and canonical digests must match the repository-owned `platform/registry.yaml`;
- `DRIFT_DETECTED`, `UNKNOWN`, malformed or missing evidence always refuses.

## Canonical admission API

`admission.py::authorize_admission()` is the **canonical enforcement/admission
API**. It does not accept a caller-supplied RoE decision: it derives the
decision internally from the signed RoE contract, the RoE step request, the
file-backed trust store and the external kill switch, and only then binds it to
the typed operation checks.

- input schema: `admission-request.schema.json` (`additionalProperties: false`,
  no `roe_decision` property);
- a request carrying `roe_decision`, `roe_decision_ref` or `authorized` is
  refused with `ROE_DECISION_CALLER_SUPPLIED`; a forged `ALLOW` can never
  produce an admission;
- campaign, RoE step request id, operation/capability, target digest,
  intrusiveness level and contract payload hash are bound deterministically;
- a missing kill-switch source (`KILL_SWITCH_SOURCE_REQUIRED`) or a missing
  trust store (`SIGNATURE_VERIFIER_UNAVAILABLE`) refuses fail-closed, as does
  any integration defect (`ROE_INTEGRATION_ERROR`, `TYPED_GATEWAY_ERROR`);
- the signature verifier is **not caller-overridable**: `trust_store_path` is
  required and the verifier is always built internally with
  `roe_contract.build_trust_store_verifier(trust_store_path)` against the
  verifier's real clock. The API exposes no verifier callable and no `now`
  parameter, so neither the cryptographic check nor key validity windows can
  be substituted or time-shifted by a caller;
- decisions expose stable codes and identifiers only — never targets,
  operation parameters, signatures or key material.

`authorize_typed_operation()` remains available for backwards compatibility
with the existing typed-contract callers and tests. It consumes a
caller-supplied `roe_decision` and is therefore **not** an enforcement
boundary on its own; it must be reached through `authorize_admission()`. No
new bypass is introduced by this block.

## Status

- typed contract and decision logic: `CANDIDATE`;
- canonical admission boundary: `CANDIDATE`;
- runtime gateway integration: `NOT_RUN`;
- normal profile arbitrary command exposure: `FORBIDDEN`;
- Kali MCP handler integration: `NOT_RUN`;
- gateway deployment: `NOT_RUN`;
- production runtime observation: `NOT_RUN`;
- runtime changes: `NO_RUNTIME_CHANGE`.
