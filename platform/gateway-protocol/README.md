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

## Status

- typed contract and decision logic: `CANDIDATE`;
- normal profile arbitrary command exposure: `FORBIDDEN`;
- Kali MCP handler integration: `NOT_RUN`;
- gateway deployment: `NOT_RUN`;
- production runtime observation: `NOT_RUN`;
- runtime changes: `NO_RUNTIME_CHANGE`.
