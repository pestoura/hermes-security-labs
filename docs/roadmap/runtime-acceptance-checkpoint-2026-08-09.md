# Runtime acceptance checkpoint — 2026-08-09

**Project:** Hermes Security Labs  
**Repository baseline:** `b71b8d4bcdb781525c08feea9dec268345a5ad3b`  
**Mode:** read-only runtime discovery; no target execution, no lab mutation, no restart, no approval bypass.

This checkpoint records facts observed through the Hermes MCP after the repository walking-skeleton work in Lanes K-O had reached Exact-SHA GREEN. It is runtime evidence about admission/discovery only; it is not pentest or scenario-execution evidence.

## Observed Hermes state

The live Hermes/Bridge path reported:

- Hermes platform version `0.20.0`;
- Bridge version `1.0.0`;
- upstream readiness `ok`;
- security posture `ready` with the production policy loaded and valid;
- HMAC required and configured;
- disk usage approximately `26.6%` during the observation;
- gateway state `draining`;
- admission `accepting_new_work=false` / `not_ready` because of `draining`.

At the start of observation the drain corresponded to real concurrent Bridge V2 API work. The active API run count then reduced naturally:

`5 -> 4 -> 3 -> 1 -> 0`

No Hermes Security Labs action stopped or cancelled those independent runs.

One unrelated Bridge V2 run ended with `Upstream idle timeout exceeded`. It was not retried by Hermes Security Labs because it belonged to another development stream and the failure was already deterministic.

## RTA-001 — stale drain after active API work reached zero

**Classification:** `BLOCKER — STALE_DRAIN`  
**State:** `BLOCKED-ON-RUNTIME`

After `active_api_runs` reached `0`, the gateway remained:

- `gateway_state=draining`;
- `accepting_new_work=false`;
- `gateway_drainable=false`.

The health response still showed active agents, while the run registry contained historical entries reported as `running`. A direct status lookup of the most recent historical Hermes Security Labs entry returned `failed / unavailable`, demonstrating that the registry view itself was not reliable evidence of live API activity.

This reproduces the known stale-drain class without relying on memory: new work is denied although there are zero active API runs.

### Safety decision

No restart, forced admission, run cancellation or policy bypass was attempted.

The currently exposed Hermes MCP tools do not provide a bounded, explicit gateway restart/recovery operation suitable for this acceptance flow. Restarting through an unrelated host mechanism would bypass the declared runtime boundary, so it is not used here.

### Closure condition

RTA-001 can be closed only after the gateway is recovered through an authorized operational path and live readiness proves all of the following at the same observation point:

- `gateway_state=running`;
- `accepting_new_work=true`;
- no unrelated active run is interrupted by the recovery;
- upstream readiness remains healthy after recovery.

## RTA-002 — Kali MCP absent from live Hermes portal

**Classification:** `BLOCKER — KALI_MCP_NOT_REGISTERED`  
**State:** `BLOCKED-ON-RUNTIME`

The Hermes MCP portal server inventory was queried twice. Both observations exposed only:

- `hermes-agent-bridge` — enabled.

No `kali-lab`, Kali MCP or equivalent server was present in the live portal inventory.

This confirms that the historical Kali MCP registration must not be assumed current. No attempt was made to register or enable an invented server entry.

### Closure condition

After RTA-001 is recovered, perform read-only host/runtime inspection through the authorized Hermes path to determine:

1. whether the canonical Kali MCP Compose/runtime still exists and where;
2. whether the `hermes-kali-mcp` container is present and healthy;
3. whether its isolation/resource/read-only-root contract still matches the accepted design;
4. what current Hermes MCP configuration is intended to register it;
5. why the server is absent from the portal.

Only after the root cause is known should a minimal registration/configuration repair be proposed. Do not reconstruct registration from historical paths alone.

## RTA-003 — approval-path blocker not exercised in this checkpoint

**Classification:** `KNOWN-RISK`  
**State:** `NOT_RUN`

The historical failure mode `waiting_for_approval` with `approval_id=null` was not exercised in this checkpoint because admission was already blocked by RTA-001 before any new runtime work could be submitted.

The existing rule remains mandatory: if this state is reproduced later, do not invent an approval identifier, bypass policy or force the operation.

## Actions deliberately not performed

To preserve the acceptance boundary, this checkpoint did **not**:

- submit a new Hermes execution while admission was false;
- contact a lab target;
- execute a scenario or security tool;
- start, stop, reset or destroy a lab;
- mutate containers or networks;
- expose Docker socket access;
- use generic shell execution;
- register a guessed Kali MCP server;
- restart the Hermes gateway through an out-of-band mechanism;
- respond to or bypass an approval without a valid approval identifier.

## Runtime acceptance state

The walking skeleton remains blocked before live provisioning/execution:

`authorize -> [RTA-001 admission blocker] -> provision -> readiness -> execute -> evidence -> reset -> known-state proof`

Additionally, the Kali tool path is independently blocked by RTA-002.

Repository/CI delivery remains GREEN; these runtime blockers do not invalidate the committed contracts. They prevent promotion from repo proof to live runtime acceptance.

## Next safe action

1. Recover the Hermes gateway from stale `draining` through an authorized operational mechanism that does not interrupt unrelated work.
2. Re-run health/readiness and require `running + accepting_new_work=true`.
3. Perform read-only Hermes-host inspection to reconcile the live Kali MCP runtime/configuration.
4. Resolve RTA-002 by root cause, not by blind re-registration.
5. Resume core-lab lifecycle/readiness acceptance using canonical target IDs and no offensive action.
6. Only after authorization, runtime effect support and evidence/reset paths are valid, attempt a bounded seeded scenario.
