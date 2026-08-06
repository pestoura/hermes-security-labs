# ADR-0006 — Versioned source of truth and provenance

- **Status:** Accepted
- **Date:** 2026-08-06
- **Decision owners:** `SVP2-A-01`, `EPIC-01`
- **Supersedes:** none
- **Superseded by:** none

## Context

The platform depends on code, schemas, policies, runbooks, laboratory definitions, images and knowledge sources. Without an authoritative version and provenance chain, a result cannot be reproduced or associated with the configuration that produced it.

## Decision

Git is the canonical source of truth for versioned platform intent and implementation artefacts. Runtime state is derived from an identified commit and must be verifiable against it.

Every contract-bearing or executable artefact declares, as applicable:

- stable identifier and version;
- source location and owning epic or component;
- immutable commit, digest or source revision;
- compatibility information;
- provenance and promotion state;
- deprecation, revocation or supersession relationship.

Runtime drift is reported explicitly. It is never silently reconciled or treated as an accepted state.

## Consequences

### Positive

- results can reference the exact implementation and contract versions used;
- review history and ownership remain visible;
- deployment and runtime divergence can block unsafe execution;
- supersession does not erase prior decisions.

### Negative

- version and compatibility metadata must be maintained;
- derived runtime state cannot become a parallel source of truth;
- emergency changes require a controlled reconciliation path back to Git.

## Security implications

Unidentified or unverifiable artefacts are not trusted for execution or assurance. Secrets, raw evidence and transient runtime state remain outside Git even though their metadata may reference versioned contracts.

## Alternatives considered

1. **Runtime host as source of truth.** Rejected because local changes are weakly reviewable and difficult to reproduce.
2. **Issue descriptions as canonical specification.** Rejected because issues are work views and may diverge from repository content.
3. **Mutable image tags as deployment identity.** Rejected because they do not identify immutable content.

## Evidence and validation

Existing deployment tracking provides current-base commit and drift evidence. Later epics extend provenance to protocol contracts, capabilities, evidence and knowledge snapshots.

## Review triggers

Review when a new artefact class is introduced, a runtime is allowed to mutate declarative state, or a parallel configuration source is proposed.
