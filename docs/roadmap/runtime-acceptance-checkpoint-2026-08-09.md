# Runtime acceptance checkpoint — 2026-08-09

**Project:** Hermes Security Labs  
**Current Hermes Security Labs main:** `88a4ae88ae958cd889fff3a89cd64b269d3b75e6`  
**Accepted/live Hermes MCP Bridge revision:** `7e4b6b1cd70ddda418f840f54ae7ecef30df52e9`  
**Mode:** bounded runtime reconciliation; fail closed; no target execution, no offensive tool invocation, no blind registration, no policy bypass.

This file is the canonical runtime-acceptance record for the current Hermes/Kali admission and discovery boundary. Repository/CI evidence and live runtime evidence remain distinct.

## Current high-level state

| Item | State |
| --- | --- |
| Labs repository contracts | `GREEN-REPO` |
| RTA-001 gateway admission | `RESOLVED-RUNTIME` |
| RTA-002 Kali MCP | `STAGE-1-GREEN / STAGE-2-EXACT-SUBSET-PENDING` |
| RTA-003 approval handoff | `RESOLVED-RUNTIME` |
| Bridge accepted repository head | `7e4b6b1cd70ddda418f840f54ae7ecef30df52e9` |
| Bridge live OCI revision | `7e4b6b1cd70ddda418f840f54ae7ecef30df52e9` |
| Kali MCP live registration | present, `enabled:false`, non-matching sentinel allowlist |
| Walking skeleton execution | not yet admitted; Stage 2/tool-policy binding and target lifecycle acceptance remain |

## Latest Hermes health/readiness observation

Live health after RTA-002 Stage 1 and RTA-003 closure:

- Hermes Agent `0.20.0`;
- gateway `running`;
- `gateway_busy=false`;
- `gateway_drainable=true`;
- `active_agents=0` at the latest observation;
- upstream/readiness `ok`;
- Bridge version `1.0.0`;
- schema `0.6.1`;
- 27/27 Bridge tools;
- state DB and approval registry ready;
- production policy loaded and valid;
- HMAC required and file-backed;
- metrics loopback-only;
- tracing/retry/circuit breaker remain disabled as accepted;
- Bridge security posture `ready`.

## RTA-001 — gateway admission

**Classification:** `RESOLVED-RUNTIME`  
**State:** `GREEN/PASS`

The later gateway drain observed during concurrent authorized work recovered without a forced restart, process kill, cancellation of an unidentified agent or policy bypass.

Closure evidence now satisfies:

`gateway_state=running`
`-> gateway_busy=false`
`-> gateway_drainable=true`
`-> admission available`

RTA-001 is no longer a blocker.

## RTA-002 — Kali MCP registration and discovery

**Classification:** `PARTIALLY ACCEPTED — STAGE 1 COMPLETE`  
**State:** `STAGE-1-GREEN / STAGE-2-EXACT-SUBSET-PENDING`

### Runtime topology retained

Kali runtime remains intentionally isolated:

- container `hermes-kali-mcp`;
- image `hermes/kali-mcp:0.2.0`;
- Compose service command `kali-server-mcp --ip 127.0.0.1 --port 5000`;
- read-only root filesystem;
- `cap_drop=all`;
- `no-new-privileges`;
- PID/memory/CPU limits retained;
- internal Docker network;
- no host port published.

The container has two distinct roles:

- `kali-server-mcp` — long-running HTTP backend on container loopback;
- `mcp-server` — FastMCP STDIO wrapper used by Hermes; it proxies to the container-local backend.

### First Stage 1 attempt — fail-closed discovery of a bad contract

The first bounded Stage 1 used the then-canonical command:

`docker exec -i hermes-kali-mcp kali-server-mcp`

Configuration validation and the narrow mutation succeeded, but `hermes mcp test hermes-kali-mcp` failed because `kali-server-mcp` is not an MCP JSON-RPC STDIO endpoint.

The run automatically restored the Hermes configuration exactly to its pre-mutation state:

- pre/restore SHA-256: `688e8c80527e45bcfee6f369c94a8772314fbe4b41ea9da856eb69e68d011939`;
- no Kali tool was invoked;
- no target traffic occurred;
- no residual Kali MCP registration remained after the failed attempt.

This failure is accepted as useful runtime evidence: it disproved the repository transport contract without weakening any boundary.

### Repository correction — PR #306

PR #306, `fix(rta002): use MCP STDIO wrapper for Kali registration`, changed the canonical STDIO path to:

`docker exec -i hermes-kali-mcp mcp-server`

It deliberately did **not** change the Compose backend command. Regression coverage now requires:

- Hermes STDIO wrapper = `mcp-server`;
- container HTTP backend = `kali-server-mcp`;
- the two roles must remain distinct.

All PR workflows completed `SUCCESS`, including:

- `security`;
- `validate`;
- `Private VAmPI source-repo access deny`;
- `issue4-kali-safe-tool-validation`;
- `issue5-synthetic-mcp-targets`.

The PR was squash-merged as Labs main:

`88a4ae88ae958cd889fff3a89cd64b269d3b75e6`

### Corrected Stage 1 — GREEN/PASS

Stable runtime execution:

- execution: `run_09f177940abe43c1be253e843abb8d85`;
- client request: `hsl-rta002-stage1-disabled-registration-mcp-server-20260809-02`.

Canonical stored entry:

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

Evidence:

- initial config contained only the existing `home-assistant` MCP server;
- backup: `/home/estourpm/.hermes/backups/config.yaml.rta002-20260809T154227Z.bak`;
- backup SHA-256: `688e8c80527e45bcfee6f369c94a8772314fbe4b41ea9da856eb69e68d011939`;
- backup/config mode: `0600`;
- installed Hermes validator accepted the exact entry;
- narrow line-splice only; no YAML re-dump of unrelated state;
- post-mutation config SHA-256: `add660c007da353c41e263e389f42eb538dcf38bb68c05c446d38a3104c0c644`;
- all unrelated top-level sections remained structurally identical;
- existing `home-assistant` entry remained identical;
- exact registration invariants were proven;
- `hermes mcp test hermes-kali-mcp` connected over STDIO/docker in approximately 1230 ms;
- server name `kali_mcp`;
- server version `1.22.0`;
- MCP protocol `2024-11-05`;
- 12 tools discovered;
- the sentinel `__hermes_rta002_no_tool__` is not a real discovered tool;
- effective accepted tool set therefore remains empty while the server is disabled;
- no discovered tool was invoked;
- no target traffic occurred;
- no rollback was required;
- the registration remains present but disabled.

Discovered tool names, metadata only:

1. `nmap_scan`
2. `gobuster_scan`
3. `dirb_scan`
4. `nikto_scan`
5. `sqlmap_scan`
6. `metasploit_run`
7. `hydra_attack`
8. `john_crack`
9. `wpscan_analyze`
10. `enum4linux_scan`
11. `server_health`
12. `execute_command`

Discovery is not authorization. No tool is enabled merely because it exists.

### Stage 2 boundary

Stage 2 must reconcile the discovered surface against the typed operation/tool registry and gateway policy, then select the **minimum exact literal subset** required by an authorized scenario.

Until that reconciliation is accepted:

- keep `hermes-kali-mcp` disabled;
- retain the non-matching sentinel;
- keep resources/prompts disabled;
- do not use wildcard allowlists;
- do not enable all 12 tools;
- treat `execute_command`, `metasploit_run`, credential-attack and scan/exploitation capabilities as excluded unless an explicit typed, scoped and authorized scenario requires them and the relevant HITL/policy gate admits them.

### RTA-002 closure condition

RTA-002 closes only after:

`Stage 1 registration/discovery GREEN`
`-> exact typed-operation/policy mapping`
`-> minimum literal allowlist accepted`
`-> bounded Stage 2 enablement`
`-> registered/reachable/healthy`
`-> effective exposed surface equals the accepted subset`

No offensive execution is required merely to close registration acceptance.

## RTA-003 — approval handoff and exact Bridge deployment

**Classification:** `RESOLVED-RUNTIME`  
**State:** `GREEN/PASS`

### Accepted candidate and supply-chain evidence

Exact accepted Bridge revision:

`7e4b6b1cd70ddda418f840f54ae7ecef30df52e9`

Candidate/live image:

- reference `hermes-mcp-bridge:1.0.0-7e4b6b1cd70d-candidate`;
- immutable image ID `sha256:b124045702bb62f6cd5cc8457a43e150e5b266c0c0f721f35d5f6b6f76e396c6`;
- OCI revision `7e4b6b1cd70ddda418f840f54ae7ecef30df52e9`;
- OCI version `1.0.0`.

Retained exact-SHA evidence generated for this candidate:

- CycloneDX SBOM: `/home/estourpm/hermes-release-evidence/1.0.0/7e4b6b1cd70ddda418f840f54ae7ecef30df52e9/sbom-cyclonedx.json`;
- SBOM SHA-256 `62894fd81b0d860b5a3d8b977aae21dea2067c2efdc470f8eaf70bb41800763a`;
- provenance: `/home/estourpm/hermes-release-evidence/1.0.0/7e4b6b1cd70ddda418f840f54ae7ecef30df52e9/image-provenance.json`;
- provenance SHA-256 `12fce725746aee2a78472358163cd13e49ed4b42016a6553301fc25761683ac6`;
- isolated acceptance marker `HERMES_BRIDGE_1_0_0_ISOLATED_ACCEPTANCE_PASS`;
- canonical preflight marker `HERMES_BRIDGE_1_0_0_PREFLIGHT_GO`;
- canonical deployment dry-run `PASS`.

A later deployment attempt correctly aborted fail-closed when its previously observed rollback baseline had changed. Read-only reconciliation then proved that a concurrent, already-authorized Bridge Phase 7-9 lane had promoted the same accepted candidate. The stale-baseline abort therefore prevented an unnecessary duplicate replacement.

Live proof after reconciliation:

- image reference `hermes-mcp-bridge:1.0.0-7e4b6b1cd70d-candidate`;
- immutable image ID exactly `sha256:b124045702bb62f6cd5cc8457a43e150e5b266c0c0f721f35d5f6b6f76e396c6`;
- OCI revision exactly `7e4b6b1cd70ddda418f840f54ae7ecef30df52e9`;
- version `1.0.0`;
- health `healthy`;
- restart count `0` at reconciliation.

### Approval handoff smoke — GREEN/PASS

Minimal non-operational request:

`hsl-rta003-approval-smoke-20260809-01`

The production policy returned `REQUIRE_APPROVAL` for `untrusted_content` and the corrected live Bridge emitted a request-bound non-null approval identifier:

`approval-prompt-c364ea4f2364127b83d4ad01113c786ff5352b44039b6785`

Acceptance sequence:

1. first exact request -> `REQUIRE_APPROVAL`;
2. `approval_id != null`;
3. audited decision -> `approved`;
4. exact same logical request retried;
5. execution `run_317ced10fb164add95872eff66f04420` completed with `RTA003_APPROVAL_SMOKE_PASS`;
6. approval registry state -> `consumed`;
7. `consumed_at=2026-08-09T15:31:25.789105+00:00`;
8. later recheck still reports `consumed`.

This proves the approval is request-bound, auditable and single-use. No approval identifier was invented and no trust label was weakened.

### RTA-003 closure condition — satisfied

`exact accepted Bridge SHA deployed`
`-> exact live OCI revision verified`
`-> health/readiness`
`-> admission available`
`-> REQUIRE_APPROVAL`
`-> approval_id != null`
`-> audited approval decision`
`-> exact logical request retry`
`-> approval consumed once`

RTA-003 is closed.

## Actions deliberately not performed

This runtime-acceptance wave has not:

- contacted a live lab target from the Stage 1 acceptance path;
- invoked a discovered Kali MCP tool during registration/discovery;
- scanned or exploited a target as part of RTA-002 Stage 1;
- published the Kali HTTP port;
- altered Kali networking;
- enabled all discovered MCP tools;
- weakened the sentinel/allowlist contract;
- forced or bypassed the gateway drain;
- invented an approval ID;
- weakened provenance/trust labels;
- disclosed secret contents;
- treated repository CI GREEN as a substitute for the live RTA-002/RTA-003 evidence above.

## Current walking-skeleton position

`authorize`
`-> RTA-001 admission GREEN`
`-> RTA-003 Bridge/approval GREEN`
`-> RTA-002 Stage 1 registration/discovery GREEN`
`-> [RTA-002 Stage 2 exact tool subset/policy binding pending]`
`-> provision/readiness`
`-> bounded typed execution`
`-> evidence`
`-> reset`
`-> known-state proof`

## Automatic continuation

1. Reconcile the 12 discovered Kali tool names against the canonical typed operation/tool registry and gateway policy.
2. Select the minimum exact literal tool subset for the first authorized walking-skeleton scenario; retain fail-closed exclusion for everything else.
3. Validate the Stage 2 configuration mutation before applying it; preserve backup/restore and unrelated-config invariants.
4. Enable only the accepted subset, keeping resources/prompts disabled.
5. Verify the effective exposed Kali tool surface equals the accepted subset exactly, without invoking a tool merely for registration proof.
6. Close RTA-002 when registration/reachability/health/policy-compliance are all demonstrated.
7. Resume WebGoat/WebWolf, DVWA and Juice Shop lifecycle/readiness acceptance through the canonical backend/lifecycle path.
8. Execute no bounded scenario until authorization, target allowlist/window, typed operation binding, gateway policy, backend readiness, evidence contract, HITL requirements and reset capability are all proven.
