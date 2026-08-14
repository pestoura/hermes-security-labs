# Live promotion evidence package — phased, candidate-bound evidence aggregation

`runtime_live_promotion_evidence.py` defines the machine-verifiable aggregation boundary between individual runtime observations and the existing Human-in-the-Loop/campaign acceptance process.

It does not collect evidence, update the validation campaign, activate policies or authorize execution.

## Why this exists

The canonical `runtime_promotion_evidence_gate.py` proves repository readiness and reads the accepted state of the validation campaign. Individual runtime verifiers prove specific facts such as host identity, user-namespace mapping, signer state or backend controls.

Before this contract there was no canonical artefact binding those individual result artefacts to the exact WebGoat L1 candidate before human review.

The live evidence package fills that gap without turning machine evidence into approval.

## Two phases

### `PRE_PROMOTION`

The required gate set is composed from the accepted assurance profile
(`platform/assurance/current-assurance-profile.yaml`, ADR-0011 Option B), resolved through
`platform/assurance/assurance_profile.py`. It is never hardcoded per phase.

Required under every profile (PROD baseline, never relaxed):

- `GATEWAY_ADMISSION_REOBSERVATION`;
- `BRIDGE_REVISION_REOBSERVATION`;
- `HOST_IDENTITY_SOCKET_TRUST`;
- `USER_NAMESPACE_MAPPING`;
- `SIGNER_PROVIDER_ATTESTATION`;
- `RECEIPT_DELIVERY`;
- `UNAUTHORIZED_PEER_NEGATIVE`.

Profile-conditional gates:

| Gate | Assurance requirement key | `LAB_L1` | `PROD` |
| --- | --- | --- | --- |
| `EVIDENCE_BACKEND_CONTROLS` | `requires_external_worm_backend` | not required | mandatory |
| `EVIDENCE_TENANT_ISOLATION` | `requires_tenant_isolation` | not required | mandatory |

Under `LAB_L1` those two gates are omissible only. They are still accepted as inputs: when
present and executed they are integrity-verified like any other gate, and a `FAIL` still
blocks completion. They can only tighten the outcome, never relax it.

An absent, invalid or unparsable profile declaration resolves to `PROD` (fail-closed), so a
broken profile document can never remove a required gate.

A complete PRE_PROMOTION package means the referenced evidence artefacts required by the
resolved profile are all `PASS`, their `evidence://` references and SHA-256 digests have been
independently verified, and the package is bound to the exact candidate commit currently
recorded in the canonical validation campaign.

The only next state exposed by the verifier is:

`HUMAN_PROMOTION_REVIEW_REQUIRED`

It never returns promotion authority.

### `POST_EFFECT`

The required gate set is profile-invariant (no POST_EFFECT gate is omissible under `LAB_L1`):

- `HITL_PROMOTION_DECISION`;
- `PROMOTED_POLICY_SET`;
- `LIVE_RUNNER_OUTCOME_PERSISTENCE`;
- `LIVE_DISPATCH_AUDIT_PERSISTENCE`;
- `WEBGOAT_L1_EFFECT_RESET`.

A complete POST_EFFECT package binds the explicit promotion decision, the effective minimum policy set, terminal/audit persistence and the one bounded effect/reset acceptance to the same candidate evidence chain.

The only next state exposed by the verifier is:

`CAMPAIGN_ACCEPTANCE_REVIEW_REQUIRED`

The validation campaign remains the canonical accepted-state source of truth.

## Evidence references

Executed gates (`PASS` or `FAIL`) must contain:

- observation timestamp;
- `evidence://...` reference;
- SHA-256 digest of the referenced result artefact.

`NOT_RUN` gates must contain none of those values.

A referenced artefact is not trusted because a package says it exists. The verifier calls an injected `EvidenceVerifier`. The default implementation denies every reference.

This means a self-authored YAML package with all gates marked `PASS` still fails until the evidence custody backend verifies every referenced artefact.

A verified `FAIL` is valid evidence but still blocks package completion.

## Candidate binding

An `ASSEMBLED` package must match:

- environment `webgoat`;
- adapter `webgoat-l1`;
- capability `web.discovery.headers`;
- level `L1`;
- the exact 40-character repository commit recorded as the candidate in `VAL-HSL-RUNNER-L1-LIVE-PROMOTION`.

This prevents evidence from one candidate being silently reused for another.

The committed example is deliberately `NOT_RUN` and uses a zero commit because it is a schema/example artefact, not promotion evidence.

## Operational use

The committed example must fail the CLI completion check:

```bash
python3 deployment/runtime-promotion/runtime_live_promotion_evidence.py \
  --package deployment/runtime-promotion/templates/live-promotion-evidence-package.example.yaml \
  --json check
```

A real package should be assembled outside the repository from custodied runtime result artefacts. The orchestration layer must inject an Evidence Plane-backed `EvidenceVerifier` before a package can become complete.

Real evidence packages should not be committed to source control.

## Fail-closed properties

- gate composition is resolved from the accepted assurance profile; an absent/invalid profile
  resolves to `PROD` and therefore to the strictest gate set;
- `PROD` always requires the external WORM/durable evidence-backend and tenant-isolation gates;
- `LAB_L1` omits only those two, and a present-but-failing omitted gate still blocks;
- required gates are exact; missing required gates or undeclared extra gates are rejected;
- duplicate gates are rejected;
- a `NOT_RUN` package cannot contain an executed gate;
- an assembled package must match the exact campaign candidate commit;
- every executed gate requires independently verified referenced evidence;
- any `FAIL`, `NOT_RUN` or unverified reference blocks completion;
- PRE_PROMOTION completion only requests human review;
- POST_EFFECT completion only requests campaign acceptance review;
- `promotion_allowed=false` always;
- recommendation remains `HOLD` always;
- no policy or campaign mutation exists in this module;
- no network, provider client, subprocess or target execution path exists.

## Phase 2 — evidence hash-chain seal (NOT wired)

The frozen evidence hash-chain seal interface (`platform/evidence-plane/seal.py`) is
deliberately **not** wired into gate composition in this phase. Wiring it would change the
exact gate set of already-accepted `LAB_L1`/`PROD` packages, so it must land as its own
deliberate change with its own change record.

The deterministic hook is declared and tested as inert:

- `PHASE2_SEAL_GATE_HOOK = "EVIDENCE_HASH_CHAIN_SEAL"`;
- `PHASE2_SEAL_GATE_REQUIREMENT_KEY = "requires_hash_chain"`;
- `PHASE2_SEAL_GATE_ENABLED = False`.

`test_phase2_seal_gate_hook_is_declared_but_not_wired` asserts the hook appears in no resolved
gate set for either profile or phase.

## Non-claims

A complete PRE_PROMOTION package does not mean promotion was approved.

A complete POST_EFFECT package does not automatically close the campaign.

Neither package phase grants authorization, changes policy, proves anything not represented by a verified result artefact, or replaces the explicit Human-in-the-Loop decision.

`NO_RUNTIME_CHANGE`.
