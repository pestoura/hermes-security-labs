# Runner adapters

This directory contains target-bound execution adapters for Runner Protocol v2. It is intentionally separate from the synthetic conformance candidates under the API pack.

## Authority and safety model

- Hermes remains the only execution-authorization authority.
- A Runner adapter may validate or refuse an `authorization_ref`; it may never create, expand or approve one.
- Target identity is fixed by the adapter registration. Raw URLs, hostnames, ports and shell commands are not execution authority.
- Generic execution is forbidden.
- Runtime promotion requires an externally verified TB1 resolver, authenticated Runner transport/identity, accepted deployment evidence and live validation.

## `webgoat-l1`

The first adapter implements the read-only effect boundary required by the seeded `webgoat-tls-transport-review` scenario:

- fixed target: `webgoat-web`;
- fixed endpoint: `http://webgoat:8080/WebGoat/` on `webgoat-lab`;
- capabilities: `web.discovery.headers` and `web.discovery.tls`;
- standard-library HTTP only;
- redirects disabled;
- sensitive response headers removed from structured output;
- durable SQLite idempotency required before network effect;
- Runner Protocol v2 terminal outcomes validated and durably replayable;
- evidence digest emitted without claiming external Evidence Plane persistence.

The default authorization resolver is deny-all. Unit tests inject a synthetic resolver only to validate the adapter boundary; this is not a runtime authorization implementation.

## Current status

- adapter code: `CANDIDATE / GREEN-REPO` only after CI acceptance;
- TB1 operational receipt issuance: `NOT_IMPLEMENTED / NOT_RUN`;
- verified runtime authorization resolver: `NOT_IMPLEMENTED / NOT_RUN`;
- authenticated Runner transport/identity: `NOT_IMPLEMENTED / NOT_RUN`;
- Evidence Plane external persistence: `NOT_IMPLEMENTED / NOT_RUN`;
- live WebGoat effect execution: `NOT_RUN`.

No repository acceptance may be interpreted as permission to execute a target-interacting action.
