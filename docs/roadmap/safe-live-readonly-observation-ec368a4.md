# Safe live read-only reobservation — run_ec368a4... (CHG-HSL-053)

**Run id:** `run_ec368a4ccc04419e985b1c4d01e0ddea`  
**Classification:** `SAFE-LIVE-READONLY` (read-only observation; no mutation)  
**Reconciled:** 2026-08-14 19:00 UTC  
**Authoritative Git HEAD:** `a63ef01925e5c1b925936c1e73b11b2d6cd2a6a5`  
**Campaign:** `validation/VAL-HSL-RUNNER-L1-LIVE-PROMOTION.yaml` (state `BLOCKED`, recommendation `HOLD`)  
**Change record:** `changes/CHG-HSL-053.yaml`

This ledger records SAFE LIVE READ-ONLY observations reobserved during `run_ec368a4...` and reconciles them into source-of-truth. It performs **no runtime, policy, trust-store, signer, systemd, network, Docker or target mutation**. None of these observations change any campaign observation result from `BLOCKED`/`OPEN`, and none promote the campaign or grant execution authority. `HOLD` / `NOT_RUN` / `promotion_allowed=false` remain invariant.

## RTA-003 Bridge SHA divergence — resolved

- **Current live Hermes MCP Bridge revision (current live observation):** `3717bd5469b061a44294b27e1a7510d477d3752b` (Bridge 1.0.0).
- **`7e4b6b1cd70ddda418f840f54ae7ecef30df52e9` is retained ONLY as historical candidate/evidence** (the Bridge accepted and observed live on 2026-08-09, recorded in `runtime-acceptance-checkpoint-2026-08-09.md`). It is **never** the current runtime and must **never** be promoted to "current".
- A later, already-authorized Bridge deployment lane promoted `3717bd5469b061a44294b27e1a7510d477d3752b` as the current live Bridge. The divergence is resolved by treating `3717bd5469b061a44294b27e1a7510d477d3752b` as the current live observation and `7e4b6b1cd70ddda418f840f54ae7ecef30df52e9` as historical-only evidence.

## Reobserved read-only facts (run_ec368a4...)

| Fact | Read-only observation |
| --- | --- |
| Execution Gateway HOLD boundary | active; PID identity `4100` |
| Runner | active; PID identity `4101` |
| Dispatch socket | `LISTEN`; owner `4101:4110`; mode `0660` |
| Installed artifact parity | `7/7` (all installed artifacts match their pinned references) |
| Runner authorization trust store | `OBSERVED_ABSENT` (`/etc/hexor/runner/authorization-trust-store.json` not present) |
| `uid_map` / `gid_map` | observed `0 0 4294967295` (full identity map) |
| Namespace relationship | **NOT re-attested** — ns/user dereference denied; no namespace relationship was derived or claimed |

## Explicitly retained NOT_RUN (no elevation)

These sub-facts remain `NOT_RUN` and are not elevated into any observation `PASS`:

- signer / provider observation: `NOT_RUN`
- peer-negative (unauthorized-peer) test: `NOT_RUN`
- phased live-evidence packages (`PRE_PROMOTION` / `POST_EFFECT`): `NOT_RUN`
- first authorized effect + reset evidence: `NOT_RUN` / `UNKNOWN`

## Invariant

`HOLD` / `NOT_RUN` / `promotion_allowed=false` remain unchanged. The campaign `validation/VAL-HSL-RUNNER-L1-LIVE-PROMOTION.yaml` continues to report `state: BLOCKED`, `promotionRecommendation: HOLD`, and every live observation `result: BLOCKED` / `status: OPEN`. No campaign observation flipped from `BLOCKED`/`OPEN`. This ledger is evidence reconciliation only; it is not a promotion path.
