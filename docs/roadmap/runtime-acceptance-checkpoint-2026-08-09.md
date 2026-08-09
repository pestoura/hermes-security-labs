# Runtime acceptance checkpoint — 2026-08-09

**Project:** Hermes Security Labs  
**Repository baseline before live acceptance:** `b71b8d4bcdb781525c08feea9dec268345a5ad3b`  
**Current Hermes Security Labs main before Lane S:** `245bf8f1d7cd3c0408fd0967ae1a20215ef749b6`  
**Mode:** bounded runtime reconciliation; no target execution, no offensive tooling, no blind registration, no policy bypass.

This checkpoint is the canonical runtime-acceptance record for admission/discovery. It distinguishes repository proof from live runtime proof and records only state observed through the authorized Hermes path.

## Observed Hermes state

Latest live health/readiness observations reported:

- Hermes platform version `0.20.0`;
- Bridge version string `1.0.0`;
- upstream/readiness `ok` / `ready`;
- gateway `running`;
- `gateway_busy=false`;
- `gateway_drainable=true`;
- admission `accepting_new_work=true`;
- approval registry `ready`;
- production policy loaded and valid;
- HMAC required and configured.

The Bridge version string alone is not accepted as revision evidence. Exact live deployment evidence below shows that the running image is not built from the repository revision containing the RTA-003 fix.

## RTA-001 — transient stale drain

**Classification:** `RECOVERED-RUNTIME — STALE_DRAIN`  
**State:** `RESOLVED-RUNTIME`

The earlier transient `draining` condition recovered naturally after active API work reduced to zero. Subsequent health/readiness observations remain:

- `gateway_state=running`;
- `gateway_busy=false`;
- `gateway_drainable=true`;
- `accepting_new_work=true`.

No restart, forced admission, run cancellation or policy bypass was used. Do not restart the gateway for this historical incident.

## RTA-002 — Kali MCP absent from live Hermes portal

**Classification:** `BLOCKER — KALI_MCP_NOT_REGISTERED`  
**State:** `ROOT-CAUSE-OBSERVED / REMEDIATION-PENDING`

Portal inventory still exposes only:

- `hermes-agent-bridge` — enabled.

No Kali MCP server is registered in the live portal inventory.

### Runtime facts now observed

A bounded read-only reconciliation was executed successfully through Hermes with valid `user_instruction` provenance. It did not mutate host, containers, configuration or targets.

Observed Kali runtime:

- container: `hermes-kali-mcp`;
- container ID prefix: `2cba5fd1d0d9`;
- health: `healthy`;
- running for approximately 10 days at observation time;
- canonical Compose path used by the live container: `/home/estourpm/hermes-labs/kali-mcp/compose.yaml`;
- Compose project: `hermes-kali-mcp`;
- service: `kali-mcp`;
- build/tag: `hermes/kali-mcp:0.2.0`;
- command: `kali-server-mcp --ip 127.0.0.1 --port 5000`;
- container root filesystem: read-only;
- capabilities: dropped (`cap_drop=all`);
- `no-new-privileges` enabled;
- PID limit: `100`;
- memory limit: `512M`;
- CPU limit: `1.0`;
- network: internal Docker bridge `hermes-kali-mcp_hermes-kali-lab`;
- no host port publication;
- maintenance profile exists separately and was not instantiated.

Observed Hermes configuration:

- `/home/estourpm/.hermes/config.yaml` contains only one configured MCP server: `home-assistant`;
- `hermes mcp list` also reports only `home-assistant`;
- there is no Kali MCP entry in the active Hermes configuration.

### Root cause

RTA-002 is no longer an unknown-registration problem.

Two independent facts currently prevent Kali MCP availability to Hermes:

1. Kali MCP is not registered in active `mcp_servers` configuration.
2. The live service binds to `127.0.0.1:5000` inside an internal Docker network and publishes no host port, so the host Hermes process cannot reach that endpoint in the current topology.

Do not perform blind registration. Registration alone would not resolve reachability.

### Closure condition

RTA-002 can close only after the canonical design is reconciled and the chosen connectivity mechanism is implemented, then proven:

`registered -> reachable -> healthy -> policy-compliant`

Any remediation must preserve client/lab isolation and must not expose an unrestricted Kali endpoint.

## RTA-003 — approval required but no approval identifier issued

**Classification:** `BLOCKER — APPROVAL_ID_NULL / DEPLOYMENT_DRIFT`  
**State:** `REPO-FIX-MERGED / LIVE-FIX-NOT-DEPLOYED`

The repository fix remains PR `#95` in `pestoura/hermes-mcp-bridge`:

- fix commit: `d4fccbe135b51c41a5b668293e9c02b0db3a5147`;
- purpose: request-bound prompt approval handoff;
- expected runtime behaviour on `REQUIRE_APPROVAL`: non-null `approval_id`, opaque `request-sha256:` resource binding, approval decision state and single-use exact-request consumption.

### Valid runtime re-test

A minimal, non-operational policy probe used a contractually valid `untrusted_content` label because the probe contained source-derived text explicitly treated as untrusted data. The prompt prohibited host inspection, network access, target access, tool calls and mutation.

Client request id:

`hsl-rta003-approval-smoke-20260809-01`

Live policy evaluation returned:

- `decision=REQUIRE_APPROVAL`;
- reason `high-risk trust label`;
- `approval_required=true`.

The live `hermes_submit` response then reproduced the defect:

- `approval_required=true`;
- `approval_id=null`;
- `execution_id=not-created`;
- resource `null`;
- no `approval_decision` field.

No approval was invented and no retry was performed with weakened trust metadata.

### Exact live deployment evidence

A separate bounded read-only runtime reconciliation established:

- live container: `hermes-mcp-bridge`;
- container ID prefix: `cebc2f719b32`;
- live image tag: `hermes-mcp-bridge:1.0.0-f0b7e72f6bdf-candidate`;
- live image ID prefix: `sha256:044ab410ab8d`;
- OCI revision: `f0b7e72f6bdf42e82712f3d2e8182ff937ae9509`;
- OCI version: `1.0.0`;
- canonical live Compose worktree: `/home/estourpm/wt-mcp-bridge-f0b7e72/deploy/1.0.0`;
- Compose files: `compose.candidate.yml` and `compose.observability.yml`;
- live worktree HEAD: `f0b7e72f6bdf42e82712f3d2e8182ff937ae9509`;
- worktree clean at observation time.

The live revision `f0b7e72...` is not a descendant of `d4fccbe...` and does not contain `src/hermes_mcp_bridge/prompt_approvals.py` or the new prompt-approval response fields.

Therefore the runtime version string `1.0.0` is true but insufficient: the deployed build predates the RTA-003 fix.

### Current Bridge repository head

GitHub `main` has advanced beyond the PR #95 fix. Current observed head:

`ce6fd89e42b691504226912234dd9c8c92b4ceff`

GitHub comparison proves `d4fccbe...` is an ancestor of `ce6fd89...` (`ahead_by=3`, `behind_by=0`). The remediation must therefore use a candidate built from the exact current accepted main revision (or a later explicitly reconciled exact SHA), not deploy the older fix SHA as a downgrade.

### Closure condition

RTA-003 closes only after all of the following are live-proven:

`exact accepted Bridge SHA deployed`
`-> health/readiness`
`-> accepting_new_work`
`-> REQUIRE_APPROVAL`
`-> approval_id != null`
`-> audited approval decision`
`-> exact logical request retry`
`-> approval consumed once`

Repository CI proof alone is not sufficient.

## Read-only Kali reconciliation request

The previously blocked Kali reconciliation was retried using the original stable client request id and valid provenance matching the actual source:

`hsl-runtime-readonly-20260809-kali-reconcile-01`

Trust metadata:

`user_instruction`

Bridge policy evaluated this read-only request as `ALLOW`. The resulting Hermes run completed successfully and produced the RTA-002 and Bridge deployment observations recorded above.

This is not a policy bypass: `user_instruction` is a valid low-risk provenance label in the Bridge contract and accurately describes the source of the bounded read-only request. No label was changed to evade a decision on an already policy-gated logical request.

## Actions deliberately not performed

This reconciliation did **not**:

- contact a lab target;
- execute a security/offensive tool;
- perform scanning or exploitation;
- start, stop, restart or replace a lab/container/service;
- change Hermes MCP registration;
- expose the Kali MCP endpoint;
- alter Docker networking;
- read or disclose secret contents;
- install packages;
- use sudo/elevation;
- bypass or self-invent an approval;
- claim the Bridge fix deployed merely because repository CI is green.

## Runtime acceptance state

Current walking-skeleton position:

`authorize`
`-> Hermes admission READY`
`-> [RTA-003: Bridge deployment drift]`
`-> [RTA-002: Kali registration + reachability remediation]`
`-> provision/readiness`
`-> bounded execution`
`-> evidence`
`-> reset`
`-> known-state proof`

RTA-001 is closed. RTA-002 now has an observed root cause. RTA-003 is conclusively a live deployment-drift blocker rather than an unresolved repository defect.

## Next safe actions

1. Reconcile the canonical Bridge candidate-build/rollout path for exact current `main` and produce immutable candidate + SBOM evidence.
2. Deploy the accepted Bridge candidate through the existing controlled deployment mechanism with exact-SHA gates and rollback evidence; do not improvise a service replacement path.
3. Re-run health/readiness/admission and the bounded RTA-003 policy probe; use only the returned audited approval path.
4. Reconcile Kali MCP connectivity design before registration. Prefer the narrowest mechanism that keeps the endpoint non-public and reachable only from the authorized Hermes runtime.
5. Implement and prove Kali `registered + reachable + healthy + policy-compliant`.
6. Resume WebGoat/WebWolf, DVWA and Juice Shop lifecycle/readiness validation.
7. Execute no bounded scenario until target authorization, typed operation binding, gateway policy, backend readiness, evidence contract and reset capability are all proven.
