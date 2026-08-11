# Hermes Security Labs — current walking-skeleton status

**Reconciled:** 2026-08-11 08:30 UTC  
**Current Labs baseline:** `6dbd34cabb5766837803c6c9083254902fefa1dc`  
**Accepted/live Hermes MCP Bridge revision:** `3717bd5469b061a44294b27e1a7510d477d3752b`

This is the concise current-state view of the walking skeleton. Repository/CI proof and live Hermes runtime proof are separate evidence classes. Historical evidence remains in [`runtime-acceptance-checkpoint-2026-08-09.md`](runtime-acceptance-checkpoint-2026-08-09.md); the governed Runner promotion campaign is [`../../validation/VAL-HSL-RUNNER-L1-LIVE-PROMOTION.yaml`](../../validation/VAL-HSL-RUNNER-L1-LIVE-PROMOTION.yaml).

> **GREEN-REPO is not live acceptance.** It means the contract/code exists and passed repository gates. It does not grant execution authority, activate a policy, prove host deployment or prove target interaction.

## Current summary

| Item | Current state |
| --- | --- |
| RTA-001 gateway admission | `RESOLVED-RUNTIME / GREEN`; re-observation required before the next live mutation |
| RTA-002 Stage 1 Kali registration/discovery | `GREEN/PASS`; canonical STDIO, disabled + sentinel retained |
| RTA-002 Stage 2 minimum health surface | `RESOLVED-RUNTIME / GREEN`; exact effective surface `[server_health]`, one bounded invocation, then rollback to disabled + sentinel |
| RTA-003 Bridge approval handoff | `RESOLVED-RUNTIME / GREEN` on Bridge `3717bd5469...` |
| WebGoat/WebWolf repository lifecycle/readiness | `PASS / READY-REPO`; publication and dual-health races fixed in #325-#327 |
| WebGoat live lifecycle | pre-fix `start/readiness/smoke PASS`; reset race found; cleanup/destroy `PASS / ZERO-RESIDUE`; post-fix rerun `UNKNOWN` |
| DVWA repository lifecycle/readiness | `PASS / READY-REPO`; host-port parity merged #329; live acceptance pending |
| Juice Shop repository lifecycle/readiness | `PASS / READY-REPO`; readiness/smoke/reset publication parity merged #329; live acceptance pending |
| WebGoat L1 real adapter | `GREEN-REPO`; typed target-bound effect exists; live dispatch not accepted |
| Runner outcome -> Evidence Plane custody | `GREEN-REPO`, #321; policy `DISABLED / NOT_RUN` |
| TB1 receipt delivery boundary | `GREEN-REPO`, #322; policy `DISABLED / NOT_RUN` |
| Runner identity/socket promotion preflight | `GREEN-REPO`, #323; runtime `NOT_RUN` |
| Hermes TB1 receipt issuer boundary | `GREEN-REPO`, #328; external signer not live-configured |
| TB1 signer + Runner trust-store deployment preflight | `GREEN-REPO`, #331; runtime `NOT_RUN` |
| Authenticated-principal dispatch audit contract | `GREEN-REPO`, #332 |
| Promotion evidence gate | `GREEN-REPO`, #334; structurally `promotion_allowed=false` |
| Dispatch audit -> Evidence Plane custody | `GREEN-REPO`, #335; production durable/WORM backend not proven |
| Runner host-evidence collector | `GREEN-REPO`, #336; read-only collector exists, host execution `NOT_RUN` |
| Runner service composition root | `GREEN-REPO`, #337; no listener/daemon; policy `DISABLED / NOT_RUN` |
| WebGoat L1 promotion bundle | `GREEN-REPO`, #338; reconciled with #335-#337; `EVIDENCE_ONLY / HOLD` |
| Full walking skeleton live completion | `HOLD / BLOCKED-ON-LIVE-PROMOTION-EVIDENCE-AND-CONNECTOR` |

## Walking skeleton

Target path:

`authorize -> admit -> provision -> readiness -> dispatch bounded effect -> evidence -> reset -> known-state proof`

| Stage | Repository/CI state | Live runtime state |
| --- | --- | --- |
| Authorize | TB1 verifier, Hermes issuer, receipt delivery, signer/trust-store preflight and host-observation capability `GREEN-REPO` | external signer attestation, installed trust store and live issuance/delivery remain `NOT_RUN` |
| Admission | Bridge exact-SHA + approval contracts accepted | RTA-001 and RTA-003 accepted; live Bridge baseline `3717bd5469...` |
| Kali registration | canonical STDIO contract `GREEN-REPO` | Stage 1 `PASS`; disabled + sentinel retained |
| Kali health | `kali.mcp.health.read -> server_health`, L0, exact mapping | Stage 2 `PASS`; only `server_health` exposed and safe state restored |
| Provision | WebGoat/DVWA/Juice lifecycle contracts `READY-REPO` | WebGoat pre-fix start accepted; DVWA/Juice live acceptance pending |
| Readiness | typed loopback readiness adapters with host-port parity `PASS` | WebGoat post-fix full rerun `UNKNOWN`; DVWA/Juice pending |
| Plan scenario | deterministic Scenario Plan Composer `GREEN-REPO` | not an execution claim |
| Dispatch bounded effect | WebGoat L1 adapter + peer identity + router + resolver + audit + service composition `GREEN-REPO` | transport/routing/resolver/delivery/service policies `DISABLED / NOT_RUN`; live effect `NOT_RUN` |
| Evidence | terminal outcome custody + dispatch audit custody use the existing Evidence Plane `GREEN-REPO` | production durable/WORM backend and live persistence remain unproven |
| Reset/cleanup | bounded reset/destroy governance exists | first failure cleanup proved zero residue; post-fix full lifecycle result remains `UNKNOWN` |

## Runtime acceptance already closed

### RTA-001 — gateway admission

**State:** `RESOLVED-RUNTIME / GREEN`.

Gateway admission was accepted as running, non-busy and drainable. Re-observe before a new live mutation; do not treat this as an open design gap.

### RTA-002 — Kali MCP

**Stage 1:** `GREEN/PASS`. Canonical STDIO registration remains disabled + sentinel by default.

**Stage 2:** `RESOLVED-RUNTIME / GREEN`. The effective Hermes surface was temporarily reduced to exactly `server_health`, one no-argument health invocation passed without target traffic, and the safe disabled + sentinel profile was restored byte-for-byte. Do not repeat Stage 2 unless drift or a new acceptance requirement exists.

### RTA-003 — Bridge approval handoff

**State:** `RESOLVED-RUNTIME / GREEN` on Bridge `3717bd5469b061a44294b27e1a7510d477d3752b`.

A no-target compatibility smoke consumed the request-bound approval exactly once. No Kali target tool was involved.

## Lifecycle/readiness

### WebGoat/WebWolf

PRs #325-#327 fixed readiness host-port parity, smoke publication ownership and the dual-service health race. The first live cycle established:

`start PASS -> readiness PASS -> smoke PASS -> reset FAIL`

Canonical destroy then proved zero residue. A post-fix full rerun was started as `run_73cd8ef359ff486f93faeb7c2dc46290`, but its result was not recoverable through the available Hermes control surface. Its status remains **UNKNOWN**, not PASS and not FAIL. Recover that run before duplicating it.

### DVWA and Juice Shop

Both are `PASS / READY-REPO` after #329. DVWA follows `DVWA_HOST_PORT`; Juice Shop follows `JUICE_SHOP_HOST_PORT`, smoke resolves the actual publication and reset uses the canonical `juice-shop-lab` network. Their live lifecycle acceptance remains pending.

## Authorization / Runner chain

The repository contains a complete **promotion candidate**, not an enabled runtime:

- Hermes-only TB1 issuer boundary (#328);
- TB1 verification and signer/trust-store deployment preflight (#331);
- authenticated receipt-delivery boundary (#322);
- `VerifiedAuthorizationResolver`;
- Unix `SO_PEERCRED` identity and identity/socket deployment preflight (#323);
- deny-by-default dispatch router;
- target-bound WebGoat L1 adapter;
- sanitized authenticated-principal/correlation audit event (#332);
- Runner terminal-outcome custody (#321);
- dispatch-audit custody into the same Evidence Plane (#335);
- read-only host evidence for identity/socket/trust-store declarations (#336);
- fail-closed service composition for an already accepted AF_UNIX peer (#337);
- aggregate EVIDENCE_ONLY promotion gate/bundle (#334/#338).

The service composition sequence is:

`SO_PEERCRED -> transport-admission audit custody -> router -> adapter-local TB1 authorization/effect -> terminal audit custody -> Runner outcome custody`

It intentionally provides no listener, daemon, generic execution path or implicit promotion.

### Still missing for live promotion

- protected external signer binding and provider/key attestation;
- host-observed Runner authorization trust store with approved digest and owner/mode;
- configured receipt-delivery AF_UNIX endpoint and authenticated live delivery;
- host evidence for actual gateway/Runner identities, socket and user-namespace mapping;
- unauthorized-peer negative test against the real Runner socket;
- production durable/append-only/WORM Evidence Plane backend and live audit observation;
- explicit promotion of only the minimum resolver/delivery/transport/routing/service/custody policy set;
- Human-in-the-Loop approval for the exact promoted candidate;
- one authorized WebGoat L1 effect, terminal/audit persistence and reset/known-state proof.

The canonical promotion gate remains `EVIDENCE_ONLY`, `HOLD`, `runtime_status: NOT_RUN`, `execution_authority: none`, and `promotion_allowed=false` even if all machine evidence becomes complete. Human promotion is a separate decision.

## Current connector state

The Hermes connector required to recover `run_73cd8ef359ff486f93faeb7c2dc46290` is not currently available through this control surface. This is **not** evidence that the Hermes gateway itself is unhealthy.

Classification:

`CONNECTOR-UNAVAILABLE / LIVE-RUN-RECOVERY-PENDING`

## Automatic continuation order

When the Hermes connector is usable again:

1. recover `run_73cd8ef359ff486f93faeb7c2dc46290` before starting another WebGoat lifecycle;
2. re-observe gateway admission and exact Bridge revision `3717bd5469b061a44294b27e1a7510d477d3752b`;
3. verify the Kali profile remains disabled + sentinel; repeat Stage 2 only on detected drift/new requirement;
4. if the recovered WebGoat run is PASS, record lifecycle/reset evidence; otherwise clean up and repeat only the failed gate;
5. execute bounded DVWA and Juice Shop lifecycle/readiness acceptance;
6. run the read-only host-evidence collector against an explicitly reviewed deployment descriptor;
7. obtain external signer attestation, trust-store proof, user-namespace mapping and unauthorized-peer negative evidence;
8. prove the selected durable Evidence Plane/audit backend live;
9. request and record explicit Human-in-the-Loop promotion for the exact candidate;
10. promote only the minimum WebGoat L1 policy set;
11. execute one bounded read-only WebGoat L1 effect, persist terminal/audit evidence, reset/destroy and prove known state;
12. on any RED, restore fail-closed state for the affected lane while unrelated repo-only work may continue.

No target-interacting action is authorized merely because repository contracts or CI are GREEN.

## Recent engineering checkpoints

| Change | PR | Merge SHA | Outcome |
| --- | --- | --- | --- |
| Runner outcome custody | #321 | `7bd1b9da3af4f1b38b9ea057b6a3c8fd97f9b636` | GREEN-REPO, policy disabled |
| TB1 receipt delivery | #322 | `dcae64435d87deb57fba64c160bb3fa1285a59bc` | GREEN-REPO, policy disabled |
| Runtime identity/socket preflight | #323 | `c6f12cefbcb1857af46835bef7531eab3e4533c5` | GREEN-REPO, runtime NOT_RUN |
| WebGoat readiness port parity | #325 | `b5b54dc54e6e8844e5bfcb5d74ed9e4c38e88645` | GREEN-REPO |
| WebGoat smoke publication ownership | #326 | `a91a325ed4ee1c66a17ab5d79a073b5f980fabbf` | GREEN-REPO |
| WebGoat dual-health lifecycle gate | #327 | `8f5d5aaedb011b8187c0a44bf8df2eaf0b9b9434` | GREEN-REPO after live-observed reset race |
| Hermes TB1 issuer boundary | #328 | `1d88a9386ed17010d784e2c519cf778569874aca` | GREEN-REPO, signer live binding NOT_RUN |
| DVWA/Juice publication parity | #329 | `1402503fa8eed62e9921b8166af86211e7ffd923` | GREEN-REPO |
| JDS baseline repair | #330 | `042c068435aa31082217c8dc1772c4658eaca375` | release-governance baseline GREEN |
| TB1 signer/trust-store deployment preflight | #331 | `472f3fbec9040519a8798044382f4462d0ad2d6b` | GREEN-REPO, runtime NOT_RUN |
| Runner dispatch audit event contract | #332 | `038a2ae503a331a371fa69623ec0586c9c60c7e5` | GREEN-REPO |
| Promotion evidence gate | #334 | `135dc1a5b360cace7a69612437933bbc7770a5cd` | GREEN-REPO, promotion authority always false |
| Dispatch audit Evidence Plane custody | #335 | `68a8ce6770532ecbdd0c0ee841a53de5b871a44f` | GREEN-REPO, production WORM NOT_RUN |
| Read-only Runner host evidence | #336 | `c52f7838a9e5bb75c7f326fa094a5e60af371445` | GREEN-REPO, host execution NOT_RUN |
| Runner service composition | #337 | `191f51e3912cd9ddd54f5f4eaf7d08f914ca8c1b` | GREEN-REPO, service policy disabled |
| Promotion bundle reconciliation | #338 | `6dbd34cabb5766837803c6c9083254902fefa1dc` | GREEN-REPO, EVIDENCE_ONLY / HOLD |

## Decision record

**Decision:** keep promotion on HOLD until live identity/trust/audit/evidence prerequisites and explicit Human-in-the-Loop promotion are proven.

**Context:** the repository chain now includes host observation, audit custody and service composition, but these remain repository capabilities and policies are still fail-closed.

**Risks accepted:** continued implementation can proceed repo-side while the connector/live prerequisites are unavailable, provided no repository result is promoted to a live claim.

**State:** `HOLD / BLOCKED-ON-LIVE-PROMOTION-EVIDENCE-AND-CONNECTOR`.
