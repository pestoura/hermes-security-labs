# ADR-0004 — Fail-safe evaluation

- **Status:** Accepted
- **Date:** 2026-08-06
- **Decision owners:** `SVP2-A-01`, `EPIC-01`
- **Supersedes:** none
- **Superseded by:** none

## Context

Security validation can fail because a target is unreachable, a capability is missing, a runner times out, evidence is malformed or cleanup is incomplete. Treating these conditions as absence of a vulnerability would create false assurance.

## Decision

Evaluation is fail-safe:

- missing, empty, malformed, stale or unverifiable evidence never produces a successful security verdict;
- tool, runtime, target and prerequisite failures remain distinct outcomes;
- an evaluator may emit a conclusive result only when the required evidence contract is satisfied;
- technical execution status and security verdict are separate fields;
- unsupported or indeterminate conditions produce an explicit inconclusive state, not an inferred pass.

The normalized outcome vocabulary may evolve through versioned contracts, but it must preserve the distinction between secure evidence, vulnerable evidence and inability to decide.

## Consequences

### Positive

- operational failures cannot be converted into false assurance;
- evidence requirements become testable;
- users can distinguish remediation success from an unavailable test.

### Negative

- the platform may report more inconclusive outcomes until capabilities mature;
- evidence contracts and negative tests add implementation effort.

## Security implications

Evaluation logic must check degraded execution conditions before criteria that infer a secure result from absent signals. Errors and diagnostics must be sanitized and must not expose secrets.

## Alternatives considered

1. **Best-effort success when no finding is observed.** Rejected because no observation is not proof of security.
2. **Single boolean pass/fail result.** Rejected because operational inability to test is neither pass nor fail.
3. **Runner-selected final verdict.** Rejected because execution and assurance responsibilities must remain separated.

## Evidence and validation

Dependent implementations require regression tests for empty output, invalid JSON, timeout, missing capability, unreachable target and partial evidence, plus an unchanged valid-success path.

## Review triggers

Review when a new outcome state is introduced or any component proposes mapping a technical error to a successful security verdict.
