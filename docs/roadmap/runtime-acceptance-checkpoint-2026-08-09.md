# Runtime acceptance checkpoint — 2026-08-09

**Project:** Hermes Security Labs  
**Current Hermes Security Labs main before Lane U:** `2f97034d599c97de22c2a75cf9d37ffcfa17e054`  
**Mode:** bounded runtime reconciliation; no target execution, no offensive tooling, no blind registration, no policy bypass.

This file is the canonical runtime-acceptance record for admission/discovery. Repository/CI evidence and live runtime evidence are kept separate.

## Current high-level state

| Item | State |
| --- | --- |
| Labs repository contracts | `GREEN-REPO` |
| RTA-001 gateway admission | `DRAIN-IN-PROGRESS / BLOCKED-ON-RUNTIME` |
| RTA-002 Kali MCP | `REPO-CONTRACT-RECONCILED / BLOCKED-ON-RUNTIME-REGISTRATION` |
| RTA-003 approval handoff | `REPO-FIX-AND-ROLLOUT-GREEN / LIVE-FIX-NOT-DEPLOYED` |
| Bridge accepted repository head | `7e4b6b1cd70ddda418f840f54ae7ecef30df52e9` |
| Bridge live OCI revision | `f0b7e72f6bdf42e82712f3d2e8182ff937ae9509` |
| Walking skeleton execution | not yet admitted |

## Latest Hermes health/readiness observation

Live Bridge health remains good:

- Hermes Agent `0.20.0`;
- Bridge contract/version `1.0.0`;
- schema `0.6.1`;
- 27/27 tools;
- upstream, state DB, approval registry and security posture ready;
- production policy loaded/valid;
- HMAC required and file-backed;
- metrics loopback-only;
- tracing/retry/circuit breaker disabled as accepted.

Admission is currently closed by a gateway drain already in progress:

- `gateway_state=draining`;
- `active_api_runs=0`;
- `active_delegations=0`;
- `gateway_busy=false`;
- `active_agents=1`;
- `gateway_drainable=false`;
- `accepting_new_work=false`;
- `exit_reason=null`.

The previously active Bridge Phase 6 API run completed successfully with `RUNBOOK_ACCEPTED`; the remaining active agent is not represented by the Bridge's current API-run count. No unknown agent is being cancelled merely to reopen admission.

Upstream Hermes semantics were reconciled read-only: `gateway_drainable=false` while already `draining` means a new drain cannot be started; it is not a busy flag. In-band restart/drain logic may preserve active turns before stop, with an upstream default `restart_after_turn_timeout` of 21600 seconds. That semantic explains why a drain may legitimately remain open, but the current health surface does not prove which actor requested this specific drain. Do not infer a restart request without direct evidence.

## RTA-001 — gateway drain/admission

**Classification:** `RUNTIME ADMISSION BLOCKER`  
**State:** `DRAIN-IN-PROGRESS / DO-NOT-FORCE`

The earlier stale drain recovered naturally and was correctly closed at that time. A later drain has since been observed during concurrent authorized work.

Observed progression:

1. gateway previously recovered to `running` / `accepting_new_work=true`;
2. a legitimate Bridge Phase 6 API run was active while the gateway entered `draining`;
3. that API run completed with `RUNBOOK_ACCEPTED`;
4. `active_api_runs` fell to zero;
5. one non-API active agent remains and admission stays closed.

No restart, forced stop, process kill or cancellation of an unidentified agent has been performed.

### Closure condition

RTA-001 returns to `RESOLVED-RUNTIME` only after live proof of:

`gateway_state=running`
`-> accepting_new_work=true`
`-> gateway_drainable=true`

If the active agent remains wedged beyond its legitimate lifecycle, identify its ownership/state through an authorized read-only mechanism before any intervention.

## RTA-002 — Kali MCP absent from Hermes registration

**Classification:** `BLOCKER — KALI_MCP_NOT_REGISTERED`  
**State:** `REPO-CONTRACT-RECONCILED / STAGE-1-PENDING-ADMISSION`

### Runtime facts already observed

Kali runtime exists and is healthy:

- container `hermes-kali-mcp`;
- container ID prefix `2cba5fd1d0d9`;
- Compose `/home/estourpm/hermes-labs/kali-mcp/compose.yaml`;
- project `hermes-kali-mcp`, service `kali-mcp`;
- image `hermes/kali-mcp:0.2.0`;
- command `kali-server-mcp --ip 127.0.0.1 --port 5000`;
- read-only root filesystem;
- `cap_drop=all`;
- `no-new-privileges`;
- PID limit `100`;
- memory `512M`;
- CPU `1.0`;
- internal Docker network;
- no host port published.

Active Hermes configuration contains only `home-assistant`; no Kali MCP entry exists.

### Canonical transport reconciliation — Lane T

The repository contradiction has been removed and merged in PR #304.

The authority is now:

`kali-mcp/config/mcp-connectivity.example.yaml`

Preferred Hermes transport:

`docker exec -i hermes-kali-mcp kali-server-mcp`

This is STDIO and requires no host listener or Docker-network exposure. Therefore the container-local `127.0.0.1:5000` listener is **not** a reason to publish a port and is no longer treated as the normal Hermes connectivity path.

The repository now also records the actual Hermes filtering semantics:

- `tools.include: []` is not deny-all; it removes the include filter and can expose all discovered tools when enabled;
- first-stage registration must remain disabled;
- use a literal non-matching sentinel include;
- resources/prompts remain disabled;
- discover metadata only;
- review exact discovered tool names;
- enable only an exact accepted subset after policy/typed-operation reconciliation.

Post-merge Labs main:

`2f97034d599c97de22c2a75cf9d37ffcfa17e054`

Exact-main validation: 8/8 repository checks `SUCCESS`.

### Stage 1 pending runtime procedure

Stable client request id:

`hsl-rta002-stage1-disabled-registration-20260809-01`

Intended bounded entry:

```yaml
mcp_servers:
  hermes-kali-mcp:
    command: docker
    args:
      - exec
      - -i
      - hermes-kali-mcp
      - kali-server-mcp
    enabled: false
    connect_timeout: 30
    tools:
      include:
        - __hermes_rta002_no_tool__
      resources: false
      prompts: false
```

Stage 1 must:

1. parse current config and fail if the entry already exists unexpectedly;
2. create a backup and retain only path/hash as evidence;
3. validate the exact entry through the installed Hermes validator;
4. make only the narrow config mutation;
5. reparse and prove unrelated config keys/server names were preserved;
6. prove the server is stored disabled;
7. run only `hermes mcp test hermes-kali-mcp` for initialize/tool discovery;
8. invoke no discovered tool;
9. auto-restore the backup if any stage fails;
10. leave the entry disabled with the sentinel on success.

An attempted Stage 1 submission was refused with HTTP 503 because the gateway was already draining. No run/execution was created and no config mutation occurred.

### Closure condition

RTA-002 closes only after:

`registered -> reachable over canonical STDIO -> healthy/discoverable -> exact tool subset policy-compliant`

Successful metadata discovery alone does not authorize offensive tool execution.

## RTA-003 — approval required but no approval identifier issued

**Classification:** `BLOCKER — APPROVAL_ID_NULL / DEPLOYMENT_DRIFT`  
**State:** `REPO-FIX-AND-ROLLOUT-GREEN / LIVE-FIX-NOT-DEPLOYED`

### Valid runtime reproduction

The minimal non-operational probe remains:

`hsl-rta003-approval-smoke-20260809-01`

Using a valid `untrusted_content` provenance label, policy returned `REQUIRE_APPROVAL`, but the live Bridge returned:

- `approval_required=true`;
- `approval_id=null`;
- `execution_id=not-created`;
- no request-bound approval resource;
- no `approval_decision`.

No approval was invented and no trust label was weakened for retry.

### Exact live drift

Live Bridge:

- container `hermes-mcp-bridge`;
- container ID prefix `cebc2f719b32`;
- image `hermes-mcp-bridge:1.0.0-f0b7e72f6bdf-candidate`;
- image ID prefix `sha256:044ab410ab8d`;
- OCI revision `f0b7e72f6bdf42e82712f3d2e8182ff937ae9509`;
- OCI version `1.0.0`;
- deployment worktree `/home/estourpm/wt-mcp-bridge-f0b7e72/deploy/1.0.0`.

That revision predates PR #95 (`d4fccbe135b51c41a5b668293e9c02b0db3a5147`) and lacks its prompt-approval handoff implementation.

### Current accepted Bridge repository state

The Bridge repository subsequently advanced through Phase 5 DAG and Phase 6 RUNBOOK while preserving the PR #95 fix and the controlled rollout correction.

Current accepted main:

`7e4b6b1cd70ddda418f840f54ae7ecef30df52e9`

Exact-main CI:

- Python 3.11 `SUCCESS`;
- Python 3.12 `SUCCESS`;
- image / isolated acceptance / Trivy / CycloneDX SBOM `SUCCESS`;
- Phase 6 reports `RUNBOOK_ACCEPTED` with the V1 `1.0.0 / 0.6.1 / 27 tools` contract unchanged.

Retained exact-SHA supply-chain evidence:

- SBOM SHA-256 `14951e787613a3c82d0c9316aa3793e9486293875714b5e413625f4429ff905f`;
- provenance SHA-256 `12fd64f55dc8b84d005c0ea3ddb0c01fd5ad14801214ba1d33f105c0452e1b03`.

### Rollout correction — PR #99

PR #99 made the existing `deploy/1.0.0` mechanism explicitly safe for a controlled `1.0.0 -> 1.0.0` candidate refresh.

It preserves:

- exact candidate Git SHA;
- exact immutable rollback image ID;
- explicit rollback Bridge version;
- CycloneDX SBOM evidence;
- preflight;
- dry-run by default;
- existing dual mutation gate;
- full `1.0` security validation when rolling back to a `1.0.0` baseline.

Do not downgrade merely to satisfy an old `0.9.0` rollback assumption and do not invent a second deployment mechanism.

### Closure condition

RTA-003 closes only after:

`exact accepted Bridge SHA deployed`
`-> exact live OCI revision verified`
`-> health/readiness`
`-> accepting_new_work`
`-> REQUIRE_APPROVAL`
`-> approval_id != null`
`-> audited approval decision`
`-> exact logical request retry`
`-> approval consumed once`

Repository GREEN is not runtime acceptance.

## Actions deliberately not performed

This runtime-reconciliation wave has not:

- contacted a lab target;
- executed a Kali/security/offensive tool;
- scanned or exploited anything;
- published the Kali HTTP port;
- altered Kali networking;
- enabled all discovered MCP tools;
- restarted/stopped/replaced the gateway merely to clear admission;
- cancelled an unidentified active agent;
- registered Kali while the gateway is draining;
- deployed/replaced the Bridge while admission is unresolved;
- read/disclosed secret contents;
- invented an approval ID;
- weakened provenance/trust labels;
- treated CI GREEN as live proof.

## Current walking-skeleton position

`authorize`
`-> [RTA-001: admission drain in progress]`
`-> [RTA-003: exact accepted Bridge not yet deployed]`
`-> [RTA-002: Stage 1 Kali registration pending]`
`-> provision/readiness`
`-> bounded execution`
`-> evidence`
`-> reset`
`-> known-state proof`

## Automatic continuation when admission reopens

1. Re-observe health/readiness and require `running + accepting_new_work`.
2. Retry the exact RTA-002 Stage 1 disabled STDIO registration request with the stable client request id.
3. Record discovered tool names without invoking them; reconcile the minimum exact accepted tool subset.
4. Re-observe the full immutable live Bridge rollback image ID and exact deployment inputs.
5. Prepare/build the Bridge candidate from exact accepted main `7e4b6b1cd70ddda418f840f54ae7ecef30df52e9` using the canonical build/provenance contract.
6. Run canonical preflight and deployment dry-run.
7. Execute the controlled replacement only through the existing exact-SHA/rollback gates and any required audited Human-in-the-Loop approval.
8. Verify the exact live OCI revision, health/readiness and admission.
9. Re-run RTA-003 approval handoff and close it only with non-null audited approval + exact-request retry proof.
10. Close RTA-002 only after the registered STDIO path and exact tool subset are policy-compliant.
11. Resume WebGoat/WebWolf, DVWA and Juice Shop lifecycle/readiness acceptance.
12. Execute no bounded scenario until authorization, typed operation binding, gateway policy, backend readiness, evidence contract and reset capability are all proven.
