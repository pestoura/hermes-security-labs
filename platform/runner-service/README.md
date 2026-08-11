# Runner service composition — repository candidate

This directory composes the existing Runner security boundaries for **one already accepted AF_UNIX peer**. It is deliberately not a daemon, listener, systemd unit or deployment manifest.

Target sequence:

`SO_PEERCRED -> transport-admission audit custody -> router -> adapter-local authorization/effect -> terminal audit custody -> Runner outcome custody`

## Composition rules

`service_composition.py` reuses the canonical controls instead of creating parallel paths:

- peer identity comes from `runner-transport/unix_peer_identity.py`;
- the dispatch router re-authenticates the same peer as defence in depth and applies exact principal/target/capability routing;
- verified TB1 authorization remains adapter-local immediately before any effect;
- audit events use `runner-dispatch/audit.py`;
- audit custody uses `evidence-plane/dispatch_audit_custody.py`;
- terminal outcome custody uses `evidence-plane/runner_outcome_custody.py`;
- both custody paths receive the **same injected Evidence Plane store**.

There is no parallel authorization service, audit datastore or evidence store.

## Fail-closed ordering

The service authenticates the kernel peer and creates a `pre-dispatch / ALLOW` event with reason `TRANSPORT_PEER_ADMITTED`. This means only that the authenticated peer may enter the routing boundary; it does **not** assert that routing or TB1 authorization succeeded.

That admission event must be custodied before the router is called. Audit-custody failure therefore prevents adapter invocation.

Router failures are classified before a denial audit is emitted. Only errors proven to occur **before adapter invocation** are recorded as `pre-dispatch / DENY / ROUTER_PRE_EFFECT_REFUSED`. Errors such as adapter dispatch failure, malformed adapter result or post-dispatch correlation failure are surfaced as `ROUTER_POST_DISPATCH_FAILED`; the service deliberately does not mislabel them as a no-effect denial.

A normal adapter refusal, including TB1 authorization denial returned as a valid terminal `runner.outcome`, follows the terminal path and is auditable as `REFUSED`.

## Post-effect custody

After a valid terminal `runner.outcome`, the service builds a terminal audit event and attempts both independent custody paths:

1. terminal audit event -> Evidence Plane;
2. Runner outcome -> execution/evidence custody -> Evidence Plane.

If one post-effect custody path fails, the other is still attempted. The service then returns `POST_EFFECT_CUSTODY_FAILED` so an evidence failure is never hidden merely because the bounded adapter already completed.

Runner statuses `PASS`, `FAIL` and `INCONCLUSIVE` map to audit terminal status `SUCCEEDED`: they describe the security/check result while the adapter lifecycle itself completed. `ERROR`, `REFUSED`, `CANCELLED` and `TIMED_OUT` map to their corresponding lifecycle state.

## Canonical policy

`composition-policy.yaml` remains:

- `state: DISABLED`;
- `default: deny`;
- `runtime_status: NOT_RUN`;
- `execution_authority: none`.

It requires Linux `SO_PEERCRED`, pre-dispatch audit custody, terminal audit custody, Runner outcome custody and one shared Evidence Plane store. Positive repository tests use temporary ENABLED copies only; no committed policy is promoted.

## Test boundary

`platform/tests/test_runner_service_composition.py` uses:

- a local `socketpair()` solely for real kernel `SO_PEERCRED`;
- temporary ENABLED copies of transport/routing/service/custody policies;
- the canonical adapter registry promoted only inside the test fixture;
- deterministic fake adapters with no network traffic;
- the real dispatch router;
- the real dispatch-audit and Runner-outcome custody bridges;
- the real `LocalEvidenceStore` reference backend.

Tests prove admission audit-before-routing, pre-effect routing denial without adapter invocation, successful dual custody, post-effect custody completion attempts and explicit separation of post-dispatch router failures from pre-effect denials.

## Deliberate non-claims

This block does **not** provide:

- a production AF_UNIX listener/accept loop;
- process supervision or systemd integration;
- live TB1 signer/trust-store configuration;
- enabled production transport/routing/resolver/custody policies;
- a production WORM/append-only Evidence Plane backend;
- host/container user-namespace mapping evidence;
- unauthorized-peer live negative tests;
- target traffic.

`NO_RUNTIME_CHANGE`.
