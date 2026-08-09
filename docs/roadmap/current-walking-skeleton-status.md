# Hermes Security Labs — current walking-skeleton status

**Reconciled:** 2026-08-09  
**Lane R exact-green merge baseline:**
`d0bfc2bd73f98c5f1644750804c89eae5102b31b` (Lane R / PR #301)  
**Bridge approval remediation:** `pestoura/hermes-mcp-bridge` PR #95,
main `d4fccbe135b51c41a5b668293e9c02b0db3a5147`, exact-main CI GREEN.

This is the concise current-state view of the walking skeleton. Repository/CI
proof and live Hermes runtime proof remain separate evidence classes.

## Status vocabulary

- `GREEN-REPO` — committed code/contracts are exercised by repository CI at an
  identified commit.
- `READY-REPO` — a supported repository capability exists and its shipped
  implementation is present.
- `READY-RUNTIME` — a specific live runtime condition was observed healthy.
- `RESOLVED-RUNTIME` — a previously observed live blocker was later observed
  cleared.
- `BLOCKED-ON-DEPLOY-AND-LIVE-VALIDATION` — repository remediation exists, but
  runtime closure requires proving that the repaired revision is deployed and
  behaves correctly live.
- `BLOCKED-ON-RUNTIME` — closure requires an authorized live Hermes/lab/tool
  observation.
- `BLOCKED-ON-CREDENTIAL` — a least-privilege external credential/permission is
  required and not yet accepted.
- `PRESENT-NOT-IMPLEMENTED` — a typed contract exists but the controlled effect
  is not implemented/accepted.
- `DEFINED-NOT-READY` — architecture/registry modelling exists but execution
  must fail closed.

## Walking skeleton

Target delivery path:

`authorize -> provision -> readiness -> execute bounded scenario -> evidence -> reset -> known-state proof`

| Stage | Repository/CI state | Live runtime state | Canonical source |
| --- | --- | --- | --- |
| Authorize | `GREEN-REPO` target registry + deny-before-dispatch boundary; Bridge approval handoff repaired repo-side | RTA-003 requires deployment/live revalidation | `platform/targets/` + Hermes policy/approval path |
| Admission | repository-independent live gate | last observation was `READY-RUNTIME`: gateway recovered naturally to `running`, zero active API runs/agents and `accepting_new_work=true` | Hermes health/readiness |
| Provision | Docker `READY-REPO` | `BLOCKED-ON-RUNTIME`; Kali MCP absent from last portal inventory | backend registry + live Hermes inventory |
| Readiness | `GREEN-REPO` manifests and adapters for WebGoat/WebWolf, DVWA and Juice Shop | `BLOCKED-ON-RUNTIME` | `platform/lab-readiness/` |
| Plan scenario | `GREEN-REPO` deterministic inert Scenario Plan Composer | not an execution claim | `platform/scenario-registry/scenario_plan.py` |
| Execute bounded scenario | typed operations/tools/scenarios registered | `BLOCKED-ON-RUNTIME`; non-health controlled effects remain `PRESENT-NOT-IMPLEMENTED` | `platform/scenario-registry/tool-registry.yaml` |
| Evidence | `GREEN-REPO` Evidence Plane v2 + structured scenario requirements | `BLOCKED-ON-RUNTIME` scenario evidence observation | `platform/evidence-plane/` + evidence contract |
| Reset/cleanup | lifecycle/reset contracts + dry-run cleanup governance exist | `BLOCKED-ON-RUNTIME` zero-residue/known-state proof | lifecycle/resource-governance contracts |
| Aggregate gate | `GREEN-REPO`; static JDS gate precedes expensive runtime CI | not live Hermes proof | `platform/scripts/jds_static_gate.py` |

## Runtime acceptance evidence

The original live pass remains immutable in
[`runtime-acceptance-checkpoint-2026-08-09.md`](runtime-acceptance-checkpoint-2026-08-09.md).
The subsequent Bridge repository remediation is recorded in
[`runtime-approval-remediation-2026-08-09.md`](runtime-approval-remediation-2026-08-09.md).

Current state:

- **RTA-001 — `STALE_DRAIN`: `RESOLVED-RUNTIME`.** Active API work reached zero;
  the gateway temporarily remained draining and then recovered naturally,
  without restart/cancellation/forced admission, to `running` and accepting new
  work.
- **RTA-002 — `KALI_MCP_NOT_REGISTERED`: `BLOCKED-ON-RUNTIME`.** Two live portal
  inventory observations exposed only `hermes-agent-bridge`. Kali MCP root cause
  is still unobserved; blind registration remains prohibited.
- **RTA-003 — `APPROVAL_ID_NULL`: `REPO-FIX-MERGED /
  BLOCKED-ON-DEPLOY-AND-LIVE-VALIDATION`.** The live request originally returned
  `approval_required=true`, `approval_id=null` and `execution_id=not-created`.
  Bridge PR #95 repaired the prompt/submit approval handoff and exact Bridge main
  `d4fccbe135b51c41a5b668293e9c02b0db3a5147` passed Python 3.11/3.12, image,
  isolated acceptance, Trivy and SBOM gates. The live Hermes connector has not
  yet been revalidated against that repaired revision.

## RTA-003 root cause and remediation boundary

Repository inspection established two separate facts:

1. `authorized-local-lab`, used by the original runtime request, is not a valid
   Hermes MCP Bridge `TrustLabel`. Invalid values map fail-closed to
   `untrusted_content`, which legitimately caused the production policy to
   require approval.
2. The V1 prompt/submit policy path did not previously create/return the bound
   approval record when `REQUIRE_APPROVAL` was returned, producing the observed
   null approval identifier.

The fix addresses item 2 without weakening item 1. Required approvals are now
bound to the exact logical request, return a non-null identifier, persist no raw
prompt, are consumed against the request fingerprint, and cannot be replayed for
changed prompt/scope/trust/action values. The public V1 27-tool contract remains
unchanged.

The original invalid trust label must not be changed merely as an approval
escape mechanism. Future live requests must use contract-valid metadata for the
actual trust provenance and still obey whatever policy decision results.

## Seeded scenario status

| Scenario | Static plan | Typed effect | Runtime acceptance |
| --- | --- | --- | --- |
| `webgoat-tls-transport-review` | `PLAN_READY` | discovery operations registered; controlled effect not accepted | `BLOCKED-ON-RUNTIME` |
| `dvwa-sql-injection-screening` | `PLAN_READY` | synthetic SQLi operation registered; controlled effect not accepted | `BLOCKED-ON-RUNTIME` |
| `juice-shop-lab-lifecycle-stop` | `PLAN_READY` | lifecycle stop operation registered; controlled effect not accepted | `BLOCKED-ON-RUNTIME` |

`PLAN_READY` proves deterministic contract resolution only; it is not runtime
execution evidence.

## Backend status

| Backend | Repository state | Interpretation |
| --- | --- | --- |
| Docker | `SUPPORTED / READY` | shipped adapter and lifecycle bindings exist |
| Kubernetes | `DEFINED / NOT_READY` | no executable driver; fail closed |
| VM | `DEFINED / NOT_READY` | no executable driver; fail closed |
| Cloud | `DEFINED / NOT_READY` | no authorized tenant/credential/driver; fail closed |
| Remote isolated | `DEFINED / NOT_READY` | no authorized remote host/transport/evidence channel; fail closed |

No non-Docker backend is promoted because its type exists in the model.

## Runtime acceptance queue

When the Hermes MCP connector is again available, continue automatically on
GREEN/PASS in this order:

1. validate Bridge live revision, `hermes_health`, `hermes_readiness` and
   `accepting_new_work=true`;
2. repeat the bounded read-only runtime reconciliation with a stable
   `client_request_id` and contract-valid trust metadata;
3. if policy requires approval, require a non-null `approval_id`, use the normal
   audited approval response path and retry the exact request;
4. reconcile Kali MCP/container/configuration read-only and resolve RTA-002 only
   from observed state;
5. perform core lab provision/readiness acceptance with canonical target IDs;
6. validate remaining Kali tool functional items from
   `platform/baseline-known-issues.md`;
7. execute only an explicitly authorized bounded seeded scenario once typed
   runtime effects are accepted;
8. capture correlated Evidence Plane records, reset and prove known state.

No offensive action is authorized by the repository remediation itself.

## External/credential dependency

GitHub issue #53 remains open for the private read-only GHCR transition.
Production/strict consumption requires a classic GitHub credential with exactly
`read:packages`; a broader DEV exception is not production acceptance. This does
not block unrelated repository engineering.

## Engineering checkpoints

| Lane | PR | Merge SHA | Demonstrated outcome |
| --- | --- | --- | --- |
| K | #294 | `f18428e96a6fa4ab9873c64336258e799d91de3f` | fail-closed inert Scenario Plan Composer |
| L | #295 | `140f359f8ea72e8af0d335ab13ccafffca2f3d95` | core web readiness adapters |
| M | #296 | `2a10282780bcf5f333baf074feae614303f50abf` | structured Scenario/Evidence Plane contract |
| N | #297 | `da22a93f5f90938ba677cf185208af477bbab04c` | aggregate static JDS gate before runtime CI |
| O | #298 | `b71b8d4bcdb781525c08feea9dec268345a5ad3b` | repo/runtime proof reconciliation |
| P | #299 | `63357eb02eb82a999aec53cf15dad1aa01dd59d0` | first live runtime checkpoint |
| Q | #300 | `0ee16ffc74e0053cfe9b9a734d9269049276bf1f` | stale-drain recovery + approval blocker reconciliation |
| R | #301 | `d0bfc2bd73f98c5f1644750804c89eae5102b31b` | Bridge approval remediation reconciliation; runtime proof intentionally remains pending |

## Decision record — repository repair is not runtime closure

**Decision:** classify the Bridge fix as `GREEN-REPO` while keeping RTA-003 open
until the repaired revision is observed live.

**Context:** exact-main Bridge CI now proves the request-bound approval state
machine and packaged image gates, but cannot prove which revision the live
Hermes connector currently serves.

**Alternatives considered:**

- close RTA-003 from CI alone — rejected as false runtime assurance;
- alter trust labels to obtain a permissive decision — rejected as a policy
  bypass pattern;
- preserve fail-closed policy and validate the repaired approval path live —
  accepted.

**Risks accepted:** deployment drift can still exist between Bridge main and the
live Hermes connector.

**Impact:** repository engineering can remain GREEN without misrepresenting live
acceptance, and the next runtime work is a bounded evidence-driven chain.

**State:** `DECISION`.
