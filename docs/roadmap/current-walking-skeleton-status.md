# Hermes Security Labs — current walking-skeleton status

**Reconciled:** 2026-08-09 18:00 UTC  
**Current Labs baseline:** `804e21feb0ec43002a5281978cd4c94c60b53200`  
**Accepted/live Hermes MCP Bridge revision:** `7e4b6b1cd70ddda418f840f54ae7ecef30df52e9`

This is the concise current-state view of the walking skeleton. Repository/CI proof and live Hermes runtime proof remain separate evidence classes. Historical detail remains in [`runtime-acceptance-checkpoint-2026-08-09.md`](runtime-acceptance-checkpoint-2026-08-09.md).

## Current summary

| Item | Current state |
| --- | --- |
| RTA-001 gateway admission | `RESOLVED-RUNTIME / GREEN` |
| RTA-002 Stage 1 registration/discovery | `GREEN/PASS` |
| RTA-002 Stage 2 semantic/policy contract | `GREEN-REPO`, merged PR #308 |
| RTA-002 Stage 2 live health acceptance | `BLOCKED-ON-CONNECTOR` |
| RTA-003 Bridge approval handoff | `RESOLVED-RUNTIME / GREEN` |
| WebGoat/WebWolf lifecycle/readiness repository | `PASS / READY-REPO` |
| DVWA lifecycle/readiness repository | `PASS / READY-REPO` |
| Juice Shop lifecycle/readiness repository | `PASS / READY-REPO`, merged PR #309 |
| Seeded bounded scenario execution | `PRESENT-NOT-IMPLEMENTED` beyond health |
| Full walking skeleton live completion | `BLOCKED-ON-CONNECTOR-AND-RUNTIME-INTEGRATION` |

## Walking skeleton

Target path:

`authorize -> provision -> readiness -> execute bounded scenario -> evidence -> reset -> known-state proof`

| Stage | Repository/CI state | Live runtime state |
| --- | --- | --- |
| Authorize | target registry, deny-before-dispatch, typed operations, RoE/TB1 verifier contracts `GREEN-REPO` | RTA-003 approval flow accepted; Hermes operational TB1 receipt issuance remains `NOT_IMPLEMENTED / NOT_RUN` |
| Admission | Bridge exact-SHA and policy/approval contracts accepted | RTA-001 last accepted observation: gateway `running`, `busy=false`, `drainable=true`, admission available |
| Kali registration | canonical STDIO contract `GREEN-REPO` | Stage 1 `GREEN/PASS`; disabled + sentinel retained after discovery |
| Kali health/policy binding | `kali.mcp.health.read -> server_health`, L0, exact mapping, `PRESENT/NOT_RUN` | Stage 2 live acceptance pending because ChatGPT Hermes connector is unavailable at invocation time |
| Provision | Docker backend `READY-REPO` | live lifecycle re-observation pending |
| Readiness | WebGoat/WebWolf, DVWA and Juice Shop repository maturity/readiness `PASS` | live readiness observation pending |
| Plan scenario | deterministic Scenario Plan Composer `GREEN-REPO` | not an execution claim |
| Execute bounded scenario | typed scenario contracts exist | non-health real runner/Kali effect integration remains `NOT_IMPLEMENTED / NOT_RUN` |
| Evidence | Evidence Plane v2 and structured scenario evidence contracts `GREEN-REPO` | real scenario persistence/observation pending |
| Reset/cleanup | bounded lifecycle/reset governance exists | live zero-residue/known-state proof pending |

## RTA-001 — gateway admission

**State:** `RESOLVED-RUNTIME / GREEN`

Accepted live observation established:

- gateway state `running`;
- `gateway_busy=false`;
- `gateway_drainable=true`;
- no forced restart or admission bypass;
- new work admission available.

This must be re-observed before the next live mutation, but it is no longer an unresolved historical blocker.

## RTA-002 — Kali MCP

### Stage 1 — `GREEN/PASS`

Canonical registration:

```yaml
mcp_servers:
  hermes-kali-mcp:
    command: docker
    args:
      - exec
      - -i
      - hermes-kali-mcp
      - mcp-server
    enabled: false
    connect_timeout: 30
    tools:
      include:
        - __hermes_rta002_no_tool__
      resources: false
      prompts: false
```

Accepted runtime evidence:

- execution `run_09f177940abe43c1be253e843abb8d85`;
- backup `/home/estourpm/.hermes/backups/config.yaml.rta002-20260809T154227Z.bak`;
- backup SHA-256 `688e8c80527e45bcfee6f369c94a8772314fbe4b41ea9da856eb69e68d011939`;
- STDIO connection through `docker exec -i hermes-kali-mcp mcp-server`;
- server `kali_mcp` `1.22.0`;
- protocol `2024-11-05`;
- 12 tool names discovered as metadata only;
- sentinel matched no real tool;
- no tool invocation and no target traffic;
- registration left disabled.

PR #306 corrected the earlier invalid STDIO assumption and permanently separates:

- `kali-server-mcp` = container-local HTTP backend;
- `mcp-server` = FastMCP STDIO wrapper used by Hermes.

### Stage 2 — minimum policy surface

PR #308 is merged. It introduces the least-privilege typed health contract:

- operation `kali.mcp.health.read`;
- normal/controlled profile;
- L0;
- no parameters;
- side effect `none`;
- exact tool mapping `kali-mcp.server-health -> server_health`;
- availability remains `PRESENT`, never `READY` from discovery alone;
- no `execute_command`;
- no scanner/exploitation/credential tool mapping;
- `kali-mcp.audit` remains `DEGRADED / UNMAPPED`.

Live Stage 2 closure is still required:

`registered -> reachable -> exact exposed subset [server_health] -> bounded server_health result -> policy/HITL compliance -> healthy`

On any mismatch, restore the disabled sentinel registration fail-closed.

## RTA-003 — Bridge exact-SHA approval handoff

**State:** `RESOLVED-RUNTIME / GREEN`

Accepted live Bridge:

- revision `7e4b6b1cd70ddda418f840f54ae7ecef30df52e9`;
- image `hermes-mcp-bridge:1.0.0-7e4b6b1cd70d-candidate`;
- immutable image ID `sha256:b124045702bb62f6cd5cc8457a43e150e5b266c0c0f721f35d5f6b6f76e396c6`;
- Bridge `1.0.0`, schema `0.6.1`, 27 tools;
- accepted supply-chain SBOM/provenance retained under the exact-SHA evidence directory.

Approval acceptance proof:

1. policy returned `REQUIRE_APPROVAL`;
2. non-null request-bound approval ID `approval-prompt-c364ea4f2364127b83d4ad01113c786ff5352b44039b6785`;
3. decision recorded `approved`;
4. exact logical request retried;
5. execution `run_317ced10fb164add95872eff66f04420` completed with `RTA003_APPROVAL_SMOKE_PASS`;
6. approval state became `consumed` and remained single-use.

The accepted deployment also proved immutable drift detection: a stale rollback baseline caused a later duplicate rollout attempt to abort before mutation instead of overwriting the already-promoted accepted image.

## Lifecycle/readiness targets

### WebGoat/WebWolf

Repository maturity `PASS`.

Readiness requires bounded TCP + HTTP checks for both WebGoat and WebWolf through the committed readiness adapter. Kali connectivity remains temporary and explicit.

### DVWA

Repository maturity `PASS`.

Readiness requires bounded TCP + HTTP `/login.php` checks. Application and database networks remain separated; Kali attach helper refuses the internal DB network.

### Juice Shop

PR #309 is merged; repository maturity is now `PASS`.

The previous two maturity findings were removed:

- fixed loopback publication became parameterized `127.0.0.1:${JUICE_SHOP_HOST_PORT:-3000}:3000`;
- executable bounded `connect-kali.sh` and `disconnect-kali.sh` helpers were added.

The helpers verify network ownership and expected endpoints and fail closed on foreign endpoints. The manifest still truthfully declares the residual publication-bridge egress risk; PR #309 did not claim to solve egress hardening.

## Seeded scenario status

| Scenario | Static plan | Current effect state | Live state |
| --- | --- | --- | --- |
| `webgoat-tls-transport-review` | `PLAN_READY` | `web.discovery.headers` and `web.discovery.tls` registered but real effect/runner integration not implemented | blocked |
| `dvwa-sql-injection-screening` | `PLAN_READY` | synthetic-only SQLi operation registered; real effect/runner integration not implemented | blocked |
| `juice-shop-lab-lifecycle-stop` | `PLAN_READY` | lifecycle stop contract registered; real Runner dispatch/outcome path not implemented | blocked |

The first implementation target should remain the WebGoat L1 read-only scenario, not L2 SQLi.

## Current runtime blocker — ChatGPT Hermes connector

The Hermes MCP app is still installed and its app-specific permission is `Allow all actions`. The current failure is not a permission denial.

Observed repeatedly in this continuation:

1. plugin/tool discovery reports `Hermes_MCP.hermes-agent-bridge_hermes_health` available;
2. immediate invocation returns `Resource not found` and asks for rediscovery;
3. rediscovery can again expose the tool, followed by the same invocation failure.

Therefore the current classification is:

`BLOCKED-ON-CONNECTOR`

This is **not** evidence that the Hermes gateway itself is unhealthy. No new runtime health claim may be made until an invocation succeeds.

## Runtime integration gap after connector recovery

Even after the connector recovers, the full walking skeleton cannot be called final merely from lifecycle/readiness because the current architecture deliberately retains these states:

- Hermes operational TB1 authorization receipt issuance: `NOT_IMPLEMENTED / NOT_RUN`;
- real runner identity/transport authentication: `NOT_IMPLEMENTED / NOT_RUN`;
- runner execution integration: `NOT_RUN`;
- Kali MCP non-health handler integration: `NOT_RUN`;
- deployed gateway outcome reception: `NOT_RUN`;
- Evidence Plane real outcome persistence: `NOT_RUN`.

The existing Runner Protocol supervised process boundary is reusable infrastructure, not a real adapter and not execution authority. Do not bypass these boundaries using `execute_command`, arbitrary shell, direct scanner calls or a caller-created authorization reference.

## Automatic continuation order

When the Hermes MCP resource is invokable again, continue without redoing completed work:

1. re-observe `hermes_health` / readiness and require gateway `running` + new-work admission;
2. revalidate exact live Bridge revision `7e4b6b1cd70ddda418f840f54ae7ecef30df52e9`;
3. read-only verify the Stage 1 Kali registration remains disabled + sentinel;
4. back up Hermes config;
5. replace only the sentinel with exact literal allowlist `[server_health]`, keep resources/prompts disabled and enable only for bounded Stage 2 acceptance;
6. prove the effective exposed surface is exactly `server_health`;
7. invoke only `server_health`; satisfy normal audited policy/HITL if required;
8. on PASS, close RTA-002 as `registered -> reachable -> healthy -> policy-compliant`, then return to least privilege (disable again unless immediately required by an accepted scenario);
9. execute lifecycle/readiness acceptance for WebGoat/WebWolf, DVWA and Juice Shop through `platform/scripts/lab_lifecycle.py` and committed readiness adapters;
10. capture lifecycle evidence and reset/known-state proof;
11. implement and validate the first real LAB_ONLY Runner adapter/typed effect for WebGoat L1 without generic execution;
12. only after the authorization/Runner/evidence chain is real, execute the first bounded scenario and continue GREEN/PASS to the remaining seeded scenarios.

No target-interacting action is authorized merely because repository contracts or CI are GREEN.

## Recent engineering checkpoints

| Change | PR | Merge SHA | Outcome |
| --- | --- | --- | --- |
| Kali STDIO role correction | #306 | `88a4ae88ae958cd889fff3a89cd64b269d3b75e6` | Stage 1 corrected transport contract |
| Runtime acceptance reconciliation | #307 | `91c055fd9f7a79f84c2124f9bc8a9ebe1039ccd4` | RTA-001/003 closed, Stage 1 recorded |
| Typed Kali health contract | #308 | `eae2b87508e4488741e1eb146a9ed49595003102` | exact L0 `server_health` policy mapping |
| Juice Shop lifecycle readiness | #309 | `804e21feb0ec43002a5281978cd4c94c60b53200` | maturity `PASS`, bounded Kali attach/detach |

## Decision record

**Decision:** do not claim the walking skeleton final while the live connector is unavailable or while TB1/runner/Kali effect integration remains deliberately unimplemented.

**Reason:** repository GREEN and lifecycle maturity are necessary but do not prove live authorization, execution, evidence or cleanup.

**Accepted approach:** preserve completed RTA evidence, continue repository engineering independently where safe, and resume the exact live gate from Stage 2 when the Hermes connector is invokable.

**State:** `BLOCKED-ON-CONNECTOR-AND-RUNTIME-INTEGRATION`.
