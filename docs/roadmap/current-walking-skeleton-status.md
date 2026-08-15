# Hermes Security Labs — current walking-skeleton status

**Reconciled:** 2026-08-15 UTC
**Current Labs baseline:** `8c654379afb2114e34d6e748bb558b3ad5b8fb4b`
**Repository reconciliation base before CHG-HSL-064:** `dd3677b6fb531c72ec7c5ea6fb5f82da94a27f37` (the exact revision exercised by the accepted WebGoat live lifecycle run; reconciliation provenance only, never a runtime authority — the eventual CHG-HSL-064 merge SHA is likewise not a runtime authority)
**Accepted/live Hermes MCP Bridge revision:** `3717bd5469b061a44294b27e1a7510d477d3752b`  
**Safe live read-only reobservation:** `run_ec368a4ccc04419e985b1c4d01e0ddea` (CHG-HSL-053)
**WebGoat live lifecycle acceptance:** `run_f3ecec54f9464366aa1edfb32ac58b33` (CHG-HSL-064)
**DVWA live lifecycle acceptance:** `run_8f2174dc4c87452098b700ff556ac978` (CHG-HSL-069, Issue #393)
**Profile-aware live-promotion gate correction:** CHG-HSL-066 / PR #396 (`b742d2dd91d5e0c2766a5ee5dc48a1e43309b6e1`; reconciliation provenance only)

This is the concise current-state view of the walking skeleton. Repository/CI proof and live Hermes runtime proof are separate evidence classes. Historical evidence remains in [`runtime-acceptance-checkpoint-2026-08-09.md`](runtime-acceptance-checkpoint-2026-08-09.md); the governed Runner promotion campaign is [`../../validation/VAL-HSL-RUNNER-L1-LIVE-PROMOTION.yaml`](../../validation/VAL-HSL-RUNNER-L1-LIVE-PROMOTION.yaml).

> **GREEN-REPO is not live acceptance.** It means the contract/code exists and passed repository gates. It does not grant execution authority, activate a policy, prove host deployment or prove target interaction.

> **The commit SHA is reconciliation provenance, not a runtime authority.** The value `a63ef01925e5c1b925936c1e73b11b2d6cd2a6a5` is *historical* CHG-HSL-053 reconciliation provenance (the exact authoritative `origin/main` at the time of that reconciliation); it is not read by any runtime, gate, policy or promotion path. The current reconciliation provenance is **CHG-HSL-068 (`8c654379afb2114e34d6e748bb558b3ad5b8fb4b`)**, recorded so a reader can pin the exact authoritative tree reconciled by CHG-HSL-068. Git and `validation/VAL-HSL-RUNNER-L1-LIVE-PROMOTION.yaml` remain the only sources of truth. A SHA must never be used to assert that a capability is live, that a policy is enabled, or that promotion authority exists.

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
`LAB_L1` prerequisites (signer/trust store, authenticated receipt delivery, `SO_PEERCRED` negative
proof, live hash-chain/audit/outcome evidence, PRE/POST packages, explicit HITL promotion and one
authorized effect + reset evidence) are actually observed. External production WORM-backend and
production tenant-isolation observations remain **PROD-only readiness**, not current LAB_L1 blockers.

## Current summary

| Item | Current state |
| --- | --- |
| RTA-001 gateway admission | `RESOLVED-RUNTIME / GREEN`; re-observation required before the next live mutation |
| RTA-002 Stage 1 Kali registration/discovery | `GREEN/PASS`; canonical STDIO, disabled + sentinel retained |
| RTA-002 Stage 2 minimum health surface | `RESOLVED-RUNTIME / GREEN`; exact effective surface `[server_health]`, one bounded invocation, then rollback to disabled + sentinel |
| RTA-003 Bridge approval handoff | `RESOLVED-RUNTIME / GREEN` on Bridge `3717bd5469...` |
| WebGoat/WebWolf repository lifecycle/readiness | `PASS / READY-REPO`; publication and dual-health races fixed in #325-#327 |
| WebGoat live lifecycle | `PASS / ACCEPTED-LIVE-LIFECYCLE` for the exact tested revision `dd3677b6fb531c72ec7c5ea6fb5f82da94a27f37`, accepted run `run_f3ecec54f9464366aa1edfb32ac58b33` (CHG-HSL-064); pre-fix history retained (`start/readiness/smoke PASS`, reset race found, cleanup/destroy `PASS / ZERO-RESIDUE`); historical run `run_73cd8ef359ff486f93faeb7c2dc46290` remains `UNKNOWN` and is never reclassified |
| DVWA repository lifecycle/readiness | `PASS / READY-REPO`; host-port parity merged #329; **live lifecycle `PASS / ACCEPTED-LIVE-LIFECYCLE`** for the exact tested revision `e3fb2554c9a5d354b82a29edfbd0830fa78fc471`, accepted run `run_8f2174dc4c87452098b700ff556ac978` (CHG-HSL-069, Issue #393); unrelated Docker resources preserved, concurrent external m365 recreation documented as a distinct concurrent-external observation within the same CHG-HSL-069 report |
| Juice Shop repository lifecycle/readiness | `PASS / READY-REPO`; readiness/smoke/reset publication parity merged #329; **live lifecycle `PASS / ACCEPTED-LIVE-LIFECYCLE`** for the exact tested revision `2b793750e95f0d0a9a8ac4b82e1b684cc7732e19`, accepted run `run_cc3cd41e85c44d9182305960ea816f18` (CHG-HSL-070, Issue #394); prior attempt `run_353c8079eca84a90be30d4a3324af451` retained as FAIL (harness dropped `JUICE_SHOP_HOST_PORT`, bound default 127.0.0.1:3000); accepted run supplied `JUICE_SHOP_HOST_PORT=14300` on every canonical invocation, zero Juice Shop residue, unrelated Docker/Runner/Kali unchanged, no Runner promotion |
| WebGoat L1 real adapter | `GREEN-REPO`; typed target-bound effect exists; live dispatch not accepted |
| Runner outcome -> Evidence Plane custody | `GREEN-REPO`, #321; policy `DISABLED / NOT_RUN` |
| TB1 receipt delivery boundary | `GREEN-REPO`, #322; policy `DISABLED / NOT_RUN` |
| Runner identity/socket promotion preflight | `GREEN-REPO`, #323; runtime `NOT_RUN` |
| Hermes TB1 receipt issuer boundary | `GREEN-REPO`, #328; external signer not live-configured |
| TB1 signer + Runner trust-store deployment preflight | `GREEN-REPO`, #331; runtime `NOT_RUN` |
| Authenticated-principal dispatch audit contract | `GREEN-REPO`, #332 |
| Promotion evidence gate | `GREEN-REPO`, #334; structurally `promotion_allowed=false` |
| Dispatch audit Evidence Plane custody | `GREEN-REPO`, #335; production durable/WORM backend not proven (PROD readiness) |
| Read-only Runner host evidence | `GREEN-REPO`, #336; host execution `NOT_RUN` |
| Runner service composition | `GREEN-REPO`, #337; no listener/daemon; policy `DISABLED / NOT_RUN` |
| Promotion bundle reconciliation | `GREEN-REPO`, #338; audit/host/service prerequisites pinned |
| Read-only user-namespace evidence | `GREEN-REPO`, #340; live `/proc` observation `NOT_RUN` |
| User-namespace promotion reconciliation | `GREEN-REPO`, #341; verifier required by bundle, live observation `NOT_RUN` |
| Evidence-bound signer-attestation verifier | `GREEN-REPO`, #342; real provider observation/source evidence `NOT_RUN` |
| Signer-attestation promotion reconciliation | `GREEN-REPO`, #343; verifier required by bundle, no live attestation claim |
| Durable Evidence Plane backend attestation verifier | `GREEN-REPO`, #345; production backend `NOT_IMPLEMENTED / NOT_RUN`; PROD-only live requirement under current LAB_L1 profile |
| Durable-backend promotion reconciliation | `GREEN-REPO`, #346; verifier required by bundle; production backend still `NOT_IMPLEMENTED / NOT_RUN` (PROD readiness) |
| Evidence Plane backend tenant-isolation verifier | `GREEN-REPO`, #348; real tenant config/evidence and cross-tenant negatives `NOT_RUN`; PROD-only live requirement under current LAB_L1 profile |
| Tenant-isolation promotion reconciliation | `GREEN-REPO`, #349; verifier required by bundle; no live isolation claim; PROD readiness, not LAB_L1 blocker |
| Phased live-promotion evidence package | `GREEN-REPO`, #351; PRE_PROMOTION/POST_EFFECT live packages `NOT_RUN`; `promotion_allowed=false` |
| Live-package promotion reconciliation | `GREEN-REPO`, #352; verifier/schema required by bundle; committed example is not live evidence |
| Profile-aware live-promotion gate | `GREEN-REPO`, CHG-HSL-066/#396; LAB_L1 omits only production backend + tenant-isolation gates, PROD still requires both; invalid profile fails closed to PROD |
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
| Provision | WebGoat/DVWA/Juice lifecycle contracts `READY-REPO` | WebGoat lifecycle `PASS` live for the exact tested revision `dd3677b6...` (run `run_f3ecec54f9464366aa1edfb32ac58b33`); DVWA lifecycle `PASS` live for the exact tested revision `e3fb2554...` (run `run_8f2174dc4c87452098b700ff556ac978`, CHG-HSL-069); Juice Shop lifecycle `PASS` live for the exact tested revision `2b793750...` (run `run_cc3cd41e85c44d9182305960ea816f18`, CHG-HSL-070, Issue #394) |
| Readiness | typed loopback readiness adapters with host-port parity `PASS` | WebGoat readiness `PASS` live for that exact revision; historical run `run_73cd8ef3...` stays `UNKNOWN`; DVWA readiness `PASS` live for the exact tested revision `e3fb2554...` (CHG-HSL-069); Juice Shop readiness `PASS` live for the exact tested revision `2b793750...` (CHG-HSL-070); no Runner promotion |
| Dispatch bounded effect | WebGoat L1 adapter + peer identity + router + resolver + audit + service composition `GREEN-REPO` | transport/routing/resolver/delivery/service policies `DISABLED / NOT_RUN`; live effect `NOT_RUN` |
| Host identity/trust | host-evidence collector #336 `GREEN-REPO` | explicit host observation `NOT_RUN` |
| User namespace | explicit-PID read-only observer #340 `GREEN-REPO` | gateway/Runner mapping observation `NOT_RUN` |
| Signer attestation | evidence-bound verifier #342 `GREEN-REPO` | provider metadata capture + source-evidence verification `NOT_RUN` |
| Evidence backend controls | durable-backend control verifier #345 `GREEN-REPO` | production backend `NOT_IMPLEMENTED / NOT_RUN`; provider observation `NOT_RUN` — PROD readiness, optional under current LAB_L1 |
| Evidence tenant isolation | provider-neutral tenant-isolation verifier #348 `GREEN-REPO` | real tenant config/evidence and cross-tenant negatives `NOT_RUN` — PROD readiness, optional under current LAB_L1 |
| Evidence custody | terminal/audit custody use the existing Evidence Plane `GREEN-REPO` | live terminal/audit persistence `NOT_RUN` |
| Live promotion evidence package | phased PRE_PROMOTION/POST_EFFECT verifier #351 + profile-aware correction CHG-HSL-066 `GREEN-REPO` | PRE_PROMOTION and POST_EFFECT packages `NOT_RUN`; even complete packages remain review evidence only |
| Reset/cleanup | bounded reset/destroy governance exists | first failure cleanup proved zero residue; WebGoat reset/destroy `PASS` live for the exact tested revision with zero project-owned residue; DVWA reset/destroy `PASS` live for the exact tested revision `e3fb2554...` with zero project-owned residue and idempotent second destroy (CHG-HSL-069); Juice Shop reset/destroy `PASS` live for the exact tested revision `2b793750...` with zero project-owned residue and idempotent second destroy (CHG-HSL-070); historical run `run_73cd8ef3...` stays `UNKNOWN` |

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

### Repository-only progression after CHG-HSL-053 (CHG-HSL-054..059)

- `CHG-HSL-054` — SAFE live-observation adapter into `EvidenceInput`; fail-closed, and `HOST_IDENTITY_SOCKET_TRUST` cannot become `PASS` while the trust store is absent.
- `CHG-HSL-055` — LAB_L1 local evidence custody/verifier using content-addressed evidence plus hash-chain integrity; no WORM, tenant-isolation or signer claim.
- `CHG-HSL-056` — custody-to-promotion bridge feeds offline `PRE_PROMOTION`; Gateway/Bridge observations and `HASH_CHAIN_SEAL` can be verified from custodized repository evidence while host trust remains `NOT_RUN`.
- `CHG-HSL-057` — repository-only operator harness for `USER_NAMESPACE_MAPPING` and `UNAUTHORIZED_PEER_NEGATIVE`; no live execution performed.
- `CHG-HSL-058` — privilege-flow correction with privileged parent and `setpriv` child; still no live execution performed.
- `CHG-HSL-059` — stdlib-only independent peer-child probe; retained as temporary LAB operational debt; no live execution performed.

Current invariants remain: `LAB_L1`, `BLOCKED`, `HOLD`, `promotion_allowed=false`, `runtime_status=NOT_RUN`, `execution_authority=none`, `supplier_selection=NO_SELECTION`, `trust-store=ABSENT`. GREEN-REPO is not live acceptance.

### Repository-only signer progression (CHG-HSL-061..063, already merged)

- `CHG-HSL-061` — repository-only signer supplier work; supplier selection stays `NO_SELECTION`.
- `CHG-HSL-062` — explicit human-decision contract for supplier selection; the current decision state is `NO_DECISION`.
- `CHG-HSL-063` — permits a staged `APPROVED` decision while supplier selection remains `NO_SELECTION`, and requires explicit decision plus candidate evidence before any future `PENDING`/`SELECTED` state. Trust binding and promotion remain off.

No live signer, provider, trust store or promotion effect is granted by this progression. The current campaign stays `LAB_L1`, `BLOCKED` / `HOLD`, with `promotion_allowed=false`.

### Profile-aware promotion reconciliation (CHG-HSL-066)

- the executable phased package verifier now derives the true mandatory gate set from the canonical ADR-0011 assurance profile;
- `LAB_L1` omits only `EVIDENCE_BACKEND_CONTROLS` and `EVIDENCE_TENANT_ISOLATION` from mandatory PRE_PROMOTION gates;
- a LAB_L1 package may retain those PROD-only gates as optional evidence: absent/`NOT_RUN` does not block, but an executed `FAIL` or unverified result still blocks;
- `PROD` always requires both gates;
- an absent, invalid or inconsistent assurance profile fails closed to `PROD`;
- POST_EFFECT requirements are unchanged and profile-invariant;
- no runtime, policy, signer/trust or campaign state was promoted by CHG-HSL-066.

The campaign remains `LAB_L1`, `BLOCKED / HOLD`, with `promotion_allowed=false`.

## Lifecycle/readiness

### WebGoat/WebWolf

PRs #325-#327 fixed readiness host-port parity, smoke publication ownership and the dual-service health race. The first live cycle established:

`start PASS -> readiness PASS -> smoke PASS -> reset FAIL`

Canonical destroy then proved zero residue. A post-fix full rerun was started as `run_73cd8ef359ff486f93faeb7c2dc46290`, but its result was not recoverable through the available Hermes control surface. Its status remains **UNKNOWN**, not PASS and not FAIL. It is retained only as historical provenance; current acceptance comes from the fresh, independently evidenced CHG-HSL-064 run below.

**Accepted live lifecycle (CHG-HSL-064): `PASS / ACCEPTED-LIVE-LIFECYCLE`.** Full record: [`webgoat-live-lifecycle-acceptance-2026-08-15.md`](webgoat-live-lifecycle-acceptance-2026-08-15.md). Accepted run `run_f3ecec54f9464366aa1edfb32ac58b33` exercised the exact repository revision `dd3677b6fb531c72ec7c5ea6fb5f82da94a27f37` from a clean temporary export, with localhost host-port overrides `WEBGOAT_HOST_PORT=18080` and `WEBWOLF_HOST_PORT=19090` (container-internal ports unchanged at `8080`/`9090`). The exact sequence completed with exit code `0` at every step:

`start PASS -> status PASS -> smoke PASS -> reset PASS -> status PASS -> smoke PASS -> destroy PASS -> second destroy PASS (idempotent)`

After the two canonical destroy operations, project-owned WebGoat containers, volumes and networks were all `0` and both override ports were free again: **zero project-owned residue**. Unrelated Docker resources were preserved.

Provenance is retained and not rewritten: the first pre-fix failure history above stays as recorded, and `run_73cd8ef359ff486f93faeb7c2dc46290` remains **UNKNOWN** — it is never reclassified as PASS or FAIL and was not reused as acceptance evidence. This acceptance covers only the WebGoat/WebWolf lifecycle/readiness/reset/zero-residue scope for that exact revision. It grants no dispatch effect, signer, evidence-custody or promotion acceptance.

### DVWA and Juice Shop

Both are `PASS / READY-REPO` after #329 and the governed lifecycle pattern is documented by CHG-HSL-065. DVWA follows `DVWA_HOST_PORT`; Juice Shop follows `JUICE_SHOP_HOST_PORT`, smoke resolves the actual publication and reset uses the canonical `juice-shop-lab` network.

**Accepted Juice Shop live lifecycle (CHG-HSL-070): `PASS / ACCEPTED-LIVE-LIFECYCLE`.** Full record: [`juice-shop-live-lifecycle-acceptance-2026-08-15.md`](juice-shop-live-lifecycle-acceptance-2026-08-15.md). Accepted run `run_cc3cd41e85c44d9182305960ea816f18` exercised the exact repository revision `2b793750e95f0d0a9a8ac4b82e1b684cc7732e19` from a clean temporary export, with `JUICE_SHOP_HOST_PORT=14300` supplied on every canonical invocation (container-internal port unchanged at `3000`); pre-mutation compose resolved `127.0.0.1:14300:3000` and runtime binding was `127.0.0.1:14300->3000/tcp` after start, before reset and after reset. The canonical digest actually used was `bkimminich/juice-shop@sha256:e68144772ebaaca0ec117b38d44903af92416793230288ef7c5437fc4f26850a`. The exact sequence completed with exit code `0` at every step:

`start PASS -> status1 PASS -> smoke1 PASS -> reset PASS -> status2 PASS -> smoke2 PASS -> destroy1 PASS -> destroy2 PASS (idempotent)`

After the two canonical destroy operations, project-owned Juice Shop containers, volumes and networks were all `0` and high port `14300` was free again: **zero project-owned residue**. Unrelated Docker resources, Runner and Kali were preserved and no concurrent external activity was observed.

Attempt 1 (`run_353c8079eca84a90be30d4a3324af451`, same exact SHA) is retained as **FAIL**: the functional lifecycle and cleanup succeeded, but the sanitized execution harness accidentally omitted `JUICE_SHOP_HOST_PORT`, so the clean rerun bound the default `127.0.0.1:3000` instead of the selected high port `14300`; cleanup remained `PASS`/zero-residue. Attempt 1 is never reclassified as PASS. The source contract already supports `JUICE_SHOP_HOST_PORT` via compose environment substitution — the first failure was an execution-harness omission, not a repository script bug. No Runner, signer, trust-store or promotion authority is granted.

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
- provider-neutral durable Evidence Plane backend-control verifier (#345), retained as PROD readiness under LAB_L1;
- provider-neutral backend tenant-isolation verifier using only opaque tenant hashes and DENIED cross-tenant list/read/write evidence (#348), retained as PROD readiness under LAB_L1;
- phased, candidate-bound live-evidence package verifier with profile-resolved PRE_PROMOTION gates and independently verified evidence references (#351 + CHG-HSL-066);
- promotion bundle requirement for the #351 verifier/schema, while explicitly excluding the inert committed example as live evidence (#352).

The service composition sequence is:

`SO_PEERCRED -> transport-admission audit custody -> router -> adapter-local TB1 authorization/effect -> terminal audit custody -> Runner outcome custody`

It intentionally provides no listener, daemon, generic execution path or implicit promotion.

### Durable backend boundary — PROD readiness

PR #345 defines the **acceptance contract**, not the production storage implementation. A future `OBSERVED` backend attestation must prove production scope, active state, encryption at rest, `WORM_COMPLIANCE`, enforced retention, legal-hold support, no privileged delete bypass, blocked public access, overwrite protection and independently verified source evidence. The verifier is provider-neutral and performs no provisioning or storage mutation.

PR #348 adds a separate **tenant-isolation acceptance contract**. It carries no customer/tenant names: only two distinct SHA-256 tenant identities. A future positive observation must prove namespace, access-policy and encryption-context isolation, no shared writable namespace, and DENIED cross-tenant list/read/write results bound to independently verified source evidence. The repository verifier does not execute those live negatives.

The production backend itself remains **unselected, undeployed and unobserved**. Real tenant configuration and cross-tenant negative acceptance remain `NOT_RUN`. `LocalEvidenceStore` remains a controlled CI reference and is not reclassified as production durable/WORM or multi-tenant storage.

Under the accepted current `LAB_L1` profile, these production backend and tenant-isolation observations are **not mandatory PRE_PROMOTION gates**. They remain visible, testable PROD readiness work. Switching to `PROD`, or falling back to `PROD` because the profile is absent/invalid/inconsistent, makes them mandatory again.

### Phased live-evidence package boundary

PR #351 defines a candidate-bound package around already-collected evidence. `PRE_PROMOTION` requires the exact prerequisite gate set resolved from the accepted assurance profile before Human-in-the-Loop review. `POST_EFFECT` binds the Human-in-the-Loop decision, promoted minimum policy set, terminal/audit persistence and bounded WebGoat L1 effect/reset evidence. Every executed gate requires an `evidence://` reference and SHA-256 verified through an injected `EvidenceVerifier`; the default verifier denies all references.

CHG-HSL-066 corrected the executable PRE_PROMOTION composition: under `LAB_L1`, `EVIDENCE_BACKEND_CONTROLS` and `EVIDENCE_TENANT_ISOLATION` are optional PROD evidence; under `PROD` both are mandatory. Supplied optional evidence can only tighten the outcome: `FAIL` or unverified executed evidence still blocks.

A complete package never grants promotion. It returns only the next review state while retaining `promotion_allowed=false` and recommendation `HOLD`. PR #352 makes only the verifier and schema promotion-bundle prerequisites. Live packages remain external evidence and are not committed as proof.

### Still missing for current LAB_L1 live promotion

- actual protected signer provider observation with independently verified source evidence, after an explicit human signer decision;
- host-observed Runner authorization trust store with approved digest and owner/mode;
- configured receipt-delivery AF_UNIX endpoint and authenticated live delivery;
- current host identity/socket evidence for the exact reviewed candidate where re-observation is required;
- current user-namespace evidence where drift or exact-candidate review requires it;
- unauthorized-peer negative test against the real Runner socket;
- live `HASH_CHAIN_SEAL` evidence plus Runner/audit/terminal persistence;
- assembled and verified PRE_PROMOTION package for the exact candidate using the LAB_L1 required gate subset;
- explicit Human-in-the-Loop promotion approval for the exact candidate;
- explicit promotion of only the minimum resolver/delivery/transport/routing/service/custody policy set;
- one authorized WebGoat L1 effect, terminal/audit persistence and reset/known-state proof;
- assembled and verified POST_EFFECT package before campaign acceptance review.

### PROD-only readiness still open

These items remain deliberately visible and `NOT_RUN`, but are not current LAB_L1 blockers after CHG-HSL-066:

- selected/deployed production durable/append-only/WORM Evidence Plane backend;
- live backend provider/control observation accepted through #345; production backend `NOT_IMPLEMENTED / NOT_RUN`;
- live backend tenant configuration and cross-tenant isolation negatives accepted through #348; real tenant config/evidence and cross-tenant negatives `NOT_RUN`.

The canonical promotion gate remains `EVIDENCE_ONLY`, `HOLD`, `runtime_status: NOT_RUN`, `execution_authority: none`, and `promotion_allowed=false` even if all machine evidence becomes complete. Human promotion is a separate decision.

## Current connector state

The ChatGPT-side Hermes control surface is currently intermittent: tool discovery may succeed while submission can fail before the bridge creates an execution ID. The most recent DVWA submission attempts failed at that control boundary, before any execution ID or Docker mutation existed. This is **not** evidence that the Hermes gateway, DVWA or Docker runtime is unhealthy.

The historical WebGoat run `run_73cd8ef359ff486f93faeb7c2dc46290` remains `UNKNOWN` as provenance, but recovery of that run is no longer a prerequisite for WebGoat lifecycle acceptance because CHG-HSL-064 established a fresh independent `PASS / ACCEPTED-LIVE-LIFECYCLE` run.

Classification:

`CONNECTOR-CONTROL-SURFACE-UNAVAILABLE / DVWA-LIVE-LANE-NOT_STARTED`

## Automatic continuation order

When the Hermes control surface and the required explicitly authorized live dependencies are usable again, continue the current `LAB_L1` path in this order:

1. re-observe gateway admission and Bridge revision `3717bd5469b061a44294b27e1a7510d477d3752b` before the next relevant live mutating Runner lane;
2. verify the Kali profile remains disabled + sentinel;
3. execute issue #393 DVWA lifecycle/readiness/reset/zero-residue acceptance from an exact clean revision export;
4. if #393 is PASS and persisted, execute #394 Juice Shop under the same governed lifecycle pattern;
5. refresh #336 host identity/socket/trust evidence for the exact candidate where required;
6. refresh/reuse #340 user-namespace evidence only when drift or exact-candidate review requires it;
7. after an explicit human signer decision, capture real external signer metadata, custody its source evidence and verify it through #342;
8. install and verify the approved Runner trust store through a separate governed change;
9. configure and prove authenticated receipt delivery without broadening policy scope;
10. execute the unauthorized-peer negative acceptance against the real Runner socket;
11. prove live `HASH_CHAIN_SEAL` plus Runner/audit/terminal persistence;
12. assemble and verify the exact-candidate PRE_PROMOTION package through #351/CHG-HSL-066; completeness leads only to `HUMAN_PROMOTION_REVIEW_REQUIRED`;
13. request and record explicit Human-in-the-Loop promotion for the exact candidate;
14. promote only the minimum WebGoat L1 policy set;
15. execute one bounded read-only WebGoat L1 effect, persist terminal/audit evidence, reset/destroy and prove known state;
16. assemble and verify the POST_EFFECT package through #351; completeness leads only to `CAMPAIGN_ACCEPTANCE_REVIEW_REQUIRED`;
17. on any RED, restore fail-closed state for the affected lane while unrelated repo-only work may continue.

**Separate PROD-readiness lane:** production WORM/backend observation (#345) and tenant-isolation configuration/negative evidence (#348) may progress independently, but they are not inserted into the current LAB_L1 critical path. They become mandatory if/when the profile is `PROD` or fail-closes to `PROD`.

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
| Profile-aware PRE/POST gate composition | `GREEN-REPO`, CHG-044/#371 + CHG-HSL-066/#396 | gate composition `GREEN-REPO`; packages `NOT_RUN` | external signer + trust store for real LAB_L1 effect; WORM/tenant only for PROD |
| SO_PEERCRED auth audit integration | `GREEN-REPO`, CHG-045 (#373/#374) | transport `DISABLED`; peer identity `NOT_RUN` | enabled transport + authorized live identity mapping |
| HASH_CHAIN_SEAL wired into phased package | `GREEN-REPO`, CHG-046 (#372) | phase-2 seal gate inert hook; `NOT_RUN` | signed/sealed live package evidence |
| Deterministic reset attestation contracts | `GREEN-REPO`, CHG-049 (#377) | `production_lab_runtime: NOT_RUN` | live reset/zero-residue execution |
| ADR-0011 assurance profiles (LAB_L1/PROD) | `ACCEPTED`, fail-closed to PROD | structural only; `runtime_status: NOT_RUN` | external signer + WORM + tenant isolation for PROD |
| External signer + purpose-bound trust store (Vault) | verifier `GREEN-REPO` (#342/#331) | `signer-provider-observation: NOT_RUN`; `trust-store: ABSENT` | **deferred**: no provider selected, Vault/trust store unconfigured |
| Durable Evidence Plane backend (WORM) | verifier `GREEN-REPO` (#345) | `production-backend: NOT_IMPLEMENTED / NOT_RUN` | **PROD-only deferred readiness**: no backend selected/deployed |
| Backend tenant isolation | verifier `GREEN-REPO` (#348) | `tenant-isolation: NOT_RUN` | **PROD-only deferred readiness**: no tenant config/negatives observed |
| Execution Gateway HOLD boundary (#359/#361) | `GREEN-REPO`, CHG-036/037 | `UNPROMOTED`; `promotion_allowed=false`; HOLD | none; intentionally non-executing |
| Full walking skeleton live completion | repository candidate complete | `HOLD / BLOCKED-ON-LIVE-PROMOTION-EVIDENCE-AND-CONNECTOR` | **LAB_L1 deferred**: signer/Vault, receipt delivery, peer-negative, live persistence/packages and HITL; WORM/tenant are PROD-only |

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
| WebGoat governed live lifecycle acceptance | #392 / CHG-HSL-064 | `7c468c4a8991d6348f8b3c27413140fbe4128d60` | PASS / ACCEPTED-LIVE-LIFECYCLE for exact tested revision; Runner promotion unchanged |
| Governed lab lifecycle runbook + Juice Shop docs | #395 / CHG-HSL-065 | `5cc24452416571e6851e936e74721e559d2e442d` | DOC_ONLY; #393 DVWA and #394 Juice Shop prepared for live acceptance |
| LAB_L1 profile-aware live-promotion gate correction | #396 / CHG-HSL-066 | `b742d2dd91d5e0c2766a5ee5dc48a1e43309b6e1` | GREEN-REPO; removes false PROD-only blockers from LAB_L1 while preserving PROD strictness and HOLD |

## Decision record

**Decision:** keep LAB_L1 promotion on HOLD until live signer/trust, authenticated receipt delivery, peer-negative proof, live hash-chain/audit/outcome persistence, a verified PRE_PROMOTION package, exact-candidate Human-in-the-Loop approval, minimum-policy promotion, one bounded effect/reset proof and verified POST_EFFECT evidence are complete. Production WORM/backend and tenant-isolation evidence remain separate PROD-only readiness requirements.

**Context:** the repository contains host, user-namespace, signer-attestation, durable-backend-control, tenant-isolation and phased live-evidence package verification boundaries. CHG-HSL-066 reconciled the executable gate with ADR-0011: WORM/backend and tenant-isolation remain mandatory for PROD but are not current LAB_L1 blockers. Their live observations still remain `NOT_RUN` and must not be misrepresented as completed.

**Risks accepted:** continued implementation may proceed repo-side while connector/live prerequisites are unavailable, provided no repository result or package schema/example is promoted to a live claim and PROD-only omissions are never generalized beyond the explicit LAB_L1 profile.

**State:** `HOLD / BLOCKED-ON-LIVE-PROMOTION-EVIDENCE-AND-CONNECTOR`.
