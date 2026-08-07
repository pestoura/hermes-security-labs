# Typed Security Gateway Protocol candidate

This directory contains the contract-only first block for `SVP2-B-01` / issue #79.

## Boundary

The implementation validates typed operation requests, constructs Runner Protocol requests after authorization, and derives sanitized terminal outcomes. It does not dispatch, execute, schedule, cancel or connect to Kali MCP, Hermes, a runner, a laboratory, a network or a target.

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
- any unknown, missing, expired, revoked or mismatched authorization evidence refuses;
- a terminal runner outcome must validate against Runner Protocol v2 and match the exact sealed request correlation before a control-plane derivative is built.

## Versioned correlation contract

`2.0.0` is the canonical request contract for new gateway/admission integrations. This decision is recorded in [`ADR-0010`](../../docs/architecture/adr/ADR-0010-versioned-uuid-correlation-contract.md).

- `admission-request-v2.schema.json` is the canonical external admission request;
- `gateway-request-v2.schema.json` is the canonical internal typed-evaluation request;
- both v2 schemas require UUID `campaign_id`, `run_id`, `step_id` and `attempt_id`;
- the original v1 schema files remain unchanged as transitional compatibility;
- unknown schema versions fail closed;
- `promote_legacy_request_to_v2()` changes only `schema_version` and succeeds only when the existing v1 identifiers already satisfy v2;
- no gateway, migration helper or handoff may generate, map, replace or normalize correlation identifiers;
- transitional v1 input may cross the Runner handoff only when all four existing correlation identifiers are already valid UUIDs.

This versioning is a repository contract change only. It does not create runtime correlation state and does not authorize execution.

## Canonical admission API

`admission.py::authorize_admission()` is the **canonical RoE/typed-operation admission API**. It does not accept a caller-supplied RoE decision: it derives the decision internally from the signed RoE contract, the RoE step request, the file-backed RoE trust store and the external kill switch, and only then binds it to typed operation checks.

- v1 and v2 admission schemas are selected explicitly from `schema_version`;
- a request carrying `roe_decision`, `roe_decision_ref` or `authorized` is refused with `ROE_DECISION_CALLER_SUPPLIED`;
- campaign, RoE step request id, operation/capability, target digest, intrusiveness level and contract payload hash are bound deterministically;
- missing kill-switch or RoE trust-store sources refuse fail-closed;
- the signature verifier is not caller-overridable and uses the real clock;
- decisions expose stable codes and identifiers only — never targets, parameters, signatures or key material.

`authorize_typed_operation()` remains available for compatibility with existing typed-contract tests. Because it consumes a caller-supplied `roe_decision`, it is **not** an enforcement boundary on its own and must not be used as proof of authorization.

## TB1 authorization authority

`ADR-0001` is authoritative: **Hermes/control plane is the only execution authorization authority**. The execution gateway may validate, restrict or refuse authorization but may not create, expand or approve it.

The canonical TB1 authorization contract lives in [`../authorization-contract/`](../authorization-contract/README.md):

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
6. enforce UUID Runner Protocol correlation requirements without rewriting identifiers;
7. construct and semantically validate the Runner Protocol message.

Any refusal returns `runner_request=None`.

- a caller-supplied `admission_decision`, `authorization_receipt`, `roe_decision`, `roe_decision_ref`, `authorized` or `authorization_ref` inside the typed request is refused with `HANDOFF_CALLER_SUPPLIED_AUTHORIZATION`;
- the positive outcome field is named `request_built`, not `dispatched`: it means only that a valid message was constructed; nothing here sends, schedules, accepts or executes it;
- `RunnerHandoffResult` metadata is sanitized. `runner_request` is RESTRICTED operational payload containing the raw target and validated parameters needed by a future runner, is excluded from `repr()`, and must not be logged as a decision;
- the emitted `authorization_ref` is copied **exactly from the verified Hermes receipt**. The gateway never creates a reference;
- the receipt reference is not a bearer token, grant, capability or signature and grants nothing by possession;
- changing validated operation parameters requires a new Hermes receipt/reference even if operation ID, target and intrusiveness are unchanged;
- `attempt_id` is
  deliberately excluded from the TB1 authorization receipt/reference so retries of the same logical step can reuse still-valid authority. It remains mandatory Runner Protocol correlation data;
- Runner Protocol v2 requires UUID correlation IDs. No substitute UUID is generated and no identifier is silently normalized;
- `idempotency_key` is derived from the logical effect plus the verified authorization reference, excluding `attempt_id` and timestamps;
- `operation.input` is derived only from the typed target, validated operation parameters and minimal metadata. Command, shell, argv, cwd, environment and secret-like fields remain forbidden;
- timeout, retry, cancellation and progress behavior comes from typed service configuration, never request data;
- `emitted_at` is produced internally in UTC with no caller-overridable clock.

## Typed execution outcome

`outcome.py` implements the repository-level `runner.outcome` → gateway → Hermes contract already declared at TB1. It is descriptive only and never creates, extends or validates execution authority.

The boundary has two steps:

1. `seal_handoff_result()` is called immediately after a valid `runner.step.request` is built. It validates the handoff metadata, creates an immutable canonical JSON snapshot of the **complete** Runner request and stores `request_envelope_sha256`. The normal Runner `request_fingerprint` is retained separately because it intentionally excludes retry-specific fields such as `attempt_id`;
2. `build_execution_outcome()` validates a terminal Runner Protocol v2 outcome against that sealed snapshot, requires exact four-ID correlation and derives `gateway.execution.outcome` using `gateway-execution-outcome.schema.json`.

The control-plane derivative carries only:

- exact campaign/run/step/attempt correlation;
- the non-bearer `authorization_ref` and idempotency key from the sealed request;
- logical request fingerprint plus full sealed-request SHA-256;
- operation/capability identity;
- terminal status and timestamps;
- evidence ID, kind, classification and SHA-256;
- `output_present` as a boolean;
- normalized error `code`, `category` and `retryable` when applicable.

It deliberately excludes:

- raw Runner `output`;
- target and operation parameters;
- evidence `uri`;
- error `message` and `safe_context`;
- credentials, secrets or authorization receipts;
- any field that could turn the result into an authorization grant.

A SHA-256 of the raw Runner outcome is also deliberately **not** forwarded because arbitrary raw output may contain sensitive low-entropy data. Integrity of retained raw artefacts belongs to `evidence_refs.sha256` and the future Evidence Plane.

The boundary validates Runner Protocol semantics but does **not** prove the identity of a real runner or transport authenticity. Runner authentication, deployed gateway outcome reception, persistence and Evidence Plane integration remain `NOT_IMPLEMENTED` / `NOT_RUN`.

This outcome block is contract transformation only. An `outcome_built=True` result means only that a sanitized derivative was constructed from a structurally valid, correlation-matched outcome; it does not prove that a real runner actually executed the operation.

## Status

- typed contract and decision logic: `CANDIDATE`;
- canonical admission boundary: `CANDIDATE`;
- canonical UUID correlation contract v2: `CANDIDATE`;
- legacy v1 correlation contract: `TRANSITIONAL_COMPATIBILITY`;
- TB1 signed authorization receipt/verifier: `CANDIDATE`;
- Hermes authorization receipt issuance: `NOT_IMPLEMENTED` and `NOT_RUN`;
- canonical gateway -> Runner Protocol v2 handoff: `CANDIDATE`;
- typed execution outcome schema/derivation: `CANDIDATE`;
- real runner identity/transport authentication: `NOT_IMPLEMENTED` / `NOT_RUN`;
- deployed gateway outcome reception: `NOT_RUN`;
- Evidence Plane outcome persistence: `NOT_RUN`;
- runtime authorization-ref resolution: `NOT_IMPLEMENTED` / `NOT_RUN`;
- runner execution integration: `execution_integration: NOT_RUN`;
- runtime gateway integration: `NOT_RUN`;
- normal profile arbitrary command exposure: `FORBIDDEN`;
- Kali MCP handler integration: `NOT_RUN`;
- gateway deployment: `NOT_RUN`;
- production runtime observation: `NOT_RUN`;
- runtime changes: `NO_RUNTIME_CHANGE`.
