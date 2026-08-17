# ADR-0017 — First PTaaS vertical-slice composition

- **Status:** Proposed
- **Date:** 2026-08-17
- **Decision owners:** Hermes Security Labs architecture / assurance
- **Related change:** CHG-HSL-083
- **Supersedes:** none
- **Superseded by:** none

> **Em validação / EM_VALIDACAO — non-final, non-operative.** This record changes no policy, template, gate, schema, runtime state or campaign observation. `VAL-HSL-RUNNER-L1-LIVE-PROMOTION` remains `BLOCKED / HOLD` with `promotion_allowed: false`, `runtime_status: NOT_RUN`, `execution_authority: none`, `supplier_selection: NO_SELECTION` and `trust-store: ABSENT`. No production code accompanies this record.

## Context

The delivery operating model defines the walking skeleton for a lab capability as `define/authorize target → provision → readiness → execute bounded scenario/tool → collect evidence → reset/cleanup → verify known state` ([delivery operating model](../../delivery-operating-model.md)).

Every stage already has an accepted repository component:

| Stage | Existing component |
| --- | --- |
| Campaign scope, intrusiveness ceiling, kill switch | [`platform/roe-contract/`](../../../platform/roe-contract/) (`roe_contract.py`, `kill_switch.py`, `campaign_kill_switch_transition.py`) |
| Target authorization from a registry `target_id` | [`platform/targets/execution_authorization.py`](../../../platform/targets/execution_authorization.py), [`target-registry.yaml`](../../../platform/targets/target-registry.yaml) |
| Deterministic plan composition (dry-run only) | [`platform/scenario-registry/scenario_plan.py`](../../../platform/scenario-registry/scenario_plan.py), [`tool-registry.yaml`](../../../platform/scenario-registry/tool-registry.yaml) |
| Typed operation admission and handoff | [`platform/gateway-protocol/`](../../../platform/gateway-protocol/) (`admission.py`, `gateway_protocol.py`, `runner_handoff.py`, `operation-registry.yaml`) |
| TB1 authorization issuance, delivery, verification | [`platform/authorization-contract/`](../../../platform/authorization-contract/), [`platform/runner-authorization/`](../../../platform/runner-authorization/) |
| Runner dispatch and target-bound adapter | [`platform/runner-dispatch/router.py`](../../../platform/runner-dispatch/router.py), [`platform/runner-adapters/`](../../../platform/runner-adapters/) |
| Controlled tool-path candidate effect | [`platform/gateway-protocol/controlled_runtime_candidate.py`](../../../platform/gateway-protocol/controlled_runtime_candidate.py) |
| Evidence custody, chain, seal, verification | [`platform/evidence-plane/`](../../../platform/evidence-plane/) |
| Normalized finding and risk state machine | [`platform/risk-findings/`](../../../platform/risk-findings/) |
| Profile-conditional gate composition and HITL requirement | [`platform/assurance/assurance_profile.py`](../../../platform/assurance/assurance_profile.py), [`current-assurance-profile.yaml`](../../../platform/assurance/current-assurance-profile.yaml) |
| Lifecycle, readiness, reset and zero-residue proof | [`platform/lab-lifecycle/`](../../../platform/lab-lifecycle/) |

What does not exist is a single declared composition that traverses those components once, for one campaign, and states which terminal campaign state and which evidence set constitute an auditable end of that traversal. Each component is individually accepted and individually inert; nothing describes the seam order, the failure precedence between seams, or the minimum evidence tuple that makes one traversal reviewable.

The absence is a design absence, not a capability absence. Choosing the composition shape before writing code determines whether the slice reuses accepted contracts or grows a parallel orchestrator, and it determines whether Vault/Bridge remain supporting dependencies or become the lane.

## Decision

No decision is taken by this record. It is a proposal in validation; the composition option below is a recommendation only, and no policy, gate, schema or campaign value changes as a consequence of merging it.

### Option comparison

#### Option A — new campaign orchestrator module

A new module (for example `platform/campaign-slice/slice_orchestrator.py`) owns the traversal: it resolves scope, authorizes the target, admits the operation, dispatches, collects evidence, normalizes the finding and computes the terminal state.

- Positive: one readable entry point; the seam order is explicit in one file; easiest to test as a unit.
- Negative: introduces a new authority-shaped component at the exact layer where authority must not accumulate; duplicates admission/authorization/evidence sequencing that `service_composition.py`, `admission.py` and `runtime_promotion_evidence_gate.py` already own; a bug in the orchestrator can silently diverge from the components it shadows; largest new-component count.

#### Option B — extend the existing Runner service composition

`platform/runner-service/service_composition.py` already composes transport identity, routing, audit and adapter binding fail-closed for one accepted peer. Option B widens it to also carry ROE scope, target authorization, evidence custody, finding normalization and terminal-state computation.

- Positive: no new module; reuses an accepted composition seam.
- Negative: overloads a component whose current contract is deliberately narrow (one accepted AF_UNIX peer, pre-effect refusal codes); couples campaign-level semantics to a peer-level boundary; makes the fail-closed refusal code space ambiguous between transport refusals and campaign refusals; the widened module becomes hard to keep `NOT_RUN`-inert.

#### Option C — declarative slice contract plus a thin read-only traversal binder

A committed slice contract (schema + YAML) names, for exactly one LAB_L1 campaign: the authorized `target_id`, the single non-destructive operation, the required evidence tuple, the required normalized finding shape, the terminal campaign state and the HITL requirement resolved from the assurance profile. A thin binder resolves that contract against the already-accepted components, verifies each seam's precondition and emits a deterministic traversal record. The binder holds no authority: it resolves, verifies and refuses; every effect, authorization decision, custody write and state transition stays owned by the existing component.

- Positive: minimal new surface (one schema, one YAML, one resolver); every authority stays where it is already accepted; the traversal is reviewable as data before any effect exists; matches the accepted precedent of `scenario_plan.py` (deterministic dry-run composition) and of the CHG-HSL-054/056 adapter/bridge lanes (thin resolvers over frozen contracts); the slice can be validated as a plan while every policy is still `DISABLED`.
- Negative: the traversal is described in two places (contract data plus resolver code) and must be kept consistent by tests; a declarative contract can drift from a component's real precondition set unless each seam is asserted; requires care so the contract does not become a second authorization surface.

### Recommendation (proposal only)

Option C is recommended: it maximizes reuse of accepted components, adds the fewest new components, and keeps the slice reviewable as data before any effect is possible. Option A is rejected because it creates a new authority-shaped orchestrator; Option B is rejected because it dilutes a deliberately narrow peer-level boundary.

The recommendation binds nothing. Implementation requires a separate, evidence-bearing change record and explicit owner approval.

## Consequences

### Positive

- The end-to-end intent becomes explicit and reviewable before implementation.
- Authority remains distributed across already-accepted components instead of concentrating in a new orchestrator.
- The minimum evidence tuple and the terminal-state definition become testable statements rather than implicit expectations.
- Vault, the Hermes MCP Bridge, signer custody and trust-store installation stay outside the slice's critical path as supporting dependencies.

### Negative

- A declarative contract plus a resolver requires seam-by-seam tests to prevent drift between declared and real preconditions.
- One more schema and one more YAML enter the governed contract inventory and must be owned.
- Describing a traversal that cannot yet run leaves a documented gap between declared intent and live proof until a separate change provides live evidence.
- Any later decision to allow a second operation or a second target in the same slice will require re-review of this composition.

## Security implications

- The slice contract is a scope declaration, never an authorization. Reachability, presence in the contract and repository acceptance all remain non-authoritative; `target_id` resolution through the canonical registry plus verified TB1 authorization remain the only execution authority.
- The single declared operation must be non-destructive and inside the target's declared scope, at intrusiveness `L1` or lower. Generic execution, shell, argv, credentials, secrets, tokens, cookies, redirect following and arbitrary locator input remain forbidden.
- No broad scanning: exactly one allowlisted target and one operation per slice traversal.
- No persistence beyond the evidence custody the Evidence Plane already governs; no credential use and no real secret material at any seam.
- HITL is included only where the resolved assurance profile already requires it (`requires_request_bound_hitl: true` under LAB_L1). The slice adds no new approval surface and grants no promotion authority.
- Findings are sanitized: digests and stable reason codes only, never raw payloads, raw locators or signature material.
- Failure precedence is fail-closed and refusal is terminal for the traversal; an unverifiable evidence write or an unavailable audit path must refuse rather than proceed.

## Alternatives considered

The three options above are the alternatives considered; Option A (new orchestrator) and Option B (widened Runner service composition) are documented as rejected in favour of the Option C recommendation. No further alternative was evaluated, and no supplier, provider or backend is selected by this record.

## Evidence and validation

- Repository evidence only. This record is documentation; no test, gate, policy or campaign value changes.
- Component inventory in the Context table was read from the repository tree at `c63fee752bfd28868da54eb9650943e2b504f659`.
- Companion design and specification: [First PTaaS vertical slice — design and specification](../first-ptaas-vertical-slice.md).
- Change record: `changes/CHG-HSL-083.yaml`, classification `DOC_ONLY`.
- No blocker is closed. `#403` (signer custody class), `#53`, and every open live-promotion blocker remain open.

## Review triggers

- An owner approves implementation of the recommended composition, requiring a new evidence-bearing change record.
- A second target, a second operation or a destructive operation is proposed for the same slice.
- The resolved assurance profile changes, altering the HITL or gate requirement set.
- Any existing component named in the Context table changes its precondition, refusal-code space or evidence contract.
- Live evidence contradicts a declared seam precondition.
