# ADR-0003 — Typed contracts over generic execution

- **Status:** Accepted
- **Date:** 2026-08-06
- **Decision owners:** `SVP2-A-01`, `EPIC-01`
- **Supersedes:** none
- **Superseded by:** none

## Context

A generic command surface is difficult to authorize granularly, validate before execution and correlate with expected evidence. It also permits implementation details to become an undocumented public contract.

## Decision

Cross-plane execution uses versioned, typed contracts. Each executable operation declares at least:

- operation identifier and contract version;
- validated input and output schemas;
- required capability and runtime profile;
- maximum intrusiveness level;
- expected side-effect class;
- timeout and cancellation behaviour;
- evidence classes produced;
- normalized refusal and error outcomes.

Generic command execution is not part of the normal platform profile. A future diagnostic exception, if approved, must be separately profiled, policy-restricted and fully audited.

## Consequences

### Positive

- authorization can target a declared operation instead of arbitrary text;
- compatibility and capability checks occur before dispatch;
- evidence and error handling become predictable;
- runners can evolve behind a stable protocol.

### Negative

- capabilities must be modelled before use;
- unsupported operations may temporarily remain unavailable;
- schema versioning and compatibility require maintenance.

## Security implications

Invalid, unknown or incompatible contracts are refused without partial execution. Input validation never expands scope, and errors do not echo secrets or raw command material.

## Alternatives considered

1. **Allowlisted command strings.** Rejected because argument semantics and side effects remain weakly defined.
2. **Shell templates with variable substitution.** Rejected because safe composition and complete authorization are difficult to prove.
3. **Generic command as the primary interface.** Rejected because it prevents capability-level governance.

## Evidence and validation

This ADR establishes the architectural contract only. Gateway and runner enforcement are delivered by dependent epics and require positive and negative contract tests.

## Review triggers

Review when an implementation proposes an untyped execution path or a contract change affects consumers in another plane.
