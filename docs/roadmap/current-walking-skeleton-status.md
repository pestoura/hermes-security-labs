# Hermes Security Labs — current walking-skeleton status

**Reconciled:** 2026-08-14 22:00 UTC  
**Current Labs baseline:** `a63ef01925e5c1b925936c1e73b11b2d6cd2a6a5`  
**Accepted/live Hermes MCP Bridge revision:** `3717bd5469b061a44294b27e1a7510d477d3752b`  
**Safe live read-only reobservation:** `run_ec368a4ccc04419e985b1c4d01e0ddea` (CHG-HSL-053)

This is the concise current-state view of the walking skeleton. Repository/CI proof and live Hermes runtime proof are separate evidence classes. Historical evidence remains in [`runtime-acceptance-checkpoint-2026-08-09.md`](runtime-acceptance-checkpoint-2026-08-09.md); the governed Runner promotion campaign is [`../../validation/VAL-HSL-RUNNER-L1-LIVE-PROMOTION.yaml`](../../validation/VAL-HSL-RUNNER-L1-LIVE-PROMOTION.yaml).

> **GREEN-REPO is not live acceptance.** It means the contract/code exists and passed repository gates. It does not grant execution authority, activate a policy, prove host deployment or prove target interaction.

> **The commit SHA is reconciliation provenance, not a runtime authority.** The value above is the exact authoritative `origin/main` at the time of the CHG-HSL-053 reconciliation (`a63ef01925e5c1b925936c1e73b11b2d6cd2a6a5`). It is recorded so a reader can pin the tree state; it is not read by any runtime, gate, policy or promotion path. Git and `validation/VAL-HSL-RUNNER-L1-LIVE-PROMOTION.yaml` remain the only sources of truth. A SHA must never be used to assert that a capability is live, that a policy is enabled, or that promotion authority exists.

## Assurance profile decision (ADR-0011, Accepted)

ADR-0011 is **Accepted** as Option B: the assurance requirement set is split into two profiles,
`LAB_L1` (narrow, controlled) and `PROD` (production-equivalent). The decision is **structural
only**; it authorizes no live effect, policy enablement, trust binding or target interaction.

- canonical profile declaration: `platform/assurance/current-assurance-profile.yaml` (`assurance_profile: LAB_L1`, `derived_from: ADR-0011`);
- schema: `platform/schemas/assurance-profile.schema.json`;
- evaluation: `platform/assurance/assurance_profile.py` (fail-closed: absent/invalid profile -> `PROD`).
- `LAB_L1` MAY omit **only** the external production WORM backend and multi-tenant production
  tenant-isolation gates. It MUST still require external signer, non-exportable private key, explicit
  trust store, `SO_PEERCRED` + audit, tamper-evident/hash-chained evidence, PRE/POST packages,
  mandatory reset/zero-residue and request-bound HITL. No automatic supplier/provider selection.
- `PROD` retains every current production-equivalent control (WORM + tenant isolation included).

**Current campaign profile: `LAB_L1`, campaign state `BLOCKED / HOLD`.** This record reflects the
*accepted profile decision* and the *current* campaign profile. It does **not** mark any unresolved
observation in `validation/VAL-HSL-RUNNER-L1-LIVE-PROMOTION.yaml` as resolved and adds **no** live
promotion path. `promotion_allowed` remains `false`; the campaign remains `HOLD` until the remaining
`LAB_L1` prerequisites (signer/trust store, `SO_PEERCRED` negative test, WORM/tenant observation,
PRE/POST packages, one authorized effect + reset evidence) are actually observed.

## Current summary

| Item | Current state |
| --- | --- |
| RTA-001 gateway admission | `RESOLVED-RUNTIME / GREEN`; re-observation required before the next live mutation |
| RTA-002 Stage 1 Kali registration/discovery | `GREEN/PASS`; canonical STDIO, disabled + sentinel retained |
| RTA-002 Stage 2 minimum health surface | `RESOLVED-RUNTIME / GREEN`; exact effective surface `[server_health]`, one bounded invocation, then rollback to disabled + sentinel |
| RTA-003 Bridge approval handoff | `RESOLVED-RUNTIME / GREEN` on Bridge `3717bd5469...` |
| WebGoat/WebWolf repository lifecycle/readiness | `PASS / READY-REPO`; publication and dual-health races fixed in #325-#327 |
| WebGoat live lifecycle | pre-fix `start/readiness/smoke PASS`; reset race found; cleanup/destroy `PASS / ZERO-RESIDUE`; post-fix rerun `UNKNOWN` |
| DVWA repository lifecycle/readiness | `PASS / READY-REPO`; host-port parity merged #329; live acceptance pending |
| Juice Shop repository lifecycle/readiness | `PASS / READY-REPO`; readiness/smoke/reset publication parity merged #329; live acceptance pending |
| WebGoat L1 real adapter | `GREEN-REPO`; typed target-bound effect exists; live dispatch not accepted |
| Runner outcome -> Evidence Plane custody | `GREEN-REPO`, #321; policy `DISABLED / NOT_RUN` |
| TB1 receipt delivery boundary | `GREEN-REPO`, #322; policy `DISABLED / NOT_RUN` |
| Runner identity/socket promotion preflight | `GREEN-REPO`, #323; runtime `NOT_RUN` |
| Hermes TB1 receipt issuer boundary | `GREEN-REPO`, #328; external signer not live-configured |
| TB1 signer + Runner trust-store deployment preflight | `GREEN-REPO`, #331; runtime `NOT_RUN` |
| Authenticated-principal dispatch audit contract | `GREEN-REPO`, #332 |
| Promotion evidence gate | `GREEN-REPO`, #334; structurally `promotion_allowed=false` |
| Dispatch audit Evidence Plane custody | `GREEN-REPO`, #335; production durable/WORM backend not proven |
| Read-only Runner host evidence | `GREEN-REPO`, #336; host execution `NOT_RUN` |
| Runner service composition | `GREEN-REPO`, #337; no listener/daemon; policy `DISABLED / NOT_RUN` |
| Promotion bundle reconciliation | `GREEN-REPO`, #338; audit/host/service prerequisites pinned |
| Read-only user-namespace evidence | `GREEN-REPO`, #340; live `/proc` observation `NOT_RUN` |
| User-namespace promotion reconciliation | `GREEN-REPO`, #341; verifier required by bundle, live observation `NOT_RUN` |
| Evidence-bound signer-attestation verifier | `GREEN-REPO`, #342; real provider observation/source evidence `NOT_RUN` |
| Signer-attestation promotion reconciliation | `GREEN-REPO`, #343; verifier required by bundle, no live attestation claim |
| Durable Evidence Plane backend attestation verifier | `GREEN-REPO`, #345; no backend selected/deployed; provider observation `NOT_RUN` |
| Durable-backend promotion reconciliation | `GREEN-REPO`, #346; verifier required by bundle; production backend still `NOT_IMPLEMENTED / NOT_RUN` |
| Evidence Plane backend tenant-isolation verifier | `GREEN-REPO`, #348; live tenant configuration/negative tests `NOT_RUN` |
| Tenant-isolation promotion reconciliation | `GREEN-REPO`, #349; verifier required by bundle; no live isolation claim |
| Phased live-promotion evidence package | `GREEN-REPO`, #351; PRE_PROMOTION/POST_EFFECT live packages `NOT_RUN`; `promotion_allowed=false` |
| Live-package promotion reconciliation | `GREEN-REPO`, #352; verifier/schema required by bundle; committed example is not live evidence |
| Full walking skeleton live completion | `HOLD / BLOCKED-ON-LIVE-PROMOTION-EVIDENCE-AND-CONNECTOR` |

## Walking skeleton

Target path:

`authorize -> admit -> provision -> readiness -> dispatch bounded effect -> evidence -> reset -> known-state proof`

| Stage | Repository/CI state | Live runtime state |
| --- | --- | --- |
| Authorize | TB1 verifier, Hermes issuer, delivery/resolver, signer/trust preflight and evidence-bound signer-attestation verifier `GREEN-REPO` | actual provider observation/source evidence, installed trust store and live issuance/delivery remain `NOT_RUN` |
| Admission | Bridge exact-SHA + approval contracts accepted | RTA-001 and RTA-003 accepted; Bridge `3717bd5469...` |
| Kali registration | canonical STDIO contract `GREEN-REPO` | Stage 1 `PASS`; disabled + sentinel retained |
| Kali health | `kali.mcp.health.read -> server_health`, L0, exact mapping | Stage 2 `PASS`; safe state restored |
| Provision | WebGoat/DVWA/Juice lifecycle contracts `READY-REPO` | WebGoat pre-fix start accepted; DVWA/Juice live acceptance pending |
| Readiness | typed loopback readiness adapters with host-port parity `PASS` | WebGoat post-fix rerun `UNKNOWN`; DVWA/Juice pending |
| Dispatch bounded effect | WebGoat L1 adapter + peer identity + router + resolver + audit + service composition `GREEN-REPO` | transport/routing/resolver/delivery/service policies `DISABLED / NOT_RUN`; live effect `NOT_RUN` |
| Host identity/trust | host-evidence collector #336 `GREEN-REPO` | explicit host observation `NOT_RUN` |
| User namespace | explicit-PID read-only observer #340 `GREEN-REPO` | gateway/Runner mapping observation `NOT_RUN` |
| Signer attestation | evidence-bound verifier #342 `GREEN-REPO` | provider metadata capture + source-evidence verification `NOT_RUN` |
| Evidence backend controls | durable-backend control verifier #345 `GREEN-REPO` | production backend `NOT_IMPLEMENTED / NOT_RUN`; provider observation `NOT_RUN` |
| Evidence tenant isolation | provider-neutral tenant-isolation verifier #348 `GREEN-REPO` | real tenant config/evidence and cross-tenant negatives `NOT_RUN` |
| Evidence custody | terminal/audit custody use the existing Evidence Plane `GREEN-REPO` | live terminal/audit persistence `NOT_RUN` |
| Live promotion evidence package | phased PRE_PROMOTION/POST_EFFECT verifier #351 `GREEN-REPO`, pinned by #352 | PRE_PROMOTION and POST_EFFECT packages `NOT_RUN`; even complete packages remain review evidence only |
| Reset/cleanup | bounded reset/destroy governance exists | first failure cleanup proved zero residue; post-fix full lifecycle remains `UNKNOWN` |

## Runtime acceptance already closed

### RTA-001 — gateway admission

**State:** `RESOLVED-RUNTIME / GREEN`.

Gateway admission was accepted as running, non-busy and drainable. Re-observe before a new live mutation.

### RTA-002 — Kali MCP

**Stage 1:** `GREEN/PASS`. Canonical STDIO registration remains disabled + sentinel by default.

**Stage 2:** `RESOLVED-RUNTIME / GREEN`. The effective Hermes surface was temporarily reduced to exactly `server_health`, one no-argument health invocation passed without target traffic, and the safe disabled + sentinel profile was restored byte-for-byte. Do not repeat Stage 2 unless drift or a new acceptance requirement exists.

### RTA-003 — Bridge approval handoff

**State:** `RESOLVED-RUNTIME / GREEN` on Bridge `3717bd5469b061a44294b27e1a7510d477d3752b`.

A no-target compatibility smoke consumed the request-bound approval exactly once. No Kali target tool was involved.

**Bridge SHA divergence (resolved, CHG-HSL-053):** the historical live Bridge observed on 2026-08-09 was `7e4b6b1cd70ddda418f840f54ae7ecef30df52e9` (recorded in [`runtime-acceptance-checkpoint-2026-08-09.md`](runtime-acceptance-checkpoint-2026-08-09.md) and the RTA-003 closure). A later, already-authorized Bridge deployment lane promoted `3717bd5469b061a44294b27e1a7510d477d3752b` as the current live Bridge 1.0.0. The divergence is resolved as: **`3717bd5469b061a44294b27e1a7510d477d3752b` is the current live observation**; **`7e4b6b1cd70ddda418f840f54ae7ecef30df52e9` is retained only as historical candidate/evidence and is never the current runtime and never promoted to "current".** No SHA is a runtime authority and no divergence changed any promotion state.

### Safe live read-only reobservation (run_ec368a4ccc04419e985b1c4d01e0ddea — CHG-HSL-053)

Read-only reobservation only; no mutation, no promotion. See the dedicated ledger [`safe-live-readonly-observation-ec368a4.md`](safe-live-readonly-observation-ec368a4.md).

| Reobserved fact | Value |
| --- | --- |
| Execution Gateway HOLD boundary | active; PID identity `4100` |
| Runner | active; PID identity `4101` |
| Dispatch socket | `LISTEN`; owner `4101:4110`; mode `0660` |
| Installed artifact parity | `7/7` |
| Runner authorization trust store | `OBSERVED_ABSENT` (`/etc/hexor/runner/authorization-trust-store.json` not present) |
| `uid_map` / `gid_map` | observed `0 0 4294967295` |
| Namespace relationship | **NOT re-attested** — ns/user dereference denied; no ns relationship derived or claimed |

Explicitly retained `NOT_RUN` (not elevated): signer/provider `NOT_RUN`; unauthorized-peer negative `NOT_RUN`; phased live-evidence packages (`PRE_PROMOTION`/`POST_EFFECT`) `NOT_RUN`; first authorized effect + reset `NOT_RUN`/`UNKNOWN`. `HOLD`/`NOT_RUN`/`promotion_allowed=false` remain invariant.

## Lifecycle/readiness

### WebGoat/WebWolf

PRs #325-#327 fixed readiness host-port parity, smoke publication ownership and the dual-service health race. The first live cycle established:

`start PASS -> readiness PASS -> smoke PASS -> reset FAIL`

Canonical destroy then proved zero residue. A post-fix full rerun was started as `run_73cd8ef359ff486f93faeb7c2dc46290`, but its result was not recoverable through the available Hermes control surface. Its status remains **UNKNOWN**, not PASS and not FAIL. Recover that run before duplicating it.

### DVWA and Juice Shop

Both are `PASS / READY-REPO` after #329. DVWA follows `DVWA_HOST_PORT`; Juice Shop follows `JUICE_SHOP_HOST_PORT`, smoke resolves the actual publication and reset uses the canonical `juice-shop-lab` network. Their live lifecycle acceptance remains pending.

## Authorization / Runner chain

The repository contains a complete **promotion candidate**, not an enabled runtime:

- Hermes-only TB1 issuer boundary (#328);
- TB1 verification and signer/trust-store deployment preflight (#331);
- authenticated receipt-delivery boundary (#322) and `VerifiedAuthorizationResolver`;
- Unix `SO_PEERCRED` identity and identity/socket deployment preflight (#323);
- deny-by-default dispatch router and target-bound WebGoat L1 adapter;
- sanitized authenticated-principal/correlation audit event (#332);
- Runner terminal-outcome custody (#321) and dispatch-audit custody in the same Evidence Plane (#335);
- read-only host evidence for identity/socket/trust-store declarations (#336);
- fail-closed service composition for an already accepted AF_UNIX peer (#337);
- aggregate EVIDENCE_ONLY promotion gate/bundle (#334/#338);
- explicit-PID read-only Linux user-namespace observation boundary (#340), required by the bundle after #341;
- provider-neutral, evidence-bound external signer observation verifier (#342), required by the bundle after #343;
- provider-neutral durable Evidence Plane backend-control verifier (#345), required by the promotion bundle after #346;
- provider-neutral backend tenant-isolation verifier using only opaque tenant hashes and DENIED cross-tenant list/read/write evidence (#348), required by the bundle after #349;
- phased, candidate-bound live-evidence package verifier with exact PRE_PROMOTION/POST_EFFECT gate sets and independently verified evidence references (#351);
- promotion bundle requirement for the #351 verifier/schema, while explicitly excluding the inert committed example as live evidence (#352).

The service composition sequence is:

`SO_PEERCRED -> transport-admission audit custody -> router -> adapter-local TB1 authorization/effect -> terminal audit custody -> Runner outcome custody`

It intentionally provides no listener, daemon, generic execution path or implicit promotion.

### Durable backend boundary

PR #345 defines the **acceptance contract**, not the production storage implementation. A future `OBSERVED` backend attestation must prove production scope, active state, encryption at rest, `WORM_COMPLIANCE`, enforced retention, legal-hold support, no privileged delete bypass, blocked public access, overwrite protection and independently verified source evidence. The verifier is provider-neutral and performs no provisioning or storage mutation.

PR #348 adds a separate **tenant-isolation acceptance contract**. It carries no customer/tenant names: only two distinct SHA-256 tenant identities. A future positive observation must prove namespace, access-policy and encryption-context isolation, no shared writable namespace, and DENIED cross-tenant list/read/write results bound to independently verified source evidence. The repository verifier does not execute those live negatives.

The production backend itself remains **unselected, undeployed and unobserved**. Real tenant configuration and cross-tenant negative acceptance remain `NOT_RUN`. `LocalEvidenceStore` remains a controlled CI reference and is not reclassified as production durable/WORM or multi-tenant storage.

### Phased live-evidence package boundary

PR #351 defines a candidate-bound package around already-collected evidence. `PRE_PROMOTION` requires the exact prerequisite gate set before Human-in-the-Loop review. `POST_EFFECT` binds the Human-in-the-Loop decision, promoted minimum policy set, terminal/audit persistence and bounded WebGoat L1 effect/reset evidence. Every executed gate requires an `evidence://` reference and SHA-256 verified through an injected `EvidenceVerifier`; the default verifier denies all references.

A complete package never grants promotion. It returns only the next review state while retaining `promotion_allowed=false` and recommendation `HOLD`. PR #352 makes only the verifier and schema promotion-bundle prerequisites. Live packages remain external evidence and are not committed as proof.

### Still missing for live promotion

- actual protected signer provider observation with independently verified source evidence;
- host-observed Runner authorization trust store with approved digest and owner/mode;
- configured receipt-delivery AF_UNIX endpoint and authenticated live delivery;
- live host evidence for gateway/Runner identities and socket;
- live user-namespace mapping evidence for the explicitly reviewed gateway/Runner PIDs;
- unauthorized-peer negative test against the real Runner socket;
- selected/deployed production durable/append-only/WORM Evidence Plane backend;
- live backend provider/control observation accepted through #345;
- live backend tenant configuration and cross-tenant isolation negatives accepted through #348;
- live Runner/audit/terminal persistence;
- assembled and verified PRE_PROMOTION package for the exact candidate;
- explicit promotion of only the minimum resolver/delivery/transport/routing/service/custody policy set;
- Human-in-the-Loop approval for the exact promoted candidate;
- one authorized WebGoat L1 effect, terminal/audit persistence and reset/known-state proof;
- assembled and verified POST_EFFECT package before campaign acceptance review.

The canonical promotion gate remains `EVIDENCE_ONLY`, `HOLD`, `runtime_status: NOT_RUN`, `execution_authority: none`, and `promotion_allowed=false` even if all machine evidence becomes complete. Human promotion is a separate decision.

## Current connector state

The Hermes connector required to recover `run_73cd8ef359ff486f93faeb7c2dc46290` is not currently available through this control surface. This is **not** evidence that the Hermes gateway itself is unhealthy.

Classification:

`CONNECTOR-UNAVAILABLE / LIVE-RUN-RECOVERY-PENDING`

## Automatic continuation order

When the Hermes connector and authorized deployment evidence are usable again:

1. recover `run_73cd8ef359ff486f93faeb7c2dc46290` before starting another WebGoat lifecycle;
2. re-observe gateway admission and Bridge revision `3717bd5469b061a44294b27e1a7510d477d3752b`;
3. verify the Kali profile remains disabled + sentinel;
4. resolve/repeat only a failed WebGoat lifecycle gate, preserving known-state cleanup;
5. execute bounded DVWA and Juice Shop lifecycle/readiness acceptance;
6. run #336 host evidence against an explicitly reviewed descriptor;
7. run #340 user-namespace evidence against explicitly reviewed PIDs;
8. capture real external signer metadata, custody its source evidence and verify it through #342;
9. select/deploy a production Evidence Plane backend, capture read-only controls and validate them through #345;
10. capture tenant-isolation configuration and bounded cross-tenant negative results and verify them through #348;
11. prove installed trust store, live Runner/Evidence handoff and live audit/terminal persistence;
12. execute the unauthorized-peer negative acceptance against the real Runner socket;
13. assemble and verify the exact-candidate PRE_PROMOTION package through #351; completeness leads only to `HUMAN_PROMOTION_REVIEW_REQUIRED`;
14. request and record explicit Human-in-the-Loop promotion for the exact candidate;
15. promote only the minimum WebGoat L1 policy set;
16. execute one bounded read-only WebGoat L1 effect, persist terminal/audit evidence, reset/destroy and prove known state;
17. assemble and verify the POST_EFFECT package through #351; completeness leads only to `CAMPAIGN_ACCEPTANCE_REVIEW_REQUIRED`;
18. on any RED, restore fail-closed state for the affected lane while unrelated repo-only work may continue.

No target-interacting action is authorized merely because repository contracts or CI are GREEN.

## Lifecycle matrix (repository vs live vs deferred)

This matrix is the explicit mapping required by CHG-HSL-052. It separates three
non-interchangeable states and forbids promoting one into another:

- **GREEN-REPO** — repository/CI state only. The contract, code or verifier exists and
  passed repository gates. It is *not* a live claim.
- **NOT_RUN / HOLD** — live runtime state is absent, disabled, or deliberately held. No
  execution authority exists.
- **Deferred signer / Vault dependency** — a capability is present in the repository but
  its live realization depends on an external signer provider and/or the external purpose-bound
  trust store (Vault) that are not configured, observed or selected. The dependency is
  explicitly named; its absence keeps the capability `NOT_RUN`.

| Capability (repository) | Repository/CI state | Live runtime state | Deferred dependency |
| --- | --- | --- | --- |
| Evidence chain + hash seal (LAB_L1) | `GREEN-REPO`, CHG-042 (#369) | `HASH_CHAIN_SEAL: NOT_RUN` for live evidence | none repo-side; signer=None on seal (authenticity=false/durability=false) |
| Local append-only audit sink | `GREEN-REPO`, CHG-043 (#370) | `audit-sink: GREEN-REPO`; live persistence `NOT_RUN` | external durable audit sink (PROD only) |
| Profile-aware PRE/POST gate composition | `GREEN-REPO`, CHG-044 (#371) | gate composition `GREEN-REPO`; packages `NOT_RUN` | external signer + trust store for real effect |
| SO_PEERCRED auth audit integration | `GREEN-REPO`, CHG-045 (#373/#374) | transport `DISABLED`; peer identity `NOT_RUN` | enabled transport + authorized live identity mapping |
| HASH_CHAIN_SEAL wired into phased package | `GREEN-REPO`, CHG-046 (#372) | phase-2 seal gate inert hook; `NOT_RUN` | signed/sealed live package evidence |
| Deterministic reset attestation contracts | `GREEN-REPO`, CHG-049 (#377) | `production_lab_runtime: NOT_RUN` | live reset/zero-residue execution |
| ADR-0011 assurance profiles (LAB_L1/PROD) | `ACCEPTED`, fail-closed to PROD | structural only; `runtime_status: NOT_RUN` | external signer + WORM + tenant isolation for PROD |
| External signer + purpose-bound trust store (Vault) | verifier `GREEN-REPO` (#342/#331) | `signer-provider-observation: NOT_RUN`; `trust-store: ABSENT` | **deferred**: no provider selected, Vault/trust store unconfigured |
| Durable Evidence Plane backend (WORM) | verifier `GREEN-REPO` (#345) | `production-backend: NOT_IMPLEMENTED / NOT_RUN` | **deferred**: no backend selected/deployed |
| Backend tenant isolation | verifier `GREEN-REPO` (#348) | `tenant-isolation: NOT_RUN` | **deferred**: no tenant config/negatives observed |
| Execution Gateway HOLD boundary (#359/#361) | `GREEN-REPO`, CHG-036/037 | `UNPROMOTED`; `promotion_allowed=false`; HOLD | none; intentionally non-executing |
| Full walking skeleton live completion | repository candidate complete | `HOLD / BLOCKED-ON-LIVE-PROMOTION-EVIDENCE-AND-CONNECTOR` | **deferred**: signer/Vault/WORM/tenant/peer-negative/HITL |

Rule: a `GREEN-REPO` row never implies the live row is `PASS`; a deferred dependency
row never implies the dependency is satisfied. `UNKNOWN` is fail-safe: missing or
unverifiable observation is never converted to `IN_SYNC` or `DRIFT_DETECTED`.

## Recent engineering checkpoints

| Change | PR | Merge SHA | Outcome |
| --- | --- | --- | --- |
| Promotion evidence gate | #334 | `135dc1a5b360cace7a69612437933bbc7770a5cd` | GREEN-REPO, promotion authority always false |
| Dispatch audit Evidence Plane custody | #335 | `68a8ce6770532ecbdd0c0ee841a53de5b871a44f` | GREEN-REPO, production WORM NOT_RUN |
| Read-only Runner host evidence | #336 | `c52f7838a9e5bb75c7f326fa094a5e60af371445` | GREEN-REPO, host execution NOT_RUN |
| Runner service composition | #337 | `191f51e3912cd9ddd54f5f4eaf7d08f914ca8c1b` | GREEN-REPO, service policy disabled |
| Promotion bundle reconciliation | #338 | `6dbd34cabb5766837803c6c9083254902fefa1dc` | GREEN-REPO, EVIDENCE_ONLY / HOLD |
| Read-only user-namespace evidence | #340 | `f0f9753152f6e1cb8d1c138d95e7f70455fceca9` | GREEN-REPO, live observation NOT_RUN |
| User-namespace promotion reconciliation | #341 | `459450fdef88b3dfc295d319a41bd2e32e138c52` | GREEN-REPO, live observation still NOT_RUN |
| Evidence-bound signer attestation verifier | #342 | `d4bb4cb7ae2bbbf54e3e806b3a2d843389ee8217` | GREEN-REPO, provider observation NOT_RUN |
| Signer-attestation promotion reconciliation | #343 | `c4c6bf3ff9630ddeab02028047f3129e3c8f0423` | GREEN-REPO, bundle requires verifier; HOLD retained |
| Runner L1 source-of-truth reconciliation | #344 | `b8c3302413a0c62bf4f98ae4f6fbb0c1ed8d2bc3` | DOC_ONLY, BLOCKED/HOLD preserved |
| Durable Evidence Plane backend attestation verifier | #345 | `5b1e889519a1929fbdd13ce3d7853043ddebd0d7` | GREEN-REPO, backend deployment/observation NOT_RUN |
| Durable-backend promotion reconciliation | #346 | `56a9965dbbdda2c6986df7b0822e33e5529c05b0` | GREEN-REPO, verifier required; backend still NOT_IMPLEMENTED/NOT_RUN |
| Backend tenant-isolation verifier | #348 | `3cd53975ae152fbf13d1c06059ba187ed35a75d9` | GREEN-REPO, tenant config/negatives NOT_RUN |
| Tenant-isolation promotion reconciliation | #349 | `05babbbbdf50253374a5add1f73b6c8d96b4eb92` | GREEN-REPO, verifier required; live isolation NOT_RUN |
| Runner L1 tenant-isolation source-of-truth reconciliation | #350 | `d136bbfc7bad7aa9d94f8616c28e6b771f234b59` | DOC_ONLY, tenant live evidence remains NOT_RUN |
| Phased live-promotion evidence package | #351 | `49cd0bd945fa4315a7faacba095fbb83318900ce` | GREEN-REPO, exact candidate/evidence binding; no promotion authority |
| Live-package promotion-bundle reconciliation | #352 | `6a77921ec2079aa6689d11e2d7118f948ccb3a60` | GREEN-REPO, verifier/schema required; live packages NOT_RUN |
| LAB_L1 evidence chain + hash seal | #369 | `1236667779f0a7b55e7b2fcd394b57680e070eac` | GREEN-REPO, signer=None; HASH_CHAIN_SEAL NOT_RUN live |
| LAB_L1 local append-only audit sink | #370 | `47a3ea8c97f146cb5869540b6c9ec8e2d56a8e2a` | GREEN-REPO, live persistence NOT_RUN |
| Live-promotion PRE/POST profile-aware composition | #371 | `970b3a38d5b9a909a554e11c3e495d33cbc8d699` | GREEN-REPO, packages NOT_RUN; PROD keeps WORM/tenant |
| LAB_L1 HASH_CHAIN_SEAL wired into phased package | #372 | `59d212ee09ea5e746b873462ca4b32f9d1add2d9` | GREEN-REPO, phase-2 seal hook inert; NOT_RUN |
| SO_PEERCRED auth audit integration | #373/#374 | `9bdc59409ea14ed238915ff6356b76fe91849add` | GREEN-REPO, transport DISABLED; peer identity NOT_RUN |
| Fail-closed observation/change consistency guards | #376 | `d545ccbd4d4def5aeb8793d291adbc0313e69258` | HARDENING, BLOCKED/HOLD + promotion_allowed false preserved |
| Deterministic reset attestation contracts | #377 | `567e143af332b96b37c0a2aaf6cb563a30cad93c` | GREEN-REPO, production_lab_runtime NOT_RUN |
| Regression coverage for LAB_L1 + Execution Gateway HOLD | #378 | `c36fa8551ed4ae2b347b3b68e4343cbe3e7b592c` | GREEN-REPO, #359/#361 UNPROMOTED; HOLD preserved |
| Walking-skeleton reconciliation (CHG-042..050) | CHG-HSL-052 | `c36fa8551ed4ae2b347b3b68e4343cbe3e7b592c` | DOC_ONLY, baseline re-pinned; BLOCKED/HOLD preserved |
| Safe live read-only reobservation (run_ec368a4) + RTA-003 SHA reconciliation | CHG-HSL-053 | `a63ef01925e5c1b925936c1e73b11b2d6cd2a6a5` | DOC_ONLY, SAFE-LIVE-READONLY; Bridge current `3717bd54`, historical `7e4b6b1c` retained; HOLD/NOT_RUN preserved |

## Decision record

**Decision:** keep promotion on HOLD until live identity/trust/signer/backend/tenant-isolation/audit/evidence prerequisites, a verified PRE_PROMOTION package and explicit Human-in-the-Loop promotion are proven; campaign acceptance additionally requires verified POST_EFFECT evidence.

**Context:** the repository now contains host, user-namespace, signer-attestation, durable-backend-control, tenant-isolation and phased live-evidence package verification boundaries, but these remain repository capabilities. No production backend or tenant configuration has been selected/deployed and the related live observations/packages have not run.

**Risks accepted:** continued implementation may proceed repo-side while connector/live prerequisites are unavailable, provided no repository result or package schema/example is promoted to a live claim.

**State:** `HOLD / BLOCKED-ON-LIVE-PROMOTION-EVIDENCE-AND-CONNECTOR`.
