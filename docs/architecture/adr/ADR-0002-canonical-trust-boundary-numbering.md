# ADR-0002 — Canonical trust-boundary numbering

- **Status:** Accepted
- **Date:** 2026-08-06
- **Decision owners:** `SVP2-A-01`, `EPIC-01`
- **Supersedes:** the conflicting TB0–TB4 labels in the initial reference architecture
- **Superseded by:** none

## Context

Two intent documents used TB0–TB4 differently. The initial reference architecture labelled architectural planes and contexts as trust boundaries, while the platform intent labelled the crossings between actors and planes. A trust boundary is meaningful at the point where identity, authority, data or execution context crosses between trust domains, so both models cannot remain canonical.

## Decision

The canonical numbering describes **crossings**, not components:

| Boundary | Crossing |
| --- | --- |
| `TB0` | operator ↔ control plane |
| `TB1` | control plane ↔ execution plane |
| `TB2` | execution plane ↔ target/laboratory plane |
| `TB3` | execution plane ↔ evidence plane |
| `TB4` | evidence plane ↔ publication and external consumers |

GitHub remains the source-of-truth context, but is not assigned a numbered trust boundary in this model. Repository-to-control-plane integrity is governed through versioned artefacts, reviewed changes, deployment verification and drift detection.

Each boundary must declare:

- responsibilities on both sides;
- prohibited actions;
- accepted contract and validation requirements;
- fail-safe behaviour when validation cannot be completed.

## Consequences

### Positive

- diagrams and contracts refer to the same crossings;
- boundary controls can be tested independently;
- source-of-truth integrity is no longer confused with an execution trust crossing.

### Negative

- existing diagrams and references using the former numbering must be updated;
- historical documents may retain the old model and must be identified as superseded rather than silently treated as current.

## Security implications

Every boundary defaults to refusal or restricted handling when identity, contract, classification or integrity validation is missing. Crossing a boundary never grants broader authority than the originating active contract.

## Alternatives considered

1. **Retain plane-based numbering.** Rejected because a component is not itself a crossing.
2. **Introduce two independent TB numbering schemes.** Rejected because duplicate identifiers would remain ambiguous.
3. **Rename boundaries without numbers.** Rejected because stable identifiers are needed by schemas, tests, ADRs and evidence.

## Evidence and validation

The reference architecture contains one canonical TB0–TB4 table with responsibilities, prohibitions, contracts and fail-safe rules. Documentation tests prevent duplicate or missing canonical identifiers.

## Review triggers

Review when a new external trust domain is introduced or an existing crossing is split into materially different security contexts.
