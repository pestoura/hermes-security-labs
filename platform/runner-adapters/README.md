# Runner adapters

This directory contains target-bound execution adapters for Runner Protocol v2. It is intentionally separate from the synthetic conformance candidates under the API pack.

## Authority and safety model

- Hermes remains the only execution-authorization authority.
- A Runner adapter may validate or refuse an `authorization_ref`; it may never create, expand or approve one.
- The canonical gateway handoff verifies the signed TB1 authorization receipt and admission controls before constructing `runner.step.request`.
- Adapters consume the canonical operation envelope produced by `platform/gateway-protocol/runner_handoff.py`; no parallel request format is accepted.
- The Runner-side resolver in `platform/runner-authorization/` can cache only canonical `VerifiedAuthorization` metadata produced by signed receipt verification; its committed policy remains disabled.
- Target identity is fixed by the adapter registration. Raw URLs, hostnames, ports and shell commands are not execution authority.
- Generic execution is forbidden.
- Runtime promotion still requires trusted live receipt delivery, enabled resolver/transport/routing policies, accepted deployment evidence and live validation.

## `webgoat-l1`

The first adapter implements the read-only effect boundary required by the seeded `webgoat-tls-transport-review` scenario:

- fixed target identity: `lab-asset:webgoat-web`;
- fixed endpoint: `http://webgoat:8080/WebGoat/` on `webgoat-lab`;
- capabilities: `web.discovery.headers` and `web.discovery.tls`;
- canonical gateway operation envelope only: operation identity/version, L1 intrusiveness, target and validated parameters;
- resolved authorization must expose canonical TB1 `VerifiedAuthorization` metadata;
- before any effect, the adapter rebinds the resolved authorization to the exact `authorization_ref`, campaign/run/step, operation/version, capability, L1 intrusiveness, canonical parameter digest and canonical target digest;
- `attempt_id` is deliberately not part of TB1 binding or Runner effect fingerprint, so an exact logical retry gets the same deterministic idempotency key/fingerprint and replays the stored outcome without a second effect;
- authorization validity timestamps are rechecked at the adapter boundary;
- standard-library HTTP only;
- redirects disabled;
- sensitive response headers removed from structured output;
- durable SQLite idempotency required before network effect;
- Runner Protocol v2 terminal outcomes validated and durably replayable;
- evidence digest emitted without claiming external Evidence Plane persistence.

The default authorization resolver remains deny-all. Unit tests use stubs only for isolated negative cases. A repository integration test proves the real chain: signed Ed25519 TB1 receipt -> canonical verification -> `VerifiedAuthorizationResolver` -> canonical gateway handoff -> WebGoat adapter -> fake HTTP effect.

## Current status

- WebGoat adapter code: `CANDIDATE / GREEN-REPO` only after CI acceptance;
- canonical gateway -> adapter message compatibility: `GREEN-REPO`;
- verified authorization resolver code: `CANDIDATE / GREEN-REPO`, canonical policy `DISABLED / NOT_RUN`;
- Unix peer transport identity code: `CANDIDATE / GREEN-REPO`, canonical policy `DISABLED / NOT_RUN`;
- authenticated dispatch router code: `CANDIDATE / GREEN-REPO`, canonical routing policy `DISABLED / NOT_RUN`;
- TB1 operational receipt issuance/delivery into the Runner process: `NOT_IMPLEMENTED / NOT_RUN`;
- Evidence Plane external persistence: `NOT_IMPLEMENTED / NOT_RUN`;
- live WebGoat effect execution: `NOT_RUN`.

No repository acceptance may be interpreted as permission to execute a target-interacting action.
