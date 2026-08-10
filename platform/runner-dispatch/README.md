# Runner dispatch router

The dispatch router is the narrow composition boundary between an authenticated local Runner channel and a target-bound Runner adapter. It is **not** an authorization authority.

## Required gates

A request reaches an adapter only when all of these conditions hold:

1. the accepted Unix peer authenticates through kernel `SO_PEERCRED` and the transport identity policy;
2. the routing policy is explicitly `ENABLED` and contains an exact principal → adapter → target → capability binding;
3. the payload validates as Runner Protocol v2 `runner.step.request`;
4. routing uses the canonical `lab-asset` target in the gateway handoff envelope;
5. exactly one adapter matches the target and capability;
6. that adapter is explicitly `status: AS_BUILT` and `runtime_status: READY`;
7. the adapter instance exists in the trusted process composition root;
8. the adapter returns valid Runner Protocol messages with matching correlation and exactly one terminal `runner.outcome`.

Failure at any gate refuses before or after adapter invocation as appropriate. The router never dynamically imports the implementation path declared in the adapter registry.

## Canonical state

The committed routing policy is intentionally non-operational:

- `state: DISABLED`;
- `default: deny`;
- `runtime_status: NOT_RUN`;
- `execution_authority: none`;
- `bindings: []`.

The committed WebGoat L1 adapter is also `CANDIDATE / NOT_RUN`. Therefore the repository state cannot route it even if someone constructs a valid Runner message.

Positive tests use temporary copies of the policies and adapter registry, mark the adapter `AS_BUILT / READY`, authenticate a local Unix `socketpair()` with kernel credentials, and compose the real WebGoat adapter with a fake HTTP probe. This proves the code path without target traffic or runtime promotion.

## Authority separation

- Hermes/TB1 decides whether the operation is authorized.
- Unix peer identity decides who delivered the Runner request.
- Routing policy decides which authenticated principal may reach which adapter/target/capability.
- Adapter registry selects the unique typed implementation and carries runtime promotion state.
- The adapter independently resolves `authorization_ref` and enforces target/capability binding before an effect.
- The dispatch audit projection records the authenticated principal together with the canonical Runner correlation identifiers; it does not create authority and does not trust a principal supplied inside the Runner request.

No one layer substitutes for another.

## Dispatch audit contract

`dispatch-audit-event.schema.json` and `audit.py` define the repository-side audit projection required before live dispatch can be considered operationally accountable.

The event binds the **transport-authenticated principal** to:

- `campaign_id`;
- `run_id`;
- `step_id`;
- `attempt_id`;
- the TB1 `authorization_ref`;
- the selected capability;
- a canonical SHA-256 of the target;
- the adapter ID when known;
- a stable reason code and decision phase;
- the terminal status for completed dispatches.

The projection deliberately excludes raw target values, operation parameters, credentials, tokens and application payload. It first validates the Runner Protocol request and derives the target digest using the canonical gateway target-digest function.

Each event has a deterministic `event_fingerprint`. `recorded_at` is excluded from that fingerprint so re-serialization time does not change the logical event identity; `attempt_id` remains included so retries are separately auditable even when the logical effect is idempotent.

### Trust boundary

`principal_id` and `transport` are explicit arguments to the projection because they must originate from the trusted transport-authentication result (for the current candidate, kernel `SO_PEERCRED`). They are never extracted from caller-controlled Runner request fields.

The schema is strict (`additionalProperties: false`) and distinguishes:

- `pre-dispatch / ALLOW`;
- `pre-dispatch / DENY`;
- `terminal / OUTCOME`.

A terminal event requires both `adapter_id` and `terminal_status`. Pre-dispatch events cannot claim a terminal status.

### Runtime status

This is **GREEN-REPO candidate functionality only**. `audit.py` is a pure projection and intentionally performs no file write, syslog call, network request, subprocess invocation or SIEM integration.

A durable append-only/immutable audit sink, retention policy and live delivery are still `NOT_IMPLEMENTED / NOT_RUN`. A repository-valid event does not prove that an event was persisted during a real dispatch.

## Remaining blockers

Before live dispatch:

- dedicated non-root gateway/Runner identities and socket permissions must be validated on the host;
- canonical transport and routing policies must be explicitly promoted from disabled state;
- WebGoat adapter must have accepted runtime promotion evidence before `AS_BUILT / READY`;
- a trustworthy runtime resolver for verified `authorization_ref` must exist;
- TB1 signer/trust-store deployment must be proven live rather than only through repository preflight;
- terminal evidence must be persisted to the Evidence Plane;
- the dispatch audit event must be persisted through a durable append-only/immutable sink and observed alongside the same correlation identifiers;
- a listener/service composition boundary must be deployed and tested;
- live negative tests must prove unauthorized peers, targets and capabilities cannot reach an adapter.
