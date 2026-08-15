# Live promotion evidence package — phased, candidate-bound evidence aggregation

`runtime_live_promotion_evidence.py` defines the machine-verifiable aggregation boundary between individual runtime observations and the existing Human-in-the-Loop/campaign acceptance process.

It does not collect evidence, update the validation campaign, activate policies or authorize execution.

## Why this exists

The canonical `runtime_promotion_evidence_gate.py` proves repository readiness and reads the accepted state of the validation campaign. Individual runtime verifiers prove specific facts such as host identity, user-namespace mapping, signer state or backend controls.

The live evidence package binds those individual result artefacts to the exact WebGoat L1 candidate before human review without turning machine evidence into approval.

## Assurance-profile resolution

Gate composition is derived from the accepted ADR-0011 Option B assurance profile:

```text
platform/assurance/current-assurance-profile.yaml
```

The declaration is validated through the canonical `platform/assurance/assurance_profile.py` contract.

Fail-closed rules:

- an absent, invalid, unparsable or internally inconsistent profile resolves to `PROD`;
- `LAB_L1` may omit **only** the external production WORM/durable-backend gate and the production tenant-isolation gate;
- signer/trust, `SO_PEERCRED` negative proof, audit, tamper-evident/hash-chained evidence, PRE/POST packages, reset and request-bound HITL are never relaxed for `LAB_L1`;
- `PROD` retains every production gate;
- `promotion_allowed=false` for every profile and package state.

## Two phases

### `PRE_PROMOTION`

Required under both `LAB_L1` and `PROD`:

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
| `EVIDENCE_BACKEND_CONTROLS` | `requires_external_worm_backend` | optional / not required | mandatory |
| `EVIDENCE_TENANT_ISOLATION` | `requires_tenant_isolation` | optional / not required | mandatory |

Under `LAB_L1`, those two PROD-only gates may be absent. For backward evidence compatibility, a LAB_L1 package may also keep either or both gates:

- `NOT_RUN` on an optional gate does **not** block LAB_L1 completion;
- an executed `PASS` is independently evidence-verified and can only strengthen the package;
- an executed `FAIL` blocks completion;
- an unverified executed optional gate also blocks completion;
- under `PROD`, both gates are mandatory and `NOT_RUN` blocks completion.

This preserves previously assembled LAB_L1 packages without turning a PROD-only missing control into an L1 blocker.

When the resolved profile sets `requires_hash_chain: true`, the canonical `HASH_CHAIN_SEAL` gate is also mandatory. Under the current accepted ADR-0011 declaration this is true for both `LAB_L1` and `PROD`.

A complete PRE_PROMOTION package means every gate mandatory for the resolved profile is `PASS`, all executed evidence references and SHA-256 digests have been independently verified, and the package is bound to the exact candidate commit recorded in `VAL-HSL-RUNNER-L1-LIVE-PROMOTION`.

The only next state exposed by the verifier is:

```text
HUMAN_PROMOTION_REVIEW_REQUIRED
```

It never returns promotion authority.

### `POST_EFFECT`

The POST_EFFECT gate set is profile-invariant:

- `HITL_PROMOTION_DECISION`;
- `PROMOTED_POLICY_SET`;
- `LIVE_RUNNER_OUTCOME_PERSISTENCE`;
- `LIVE_DISPATCH_AUDIT_PERSISTENCE`;
- `WEBGOAT_L1_EFFECT_RESET`;
- `HASH_CHAIN_SEAL` when the profile requires hash-chain integrity.

A complete POST_EFFECT package binds the explicit promotion decision, the effective minimum policy set, terminal/audit persistence and the one bounded effect/reset acceptance to the same candidate evidence chain.

The only next state exposed by the verifier is:

```text
CAMPAIGN_ACCEPTANCE_REVIEW_REQUIRED
```

The validation campaign remains the canonical accepted-state source of truth.

## `HASH_CHAIN_SEAL` — wired integrity gate

The frozen Evidence Plane hash-chain/seal primitive is actively wired into gate composition through:

```text
platform/evidence-plane/seal.py
platform/schemas/evidence-chain.schema.json
```

For an executed `HASH_CHAIN_SEAL` gate the verifier requires:

1. a schema-valid evidence-chain document;
2. successful verification by the real `verify_seal` primitive;
3. exact binding between the gate's `evidence_sha256` and the verified `chain_state_digest_sha256`.

Missing documents, tampered entries, tampered seal state or digest-binding mismatches fail closed.

This proves integrity/tamper evidence only. It does not claim external WORM durability, signer authenticity or production tenant isolation.

## Evidence references

Executed gates (`PASS` or `FAIL`) must contain:

- observation timestamp;
- canonical `evidence://...` reference;
- SHA-256 digest of the referenced result artefact.

Required `NOT_RUN` gates contain none of those values and block completion. Optional LAB_L1 PROD-only gates may also be `NOT_RUN`, but do not become blockers merely because the production-only control is absent.

A referenced artefact is not trusted because a package says it exists. The verifier calls an injected `EvidenceVerifier`; the default implementation denies every delegated reference.

A self-authored package with required gates marked `PASS` therefore remains incomplete until the referenced evidence is independently verified. `HASH_CHAIN_SEAL` is self-verified by its frozen primitive rather than by the delegated verifier.

A verified `FAIL` is valid evidence but still blocks package completion.

## Candidate binding

An `ASSEMBLED` package must match:

- environment `webgoat`;
- adapter `webgoat-l1`;
- capability `web.discovery.headers`;
- level `L1`;
- the exact 40-character repository commit recorded as the candidate in `VAL-HSL-RUNNER-L1-LIVE-PROMOTION`.

This prevents evidence from one candidate being silently reused for another.

The committed example is deliberately `NOT_RUN` and uses a zero commit because it is a schema/example artefact, not promotion evidence. It may retain the two PROD-only PRE gates as optional `NOT_RUN` fields for backward compatibility.

## Offline assembler compatibility

`offline_evidence_package_assembler.py` may emit the historical PRE_PROMOTION superset containing both PROD-only gates. Under `LAB_L1` those optional `NOT_RUN` gates are accepted without becoming blockers. This preserves existing package shape and evidence tooling while the canonical verifier remains the authority for the profile-resolved mandatory subset.

New code that needs the true profile requirement set should use `profile_required_gate_ids(...)`; the legacy `required_gate_ids(...)` projection remains the accepted historical superset for compatibility with already-assembled packages and callers.

## Operational use

The committed example must remain incomplete:

```bash
python3 deployment/runtime-promotion/runtime_live_promotion_evidence.py \
  --package deployment/runtime-promotion/templates/live-promotion-evidence-package.example.yaml \
  --json check
```

A real package is assembled outside the repository from custodied runtime result artefacts. The orchestration layer must inject an Evidence Plane-backed verifier for delegated evidence before a package can become complete.

Real evidence packages should not be committed to source control.

## Fail-closed properties

- canonical ADR-0011 profile validation drives the mandatory gate subset;
- absent/invalid/inconsistent profile -> `PROD`;
- `PROD` always requires external WORM/durable-backend and tenant-isolation gates;
- `LAB_L1` omits only those two from its mandatory subset;
- optional LAB_L1 PROD gates may be absent or `NOT_RUN`, but supplied `FAIL`/unverified evidence blocks;
- required gates cannot be omitted;
- undeclared extra gates are rejected;
- duplicate gates are rejected;
- a `NOT_RUN` package cannot contain executed gates;
- an assembled package must match the exact campaign candidate commit;
- every executed delegated gate requires independently verified referenced evidence;
- `HASH_CHAIN_SEAL` requires a real verified seal and digest binding;
- any required `FAIL`, `NOT_RUN` or unverified evidence blocks completion;
- PRE_PROMOTION completion only requests human review;
- POST_EFFECT completion only requests campaign acceptance review;
- `promotion_allowed=false` always;
- recommendation remains `HOLD` always;
- no policy or campaign mutation exists in this module;
- no network, provider client, subprocess or target execution path exists.

## Non-claims

A complete PRE_PROMOTION package does not mean promotion was approved.

A complete POST_EFFECT package does not automatically close the campaign.

Neither package phase grants authorization, changes policy, proves anything not represented by verified evidence, or replaces the explicit Human-in-the-Loop decision.

`NO_RUNTIME_CHANGE`.
