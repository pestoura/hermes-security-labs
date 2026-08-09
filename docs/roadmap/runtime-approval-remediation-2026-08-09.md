# Runtime approval remediation — 2026-08-09

**Project:** Hermes Security Labs  
**Scope:** repository-side remediation of runtime blocker RTA-003  
**Hermes Security Labs baseline:** `0ee16ffc74e0053cfe9b9a734d9269049276bf1f`  
**Hermes MCP Bridge remediation:** PR #95, main commit `d4fccbe135b51c41a5b668293e9c02b0db3a5147`  
**State:** `GREEN-REPO / RUNTIME-VALIDATION-PENDING`

This record follows the immutable live checkpoint in
[`runtime-acceptance-checkpoint-2026-08-09.md`](runtime-acceptance-checkpoint-2026-08-09.md).
It records the repository repair that became available after that checkpoint. It
does **not** retroactively change the live evidence captured there and does not
claim that the repaired Bridge has already been deployed or exercised by Hermes
Security Labs.

## Facts established from the Bridge repository

The live RTA-003 request had used the trust label `authorized-local-lab`.
Repository inspection of Hermes MCP Bridge 1.0.0 established that this is not a
member of the Bridge `TrustLabel` contract. The accepted values are:

- `trusted_policy`;
- `user_instruction`;
- `agent_proposal`;
- `tool_result`;
- `untrusted_content`;
- `unknown`.

The Bridge deliberately maps an unparseable trust label to
`untrusted_content`. That fail-closed behaviour caused the production policy to
classify the request as high risk and return `REQUIRE_APPROVAL`.

A second, independent defect then became material: the generic prompt/submit
policy path returned `approval_required=true`, but it did not create a bound
approval record or return a usable approval identifier. This is consistent with
the live observation `approval_id=null` and `execution_id=not-created` recorded
in RTA-003.

The invalid label is therefore a contract mismatch in the request metadata; it
is **not** a reason to weaken the policy or relabel a denied request merely to
make it execute. The approval issuance defect was repaired instead.

## Bridge remediation

Hermes MCP Bridge PR #95 introduced an internal fail-closed approval handoff for
policy-gated `hermes_prompt` and `hermes_submit` calls without changing the
public V1 tool contract.

The implementation:

1. binds an approval to the exact logical request using action, prompt digest,
   client request id, session/agent/orchestration values, expected actions,
   resource scopes and trust labels;
2. persists only an opaque request digest and sanitized metadata — never the raw
   prompt;
3. returns a stable, non-null approval identifier while the request is pending;
4. consumes an approved record against the exact resource fingerprint before
   delegation;
5. prevents a changed prompt, scope, trust label or action from reusing an old
   approval;
6. treats consumed approvals as non-replayable except for recovery of an already
   persisted idempotent execution mapping;
7. fails closed on rejected, expired, stale, mismatched or registry-error states.

No trust-label rule, policy decision or authorization boundary was weakened.
The V1 public contract remains Bridge `1.0.0`, schema `0.6.1`, with the existing
27-tool surface.

## Verification evidence

PR #95 completed successfully on Python 3.11 and 3.12, including compile, Ruff,
ShellCheck and the complete test suite. Its downstream image gate also passed:

- runtime image build;
- image provenance validation;
- isolated Docker acceptance;
- Trivy scan;
- CycloneDX SBOM generation and validation;
- retention of acceptance/SBOM evidence.

After merge, the exact Bridge main commit
`d4fccbe135b51c41a5b668293e9c02b0db3a5147` was independently revalidated by
the push CI. Both Python jobs and the complete image/isolated
acceptance/Trivy/SBOM job completed with `success`.

Repository-side remediation of the `approval_id=null` defect is therefore
`GREEN-REPO`.

## Runtime state after repository remediation

RTA-003 is **not** yet `RESOLVED-RUNTIME`.

The closure state is now:

`RTA-003 = REPO-FIX-MERGED / BLOCKED-ON-DEPLOY-AND-LIVE-VALIDATION`

A runtime pass is still required to prove that the live Hermes connector is
running the repaired Bridge and that the approval workflow behaves as intended.
The current ChatGPT execution context cannot use the Hermes MCP connector, so no
live deployment or acceptance claim is made from repository evidence alone.

RTA-002 remains independently open:

`RTA-002 = BLOCKED-ON-RUNTIME — KALI_MCP_NOT_REGISTERED`

No historical Kali MCP path or registration is promoted to authority until the
live host/runtime can be inspected through the legitimate Hermes path.

## Next executable runtime chain

When the Hermes MCP connector is again available, resume from evidence rather
than assumptions:

1. `hermes_health` and `hermes_readiness`;
2. confirm `gateway_state=running` and `accepting_new_work=true`;
3. inspect the live portal inventory read-only;
4. repeat the bounded local-runtime reconciliation with a stable
   `client_request_id` and contract-valid request metadata;
5. if policy returns `REQUIRE_APPROVAL`, require a non-null `approval_id`, use
   the normal audited approval response path, then retry the **exact** request;
6. inspect Kali MCP/container/configuration state read-only and determine the
   observed root cause of RTA-002;
7. correct RTA-002 only from that observed state;
8. perform core lab provision/readiness acceptance using canonical target IDs;
9. execute only a bounded, explicitly authorized seeded scenario after the
   typed runtime effect is supported;
10. capture correlated Evidence Plane records, reset, and prove known state.

No offensive execution is authorized by this remediation record itself.

## Decision record

**Decision:** accept the Bridge repository fix as `GREEN-REPO`, while keeping
RTA-003 runtime closure separate until the repaired build is observed live.

**Context:** repository tests can prove approval state-machine behaviour but
cannot prove which Bridge revision the live Hermes connector is serving.

**Alternatives considered:**

- mark RTA-003 resolved after CI — rejected as false runtime assurance;
- change the original trust label and retry to avoid approval — rejected because
  it would convert a contract mismatch into a policy-bypass pattern;
- repair the approval handoff and revalidate live later — accepted.

**Risks accepted:** runtime deployment may lag repository main; the live
connector may expose additional drift that repository CI cannot observe.

**Impact:** the repository blocker is removed without weakening authorization,
while the project preserves a strict distinction between repository proof and
runtime proof.

**State:** `DECISION`.
