# SVP2-B-02 — Completion / AS_BUILT Evidence Record

## 1. Decision

`SVP2-B-02 — Runner Protocol v2 with correlation cancellation and normalized errors` is eligible for delivery status **`completed`** at the repository / controlled-synthetic protocol boundary.

This completion decision applies to the **delivery umbrella `SVP2-B-02` only**. It does not promote concept `EPIC-05 — Runner Protocol v2` to `FINAL`. EPIC-05 remains **`AS_BUILT` / `FINAL=no`** while production runner integration, sandboxing, remote/deployed transport and real capability execution remain `NOT_IMPLEMENTED` / `NOT_RUN` as applicable.

The historical sentence in EPIC-05 section 15 stating that the umbrella could close only after EPIC-level production criteria and `FINAL` was written before the repository governance distinction between **delivery completion** and **concept finality** was applied consistently. This record supersedes that sentence **only for `SVP2-B-02` delivery status**. It does not supersede any EPIC-05 production limitation or permit a `FINAL` claim.

## 2. Completion boundary

The completed umbrella has repository-backed evidence for its declared scope and acceptance criteria:

1. one canonical Runner Protocol v2 schema/SDK for API, DevSecOps and AI/MCP runner families;
2. mandatory campaign/run/step/attempt correlation identifiers;
3. deterministic idempotency classification plus durable transactional replay state;
4. cancellation, retry and timeout semantics;
5. normalized stable error taxonomy with fail-closed secret rejection;
6. mandatory terminal evidence references;
7. vendor-neutral JSON-lines conformance plus cross-family fixed-worker supervised conformance;
8. gateway handoff and terminal-result boundaries that preserve exact correlation and a Hermes-issued authorization reference without claiming real dispatch.

The following remain **outside the completion claim**:

- production API, DevSecOps or AI/MCP Runner Protocol adapters;
- real security-tool/capability execution through Runner Protocol;
- sandboxing with namespaces/cgroups/seccomp/network/privilege/resource isolation;
- remote/deployed Runner transport;
- production Evidence Plane chain-of-custody integration;
- operational Hermes authorization-receipt issuance;
- production runner promotion/readiness.

## 3. Acceptance criteria disposition

| Acceptance criterion | Disposition | Evidence |
| --- | --- | --- |
| All records and evidence transport the four correlation IDs | `MET` at the declared Runner Protocol / conformance boundary | Canonical schema requires `campaign_id`, `run_id`, `step_id`, `attempt_id`; vendor-neutral and cross-family supervised conformance validate correlation preservation; gateway handoff/terminal boundary PRs #161/#164/#165 preserve exact correlation. |
| Repeating a step with the same idempotency key does not duplicate effects | `MET` at the declared synthetic enforcement boundary | Stable fingerprint/conflict logic, transactional SQLite ledger (#113), restart replay (#115), fixed-worker supervised candidates and cross-family conformance (#129) demonstrate no second synthetic effect/process for completed replay and fail closed on conflict/uncertain state. |
| Errors use a stable taxonomy and never contain secrets | `MET` | Canonical schema/semantic validator fixes normalized error codes/categories/retryability; recursive secret-key rejection, conformance secret canary and sanitized process-output/evidence tests reject leaks and raw error/process material. |

## 4. Deliverables disposition

| Deliverable | Result | Canonical implementation |
| --- | --- | --- |
| Runner Protocol v2 specification | `MET` | `platform/runner-protocol/README.md`, `schemas/runner-protocol-v2.schema.json`, `runner_protocol_v2` SDK and semantic validator. |
| Version compatibility matrix | `MET` | `platform/runner-protocol/compatibility.yaml` schema version `1.3`, exact-major/fail-closed compatibility rules, migration gates and per-family synthetic conformance state. |

## 5. Key evidence

### Contract, SDK and enforcement primitives

- PR #105 — canonical Runner Protocol v2 schema/semantics; merge `3f9753ea2e1db5750f971f01bb1dbfea558723fb`; post-merge validate `31076955536` PASS; security `31076955527` PASS.
- PR #107 — vendor-neutral JSON-lines conformance kit; merge `944d198a106ebf106631fd18b9c5c5b9aef63942`; post-merge validate `31078149317` PASS; security `31078149409` PASS.
- PR #109 — importable repository-local SDK; merge `dd742e41787bfcaec1feac347abf94c73d5b59fd`; post-merge validate `31079378064` PASS; security `31079378148` PASS.
- PR #113 — durable transactional SQLite idempotency ledger; merge `cc879b9fc5e20afcb8052c0f7197457c0ebcc86d`; post-merge validate `31089022988` PASS; security `31089022565` PASS.
- PR #115 — API durable synthetic restart replay; merge `3ff427e4c5122f0733bc04c9291acfdfc28b1448`; post-merge validate `31090875891` PASS; security `31090875979` PASS.
- PR #117 — POSIX process supervisor; merge `bf71fd7c6da2dcd2e179462677341a90f4f22b7a`; post-merge validate `31093252331` PASS; security `31093252418` PASS.

### Cross-family synthetic conformance

- PR #119 — API fixed-worker supervised candidate; merge `bc7e301baf977e041ff267a045bbb8ee592c6455`; `PASS_SYNTHETIC_PROCESS`.
- PRs #121/#122 — shared engine + DevSecOps fixed-worker supervised candidate; lifecycle main `f2be46da70601aafe92a436636d8c09201a1b259`; `PASS_SYNTHETIC_PROCESS`.
- PRs #124/#125 — AI/MCP fixed-worker supervised candidate; lifecycle main `40b0e60bbf0fecf0f76da648ab3b3560e02cb41c`; `PASS_SYNTHETIC_PROCESS` while calibrated AI/MCP runtime remains disconnected.
- PR #129 — cross-family supervised synthetic conformance; validated head `5421a7652b2b1eee6a3c00fb728f8bc79ee8c453`; merge `586802146b8e575f4f9c71fcc2bb7a0ae4134880`; post-merge validate `31129689358` PASS; security `31129689363` PASS. The harness normalizes message shape, exact correlation fields, terminal/error/evidence shape, replay/conflict, timeout, cancellation, residue and refusal behaviour across API/DevSecOps/AI-MCP.

### Gateway / authority / terminal boundaries

- PR #161 — gateway handoff to canonical `runner.step.request`; merge `316f70e7c2d319e9f5a97e47c34e58042d284974`; positive result remains `request_built`, never `dispatched`.
- PR #162 — Runner request consumes the exact verified Hermes-issued TB1 authorization reference; merge `57130293524cd714ce2a6b36dbee63542a021605`; gateway cannot create/expand authorization.
- PR #164 — gateway/admission correlation version alignment; merge `90b3bb3a99ac5b859528c2587b3347b3571bc154`; canonical v2 UUID correlation preserved without silent legacy rewrite.
- PR #165 — repository terminal-result boundary; merge `74417961f7387e85b2a6ebb16f0ae1d822162b6d`; terminal outcome must match exact campaign/run/step/attempt correlation and exposes sanitized normalized metadata only.

### Additional controlled transport evidence

Later A-02 integration tests reuse the canonical B-02 transport/cancellation surface without changing its production status:

- PR #208 — cancellation crossed a separate supervised synthetic Runner subprocess via JSON-lines stdin/stdout; integrated main `d489e77403c8ab1ae8f5780d875a5ec81f6d065a`; post-merge security `31258975026` PASS; validate `31258975027` PASS.
- PR #209 — campaign-scoped selectivity across concurrent synthetic Runner work; integrated main `9654426979b77f28fceb4bab1b9b06f97a0ee310`; post-merge security `31259265339` PASS; validate `31259265360` PASS.
- PR #211 — missing/invalid kill-switch source failed closed and transported cancellation to all active synthetic attempts; integrated main `8fc271d430435e4389002b804ec2c91c16128dd3`; post-merge security `31260159369` PASS; validate `31260159327` PASS.

These are supporting controlled-synthetic transport observations, not production Runner conformance.

## 6. Definition of Done assessment

| DoD | Result | Evidence / limitation |
| --- | --- | --- |
| DOD-01 — declared deliverables merged | `PASS` | Canonical Runner Protocol specification, SDK and compatibility matrix are in `main`. |
| DOD-02 — final-head repository/security gates | `PASS` | Historical implementation blocks were promoted only after validation/security gates; the completion PR must also be GREEN on its exact final head. |
| DOD-03 — post-merge validation on main | `PASS after completion merge` | Existing technical blocks have post-merge evidence; completion status is valid only after exact-SHA post-merge `security` + `validate` PASS. |
| DOD-04 — positive/negative/adversarial/regression testing | `PASS` | Reference/broken candidates, duplicate-effect detection, idempotency conflicts, restart replay, concurrency, timeout/cancellation, residue, unsupported capability/refusal and secret canary are covered. |
| DOD-05 — canonical documentation | `PASS with explicit reconciliation` | EPIC-05 remains the concept AS_BUILT record; this completion record is the canonical delivery-level reconciliation and explicitly supersedes its historical umbrella-closure sentence only for B-02 status. |
| DOD-06 — no committed secrets | `PASS` | Security/gitleaks gates remain GREEN; semantic/conformance tests explicitly reject secret fields/canaries. |
| DOD-07 — failures/missing evidence fail-safe | `PASS` | Unknown/invalid protocol fails closed; corrupt/unknown ledger state fails closed; uncertain `IN_PROGRESS` is not automatically reclaimed; cleanup uncertainty cannot become PASS. |
| DOD-08 — rollback / runtime boundary | `PASS with explicit limitation` | Production promotion remains blocked; compatibility declares `NO_RUNTIME_CHANGE`, sandbox `NOT_IMPLEMENTED`, execution integration `NOT_RUN`. |
| DOD-09 — issue/backlog status reconciliation | `PENDING UNTIL MERGE` | Completion PR must update canonical backlog; after exact-SHA post-merge GREEN issue #80 must receive `status:completed`, immutable evidence and closure as completed. |
| DOD-10 — no false FINAL claim | `PASS` | `SVP2-B-02 completed` remains explicitly separate from `EPIC-05 FINAL`; production adapters, sandboxing and real execution remain non-final limitations. |

## 7. Finality assessment

`SVP2-B-02 = completed` means the **Phase-1 Runner Protocol delivery** has met its declared deliverables and backlog acceptance criteria using repository and controlled-synthetic evidence.

It does **not** mean:

- production Runner Protocol conformance;
- production API/DevSecOps/AI-MCP execution integration;
- sandboxed real security-tool execution;
- remote/deployed Runner transport readiness;
- production Evidence Plane integration;
- automatic candidate promotion;
- `EPIC-05 FINAL`.

Therefore:

- `SVP2-B-02`: **candidate for `completed`**;
- `EPIC-05`: **`AS_BUILT`**;
- `EPIC-05 FINAL`: **`no`**;
- compatibility protocol status: **`contract_only`**;
- cross-family conformance: **`PASS_SYNTHETIC_PROCESS`**;
- production execution integration: **`NOT_RUN`**;
- sandbox: **`NOT_IMPLEMENTED`**;
- promotion: **blocked**.

## 8. Decision record

| Field | Value |
| --- | --- |
| Decision | Complete delivery umbrella `SVP2-B-02` without promoting `EPIC-05` to `FINAL`. |
| Context | Both declared deliverables exist and the three backlog acceptance criteria are demonstrated across canonical contracts, durable state and cross-family controlled synthetic conformance. |
| Alternative considered | Keep B-02 `implementing` until production runner adapters are integrated. |
| Reason rejected | That would conflate Phase-1 protocol delivery completion with EPIC-level production finality; governance permits completion with explicit non-final limitations and DOD-10 protects against overclaim. |
| Accepted risk | Production adapters can reveal transport, sandbox, authorization, Evidence Plane or real-effect idempotency defects not observable in controlled synthetic evidence. |
| Mitigation | Preserve `EPIC-05 FINAL=no`, `contract_only`, `execution_integration=NOT_RUN`, `sandbox_status=NOT_IMPLEMENTED`, `promotion_status=blocked`, and require separate runtime/deployment gates before any production claim. |
| State | `Em validação` until completion PR and exact-SHA post-merge gates are GREEN; then `Decisão`. |
| Next action | Reconcile issue #80 after merge and audit the v2.0 Foundation release gate. |
