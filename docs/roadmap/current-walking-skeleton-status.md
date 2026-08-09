# Hermes Security Labs — current walking-skeleton status

**Reconciled:** 2026-08-09  
**Exact-green engineering baseline used for this reconciliation:**
`da22a93f5f90938ba677cf185208af477bbab04c` (Lane N / PR #297)

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
| Authorize | `GREEN-REPO` — target registry and deny-before-dispatch boundary | requires live authorized target/window | `platform/targets/` |
| Provision | `READY-REPO` for Docker backend | live lab provisioning acceptance pending | `platform/backends/backend-registry.yaml` |
| Readiness | `GREEN-REPO` manifests + adapters; core adapters added for WebGoat/WebWolf, DVWA and Juice Shop | `BLOCKED-ON-RUNTIME` | `platform/lab-readiness/` |
| Plan scenario | `GREEN-REPO` deterministic inert Scenario Plan Composer | not an execution claim | `platform/scenario-registry/scenario_plan.py` |
| Execute bounded scenario | typed operations/tools/scenarios are registered; only gateway health is currently `READY` in the semantic tool bridge | `BLOCKED-ON-RUNTIME`; non-health controlled effects remain `PRESENT-NOT-IMPLEMENTED` | `platform/scenario-registry/tool-registry.yaml` |
| Evidence | `GREEN-REPO` Evidence Plane v2 + structured per-scenario correlation/classification/SHA-256 requirements | `BLOCKED-ON-RUNTIME` scenario evidence observation | `platform/evidence-plane/`, `platform/scenario-registry/evidence_contract.py` |
| Reset/cleanup | lifecycle/reset contracts and dry-run cleanup governance exist | `BLOCKED-ON-RUNTIME` zero-residue/known-state proof for the end-to-end run | lifecycle + resource-governance contracts |
| Aggregate gate | `GREEN-REPO`; static walking-skeleton gate precedes expensive runtime CI | not live Hermes proof | `platform/scripts/jds_static_gate.py` |

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

1. **Kali MCP runtime registration and health** — re-discover the actual Hermes
   registration and live Kali container state; do not rely on historical state.
2. **Core lab acceptance** — Juice Shop and WebGoat/DVWA lifecycle/readiness must
   be observed in the live isolated environment using canonical target IDs.
3. **Kali tool functional acceptance** — WPScan writable state, Gobuster, Dirb,
   SQLMap, Hydra, John, Enum4linux and Metasploit items remain runtime-gated as
   detailed in `platform/baseline-known-issues.md`.
4. **Scenario execution/evidence/reset** — execute only bounded authorized lab
   scenarios once the typed runtime effect exists and collect correlated Evidence
   Plane records plus known-state proof.
5. **Live deployment drift** — compare deployment metadata with the actual Hermes
   host through the authorized runtime path.

## External/credential dependency

GitHub issue #53 remains open for the private read-only GHCR transition.
Production/strict consumption must retain a classic GitHub credential with
exactly `read:packages`; a broader DEV exception is not production acceptance.
This dependency does not block unrelated repository-only engineering.

## Known approval-path blocker

A historical Hermes upstream failure mode can return:

`waiting_for_approval` with `approval_id = null`

If reproduced during runtime acceptance, classify it as a real runtime blocker.
Do not invent an approval identifier, bypass policy or force execution. Preserve
state and continue only with independent safe work.

## Engineering checkpoints

| Lane | PR | Merge SHA | Demonstrated outcome |
| --- | --- | --- | --- |
| K | #294 | `f18428e96a6fa4ab9873c64336258e799d91de3f` | fail-closed inert Scenario Plan Composer |
| L | #295 | `140f359f8ea72e8af0d335ab13ccafffca2f3d95` | core web readiness adapters |
| M | #296 | `2a10282780bcf5f333baf074feae614303f50abf` | structured scenario Evidence Plane contract |
| N | #297 | `da22a93f5f90938ba677cf185208af477bbab04c` | aggregate static JDS gate before runtime CI |

Each lane was merged only after its PR gates were green and the resulting main
commit was revalidated at the exact SHA.

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

**Next action:** after this reconciliation is green on `main`, resume live
runtime acceptance through Hermes MCP, starting with safe health/discovery and
without bypassing the approval path.
