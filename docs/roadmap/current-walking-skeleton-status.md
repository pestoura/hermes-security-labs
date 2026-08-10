# Hermes Security Labs — current walking-skeleton status

**Reconciled:** 2026-08-10 21:05 UTC  
**Current Labs baseline:** `038a2ae503a331a371fa69623ec0586c9c60c7e5`  
**Accepted/live Hermes MCP Bridge revision:** `3717bd5469b061a44294b27e1a7510d477d3752b`

This is the concise current-state view of the walking skeleton. Repository/CI proof and live Hermes runtime proof are separate evidence classes. Historical evidence remains in [`runtime-acceptance-checkpoint-2026-08-09.md`](runtime-acceptance-checkpoint-2026-08-09.md); the live Runner promotion campaign is [`../../validation/VAL-HSL-RUNNER-L1-LIVE-PROMOTION.yaml`](../../validation/VAL-HSL-RUNNER-L1-LIVE-PROMOTION.yaml).

> **GREEN-REPO is not live acceptance.** It means the contract/code exists and passed repository gates. It does not grant execution authority, activate a policy, prove host deployment or prove target interaction.

## Current summary

| Item | Current state |
| --- | --- |
| RTA-001 gateway admission | `RESOLVED-RUNTIME / GREEN`; re-observation required before the next live mutation |
| RTA-002 Stage 1 Kali registration/discovery | `GREEN/PASS`; canonical STDIO, disabled + sentinel retained |
| RTA-002 Stage 2 minimum health surface | `RESOLVED-RUNTIME / GREEN`; exact effective surface `[server_health]`, one bounded invocation, then rollback to disabled + sentinel |
| RTA-003 Bridge approval handoff | `RESOLVED-RUNTIME / GREEN` on Bridge `3717bd5469...` |
| WebGoat/WebWolf repository lifecycle/readiness | `PASS / READY-REPO`; publication and dual-health races fixed in #325-#327 |
| WebGoat live lifecycle | first cycle `start/readiness/smoke PASS`; reset race found; cleanup/destroy `PASS / ZERO-RESIDUE`; post-fix full rerun result currently `UNKNOWN` because connector recovery failed |
| DVWA repository lifecycle/readiness | `PASS / READY-REPO`; `DVWA_HOST_PORT` parity merged #329 |
| Juice Shop repository lifecycle/readiness | `PASS / READY-REPO`; readiness/smoke/reset publication parity merged #329 |
| WebGoat L1 real adapter | `GREEN-REPO`; typed target-bound HTTP header effect exists, live end-to-end dispatch not accepted |
| Runner outcome -> Evidence Plane custody | `GREEN-REPO`, #321; policy `DISABLED / NOT_RUN` |
| TB1 receipt delivery boundary | `GREEN-REPO`, #322; policy `DISABLED / NOT_RUN` |
| Runner identity/socket promotion preflight | `GREEN-REPO`, #323; runtime remains `NOT_RUN` |
| Hermes TB1 receipt issuer boundary | `GREEN-REPO`, #328; external signer not live-configured |
| TB1 signer + Runner trust-store deployment preflight | `GREEN-REPO`, #331; descriptor only, runtime `NOT_RUN` |
| Authenticated-principal dispatch audit event | `GREEN-REPO`, #332; durable audit sink `NOT_IMPLEMENTED / NOT_RUN` |
| Full walking skeleton live completion | `HOLD / BLOCKED-ON-LIVE-PROMOTION-EVIDENCE-AND-CONNECTOR` |

## Walking skeleton

Target path:

`authorize -> admit -> provision -> readiness -> dispatch bounded effect -> evidence -> reset -> known-state proof`

| Stage | Repository/CI state | Live runtime state |
| --- | --- | --- |
| Authorize | TB1 verifier, Hermes issuer, trusted local receipt delivery and signer/trust-store deployment preflight `GREEN-REPO` | signer provider, protected private-key custody, installed trust store and live receipt issuance/delivery remain `NOT_RUN` |
| Admission | Bridge exact-SHA + approval contracts accepted | RTA-001 and RTA-003 accepted; live Bridge baseline `3717bd5469...` |
| Kali registration | canonical STDIO contract `GREEN-REPO` | Stage 1 `PASS`; disabled + sentinel retained |
| Kali health | `kali.mcp.health.read -> server_health`, L0, exact mapping | Stage 2 `PASS`; only `server_health` exposed for the acceptance and the config was restored to least privilege afterwards |
| Provision | WebGoat/DVWA/Juice lifecycle contracts `READY-REPO` | WebGoat start accepted before the reset race; other labs pending live acceptance |
| Readiness | typed loopback readiness adapters with host-port parity `PASS` | WebGoat readiness accepted in first cycle; complete post-fix rerun `UNKNOWN`; DVWA/Juice pending |
| Plan scenario | deterministic Scenario Plan Composer `GREEN-REPO` | not an execution claim |
| Dispatch bounded effect | WebGoat L1 adapter, Unix peer identity, router, authorization resolver and sanitized audit-event contract exist `GREEN-REPO` | transport/routing/resolver/delivery policies remain `DISABLED / NOT_RUN`; durable audit sink not deployed |
| Evidence | Evidence Plane v2 + idempotent Runner terminal-outcome custody `GREEN-REPO` | real Runner terminal outcome persistence remains `NOT_RUN` |
| Reset/cleanup | bounded reset/destroy governance exists | first WebGoat failure cleanup proved zero residue; post-fix full lifecycle result still unknown |

## RTA-001 — gateway admission

**State:** `RESOLVED-RUNTIME / GREEN`.

Accepted observation proved gateway `running`, `busy=false`, `drainable=true` and able to admit new work without restart or bypass. This must be re-observed before a new live mutation; it is not an outstanding design gap.

## RTA-002 — Kali MCP

### Stage 1 — `GREEN/PASS`

Canonical Hermes registration remains fail-closed:

```yaml
mcp_servers:
  kali-lab:
    command: docker
    args: [exec, -i, hermes-kali-mcp, mcp-server]
    enabled: false
    tools:
      include: [__hermes_rta002_no_tool__]
      resources: false
      prompts: false
```

Latest accepted discovery proved:

- canonical STDIO handshake through `docker exec -i hermes-kali-mcp mcp-server`;
- Kali MCP `1.22.0`;
- MCP protocol `2025-06-18`;
- 12 upstream tools visible as metadata;
- sentinel matched no real tool;
- zero tool invocation and zero target traffic.

### Stage 2 — `RESOLVED-RUNTIME / GREEN`

The repository contract remains L0 `kali.mcp.health.read -> server_health` with no parameters and no generic execution.

Live acceptance proved:

1. the active `pentest-lab` profile was transactionally changed from disabled + sentinel to enabled + exact allowlist `[server_health]`;
2. the upstream server still advertised 12 tools but the effective Hermes model-facing surface exposed exactly one tool: `mcp__kali_lab__server_health`;
3. exactly one `server_health` invocation occurred, with no arguments and no lab-target traffic;
4. the Kali MCP service reported healthy;
5. the transaction restored the safe backup and returned the profile byte-for-byte to disabled + sentinel.

The health result also reported some optional Kali binaries (`nmap`, `nikto`, `dirb`, `gobuster`) unavailable. That does not invalidate the L0 health gate, but those capabilities must not be claimed READY until separately proven.

Do **not** repeat Stage 2 merely because the connector is unavailable later. Re-run only if drift or a new acceptance requirement makes it necessary.

## RTA-003 — Bridge approval handoff

**State:** `RESOLVED-RUNTIME / GREEN`.

The earlier `7e4b6b1...` baseline was superseded by the live Bridge revision:

`3717bd5469b061a44294b27e1a7510d477d3752b`

Repository evidence for that revision was GREEN. A fresh no-tool/no-target compatibility smoke exercised the normal request-bound approval flow; the approval was consumed exactly once and the run returned the expected RTA-003 PASS marker. No Kali tool or target action was involved.

## Lifecycle/readiness

### WebGoat/WebWolf

Repository fixes #325-#327 closed three concrete acceptance defects:

- readiness can follow typed loopback-only `WEBGOAT_HOST_PORT` / `WEBWOLF_HOST_PORT` overrides;
- smoke resolves published ports through `webgoat-proxy`, the service that actually owns the host publications;
- both `start` and `reset` wait fail-closed for **webgoat and webgoat-proxy** to become healthy before success/smoke.

First live cycle on pre-#327 code established:

`start PASS -> readiness PASS -> smoke PASS -> reset FAIL (proxy still starting)`

The failure path then executed canonical `destroy --yes` and proved:

- project containers absent;
- project volume absent;
- `webgoat-lab` network absent;
- selected loopback listeners absent;
- `hermes-kali-mcp` still running and disconnected.

A post-#327 full rerun was started as `run_73cd8ef359ff486f93faeb7c2dc46290`. The ChatGPT Hermes connector became unavailable before its result could be recovered. The run result is therefore **UNKNOWN**, not PASS and not FAIL. Do not duplicate it blindly; first attempt recovery when the connector is usable.

### DVWA

Repository state `PASS / READY-REPO`. PR #329 aligned TCP/HTTP readiness with the existing `DVWA_HOST_PORT` Compose publication while retaining application/database network separation. Live lifecycle acceptance remains pending.

### Juice Shop

Repository state `PASS / READY-REPO`. PR #329 aligned readiness with `JUICE_SHOP_HOST_PORT`, made smoke resolve the actual loopback Compose port rather than hardcode `3000`, and corrected reset to disconnect Kali from the explicit canonical `juice-shop-lab` network. Live lifecycle acceptance remains pending.

## Authorization / Runner chain

The repository now contains the complete **candidate** chain required to attempt a future live WebGoat L1 promotion without generic execution:

- Hermes-only TB1 receipt issuer boundary (#328);
- canonical TB1 receipt verification;
- signer/trust-store deployment declaration and read-only preflight (#331);
- authenticated local receipt-delivery boundary (#322);
- `VerifiedAuthorizationResolver`;
- Unix `SO_PEERCRED` identity contract and deployment preflight (#323);
- deny-by-default dispatch router;
- real target-bound WebGoat L1 adapter;
- sanitized authenticated-principal/correlation audit event (#332);
- Runner terminal outcome -> Evidence Plane custody bridge (#321).

This does **not** mean the live chain is enabled. Canonical resolver, delivery, transport, routing and outcome-custody policies remain deliberately `DISABLED / deny / NOT_RUN / execution_authority: none` where applicable.

### Still missing for live promotion

- live external signer binding and evidence of protected key custody;
- installed Runner authorization trust store with owner/mode evidence;
- configured receipt-delivery AF_UNIX endpoint and live authenticated delivery;
- host evidence for dedicated gateway/Runner UID/GID and namespace mapping;
- negative live peer tests against the real Runner socket;
- durable append-only/immutable audit sink; the event contract alone is not persistence;
- live principal + correlation event observation at that sink;
- explicit authorized promotion of resolver/delivery/transport/routing/custody policies;
- live WebGoat L1 dispatch, terminal outcome custody and reset/known-state proof.

## Seeded scenarios

| Scenario | Repository effect state | Live state |
| --- | --- | --- |
| `webgoat-tls-transport-review` | WebGoat L1 typed HTTP effect exists; supporting TLS operation remains separately governed | blocked on live promotion chain |
| `dvwa-sql-injection-screening` | higher-intrusiveness/synthetic path; not the first live target | blocked |
| `juice-shop-lab-lifecycle-stop` | lifecycle contract available | lifecycle acceptance pending |

The first real effect remains the least-intrusive **WebGoat L1 read-only** path. Do not jump to L2 SQLi.

## Current connector state

The ChatGPT Hermes connector is presently inconsistent/unavailable. During this continuation the namespace briefly reappeared, but `hermes_status(run_73cd...)` returned `Resource not found`; immediate rediscovery then reported no usable Hermes MCP namespace.

Classification:

`CONNECTOR-UNAVAILABLE / LIVE-RUN-RECOVERY-PENDING`

This is not evidence that the Hermes gateway itself is unhealthy. It means no new live gateway or run claim can be made through this control surface.

## Automatic continuation order

When the Hermes connector is usable again:

1. recover `run_73cd8ef359ff486f93faeb7c2dc46290` before starting another WebGoat lifecycle;
2. re-observe gateway admission and exact Bridge revision `3717bd5469b061a44294b27e1a7510d477d3752b`;
3. verify the Kali profile is still disabled + sentinel; do not repeat RTA-002 Stage 2 unless drift is detected;
4. if the recovered WebGoat run is PASS, record its full lifecycle/reset evidence; otherwise clean up canonically and repeat only the failed acceptance gate;
5. execute bounded lifecycle/readiness acceptance for DVWA and Juice Shop using their typed loopback port overrides;
6. produce host evidence for Runner identities/socket, TB1 signer/trust store and the durable audit sink;
7. validate negative peer/trust-key cases;
8. request/record the explicit Human-in-the-Loop promotion decision for the exact runtime candidate;
9. promote only the minimum WebGoat L1 policy set;
10. execute one bounded read-only WebGoat L1 effect, persist terminal evidence and audit events, then destroy/reset and prove known state;
11. on any RED, stop the affected lane, restore fail-closed state and keep unrelated repo-only lanes independent.

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
| Runner dispatch audit event contract | #332 | `038a2ae503a331a371fa69623ec0586c9c60c7e5` | GREEN-REPO, durable sink NOT_RUN |

## Decision record

**Decision:** keep promotion on HOLD until live identity/trust/audit/evidence prerequisites and explicit Human-in-the-Loop promotion are proven.

**Reason:** the repository chain is now materially more complete, but GREEN-REPO cannot substitute for protected key custody, authenticated live transport, immutable audit persistence, real outcome custody or reset evidence.

**State:** `HOLD / BLOCKED-ON-LIVE-PROMOTION-EVIDENCE-AND-CONNECTOR`.
