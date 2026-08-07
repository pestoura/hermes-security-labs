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

## Canonical Runner Protocol v2 handoff

`runner_handoff.py::build_step_request()` is the canonical path that turns an
*admitted* typed operation into a Runner Protocol v2 `runner.step.request`. It
imports the canonical `runner_protocol_v2` SDK and duplicates no protocol
schema or logic.

- authorization is **issued by the Hermes control plane**, never by this
  gateway. `build_step_request()` requires two separate TB1 artefacts: the
  typed gateway request (which carries no authorization at all) and
  `authorization_receipt_document`, a signed control-plane authorization
  receipt supplied through the Hermes -> gateway boundary parameter. A
  caller-supplied `admission_decision`, `roe_decision`, `roe_decision_ref`,
  `authorized`, `authorization`, `authorization_receipt` or
  `authorization_ref` embedded in the typed request is refused with
  `HANDOFF_CALLER_SUPPLIED_AUTHORIZATION` before anything else runs. A naked
  `authorization_ref` without a signed receipt is never accepted;
- the fail-closed sequence is: service configuration -> receipt verification
  (schema, domain, control-plane issuer, validity window, key purpose,
  reference integrity, signature) -> `authorize_admission()` -> exact
  cross-check of the verified receipt against the freshly admitted context
  (campaign/run/step, RoE contract id and payload hash, RoE step request id,
  operation id/version, capability, canonical target digest, intrusiveness
  level) -> UUID correlation gate -> message construction. Any divergence
  yields `runner_request=None` and a stable sanitized code;
- the authorization signing keys live in a **dedicated, purpose-bound**
  authorization trust store (`purpose: tb1-authorization`), configured
  server-side via `RunnerHandoffConfig.authorization_trust_store_path`. It is
  deliberately not the RoE signing trust store: a valid RoE-purpose key is
  refused with `AUTHORIZATION_KEY_PURPOSE_MISMATCH`, which closes the
  cross-protocol key-confusion path;
- a message is built only after a positive admission **and** successful
  `runner_protocol_v2.validate_semantics()`; any refusal or integration defect
  returns `runner_request=None`. There is no partial construction and no
  partial effect;
- the positive outcome field is named `request_built`, not `dispatched`: it
  states only that a valid `runner.step.request` was *constructed*. Nothing in
  this block dispatches, sends, schedules, accepts or executes a request, and
  no result field may be read as evidence that it did;
- `RunnerHandoffResult` separates two confidentiality levels. Its metadata
  (codes, identifiers, `authorization_ref`, `idempotency_key`,
  `request_fingerprint`) is sanitized and safe to record as a decision.
  `runner_request` is **not** sanitized: it deliberately carries the raw target
  and the operation parameters for future runner consumption, so it is
  RESTRICTED operational payload, is excluded from the dataclass `repr()` and
  must never be logged or persisted as a decision. `sanitized_summary()`
  returns the log-safe projection, with `runner_request_present` as a boolean
  presence flag only;
- the emitted `authorization_ref` is exactly the reference carried by the
  verified receipt, i.e. the one issued by the control plane. The gateway
  never mints one. It may recompute the expected reference with
  `expected_authorization_ref()` **solely to verify** that the supplied
  reference matches the signed body; recomputation is an integrity check and
  creates no authority. The canonical derivation
  (`hex0r-authz:v1:<digest>`, domain-separated by
  `hex0r.tb1.authorization.v1` over the sanitized authorization body
  excluding the reference and the signature) is owned by
  [`platform/roe-contract/authorization_receipt.py`](../roe-contract/README.md).
  `attempt_id` is not part of the authorization at all, so retries of the same
  logical step reuse the same receipt and the same reference, while a
  different `run_id` requires a different receipt and yields a different
  reference. It remains a **reference**: not a bearer token, not a grant, not
  a capability and not a signature. The raw target value is never part of it,
  only its digest. Runtime resolution of the reference against a trusted
  authority / control plane is `NOT_IMPLEMENTED` and `NOT_RUN`;
- the four Runner Protocol correlation identifiers are preserved exactly.
  Runner Protocol v2 requires UUIDs while the existing gateway schema still
  allows non-UUID identifiers; that gap is exposed fail-closed here with
  `CORRELATION_NOT_UUID:<field>`. No substitute UUID is generated and no
  identifier is silently normalized. The gateway schema is deliberately left
  unchanged in this block;
- `idempotency_key` is derived from the logical effect and the authorization
  context, excluding `attempt_id` and timestamps, so a retry under a new
  attempt keeps the same key while a changed effect changes both the key and
  the canonical `request_fingerprint`;
- `operation.input` is derived only from the typed target, the already
  validated operation parameters and minimal operation/capability metadata.
  Command, shell, argv, cwd, environment and secret-like fields are refused;
- timeout, retry, cancellation and progress behaviour comes from the typed
  service configuration `RunnerHandoffConfig` / `RunnerDispatchPolicy`, never
  from request-level data, and is validated against the canonical Runner
  Protocol bounds and error taxonomy. Request data can never widen a budget or
  amplify authorization;
- `emitted_at` is produced internally in UTC; no caller-overridable clock is
  exposed.

This block proves the boundary only. It is not connected to the synthetic
candidates, the supervisor or any process, and no runner, laboratory, network
or target is contacted: `execution_integration: NOT_RUN`,
`NO_RUNTIME_CHANGE`.

## Status

- typed contract and decision logic: `CANDIDATE`;
- canonical gateway -> Runner Protocol v2 handoff: `CANDIDATE`;
- runtime authorization-ref resolution: `NOT_IMPLEMENTED` / `NOT_RUN`;
- runner execution integration: `execution_integration: NOT_RUN`;
- canonical admission boundary: `CANDIDATE`;
- runtime gateway integration: `NOT_RUN`;
- normal profile arbitrary command exposure: `FORBIDDEN`;
- Kali MCP handler integration: `NOT_RUN`;
- gateway deployment: `NOT_RUN`;
- production runtime observation: `NOT_RUN`;
- runtime changes: `NO_RUNTIME_CHANGE`.
