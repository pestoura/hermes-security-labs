# ADR-0011 — Assurance profiles for the first isolated L1 lab effect (proposal)

- **Status:** Proposed — **Em validação / EM_VALIDACAO, non-final, non-operative**
- **Date:** 2026-08-14
- **Decision owners:** `SVP2-A-01`, `EPIC-01`
- **Supersedes:** none
- **Superseded by:** none

> **Non-operative notice.** This record is a **proposal under validation**. It changes no policy,
> no template, no gate, no runtime code and no campaign state. `VAL-HSL-RUNNER-L1-LIVE-PROMOTION`
> remains `BLOCKED / HOLD`, with `promotion_allowed: false`, `runtime_status: NOT_RUN`,
> `execution_authority: none` and `default: deny`. Nothing in this document authorizes a live
> effect, a policy enablement, a trust binding or a target interaction. Acceptance of any option
> below would require a separate, explicitly authorized decision and its own change record.

## Context

The canonical promotion gate for the first live isolated L1 laboratory effect currently requires a
production-equivalent assurance stack in a single step. The recorded blockers include: an external
signer and purpose-bound public trust store; a durable WORM evidence backend; tenant isolation; an
audit sink; PRE/POST packages; the live effect itself; and a human-in-the-loop decision.

Observed facts on `origin/main` (post PR #363, base `7e686f8`):

- userns observation is `PASS` for the two reviewed PIDs; host identity and socket observations are
  `OBSERVED`; the Runner authorization trust store is `ABSENT` (single fail-closed finding);
- the unauthorized-peer refusal currently demonstrable is an `EACCES` at the DAC layer only. The
  canonical negative test requires an **enabled `SO_PEERCRED` identity mapping plus audit**, so DAC
  refusal is **insufficient** for campaign promotion and this ADR does not treat it as evidence of
  boundary enforcement;
- both HOLD boundaries (#354 Runner, #359 Execution Gateway) remain strictly non-executing.

The open architectural question is narrow: **is it over-coupled to require production-grade WORM
retention and multi-tenant isolation before the first controlled, single-tenant L1 lab effect?**
Compliance-grade retention and tenant separation protect properties (regulated immutability,
cross-customer confidentiality) that a single-tenant disposable lab does not yet exercise, while
identity, authorization and tamper-evidence protect properties that the first live effect *does*
exercise. Coupling all of them in one gate may delay the evidence needed to validate the boundary
itself, without adding proportional security value.

## Decision

**No decision is taken.** This ADR records the option space and a *recommended proposal* for later
human decision. Three options are compared.

### Option A — keep the strict production-equivalent promotion gate unchanged

Promotion of any live effect, including a single isolated L1 lab, requires the complete production
assurance stack: external signer/trust store, external WORM compliance backend, tenant isolation,
audit sink, PRE/POST packages, enabled `SO_PEERCRED` identity mapping with audit, and HITL.

### Option B — split assurance profiles (`LAB_L1` and `PROD`) — *proposed, not decided*

Two named assurance profiles with explicitly different, individually auditable requirement sets:

| Requirement | `LAB_L1` (controlled promotion) | `PROD` (unchanged) |
| --- | --- | --- |
| Authorization signer | external signer + public purpose-bound trust store, `private_key_local: false` | identical, unchanged |
| Peer identity | enabled `SO_PEERCRED` identity mapping **with audit**; DAC-only refusal never accepted | identical, unchanged |
| Evidence integrity | local tamper-evident, content-addressed store with append-only hash chain and sealed packages | external WORM compliance backend |
| Retention class | non-compliance, lab-scoped, expiry documented | regulated retention, compliance-attested |
| Tenancy | single-tenant lab boundary, declared and machine-checked | tenant isolation required |
| Audit sink | local append-only sink, integrity-verified | external durable audit sink |
| PRE/POST packages | required, sealed, hash-linked | required |
| HITL | required | required |
| Blast radius | one disposable isolated L1 lab, egress denied | production scope |

`PROD` requirements are **not weakened**. `LAB_L1` is an additional, narrower profile whose scope is
bounded by the isolation invariants of ADR-0005 and whose evidence classification follows ADR-0007.

### Option C — simulation-only until the full production stack exists

No live effect at all; the boundary is exercised only through simulated dispatch and static
evidence until every production blocker is closed.

## Consequences

### Positive

- **A** — one gate, one posture; no risk of a lab profile being mistaken for production assurance;
  no schema, profile or reviewer-training cost.
- **B** — allows the identity/authorization boundary to be validated by real evidence early, while
  keeping compliance retention and tenancy where they matter; keeps the two axes (acceptance vs
  promotion) visibly separate; produces sealed, hash-chained artefacts that are portable to a WORM
  backend later; suitable for MVP because it removes the two heaviest, least lab-relevant blockers
  without removing any identity or authorization control.
- **C** — zero live risk; fully deterministic; no new profile machinery.

### Negative

- **A** — the first real evidence about the boundary arrives only after the most expensive
  components exist; long feedback loop; higher chance that a design flaw is found late and
  invalidates work; sustained `HOLD` with no empirical validation of `SO_PEERCRED` + audit.
- **B** — introduces a second assurance vocabulary, which is a governance risk: profile confusion,
  scope creep of `LAB_L1` into production-adjacent work, and a real migration obligation for
  evidence produced under the local store. Requires machine-checked profile declaration and a
  fail-closed default (`PROD` when the profile is absent or unparsable).
- **C** — simulation cannot produce the peer-identity, audit-sink or evidence-sealing evidence the
  campaign requires; risk of a permanently deferred boundary and of accumulating unvalidated
  assumptions; least MVP-suitable.

## Security implications

- No option may accept DAC-layer `EACCES` as the canonical negative test. Under every option the
  negative test requires an **enabled** `SO_PEERCRED` identity mapping and an audit record.
- Under **B**, evidence integrity moves from "external immutability guarantee" to "local
  tamper-evidence": an attacker with sufficient local privilege can destroy or truncate the chain,
  but cannot silently alter sealed content without breaking hash linkage. This is a *detectability*
  guarantee, not a *durability* guarantee, and must be stated in every artefact produced under
  `LAB_L1`.
- Under **B**, single-tenant status must be an enforced precondition, not an assumption; any
  multi-tenant or shared-target scenario falls under `PROD`.
- Raw evidence remains out of Git under every option (ADR-0007). Trust stores are external-only and
  private keys are never generated in-repo.
- Fail-safe evaluation (ADR-0004) is unchanged: absent, unparsable or unverifiable evidence never
  yields a successful verdict, in any profile.

## Complexity, cost and MVP suitability

| Criterion | A | B | C |
| --- | --- | --- | --- |
| Security posture at first live effect | highest | high (identity/authorization intact) | n/a (no live effect) |
| Auditability | compliance-grade | tamper-evident + sealed, migratable | static only |
| Implementation complexity | low (no change) | moderate (profiles, hash chain, sealing, profile gate) | low |
| Cost to first evidence | high | moderate | none, but no evidence produced |
| MVP suitability | low | high | low |
| Main risk | late discovery of design flaws | profile confusion / scope creep | permanent deferral |

## Migration path if Option B were later accepted

1. define the profile vocabulary and a strict schema; default to `PROD` fail-closed when absent;
2. specify the content-addressed evidence layout, hash-chain and sealing format so it is a strict
   subset of the future WORM ingestion contract;
3. require the `LAB_L1` declaration to carry the single-tenant boundary, expiry and non-compliance
   retention class;
4. keep the canonical negative test (enabled `SO_PEERCRED` + audit) identical across profiles;
5. on WORM availability, ingest sealed `LAB_L1` packages by hash without rewriting them, and record
   the migration as provenance rather than re-derivation;
6. no `LAB_L1` result is ever promoted to a `PROD` assurance claim by re-labelling.

## Recommendation (proposal only)

**Option B is proposed**, subject to human decision. Rationale: it removes the two blockers whose
security relevance to a single disposable lab is weakest (regulated WORM durability, multi-tenant
isolation) while keeping every identity, authorization, audit and tamper-evidence control that the
first live effect actually exercises. It is explicitly *not* adopted here, and Option A remains the
current gate until a separate authorized decision says otherwise.

## Alternatives considered

1. **Option A — unchanged strict gate.** Retained as the status quo and as the fallback if profile
   governance cannot be made machine-checkable.
2. **Option C — simulation-only.** Rejected as a *proposal* because it cannot produce the required
   peer-identity and audit evidence; retained as a valid conservative choice if any residual risk of
   live effect is judged unacceptable.
3. **Weaken the negative test to DAC refusal.** Rejected outright: it does not demonstrate identity
   mapping or audit, and would silently lower the boundary claim.
4. **Local-only signing key for the lab profile.** Rejected outright: private-key custody must stay
   external in every profile.

## Evidence and validation

This ADR is documentation only. It cites the repository state at base `7e686f8` and the sanitized
observation evidence already recorded under `CHG-HSL-038`. It introduces no test of runtime
behaviour, changes no gate and produces no promotion evidence. Repository validation for this record
is limited to documentation and source-of-truth integrity tests.

Companion analysis: [Lab assurance signer requirements (provider-neutral)](../lab-assurance-signer-requirements.md).

## Review triggers

Review when: a human decision is taken on the profile split; the external signer or trust-store
availability changes; a WORM or audit-sink backend becomes available; any multi-tenant scenario is
introduced; or the canonical negative test definition changes.
