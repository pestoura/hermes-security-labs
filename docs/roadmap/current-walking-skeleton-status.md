# Hermes Security Labs — current walking-skeleton status

**Reconciled:** 2026-08-28 UTC
**Current Labs baseline:** `8c654379afb2114e34d6e748bb558b3ad5b8fb4b`
**Foundation functional baseline:** `7711ddf2920c87259b6c0c4a4119d5441dba4181`
**Latest reconciled repository milestone:** CHG-HSL-100 / PR #448 / `0349cea6eb60f0719464e8735bfc1d0bdf2f227f`
**Foundation / Walking Skeleton (Level A): `COMPLETE`** — repository/CI criteria and CHG-HSL-097 post-merge POSIX/runtime re-observation are PASS on Foundation functional baseline `7711ddf2920c87259b6c0c4a4119d5441dba4181`; final PromptMe cleanup is zero-residue.
**Core Operational v1 / LAB_L1 promotion:** `IN_PROGRESS / BLOCKED_AT_SECRET_ZERO_HITL` — preparation through CHG-HSL-100 is merged and GREEN; the next state transition remains operator-only Secret Zero.
**Secret Zero:** `NOT_RUN`
**signer human decision:** `NO_DECISION`
**supplier selection:** `NO_SELECTION`
**CHG-HSL-072 reconciliation base:** `9448817e436ee096e0f839b6bb8b9bf9e06d8d6d`
**Accepted/live Hermes MCP Bridge revision:** `3717bd5469b061a44294b27e1a7510d477d3752b`
**DVWA live lifecycle acceptance:** `run_8f2174dc4c87452098b700ff556ac978`
**Juice Shop live lifecycle acceptance:** `run_cc3cd41e85c44d9182305960ea816f18`
**CHG-HSL-071 accepted merge:** `c4f409d05e5575e815d4b35e0ca5fda45a73bf8c` (PR #401; post-merge Exact-SHA GREEN)
**CHG-HSL-086 accepted merge:** `c8e4c4517e0fceaa9e37d28fe05c53554af07723` (PR #431; shared-Vault pre-Secret-Zero probe merged and live-observed)
**CHG-HSL-088 accepted merge:** `1d368ea8eb54d65d4fc2a5022d8a88e93252a6c2` (PR #433; authenticated receipt-delivery boundary merged and live-observed in AUTHENTICATED_HOLD)
**CHG-HSL-090 accepted merge:** `eada361cb5fd3f612b7b5911146cd4b448241e04` (PR #437; synthetic authorization-audit custody probe merged and live-observed)
**CHG-HSL-097 accepted merge:** `7711ddf2920c87259b6c0c4a4119d5441dba4181` (PR #445; controlled PromptMe Runner cancellation merged and post-merge POSIX/runtime re-observed PASS with zero residue)
**CHG-HSL-098 accepted merge:** `af65af1105384c3f8ffaa0aee5d5a5658dac663e` (PR #446; Juice Shop fail-closed lifecycle merged and post-merge zero-residue accepted)
**CHG-HSL-099 accepted merge:** `d418c0ad30054c464c2bc2316bf6b81d03082e83` (PR #447; Foundation final snapshot merged; Level A COMPLETE only)
**CHG-HSL-100 accepted merge:** `0349cea6eb60f0719464e8735bfc1d0bdf2f227f` (PR #448; sanitized Secret Zero reconciliation contract merged; operator-only HITL remains NOT_RUN and does not grant trust, Runner or target authority)

This file is the concise current-state view. Historical detail remains in the dedicated roadmap/evidence records and the governed campaign at [`../../validation/VAL-HSL-RUNNER-L1-LIVE-PROMOTION.yaml`](../../validation/VAL-HSL-RUNNER-L1-LIVE-PROMOTION.yaml).

> **GREEN-REPO is not live acceptance.** Repository/CI proof and live runtime proof are separate evidence classes.

> **The commit SHA is reconciliation provenance, not a runtime authority.** The current reconciliation provenance is **CHG-HSL-068 (`8c654379afb2114e34d6e748bb558b3ad5b8fb4b`)** for the walking-skeleton baseline. CHG-HSL-072 additionally pins the exact harness tree `9448817e436ee096e0f839b6bb8b9bf9e06d8d6d` used for issue #402 evidence. Neither SHA grants execution authority.

## Assurance profile and locked invariants

The accepted assurance profile is `LAB_L1`. The campaign remains `BLOCKED / HOLD`.

Locked invariants:

- `promotion_allowed=false`
- `runtime_status=NOT_RUN`
- `execution_authority=none`
- `supplier_selection=NO_SELECTION`
- `trust-store=ABSENT`
- no policy is enabled by repository evidence
- no signer/provider is selected automatically
- production WORM/backend and production tenant-isolation remain PROD-only readiness, not current LAB_L1 blockers

A complete machine-evidence package still cannot promote the Runner without explicit Human-in-the-Loop approval.

## Current live acceptance summary

| Item | State |
| --- | --- |
| RTA-001 gateway admission | `RESOLVED-RUNTIME / GREEN`; re-observe before a future live mutating lane |
| RTA-002 Kali Stage 1 | `GREEN/PASS`; disabled + sentinel retained |
| RTA-002 Kali minimum health | `RESOLVED-RUNTIME / GREEN`; safe state restored |
| RTA-003 Bridge approval handoff | `RESOLVED-RUNTIME / GREEN` on `3717bd5469b061a44294b27e1a7510d477d3752b` |
| WebGoat lifecycle | `PASS / ACCEPTED-LIVE-LIFECYCLE` via `run_f3ecec54f9464366aa1edfb32ac58b33`; historical `run_73cd8ef359ff486f93faeb7c2dc46290` remains `UNKNOWN` |
| DVWA lifecycle | `PASS / ACCEPTED-LIVE-LIFECYCLE`; #393 closed |
| Juice Shop lifecycle | `PASS / ACCEPTED-LIVE-LIFECYCLE`; #394 closed; first harness attempt remains recorded as FAIL |
| Current user-namespace re-attestation | `PASS / ACCEPTED-LIVE-OBSERVATION` by CHG-HSL-072 |
| Unauthorized peer negative | `PASS / ACCEPTED-LIVE-OBSERVATION`; `HOLD_REFUSAL_OBSERVED`, `canonical_proof=true`, `payload_sent=false` |
| PRE_PROMOTION package | `ASSEMBLED / HOLD / INCOMPLETE` through CHG-HSL-071 plus CHG-HSL-072 evidence |
| Hermes Vault v1 | `OPERATIONAL BASELINE`; shared ecosystem service healthy/unsealed on HermesJarvas |
| HSL shared-Vault pre-Secret-Zero probe | `PASS / OBSERVED_PRE_SECRET_ZERO`; TLSv1.3 verified; consumer `172.25.0.3/32`; `SECRETID_ISSUANCE=NOT_RUN` |
| HSL authenticated receipt-delivery boundary | `PASS / AUTHENTICATED_HOLD`; `/run/hexor/runner-authz.sock`; `4101:4110`; mode `0660`; peer uid `4100`; policy remains `DISABLED / NOT_RUN` |
| Authorization-audit synthetic custody proof | `PASS / OBSERVED_SYNTHETIC_CUSTODY`; canonical custody persisted one sanitized synthetic event, verified after reopen and through AuditSink, cleanup PASS; operational policy remains `DISABLED / NOT_RUN` |
| Full walking skeleton live completion | `HOLD / BLOCKED-ON-LIVE-PROMOTION-EVIDENCE` |

## CHG-HSL-085/086 — shared Hermes Vault consumer path

The former isolated `deployment/vault-lab-l1` runtime path is superseded as an active signer authority. ADR-0018 and CHG-HSL-085 make HSL a consumer of the shared Hermes Vault service; the legacy package remains historical/verify-only provenance with no automatic fallback.

The shared **Hermes Vault v1** service is treated as the `OPERATIONAL BASELINE` for the Hermes ecosystem. CHG-HSL-086 then proved the bounded HSL pre-Secret-Zero runtime path from merged `main` on HermesJarvas:

- exact endpoint `https://hermes-vault:8200`;
- only `hermes-security-plane` attached to the disposable probe;
- DNS resolution and hostname-verified TLS succeeded with `TLSv1.3`;
- observed consumer identity `172.25.0.3/32`;
- `runtime_status=OBSERVED_PRE_SECRET_ZERO`;
- `credential_stage=NOT_RUN`;
- `SECRETID_ISSUANCE=NOT_RUN`;
- `promotion_allowed=false`;
- `execution_authority=NONE`.

This observation is network/TLS readiness only. It is not signer attestation, provider/source evidence, R1-R8 completion, trust binding or execution authority. The campaign remains `BLOCKED / HOLD`. The next signer-dependent action is the Secret Zero operator HITL; ChatGPT automation must not create, unwrap, read or transport the resulting credentials.

## CHG-HSL-088 — authenticated receipt-delivery live boundary

The merged CHG-HSL-088 runtime was installed by an authorized operator and independently re-observed on HermesJarvas. The dedicated AF_UNIX endpoint `/run/hexor/runner-authz.sock` is enabled, active and listening as `hexor-runner` uid 4101 / `hexor-dispatch` gid 4110 with mode `0660`; the accepted peer contract remains uid 4100 / `hexor.execution-gateway`. All five installed artifacts match merged main byte-for-byte, the existing `runner-dispatch.sock` remains independently active, and an unprivileged caller is refused at the DAC boundary.

This is an endpoint-boundary observation only. The receipt-delivery and resolver policies remain `DISABLED / NOT_RUN`; `execution_authority=none`, `promotion_allowed=false`, target effects remain none, trust-store remains absent, and signer/Secret Zero remain unexecuted. The campaign therefore remains `BLOCKED / HOLD`.

## CHG-HSL-090 — synthetic authorization-audit custody proof

Merged main `eada361cb5fd3f612b7b5911146cd4b448241e04` was exercised on HermesJarvas with the bounded CHG-HSL-090 probe. One sanitized synthetic authorization-audit event was persisted through the canonical custody adapter into the existing Evidence Plane local store, verified after reopening the store, verified through the AuditSink evidence resolver, and removed by the probe cleanup. The observed runtime class is `OBSERVED_SYNTHETIC_CUSTODY`.

This proves the synthetic local custody composition only. The committed authorization-audit custody policy remains `DISABLED / NOT_RUN`; operational live authorization flow remains `NOT_RUN`; `execution_authority=none`, `promotion_allowed=false`, target effects remain none, and no signer/trust or Secret Zero state changed. `OBS-EVIDENCE-CUSTODY` and the campaign therefore remain `BLOCKED / HOLD`.

## CHG-HSL-072 — current-PID userns + unauthorized-peer acceptance

Issue #402 was executed only through the canonical privileged operator harness on exact repository SHA `9448817e436ee096e0f839b6bb8b9bf9e06d8d6d`.

Preflight and collection established:

- ephemeral UID `2000` was unassigned and inactive;
- Gateway service was active and observed at PID `3649254`;
- Runner service was active and observed at PID `409235`;
- dispatch socket was an AF_UNIX socket, owner `4101:4110`; mode `0660`;
- reviewed descriptor SHA-256: `e10cdbe95e58f5ffde74c000bb660415eb945ae93e48be863397e7c3ba4257d5`;
- operator evidence SHA-256: `bf7a2b498cd9a547852d594b8c2cc43bbefbe73ee4eddc5c7ca3b7ad5d11a2a8`.

### USER_NAMESPACE_MAPPING

The current Gateway/Runner PIDs were re-attested with no findings:

- Gateway PID `3649254`, start ticks `334245705`;
- Runner PID `409235`, start ticks `338949789`;
- both expose the observed mapping `0 0 4294967295`;
- namespace relationship: `same`;
- result: `PASS`, `re_attested=true`.

The historical CHG-HSL-038 reviewed-PID PASS remains historical only. The CHG-HSL-053 historical observation remains explicitly **NOT re-attested** and is not rewritten. CHG-HSL-072 is the accepted current-PID observation for this gate.

### UNAUTHORIZED_PEER_NEGATIVE

The canonical child used `/usr/bin/setpriv` with UID/GID `2000` and supplementary GID `4110` solely to reach the socket at the DAC layer. It created no persistent identity and sent no Runner request payload.

Accepted result:

- `HOLD_REFUSAL_OBSERVED`
- `canonical_proof=true`
- `payload_sent=false`
- `persistent_state_created=false`

A DAC-only `EACCES/EPERM` would not have been accepted as canonical proof. No permission, socket mode, directory mode, group membership or policy was weakened to obtain this result.

## Historical bridge and host-boundary provenance

The accepted current live Bridge observation is `3717bd5469b061a44294b27e1a7510d477d3752b`. Historical Bridge revision `7e4b6b1cd70ddda418f840f54ae7ecef30df52e9` is retained only as historical evidence and is never promoted to "current".

Historical/read-only host observations established Gateway PID identity `4100`, Runner PID identity `4101`, and the dispatch socket owner `4101:4110`; mode `0660`. The Runner authorization trust store remains `OBSERVED_ABSENT` and therefore `trust-store=ABSENT` remains a live blocker.

## Evidence custody

CHG-HSL-071 remains authoritative for the already-produced custody package:

- `HASH_CHAIN_SEAL` VERIFIED;
- Gateway admission reobservation PASS;
- Bridge revision reobservation PASS;
- PRE_PROMOTION `ASSEMBLED / HOLD / INCOMPLETE`;
- signer authenticity remains false/absent for the current seal;
- POST_EFFECT remains `NOT_RUN`.

CHG-HSL-072 adds two independent accepted evidence inputs only: `USER_NAMESPACE_MAPPING` and `UNAUTHORIZED_PEER_NEGATIVE`. It does not rewrite CHG-HSL-071 history and it does not promote the Runner.

## Still missing for current LAB_L1 promotion

The two issue #402 blockers are now closed at evidence level. The remaining critical path is:

1. shared-Vault Secret Zero operator HITL, followed by sanitized external signer/provider observation, independently verified source evidence, trust-manifest input and R1-R8 evidence;
2. evidence-backed #403 operational decision (`APPROVED + NO_SELECTION`), without automatic supplier/provider selection, then approved Runner authorization trust store installed and host-observed;
3. refreshed host identity/socket/trust evidence where exact-candidate re-observation is required;
4. live Runner/audit/terminal persistence evidence;
5. completion and verification of all remaining mandatory PRE_PROMOTION gates;
6. explicit Human-in-the-Loop promotion approval for the exact candidate;
7. promotion of only the minimum required policy set;
8. one authorized bounded WebGoat L1 effect plus terminal/audit persistence and reset/known-state proof;
9. complete and verified POST_EFFECT package before campaign acceptance review.

Production WORM/backend controls and production tenant-isolation remain visible as PROD-only readiness and are not inserted into the current LAB_L1 critical path.

## Current connector state

The Hermes MCP control surface is currently **callable** based on the last accepted project-runtime observation. ChatGPT connector exposure is an execution-context concern and must not be interpreted as runtime failure without independent project-runtime evidence.

Classification:

`CONNECTOR-LAST-ACCEPTED-CALLABLE / DVWA-AND-JUICE-LIFECYCLES-ACCEPTED`

#393 DVWA and #394 Juice Shop are already accepted/closed and are not continuation steps.

## Automatic continuation order

1. preserve the accepted CHG-HSL-072 issue #402 evidence without re-running it merely for progression;
2. preserve the accepted CHG-HSL-088 authenticated receipt-delivery endpoint proof while keeping delivery/resolver policies disabled, then continue the next independent non-secret lane: live authorization-audit persistence;
3. at the explicit operator HITL, complete shared-Vault Secret Zero locally and capture only sanitized signer attestation/source evidence;
4. record the evidence-backed #403 operational decision and install/verify the approved trust store in a separately governed change;
5. reconcile exact-candidate receipt/trust/host evidence;
6. collect remaining live Runner/audit/terminal persistence evidence;
7. complete PRE_PROMOTION required gates; completeness leads only to `HUMAN_PROMOTION_REVIEW_REQUIRED`;
8. obtain explicit Human-in-the-Loop promotion;
9. promote only the minimum WebGoat L1 policy set;
10. execute one authorized bounded effect, persist evidence, reset/destroy and prove known state;
11. assemble/verify POST_EFFECT; completeness leads only to `CAMPAIGN_ACCEPTANCE_REVIEW_REQUIRED`.

No target-interacting action is authorized merely because repository contracts, lifecycle tests or CI are GREEN.
