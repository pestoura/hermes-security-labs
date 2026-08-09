# Baseline known issues — reconciled 2026-08-09

This file reconciles the operational baseline imported on 2026-07-30 with the
repository state demonstrated on `main` and the later runtime reconciliation
lanes.

It is deliberately conservative: repository and CI evidence never substitutes
for live Hermes/Kali/runtime acceptance.

## Status model

- `RESOLVED-REPO` — the original repository defect is corrected and covered by
  the normal repository validation path. This does **not** imply separate live
  runtime acceptance unless stated explicitly.
- `LIVE-STAGE-1-ACCEPTED` — the bounded live registration/discovery stage is
  accepted, but later enablement or functional execution remains separately
  gated.
- `RESOLVED-RUNTIME` — the specific imported runtime defect has direct live
  evidence satisfying its closure condition.
- `BLOCKED-ON-RUNTIME` — repository work can describe or prepare the contract,
  but closure requires an authorized live Hermes/lab/tool observation.
- `OPEN` — neither repository nor runtime evidence is sufficient to close the
  item.

## Reconciled imported baseline

### 1. Kali MCP connectivity and registration contract

**Status: `RESOLVED-REPO / LIVE-STAGE-1-ACCEPTED / STAGE-2-PENDING`**

The earlier repository guidance that treated `@url:http://127.0.0.1:5000` as the
normal Hermes registration path was superseded. A later live Stage 1 run also
disproved the first STDIO command that used `kali-server-mcp` directly.

The runtime demonstrated two distinct container roles:

- `kali-server-mcp` is the long-running HTTP backend bound only to container
  loopback (`127.0.0.1:5000`);
- `mcp-server` is the FastMCP STDIO wrapper that Hermes must execute; it proxies
  to the container-local backend.

Repository authority is now consistent and merged through PR #306:

- `kali-mcp/config/mcp-connectivity.example.yaml` prefers zero-listener STDIO via
  `docker exec -i hermes-kali-mcp mcp-server`;
- the Compose service deliberately remains
  `kali-server-mcp --ip 127.0.0.1 --port 5000`;
- regression tests require the STDIO wrapper and HTTP backend roles to remain
  distinct;
- the container-local HTTP listener remains non-published and is not the normal
  host Hermes transport;
- `skills/kali-mcp-lab/SKILL.md` references the same authority instead of
  defining a competing URL contract;
- registration starts disabled with an explicit non-matching sentinel include,
  because current Hermes semantics treat `tools.include: []` as no include
  filter rather than deny-all;
- resources/prompts remain disabled;
- discovered tools are enabled only as an exact literal accepted subset after
  typed-operation/policy review.

Live Stage 1 is now accepted:

- corrected registration command:
  `docker exec -i hermes-kali-mcp mcp-server`;
- registration stored `enabled:false`;
- sentinel `__hermes_rta002_no_tool__` retained;
- `hermes mcp test hermes-kali-mcp` connected over STDIO;
- server `kali_mcp` version `1.22.0`, protocol `2024-11-05`;
- 12 tool names discovered as metadata only;
- sentinel did not match a discovered tool;
- no discovered tool was invoked and no target traffic occurred.

The item is not fully closed because Stage 2 still requires exact tool-subset
reconciliation and policy-compliant bounded enablement. Discovery alone is not
authorization.

### 2. Juice Shop healthcheck depends on wget

**Status: `RESOLVED-REPO`**

The canonical Juice Shop Compose healthcheck no longer depends on `wget`. It
uses the image's Node runtime to perform the bounded loopback HTTP healthcheck.
The Compose contract is validated in CI.

This closes the imported repository defect; it does not replace an end-to-end
Hermes-host lifecycle acceptance.

### 3. WPScan writable state

**Status: `BLOCKED-ON-RUNTIME`**

The historical live Kali observation was that `wpscan --version` could not use
`/root/.wpscan` with the read-only root filesystem. Repository/CI controlled-tool
validation is GREEN, but that does not substitute for live Hermes runtime
acceptance.

Required closure evidence: authorized live tool-health/functional acceptance
showing the intended writable path while preserving read-only root, resource
limits and isolation.

### 4. Gobuster MCP execution validation

**Status: `BLOCKED-ON-RUNTIME`**

Binary presence or repository declaration is not functional acceptance. Closure
requires an authorized disposable lab target, bounded execution and captured
runtime evidence proving a successful Gobuster operation inside the isolated
Kali MCP path.

### 5. Dirb MCP execution validation

**Status: `BLOCKED-ON-RUNTIME`**

Closure requires the same class of authorized isolated runtime proof as
Gobuster. No repository-only result is promoted to `FUNCTIONAL-PASS`.

### 6. SQLMap synthetic SQLi target

**Status: `BLOCKED-ON-RUNTIME`**

The repository contains a canonical DVWA synthetic SQL-injection scenario, a
typed `web.validation.sql-injection` semantic operation and corresponding tool
registry coverage. Controlled CI synthetic-MCP validation is GREEN, but the
live Hermes walking-skeleton acceptance remains separate.

Closure requires an authorized live local synthetic SQLi target and bounded,
correlated runtime evidence through the accepted Hermes path.

### 7. Hydra synthetic authentication target

**Status: `BLOCKED-ON-RUNTIME`**

Controlled CI coverage exists, but no live Hermes disposable authentication
service plus scoped synthetic credentials has been accepted through the current
runtime path. Do not create or reuse real credentials merely to close this test.

### 8. John the Ripper synthetic hash

**Status: `BLOCKED-ON-RUNTIME`**

Controlled CI validation is GREEN. The imported runtime issue still requires a
live isolated Kali acceptance proving an intentional writable state/cache path
with a synthetic hash and no weakening of the read-only-root boundary.

### 9. Enum4linux disposable Samba target

**Status: `BLOCKED-ON-RUNTIME`**

Controlled CI synthetic-MCP coverage is GREEN, but no accepted live Hermes
disposable Samba target and bounded Enum4linux validation are recorded. A
reachable host alone is not authorization.

### 10. Metasploit writable state

**Status: `BLOCKED-ON-RUNTIME`**

Controlled non-exploitation CI validation is GREEN. The historical live runtime
warning about writable state still requires live isolated acceptance of the
intended Metasploit state path without broadening host access, privileges or
persistence.

### 11. Juice Shop end-to-end workflow

**Status: `BLOCKED-ON-RUNTIME`**

Repository contracts cover canonical target authorization, Docker backend
planning, lifecycle, a Juice Shop readiness adapter, structured scenario
evidence expectations and reset/cleanup proof expectations. The aggregate JDS
static gate composes the seeded scenario set before expensive CI runtime jobs.

The original issue remains open because the full live Hermes walking skeleton
has not yet been accepted as one correlated run:

`authorize -> provision -> readiness -> execute bounded scenario -> evidence -> reset -> known-state proof`

### 12. Deployment drift detection

**Status: `RESOLVED-RUNTIME`**

This acceptance wave directly exercised the drift guard during the Bridge
`1.0.0` exact-SHA rollout. A controlled deploy invocation aborted fail-closed
before mutation because the previously observed rollback baseline no longer
matched the live immutable image ID.

Read-only reconciliation then proved the live Bridge had already been promoted
by another authorized lane to the accepted candidate:

- OCI revision `7e4b6b1cd70ddda418f840f54ae7ecef30df52e9`;
- image ID
  `sha256:b124045702bb62f6cd5cc8457a43e150e5b266c0c0f721f35d5f6b6f76e396c6`;
- Bridge `1.0.0`;
- healthy;
- restart count `0` at reconciliation.

The stale-baseline deployment did not force the rollout and did not overwrite a
newer live state. This is the required live proof that immutable deployment
drift is detected and fails closed.

## Repository walking-skeleton status after current reconciliation

The following repository/CI status must not be read as live scenario acceptance:

| Contract | Repository status | Runtime status |
| --- | --- | --- |
| Scenario Plan Composer | `GREEN` — deterministic, inert, fail-closed | not an executor |
| Core web readiness adapters | `GREEN` — WebGoat/WebWolf, DVWA, Juice Shop declarations | `BLOCKED-ON-RUNTIME` acceptance |
| Structured scenario evidence contract | `GREEN` — aligned with Evidence Plane v2 policy | `BLOCKED-ON-RUNTIME` scenario evidence observation |
| Aggregate JDS static gate | `GREEN` — stages static contracts before Docker/runtime CI | not live Hermes proof |
| Target authorization boundary | `GREEN` repository contract | live execution still requires authorized target/window |
| Backend abstraction | Docker `SUPPORTED/READY`; other backends fail closed | VM/Kubernetes/Cloud/Remote remain not ready |
| Kali MCP registration Stage 1 | `GREEN` contract | `LIVE-STAGE-1-ACCEPTED`; Stage 2 pending |
| Bridge approval handoff | `GREEN` contract | `RESOLVED-RUNTIME` |

Recent merged reconciliation checkpoints include:

- Lane K — PR #294 — `f18428e96a6fa4ab9873c64336258e799d91de3f`;
- Lane L — PR #295 — `140f359f8ea72e8af0d335ab13ccafffca2f3d95`;
- Lane M — PR #296 — `2a10282780bcf5f333baf074feae614303f50abf`;
- Lane N — PR #297 — `da22a93f5f90938ba677cf185208af477bbab04c`;
- Kali STDIO role correction — PR #306 — main `88a4ae88ae958cd889fff3a89cd64b269d3b75e6`.

## Separate open dependency — private read-only GHCR

GitHub issue #53 remains separate from the imported runtime baseline. The
strict/private consumption target still requires a classic GitHub credential
with exactly `read:packages` for the final Hermes production boundary, plus the
specified anonymous-deny/authenticated-read and negative write controls.

The temporary DEV exception for a broader PAT does not relax the strict target
state and does not block unrelated repository-only work.

## Runtime acceptance rule

Do not convert repository `GREEN` into runtime `ACCEPTED` by inference.
Re-observe Hermes health, canonical targets, isolation, readiness, evidence and
reset proof for every live acceptance boundary.

The current Bridge approval handoff has been accepted with a non-null,
request-bound approval ID, audited `approved` decision, exact logical request
retry and single-use `consumed` state. If a future approval path ever regresses
to `approval_required=true` with `approval_id=null`, fail closed: do not bypass
it, do not invent an identifier and do not weaken the trust label.
