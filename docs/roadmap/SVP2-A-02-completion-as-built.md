# SVP2-A-02 — Completion / AS_BUILT Evidence Record

## 1. Decision

`SVP2-A-02 — Rules of Engagement as Code and intrusiveness levels L0-L4` is eligible for delivery status **`completed`** at the repository / controlled-synthetic boundary.

This completion decision applies to the **delivery umbrella `SVP2-A-02` only**. It does not promote concept `EPIC-09 — Exploitation safety` to `FINAL`. EPIC-09 remains **`AS_BUILT` / `FINAL=no`** while deployed and production evidence remains `NOT_IMPLEMENTED` / `NOT_RUN`.

## 2. Completion boundary

The completed umbrella now has repository-backed evidence for its declared scope and acceptance criteria:

1. machine-readable signed Rules of Engagement (RoE), scope/window/limits/approvals and deterministic refusal;
2. L0-L4 intrusiveness policy with approval and rollback requirements, including distinct dual approval for L4;
3. external global/campaign kill-switch semantics and fail-closed source handling;
4. deterministic kill-switch lifecycle transition for every canonical active campaign state `AUTHORIZED`, `READY`, `RUNNING`, `PAUSED` to `STOPPING`;
5. in-flight cancellation planning for active Runner Protocol v2 attempts;
6. controlled synthetic evidence that a `RUNNING` supervised process can be cancelled, force-killed after grace when required and cleaned without residue;
7. controlled local subprocess JSON-lines transport evidence, campaign-scope isolation and fail-closed cancellation when the kill-switch source is missing or invalid.

The following are deliberately **outside the completion claim** and remain future runtime/deployment evidence:

- authoritative deployed supervisor integration;
- remote/deployed Runner transport;
- deployed control-plane mutation of campaign state;
- production trust-store / attestation-key distribution, rotation and emergency revocation;
- deployed global/campaign kill-switch drills;
- deployed cooperative / force-after-grace interruption;
- customer or external-target execution;
- real L3/L4 destructive execution.

## 3. Acceptance criteria disposition

| Acceptance criterion | Disposition | Evidence |
| --- | --- | --- |
| A step not covered by the active contract is refused by specification | `MET` | PR #133 and signed-RoE/gateway admission regressions through PR #160; caller-controlled authorization decisions remain refused. |
| Every intrusiveness level declares approval and rollback requirements | `MET` | Canonical `intrusiveness-policy.yaml`; L0-L4 policy, L2+ approval requirements, L3/L4 rollback, distinct customer/provider dual approval for L4. |
| The kill switch acts in every active campaign state | `MET` at control-contract boundary; `PASS_SYNTHETIC_RUNTIME/TRANSPORT` for `RUNNING` | PR #212 deterministically maps `AUTHORIZED`, `READY`, `RUNNING`, `PAUSED` to `STOPPING`; PRs #206/#208/#209/#211 demonstrate actual controlled synthetic interruption for running work. Deployed state mutation remains separately `NOT_RUN`. |

## 4. Key implementation evidence

### Contract and policy foundation

- PR #133 — L0-L4 intrusiveness, approval, rollback and stop-condition decision contract.
- PR #159 — public-key trust-store verification and external file-backed kill switch.
- PR #160 — signed RoE integrated into canonical gateway admission.
- PR #198 — active-attempt inventory and global/campaign cancellation-message fan-out.
- PR #200 — trust-store generation freshness, monotonic lifecycle and anti-rollback assessment.
- PR #202 — externally verified provenance/freshness of the exact active-attempt inventory.
- PR #204 — deterministic cancellation ACK/outcome observation.
- PR #205 — `RUNNER_EVENT_ATTESTATION_V1` event-source attestation.

### Controlled runtime / transport evidence

- PR #206 — integrated main `4c1b29192ede22611c3be8311b852136b418b81a`; post-merge `security` `31258137581` PASS; `validate` `31258137561` PASS. Global kill switch reached a fixed supervised synthetic process; ACK `accepted`, terminal `CANCELLED`, `force_killed=true`, `cleanup_failed=false`, no active residue.
- PR #208 — integrated main `d489e77403c8ab1ae8f5780d875a5ec81f6d065a`; post-merge `security` `31258975026` PASS; `validate` `31258975027` PASS. Cancellation crossed a separate Runner subprocess over the existing JSON-lines stdin/stdout control surface and the adapter shut down cleanly.
- PR #209 — integrated main `9654426979b77f28fceb4bab1b9b06f97a0ee310`; post-merge `security` `31259265339` PASS; `validate` `31259265360` PASS. Campaign-A cancellation terminated only campaign A while campaign B remained active until explicit cleanup.
- PR #211 — final head `11afc9311dce4cfd5c5a7ea5ecb26d4ec0f3de73`; integrated main `8fc271d430435e4389002b804ec2c91c16128dd3`; post-merge `security` `31260159369` PASS; `validate` `31260159327` PASS. Missing and invalid kill-switch sources failed closed and cancelled every active synthetic attempt through the separate Runner subprocess.

### All-active-state lifecycle evidence

- PR #212 final head `682ece36324c149831eb75847f780a83c1fd73d7`.
- Pre-merge `security` `31260496653` PASS; `validate` `31260496663` PASS.
- Integrated main `e82ffd40c4ef4ced7dcda3002a8bb8bd7175fa0a`.
- Post-merge `security` `31260611139` PASS; `validate` `31260611137` PASS.
- `campaign_kill_switch_transition.py` validates the canonical policy and deterministically plans the restrictive transition from `AUTHORIZED`, `READY`, `RUNNING`, `PAUSED` to `STOPPING`.
- Missing/invalid source and stale/future/missing release evidence fail closed for those active states.
- `DRAFT`, `STOPPING` and terminal states are never restarted or broadened.
- The planner is side-effect free and preserves `authorization_effect=NONE` and `execution_authority=NONE`.

## 5. Definition of Done assessment

| DoD | Result | Evidence / limitation |
| --- | --- | --- |
| DOD-01 — declared deliverables merged | `PASS` | RoE schema/policy, L0-L4 model, campaign state-machine/kill-switch contracts and supporting evidence are in `main`. |
| DOD-02 — final-head repository/security gates | `PASS` | Every final implementation head was merged only after `security` and `validate` PASS; PR #212 final-head runs are recorded above. |
| DOD-03 — post-merge validation on main | `PASS` | Exact-SHA post-merge validation is recorded for each promoted block; PR #212 main is GREEN. |
| DOD-04 — positive/negative/adversarial/regression testing | `PASS` | Scope matching/nonmatching, invalid/missing/stale sources, anti-replay/freshness, campaign isolation, forced cancellation, cleanup and lifecycle-state regressions are covered. |
| DOD-05 — canonical documentation | `PASS` | EPIC-09 records repository/synthetic evidence and non-final limitations; this completion record captures the umbrella completion decision and remaining deployed gaps. |
| DOD-06 — no committed secrets | `PASS` | Security gates remain GREEN; trust/signing material is external and tests use synthetic identifiers/state. |
| DOD-07 — failures/missing evidence fail-safe | `PASS` | Missing/invalid kill-switch source and stale/future release evidence fail closed; absence of evidence does not create PASS or authorization. |
| DOD-08 — rollback / runtime boundary | `PASS with explicit limitation` | Repository planners are restrictive and side-effect free; synthetic processes are disposable/cleaned. No deployed/production runtime change is claimed. |
| DOD-09 — issue/backlog status reconciliation | `PENDING UNTIL MERGE` | Completion PR must update the canonical backlog to `completed`; after merge issue #77 must receive `status:completed`, evidence comment and closure as completed. |
| DOD-10 — no false FINAL claim | `PASS` | `SVP2-A-02 completed` is explicitly separate from `EPIC-09 FINAL`; EPIC-09 remains `AS_BUILT`, `FINAL=no`, with deployed/production `NOT_RUN` / `NOT_IMPLEMENTED` limitations. |

## 6. Finality assessment

`SVP2-A-02 = completed` means the **declared Phase-1 governance/architecture delivery** has met its Definition of Done with controlled repository and synthetic evidence.

It does **not** mean:

- production-ready exploitation safety;
- deployed kill-switch effectiveness;
- remote Runner transport conformance;
- production trust lifecycle effectiveness;
- authorization of L3/L4 execution;
- customer-target safety evidence.

Those claims require separate runtime/deployment work and evidence. Therefore:

- `SVP2-A-02`: **candidate for `completed`**;
- `EPIC-09`: **`AS_BUILT`**;
- `EPIC-09 FINAL`: **`no`**;
- deployed/production evidence: **open / non-final limitation**.

## 7. Decision record

| Field | Value |
| --- | --- |
| Decision | Complete delivery umbrella `SVP2-A-02` without promoting `EPIC-09` to `FINAL`. |
| Context | All declared Phase-1 deliverables and acceptance criteria now have repository evidence; running-work mechanics additionally have controlled synthetic runtime/transport evidence. |
| Alternative considered | Keep A-02 indefinitely `implementing` until production deployment exists. |
| Reason rejected | Governance permits `completed` with explicit non-final limitations; requiring production evidence for a Phase-1 governance/architecture umbrella would conflate delivery completion with concept finality and block dependent roadmap work without improving truthfulness. |
| Accepted risk | Deployment integration can still reveal transport, state-mutation, key-lifecycle or runtime-specific defects not observable in repository/synthetic evidence. |
| Mitigation | Preserve `FINAL=no`, explicit NOT_RUN/NOT_IMPLEMENTED limitations, fail-closed runtime rules and separate deployment gates. |
| State | `Em validação` until completion PR and exact-SHA post-merge gates are GREEN; then `Decisão`. |
| Next action | Reconcile issue #77 after merge and continue with the next v2.0 Foundation delivery gap. |
