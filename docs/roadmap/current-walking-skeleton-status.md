# Hermes Security Labs — current walking-skeleton status

**Reconciled:** 2026-08-11 20:20 UTC  
**Current Labs baseline:** `56a9965dbbdda2c6986df7b0822e33e5529c05b0`  
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
| Dispatch audit Evidence Plane custody | `GREEN-REPO`, #335; production durable/WORM backend not proven |
| Read-only Runner host evidence | `GREEN-REPO`, #336; host execution `NOT_RUN` |
| Runner service composition | `GREEN-REPO`, #337; no listener/daemon; policy `DISABLED / NOT_RUN` |
| Promotion bundle reconciliation | `GREEN-REPO`, #338; audit/host/service prerequisites pinned |
| Read-only user-namespace evidence | `GREEN-REPO`, #340; live `/proc` observation `NOT_RUN` |
| User-namespace promotion reconciliation | `GREEN-REPO`, #341; verifier required by bundle, live observation `NOT_RUN` |
| Evidence-bound signer-attestation verifier | `GREEN-REPO`, #342; real provider observation/source evidence `NOT_RUN` |
| Signer-attestation promotion reconciliation | `GREEN-REPO`, #343; verifier required by bundle, no live attestation claim |
| Durable Evidence Plane backend attestation verifier | `GREEN-REPO`, #345; no backend selected/deployed; provider observation `NOT_RUN` |
| Durable-backend promotion reconciliation | `GREEN-REPO`, #346; verifier required by bundle; production backend still `NOT_IMPLEMENTED / NOT_RUN` |
| Full walking skeleton live completion | `HOLD / BLOCKED-ON-LIVE-PROMOTION-EVIDENCE-AND-CONNECTOR` |

## Walking skeleton

Target path:

`authorize -> admit -> provision -> readiness -> dispatch bounded effect -> evidence -> reset -> known-state proof`

| Stage | Repository/CI state | Live runtime state |
| --- | --- | --- |
| Authorize | TB1 verifier, Hermes issuer, delivery/resolver, signer/trust preflight and evidence-bound signer-attestation verifier `GREEN-REPO` | actual provider observation/source evidence, installed trust store and live issuance/delivery remain `NOT_RUN` |
| Admission | Bridge exact-SHA + approval contracts accepted | RTA-001 and RTA-003 accepted; Bridge `3717bd5469...` |
| Kali registration | canonical STDIO contract `GREEN-REPO` | Stage 1 `PASS`; disabled + sentinel retained |
| Kali health | `kali.mcp.health.read -> server_health`, L0, exact mapping | Stage 2 `PASS`; safe state restored |
| Provision | WebGoat/DVWA/Juice lifecycle contracts `READY-REPO` | WebGoat pre-fix start accepted; DVWA/Juice live acceptance pending |
| Readiness | typed loopback readiness adapters with host-port parity `PASS` | WebGoat post-fix rerun `UNKNOWN`; DVWA/Juice pending |
| Dispatch bounded effect | WebGoat L1 adapter + peer identity + router + resolver + audit + service composition `GREEN-REPO` | transport/routing/resolver/delivery/service policies `DISABLED / NOT_RUN`; live effect `NOT_RUN` |
| Host identity/trust | host-evidence collector #336 `GREEN-REPO` | explicit host observation `NOT_RUN` |
| User namespace | explicit-PID read-only observer #340 `GREEN-REPO` | gateway/Runner mapping observation `NOT_RUN` |
| Signer attestation | evidence-bound verifier #342 `GREEN-REPO` | provider metadata capture + source-evidence verification `NOT_RUN` |
| Evidence | terminal/audit custody plus provider-neutral durable-backend control verifier #345 `GREEN-REPO` | production backend `NOT_IMPLEMENTED / NOT_RUN`; provider observation and live persistence `NOT_RUN` |
| Reset/cleanup | bounded reset/destroy governance exists | first failure cleanup proved zero residue; post-fix full lifecycle remains `UNKNOWN` |

## Runtime acceptance already closed

### RTA-001 — gateway admission

**State:** `RESOLVED-RUNTIME / GREEN`.

Gateway admission was accepted as running, non-busy and drainable. Re-observe before a new live mutation.

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
- authenticated receipt-delivery boundary (#322) and `VerifiedAuthorizationResolver`;
- Unix `SO_PEERCRED` identity and identity/socket deployment preflight (#323);
- deny-by-default dispatch router and target-bound WebGoat L1 adapter;
- sanitized authenticated-principal/correlation audit event (#332);
- Runner terminal-outcome custody (#321) and dispatch-audit custody in the same Evidence Plane (#335);
- read-only host evidence for identity/socket/trust-store declarations (#336);
- fail-closed service composition for an already accepted AF_UNIX peer (#337);
- aggregate EVIDENCE_ONLY promotion gate/bundle (#334/#338);
- explicit-PID read-only Linux user-namespace observation boundary (#340), required by the bundle after #341;
- provider-neutral, evidence-bound external signer observation verifier (#342), required by the bundle after #343;
- provider-neutral durable Evidence Plane backend-control verifier (#345), required by the promotion bundle after #346.

The service composition sequence is:

`SO_PEERCRED -> transport-admission audit custody -> router -> adapter-local TB1 authorization/effect -> terminal audit custody -> Runner outcome custody`

It intentionally provides no listener, daemon, generic execution path or implicit promotion.

### Durable backend boundary

PR #345 defines the **acceptance contract**, not the production storage implementation. A future `OBSERVED` backend attestation must prove production scope, active state, encryption at rest, `WORM_COMPLIANCE`, enforced retention, legal-hold support, no privileged delete bypass, blocked public access, overwrite protection and independently verified source evidence. The verifier is provider-neutral and performs no provisioning or storage mutation.

The production backend itself remains **unselected, undeployed and unobserved**. `LocalEvidenceStore` remains a controlled CI reference and is not reclassified as production durable/WORM storage.

### Still missing for live promotion

- actual protected signer provider observation with independently verified source evidence;
- host-observed Runner authorization trust store with approved digest and owner/mode;
- configured receipt-delivery AF_UNIX endpoint and authenticated live delivery;
- live host evidence for gateway/Runner identities and socket;
- live user-namespace mapping evidence for the explicitly reviewed gateway/Runner PIDs;
- unauthorized-peer negative test against the real Runner socket;
- selected/deployed production durable/append-only/WORM Evidence Plane backend;
- live backend provider observation accepted through #345 and live Runner/audit persistence;
- explicit promotion of only the minimum resolver/delivery/transport/routing/service/custody policy set;
- Human-in-the-Loop approval for the exact promoted candidate;
- one authorized WebGoat L1 effect, terminal/audit persistence and reset/known-state proof.

The canonical promotion gate remains `EVIDENCE_ONLY`, `HOLD`, `runtime_status: NOT_RUN`, `execution_authority: none`, and `promotion_allowed=false` even if all machine evidence becomes complete. Human promotion is a separate decision.

## Current connector state

The Hermes connector required to recover `run_73cd8ef359ff486f93faeb7c2dc46290` is not currently available through this control surface. This is **not** evidence that the Hermes gateway itself is unhealthy.

Classification:

`CONNECTOR-UNAVAILABLE / LIVE-RUN-RECOVERY-PENDING`

## Automatic continuation order

When the Hermes connector and authorized deployment evidence are usable again:

1. recover `run_73cd8ef359ff486f93faeb7c2dc46290` before starting another WebGoat lifecycle;
2. re-observe gateway admission and Bridge revision `3717bd5469b061a44294b27e1a7510d477d3752b`;
3. verify the Kali profile remains disabled + sentinel;
4. resolve/repeat only a failed WebGoat lifecycle gate, preserving known-state cleanup;
5. execute bounded DVWA and Juice Shop lifecycle/readiness acceptance;
6. run #336 host evidence against an explicitly reviewed descriptor;
7. run #340 user-namespace evidence against explicitly reviewed PIDs;
8. capture real external signer metadata, custody its source evidence and verify it through #342;
9. select/deploy a production Evidence Plane backend, capture read-only control metadata and validate it through #345;
10. prove installed trust store, live Runner/Evidence handoff and live audit/terminal persistence;
11. execute the unauthorized-peer negative acceptance against the real Runner socket;
12. request and record explicit Human-in-the-Loop promotion for the exact candidate;
13. promote only the minimum WebGoat L1 policy set;
14. execute one bounded read-only WebGoat L1 effect, persist terminal/audit evidence, reset/destroy and prove known state;
15. on any RED, restore fail-closed state for the affected lane while unrelated repo-only work may continue.

No target-interacting action is authorized merely because repository contracts or CI are GREEN.

## Recent engineering checkpoints

| Change | PR | Merge SHA | Outcome |
| --- | --- | --- | --- |
| Promotion evidence gate | #334 | `135dc1a5b360cace7a69612437933bbc7770a5cd` | GREEN-REPO, promotion authority always false |
| Dispatch audit Evidence Plane custody | #335 | `68a8ce6770532ecbdd0c0ee841a53de5b871a44f` | GREEN-REPO, production WORM NOT_RUN |
| Read-only Runner host evidence | #336 | `c52f7838a9e5bb75c7f326fa094a5e60af371445` | GREEN-REPO, host execution NOT_RUN |
| Runner service composition | #337 | `191f51e3912cd9ddd54f5f4eaf7d08f914ca8c1b` | GREEN-REPO, service policy disabled |
| Promotion bundle reconciliation | #338 | `6dbd34cabb5766837803c6c9083254902fefa1dc` | GREEN-REPO, EVIDENCE_ONLY / HOLD |
| Read-only user-namespace evidence | #340 | `f0f9753152f6e1cb8d1c138d95e7f70455fceca9` | GREEN-REPO, live observation NOT_RUN |
| User-namespace promotion reconciliation | #341 | `459450fdef88b3dfc295d319a41bd2e32e138c52` | GREEN-REPO, live observation still NOT_RUN |
| Evidence-bound signer attestation verifier | #342 | `d4bb4cb7ae2bbbf54e3e806b3a2d843389ee8217` | GREEN-REPO, provider observation NOT_RUN |
| Signer-attestation promotion reconciliation | #343 | `c4c6bf3ff9630ddeab02028047f3129e3c8f0423` | GREEN-REPO, bundle requires verifier; HOLD retained |
| Runner L1 source-of-truth reconciliation | #344 | `b8c3302413a0c62bf4f98ae4f6fbb0c1ed8d2bc3` | DOC_ONLY, BLOCKED/HOLD preserved |
| Durable Evidence Plane backend attestation verifier | #345 | `5b1e889519a1929fbdd13ce3d7853043ddebd0d7` | GREEN-REPO, backend deployment/observation NOT_RUN |
| Durable-backend promotion reconciliation | #346 | `56a9965dbbdda2c6986df7b0822e33e5529c05b0` | GREEN-REPO, verifier required; backend still NOT_IMPLEMENTED/NOT_RUN |

## Decision record

**Decision:** keep promotion on HOLD until live identity/trust/signer/backend/audit/evidence prerequisites and explicit Human-in-the-Loop promotion are proven.

**Context:** the repository now contains host, user-namespace, signer-attestation and durable-backend-control verification boundaries, but these remain repository capabilities. No production backend has been selected/deployed and the related live observations have not run.

**Risks accepted:** continued implementation may proceed repo-side while connector/live prerequisites are unavailable, provided no repository result is promoted to a live claim.

**State:** `HOLD / BLOCKED-ON-LIVE-PROMOTION-EVIDENCE-AND-CONNECTOR`.
