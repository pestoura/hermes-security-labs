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
- RoE is freshly revalidated against the signed contract, target and operation;
- a separate Hermes-issued TB1 authorization receipt must validate and bind exactly to the admitted typed effect before runner-message construction;
- the operation intrusiveness level cannot exceed the RoE ceiling;
- runtime state must be `IN_SYNC`;
- observed and canonical digests must match the repository-owned `platform/registry.yaml`;
- any unknown, missing, expired, revoked or mismatched authorization evidence refuses.

## Canonical admission API

`admission.py::authorize_admission()` is the **canonical RoE/typed-operation admission API**. It does not accept a caller-supplied RoE decision: it derives the decision internally from the signed RoE contract, the RoE step request, the file-backed RoE trust store and the external kill switch, and only then binds it to typed operation checks.

- input schema: `admission-request.schema.json` (`additionalProperties: false`, no `roe_decision` property);
- a request carrying `roe_decision`, `roe_decision_ref` or `authorized` is refused with `ROE_DECISION_CALLER_SUPPLIED`;
- campaign, RoE step request id, operation/capability, target digest, intrusiveness level and contract payload hash are bound deterministically;
- missing kill-switch or RoE trust-store sources refuse fail-closed;
- the signature verifier is not caller-overridable and uses the real clock;
- decisions expose stable codes and identifiers only — never targets, parameters, signatures or key material.

`authorize_typed_operation()` remains available for compatibility with existing typed-contract tests. Because it consumes a caller-supplied `roe_decision`, it is **not** an enforcement boundary on its own and must not be used as proof of authorization.

## TB1 authorization authority

`ADR-0001` is authoritative: **Hermes/control plane is the only execution authorization authority**. The execution gateway may validate, restrict or refuse authorization but may not create, expand or approve it.

The canonical TB1 contract lives in [`../authorization-contract/`](../authorization-contract/README.md):

- Hermes issues a short-lived signed authorization receipt containing identifiers and digests only;
- the receipt binds the exact typed effect through operation ID/version, capability, target digest, intrusiveness and the canonical SHA-256 of validated operation parameters;
- the receipt carries a deterministic `authorization_ref` derived by the control plane using domain-separated canonical JSON;
- the gateway uses a dedicated `tb1-authorization` trust purpose/domain, separate from RoE signing, preventing cross-protocol key confusion;
- the execution plane may recompute the expected reference only to check receipt integrity. That recomputation does **not** create authority;
- a naked `authorization_ref`, embedded receipt or caller-supplied `ALLOW` is never sufficient;
- Hermes operational receipt issuance remains `NOT_IMPLEMENTED` and `NOT_RUN`; deployed verification remains `NOT_RUN`.

## Canonical Runner Protocol v2 handoff

`runner_handoff.py::build_step_request()` is the canonical repository-level path from TB1 authorization and fresh gateway admission to a Runner Protocol v2 `runner.step.request`.

The order is fail-closed:

1. reject authorization/policy fields embedded in the typed request;
2. validate service dispatch policy;
3. verify the separate signed Hermes TB1 authorization receipt and dedicated trust store;
4. freshly execute `authorize_admission()` against signed RoE + kill switch + typed gateway bindings;
5. require exact receipt/admission binding for campaign, run, step, RoE contract id/hash, RoE step request, operation/version, **operation-parameters digest**, capability, target digest and intrusiveness;
6. enforce Runner Protocol correlation requirements;
7. construct and semantically validate the Runner Protocol message.

Any refusal returns `runner_request=None`.

- a caller-supplied `admission_decision`, `authorization_receipt`, `roe_decision`, `roe_decision_ref`, `authorized` or `authorization_ref` inside the typed request is refused with `HANDOFF_CALLER_SUPPLIED_AUTHORIZATION`;
- the positive outcome field is named `request_built`, not `dispatched`: it means only that a valid message was constructed; nothing here sends, schedules, accepts or executes it;
- `RunnerHandoffResult` metadata is sanitized. `runner_request` is RESTRICTED operational payload containing the raw target and validated parameters needed by a future runner, is excluded from `repr()`, and must not be logged as a decision;
- the emitted `authorization_ref` is copied **exactly from the verified Hermes receipt**. The gateway never creates a reference;
- the receipt reference is not a bearer token, grant, capability or signature and grants nothing by possession;
- changing validated operation parameters requires a new Hermes receipt/reference even if operation ID, target and intrusiveness are unchanged;
- `attempt_id` is deliberately excluded from the TB1 authorization receipt/reference so retries of the same logical step can reuse still-valid authority. It remains mandatory Runner Protocol correlation data;
- Runner Protocol v2 requires UUID correlation IDs. No substitute UUID is generated and no identifier is silently normalized;
- `idempotency_key` is derived from the logical effect plus the verified authorization reference, excluding `attempt_id` and timestamps;
- `operation.input` is derived only from the typed target, validated operation parameters and minimal metadata. Command, shell, argv, cwd, environment and secret-like fields remain forbidden;
- timeout, retry, cancellation and progress behavior comes from typed service configuration, never request data;
- `emitted_at` is produced internally in UTC with no caller-overridable clock.

This block proves contract/message boundaries only. It is not connected to synthetic candidates, a supervisor or any runtime process: `execution_integration: NOT_RUN`, `NO_RUNTIME_CHANGE`.

## Status

- typed contract and decision logic: `CANDIDATE`;
- canonical admission boundary: `CANDIDATE`;
- TB1 signed authorization receipt/verifier: `CANDIDATE`;
- Hermes authorization receipt issuance: `NOT_IMPLEMENTED` and `NOT_RUN`;
- canonical gateway -> Runner Protocol v2 handoff: `CANDIDATE`;
- runtime authorization-ref resolution: `NOT_IMPLEMENTED` and `NOT_RUN`;
- runner execution integration: `execution_integration: NOT_RUN`;
- runtime gateway integration: `NOT_RUN`;
- normal profile arbitrary command exposure: `FORBIDDEN`;
- Kali MCP handler integration: `NOT_RUN`;
- gateway deployment: `NOT_RUN`;
- production runtime observation: `NOT_RUN`;
- runtime changes: `NO_RUNTIME_CHANGE`.
