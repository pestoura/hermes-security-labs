# Hermes Security Labs — current walking-skeleton status

**Reconciled:** 2026-08-09  
**Latest exact-green repository baseline before this update:**
`63357eb02eb82a999aec53cf15dad1aa01dd59d0` (Lane P / PR #299)

This document is the concise status view for the currently demonstrated
walking skeleton. It distinguishes repository/CI proof from live Hermes runtime
proof. It does not replace the canonical registries, policies or roadmap.

## Status vocabulary

- `GREEN-REPO` — committed contract/code is exercised by repository CI at an
  identified commit.
- `READY-REPO` — the repository declares a supported executable backend or
  component and the required shipped repository capabilities exist.
- `PRESENT-NOT-IMPLEMENTED` — the typed contract exists, but the controlled
  effect is not implemented/accepted.
- `READY-RUNTIME` — the specific live runtime condition was observed healthy;
  this does not imply later stages are accepted.
- `RESOLVED-RUNTIME` — a previously observed runtime blocker was subsequently
  observed cleared without inference.
- `BLOCKED-ON-RUNTIME` — closure requires an authorized live Hermes/lab/tool
  observation and cannot be inferred from CI.
- `BLOCKED-ON-CREDENTIAL` — a least-privilege credential or external permission
  required by the strict target state is not available/accepted.
- `DEFINED-NOT-READY` — architecture/registry modelling exists but execution
  must fail closed.

## Walking skeleton

Target delivery path:

`authorize -> provision -> readiness -> execute bounded scenario -> evidence -> reset -> known-state proof`

| Stage | Repository/CI state | Live runtime state | Canonical source |
| --- | --- | --- | --- |
| Authorize | `GREEN-REPO` — target registry and deny-before-dispatch boundary | policy gate is active; approval issuance currently blocked by RTA-003 for gated host inspection | `platform/targets/` + Hermes policy |
| Admission | repository-independent live gate | `READY-RUNTIME` — gateway recovered naturally to `running`, `active_api_runs=0`, `active_agents=0`, `accepting_new_work=true` | Hermes health/readiness |
| Provision | `READY-REPO` for Docker backend | host/runtime reconciliation cannot proceed through policy because RTA-003 returns no approval ID | `platform/backends/backend-registry.yaml` |
| Readiness | `GREEN-REPO` manifests + adapters; core adapters added for WebGoat/WebWolf, DVWA and Juice Shop | `BLOCKED-ON-RUNTIME` | `platform/lab-readiness/` |
| Plan scenario | `GREEN-REPO` deterministic inert Scenario Plan Composer | not an execution claim | `platform/scenario-registry/scenario_plan.py` |
| Execute bounded scenario | typed operations/tools/scenarios are registered; only gateway health is currently `READY` in the semantic tool bridge | `BLOCKED-ON-RUNTIME`; non-health controlled effects remain `PRESENT-NOT-IMPLEMENTED` | `platform/scenario-registry/tool-registry.yaml` |
| Evidence | `GREEN-REPO` Evidence Plane v2 + structured per-scenario correlation/classification/SHA-256 requirements | `BLOCKED-ON-RUNTIME` scenario evidence observation | `platform/evidence-plane/`, `platform/scenario-registry/evidence_contract.py` |
| Reset/cleanup | lifecycle/reset contracts and dry-run cleanup governance exist | `BLOCKED-ON-RUNTIME` zero-residue/known-state proof for the end-to-end run | lifecycle + resource-governance contracts |
| Aggregate gate | `GREEN-REPO`; static walking-skeleton gate precedes expensive runtime CI | not live Hermes proof | `platform/scripts/jds_static_gate.py` |

## Live runtime acceptance checkpoint

The live acceptance pass is recorded in
[`runtime-acceptance-checkpoint-2026-08-09.md`](runtime-acceptance-checkpoint-2026-08-09.md).

Current runtime state from that pass:

- **RTA-001 — `STALE_DRAIN`: `RESOLVED-RUNTIME`.** Active API work naturally
  reduced from five runs to zero and the gateway briefly remained `draining`;
  without restart, cancellation or forced admission it later returned to
  `gateway_state=running`, `active_agents=0`, `gateway_drainable=true` and
  `accepting_new_work=true`. This remains an operational lifecycle observation,
  but it is not a current blocker.
- **RTA-002 — `KALI_MCP_NOT_REGISTERED`: `BLOCKED-ON-RUNTIME`.** Two portal
  inventory observations exposed only `hermes-agent-bridge`; no Kali MCP server
  was registered/live in the portal inventory. Root cause remains unobserved.
- **RTA-003 — `APPROVAL_ID_NULL`: `BLOCKED-ON-RUNTIME`.** After admission was
  READY, the bounded read-only Kali reconciliation request was policy-gated with
  `approval_required=true`, but returned `approval_id=null` and
  `execution_id=not-created`. The request was not relabelled or retried to evade
  policy, and no inspection/mutation occurred.

## Seeded scenario status

| Scenario | Static plan | Typed effect | Runtime acceptance |
| --- | --- | --- | --- |
| `webgoat-tls-transport-review` | `PLAN_READY` | discovery operations registered; controlled effect not implemented | `BLOCKED-ON-RUNTIME` |
| `dvwa-sql-injection-screening` | `PLAN_READY` | synthetic SQLi operation registered; controlled effect not implemented | `BLOCKED-ON-RUNTIME` |
| `juice-shop-lab-lifecycle-stop` | `PLAN_READY` | lifecycle stop operation registered; controlled effect not implemented | `BLOCKED-ON-RUNTIME` |

`PLAN_READY` means the inert composer resolved the complete declared contract.
It does not mean the scenario was executed.

## Backend status

The backend registry is intentionally fail-closed:

| Backend | Repository state | Interpretation |
| --- | --- | --- |
| Docker | `SUPPORTED / READY` | shipped adapter and lifecycle bindings exist |
| Kubernetes | `DEFINED / NOT_READY` | no executable driver; fail closed |
| VM | `DEFINED / NOT_READY` | no executable driver; fail closed |
| Cloud | `DEFINED / NOT_READY` | no authorized tenant/credential/driver; fail closed |
| Remote isolated | `DEFINED / NOT_READY` | no authorized remote host/transport/evidence channel; fail closed |

No non-Docker backend is promoted merely because its type exists in the model.

## Runtime acceptance queue

These are runtime dependencies, not generic product backlog:

1. **Repair RTA-003 legitimately** — a policy-gated Hermes request must receive a
   valid `approval_id` and be handled through the normal audited approval
   status/respond path. Do not weaken policy or alter request labels to bypass
   the gate.
2. **Reconcile RTA-002 after approval works** — repeat the same bounded read-only
   Kali MCP host/container/configuration inspection through a valid approval;
   historical paths are not authority and blind registration is prohibited.
3. **Core lab acceptance** — Juice Shop and WebGoat/DVWA lifecycle/readiness must
   be observed in the live isolated environment using canonical target IDs.
4. **Kali tool functional acceptance** — WPScan writable state, Gobuster, Dirb,
   SQLMap, Hydra, John, Enum4linux and Metasploit items remain runtime-gated as
   detailed in `platform/baseline-known-issues.md`.
5. **Scenario execution/evidence/reset** — execute only bounded authorized lab
   scenarios once the typed runtime effect exists and collect correlated Evidence
   Plane records plus known-state proof.
6. **Live deployment drift** — compare deployment metadata with the actual Hermes
   host through the authorized runtime path.

## External/credential dependency

GitHub issue #53 remains open for the private read-only GHCR transition.
Production/strict consumption must retain a classic GitHub credential with
exactly `read:packages`; a broader DEV exception is not production acceptance.
This dependency does not block unrelated repository-only engineering.

## Active approval-path blocker

RTA-003 has now been reproduced live. The bounded read-only Hermes request was
rejected with:

- `approval_required=true`;
- `approval_id=null`;
- `execution_id=not-created`.

This is a real fail-closed blocker. Do not invent an approval identifier, change
trust labels to escape the policy decision, bypass policy or force execution.
The approval issuance path must be repaired through its authorized Bridge/runtime
maintenance process before the Kali root-cause inspection can continue.

## Engineering checkpoints

| Lane | PR | Merge SHA | Demonstrated outcome |
| --- | --- | --- | --- |
| K | #294 | `f18428e96a6fa4ab9873c64336258e799d91de3f` | fail-closed inert Scenario Plan Composer |
| L | #295 | `140f359f8ea72e8af0d335ab13ccafffca2f3d95` | core web readiness adapters |
| M | #296 | `2a10282780bcf5f333baf074feae614303f50abf` | structured scenario Evidence Plane contract |
| N | #297 | `da22a93f5f90938ba677cf185208af477bbab04c` | aggregate static JDS gate before runtime CI |
| O | #298 | `b71b8d4bcdb781525c08feea9dec268345a5ad3b` | baseline/roadmap reconciliation with repo/runtime proof separation |
| P | #299 | `63357eb02eb82a999aec53cf15dad1aa01dd59d0` | first live runtime checkpoint and durable blocker evidence |

Each engineering lane was merged only after its PR gates were green and the
resulting main commit was revalidated at the exact SHA.

## Decision record — repository proof vs runtime proof

**Decision:** keep repository/CI delivery state and live runtime acceptance as
separate evidence classes.

**Context:** the project now has enough static contracts to compose the walking
skeleton, while several execution effects and live Hermes/Kali observations are
still absent or runtime-gated.

**Alternatives considered:**

- treat green CI as runtime acceptance — rejected because it would create false
  assurance;
- keep all gaps as generic backlog — rejected because it hides external/runtime
  dependencies;
- explicitly classify `BLOCKED-ON-RUNTIME` — accepted.

**Risks accepted:** documentation can temporarily lag a new runtime observation;
therefore runtime acceptance must update this view after evidence is captured.

**Impact:** planning can continue repo-only without weakening authorization,
isolation or evidence requirements, and runtime work has a bounded acceptance
queue rather than an ambiguous backlog.

**State:** `DECISION`.

**Next action:** repair the legitimate approval issuance path for RTA-003. Once a
valid approval ID can be issued and audited, repeat the exact bounded read-only
Kali reconciliation to determine RTA-002 root cause. No approval or policy bypass.
