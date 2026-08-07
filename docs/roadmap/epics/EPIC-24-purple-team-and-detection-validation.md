# EPIC-24 — Purple Team and detection validation

## 1. Metadata

| Field | Value |
| --- | --- |
| Concept epic ID | `EPIC-24` |
| Slug | `purple-team-and-detection-validation` |
| Pillar | `F` — Threat-Informed Validation |
| Phase | 7 |
| Priority | P1 |
| Delivery umbrella | `SVP2-F-02` (issue [#89](https://github.com/pestoura/hermes-security-labs/issues/89)) |
| Document version | 1.1.0 |
| Document date | 2026-08-07 |
| Catalogue | [Epic catalogue 45](../epic-catalogue-45.md) |
| Lifecycle contract | [Architecture documentation lifecycle](../../architecture/architecture-documentation-lifecycle.md) |

## 2. Current status

**IMPLEMENTING** — PR #153 integrated a repository-level Purple Team outcome contract. Defensive telemetry/SIEM/EDR integration and real containment/emulation remain `NOT_IMPLEMENTED` / `NOT_RUN`.

| Lifecycle state | Reached |
| --- | --- |
| INTENT | yes |
| IMPLEMENTING | yes |
| AS_BUILT | no |
| FINAL | no |

Implemented contract state:

- every emulation step resolves to exactly one of five explicit states: `PREVENTED`, `DETECTED`, `OBSERVED_NOT_DETECTED`, `DETECTED_NOT_ACTIONABLE`, `NOT_OBSERVED`;
- absence of observation can never be recorded as prevention or detection;
- prevention/detection outcomes require explicit evidence references;
- detected outcomes require non-negative time-to-detect;
- time-to-contain is represented as a non-negative measured duration when available;
- detection expectations may reference D3FEND techniques.

The current outcome taxonomy uses `NOT_OBSERVED` rather than an explicit `UNKNOWN` label for absent defensive telemetry, but preserves the intended fail-safe semantic: no observation is never converted into prevention/detection. Live defensive telemetry, SIEM/EDR connectors and containment actions remain unimplemented/unexecuted.

## 3. Problem and motivation

Offensive validation does not answer whether the defensive stack detected, alerted or blocked the behaviour.

## 4. Intended outcome

Every technique execution carries a detection expectation, and the outcome records prevented, detected, alerted or missed.

## 5. Scope and non-goals

### In scope

- Detection expectation model per technique
- Outcome taxonomy prevented/detected/alerted/missed
- Detection gap reporting
- Defensive mapping alignment

### Non-goals

- Modifying defensive tooling configuration automatically

## 6. Intent architecture

Detection expectations are declared alongside the runbook; the outcome is derived from defensive telemetry evidence, not from the offensive runner's own claim.

## 7. Contracts, data and capabilities

- Detection expectation record
- Detection outcome record

Contracts are canonical in Git. Where this epic reuses a platform-wide contract, the canonical definition lives in the [reference architecture](../../architecture/security-validation-reference-architecture.md) and in [EPIC-01](EPIC-01-architecture-and-canonical-contracts.md); this document references it instead of restating it.

## 8. Dependencies and sequencing

- [EPIC-23 — Attack Graph and Attack Flow](EPIC-23-attack-graph-and-attack-flow.md)
- [EPIC-11 — Technical observability](EPIC-11-technical-observability.md)

Sequencing follows the phase model in the [intent document](../../architecture/security-validation-platform-v2-intent.md). This epic is planned for phase 7.

## 9. Security, risks and failure modes

- Missing defensive telemetry recorded as success
- Expectation drift as detections change
- Offensive runner evidence being mistaken for independent defensive observation
- Missing telemetry connector coverage being interpreted as a real detection gap

Platform-wide invariants that this epic must not weaken:

- absence of evidence never produces a `PASS` verdict;
- no execution outside an active authorization contract;
- no secrets, tokens, cookies or raw credential material in documentation, telemetry or persisted evidence;
- no target outside registered laboratories.

## 10. Deliverables

- Purple team validation specification

## 11. Acceptance criteria

- Absent defensive telemetry yields UNKNOWN, not missed
- Every outcome cites the telemetry evidence used

The current contract satisfies the fail-safe intent through `NOT_OBSERVED` and evidence requirements for prevention/detection. A live defensive telemetry integration is still required before `AS_BUILT` or `FINAL`.

## 12. Evidence and validation plan

- Contract tests from PR #153
- Future defensive telemetry/SIEM/EDR integration evidence
- Future detection outcome matrix per campaign
- Future measured time-to-detect/time-to-contain observations

## 13. Decisions and open questions

### Decisions taken

- Detection/prevention claims require explicit evidence.
- Missing observation maps to `NOT_OBSERVED`, never to successful prevention/detection.
- Defensive outcome logic is deterministic and side-effect free.

### Open questions

- How to onboard defensive telemetry sources safely
- Whether `NOT_OBSERVED` should remain the canonical label or be mapped to an external `UNKNOWN` presentation state

## 14. Implementation notes

> Reserved. Populate during implementation with pull request references, deviations from intent, and decisions taken while building. Do not delete this heading.

- PR #153 integrated the Purple Team outcome contract candidate.
- Defensive telemetry/SIEM/EDR integration remains `NOT_IMPLEMENTED`.
- Containment actions and adversary emulation remain `NOT_RUN`.
- `NO_RUNTIME_CHANGE`.

## 15. As-built / final architecture

> Reserved. Populate when the delivery umbrella reaches completion. Must record what was actually built, evidence links, and every divergence from sections 6 to 11. No umbrella may be closed while this section is empty.

_Not final. Live defensive telemetry integration and real Purple Team execution remain NOT_IMPLEMENTED/NOT_RUN._

## 16. Document change log

| Date | Version | Change |
| --- | --- | --- |
| 2026-08-06 | 1.0.0 | Initial intent document created from the concept epic catalogue. |
| 2026-08-07 | 1.1.0 | Reconciled lifecycle to IMPLEMENTING against PR #153 while preserving defensive telemetry/runtime non-claims. |
