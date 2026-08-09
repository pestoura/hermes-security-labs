# Runtime acceptance checkpoint — 2026-08-09

**Project:** Hermes Security Labs  
**Repository baseline before live acceptance:** `b71b8d4bcdb781525c08feea9dec268345a5ad3b`  
**Latest exact-green repository checkpoint before this reconciliation:** `63357eb02eb82a999aec53cf15dad1aa01dd59d0`  
**Mode:** read-only runtime discovery; no target execution, no lab mutation, no restart, no approval bypass.

This checkpoint records facts observed through the Hermes MCP after the repository walking-skeleton work in Lanes K-O had reached Exact-SHA GREEN. It is runtime evidence about admission/discovery only; it is not pentest or scenario-execution evidence.

## Observed Hermes state

The live Hermes/Bridge path reported:

- Hermes platform version `0.20.0`;
- Bridge version `1.0.0`;
- upstream readiness `ok`;
- security posture `ready` with the production policy loaded and valid;
- HMAC required and configured;
- disk usage approximately `26.6%` during the observation.

At the start of observation the gateway was `draining` because concurrent Bridge V2 API work was genuinely active. The active API run count then reduced naturally:

`5 -> 4 -> 3 -> 1 -> 0`

No Hermes Security Labs action stopped or cancelled those independent runs.

One unrelated Bridge V2 run ended with `Upstream idle timeout exceeded`. It was not retried by Hermes Security Labs because it belonged to another development stream and the failure was already deterministic.

## RTA-001 — transient stale drain after active API work reached zero

**Classification:** `RECOVERED-RUNTIME — STALE_DRAIN`  
**State:** `RESOLVED-RUNTIME`

Immediately after `active_api_runs` reached `0`, the gateway temporarily remained:

- `gateway_state=draining`;
- `accepting_new_work=false`;
- `gateway_drainable=false`.

The health response still showed active agents, while the run registry contained historical entries reported as `running`. A direct status lookup of the most recent historical Hermes Security Labs entry returned `failed / unavailable`, demonstrating that the registry view itself was not reliable evidence of live API activity.

This reproduced the known stale-drain class without relying on memory: new work remained denied for a period even though there were zero active API runs.

### Natural recovery observed

No restart, forced admission, run cancellation or policy bypass was attempted. A subsequent live health/readiness observation showed that the gateway recovered automatically:

- `gateway_state=running`;
- `active_api_runs=0`;
- `active_agents=0`;
- `gateway_busy=false`;
- `gateway_drainable=true`;
- upstream readiness remained healthy;
- admission returned `accepting_new_work=true`.

The recovery happened without Hermes Security Labs mutating runtime state. RTA-001 is therefore not a current blocker, while the transient stale-drain behaviour remains a valid operational observation for Bridge lifecycle hardening.

## RTA-002 — Kali MCP absent from live Hermes portal

**Classification:** `BLOCKER — KALI_MCP_NOT_REGISTERED`  
**State:** `BLOCKED-ON-RUNTIME`

The Hermes MCP portal server inventory was queried twice. Both observations exposed only:

- `hermes-agent-bridge` — enabled.

No `kali-lab`, Kali MCP or equivalent server was present in the live portal inventory.

This confirms that the historical Kali MCP registration must not be assumed current. No attempt was made to register or enable an invented server entry.

### Root cause not yet observed

After RTA-001 recovered, a read-only host/runtime inspection was prepared to determine:

1. whether the canonical Kali MCP Compose/runtime still exists and where;
2. whether the `hermes-kali-mcp` container is present and healthy;
3. whether its isolation/resource/read-only-root contract still matches the accepted design;
4. what current Hermes MCP configuration is intended to register it;
5. why the server is absent from the portal.

That inspection did not execute because the approval path failed as RTA-003 below. Therefore no root-cause claim is made for RTA-002 and no historical path is promoted to current authority.

## RTA-003 — approval required but no approval identifier issued

**Classification:** `BLOCKER — APPROVAL_ID_NULL`  
**State:** `BLOCKED-ON-RUNTIME`

Once Hermes admission had naturally recovered to `running` and `accepting_new_work=true`, one explicit read-only Hermes request was submitted for local host/runtime reconciliation.

The request explicitly prohibited mutation, including:

- file creation/edit/delete;
- service or container start/stop/restart;
- MCP registration or enable/disable;
- target/network probing;
- offensive/security-tool execution;
- package installation;
- sudo/elevated access;
- secret/token/key disclosure.

It requested factual read-only inspection only and used the client request id:

`hsl-runtime-readonly-20260809-kali-reconcile-01`

The policy response was deterministic:

- `approval_required=true`;
- message: `policy requires approval: high-risk trust label`;
- `approval_id=null`;
- `execution_id=not-created`;
- status `failed`.

No Hermes execution was created and no host/container/runtime inspection occurred.

### Safety decision

The request was **not** retried with reduced or altered trust labels to escape policy. No approval identifier was invented and no alternate mechanism was used to bypass the approval boundary.

### Closure condition

RTA-003 can be closed only when the legitimate approval path can issue a usable approval identifier for a policy-gated request, such that the normal approval status/respond mechanism can be used and audited, or when the approval-path defect is formally corrected through the authorized Bridge/runtime maintenance process.

After that repair, repeat the same bounded read-only Kali reconciliation through the valid approval path. Do not weaken the policy merely to make the inspection executable.

## Actions deliberately not performed

To preserve the acceptance boundary, this checkpoint did **not**:

- contact a lab target;
- execute a scenario or security tool;
- start, stop, reset or destroy a lab;
- mutate containers or networks;
- expose Docker socket access;
- use generic shell execution as a product/runtime bypass;
- register a guessed Kali MCP server;
- restart the Hermes gateway through an out-of-band mechanism;
- relabel a denied request to avoid approval;
- respond to or bypass an approval without a valid approval identifier.

## Runtime acceptance state

Hermes admission is currently demonstrated READY after natural recovery, but host/runtime reconciliation cannot pass the approval boundary:

`authorize -> admission READY -> [RTA-003 approval issuance blocker] -> host/runtime reconciliation -> provision/readiness -> execute -> evidence -> reset -> known-state proof`

The Kali execution path is also independently unresolved because RTA-002 confirms that Kali MCP is absent from the live portal inventory.

Repository/CI delivery remains GREEN; these runtime blockers do not invalidate the committed contracts. They prevent promotion from repo proof to live runtime acceptance.

## Next safe action

1. Repair or restore the legitimate Bridge approval issuance path so a policy-gated request receives a valid `approval_id` and can be audited through normal approval tools.
2. Re-run Hermes health/readiness and confirm admission remains `running + accepting_new_work=true`.
3. Repeat the same bounded read-only Kali MCP host/runtime inspection through the valid approval path.
4. Resolve RTA-002 from observed root cause rather than blind re-registration.
5. Resume core-lab lifecycle/readiness acceptance using canonical target IDs and no offensive action.
6. Only after authorization, runtime effect support and evidence/reset paths are valid, attempt a bounded seeded scenario.
