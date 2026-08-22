# CHG-HSL-089 — receipt-delivery live reconciliation

## Decision

Reconcile the independently verified CHG-HSL-088 HermesJarvas installation into the
walking-skeleton status and governed promotion campaign without rewriting the historical
CHG-HSL-088 pre-live change record.

The accepted observation is the AF_UNIX endpoint boundary only:
- `/run/hexor/runner-authz.sock` enabled, active and listening;
- owner identity `hexor-runner` uid 4101, group `hexor-dispatch` gid 4110, mode `0660`;
- peer contract uid 4100 / `hexor.execution-gateway`;
- installed artifacts byte-identical to merged main;
- unprivileged peer denied before connection;
- existing `runner-dispatch.sock` remains independently active.

## Non-authority invariants

Receipt-delivery and resolver policies remain `DISABLED / NOT_RUN`.
`execution_authority=none`, `promotion_allowed=false`, target effects remain none,
trust-store remains absent, signer/Secret Zero remain NOT_RUN and campaign remains
`BLOCKED / HOLD`.
