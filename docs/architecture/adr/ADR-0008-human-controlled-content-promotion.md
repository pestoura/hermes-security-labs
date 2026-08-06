# ADR-0008 — Human-controlled content promotion

- **Status:** Accepted
- **Date:** 2026-08-06
- **Decision owners:** `SVP2-A-01`, `EPIC-01`
- **Supersedes:** none
- **Superseded by:** none

## Context

Campaign evidence and knowledge sources can identify coverage gaps and generate candidate runbooks, laboratories, mappings or detections. Automatically accepting generated content would allow unreviewed logic or unsafe assumptions to enter the execution and assurance paths.

## Decision

Automated systems may generate, enrich, rank and test **proposals**, but promotion into an accepted catalogue requires recorded human review.

Promotion requires, according to content type:

- declared source and generation provenance;
- schema and policy validation;
- positive and negative controls;
- reproducibility evidence;
- security and licensing review where external content is involved;
- explicit reviewer decision;
- immutable accepted version or digest.

Generated content is never auto-merged. Rejection, quarantine, supersession and retirement remain explicit lifecycle states.

## Consequences

### Positive

- automation increases coverage without becoming an authorization authority;
- accepted content has accountable review and evidence;
- duplicate, unsafe or low-confidence proposals can be quarantined.

### Negative

- review capacity can become a delivery bottleneck;
- candidate queues require prioritization and retirement;
- generated content may remain unaccepted despite technically passing basic tests.

## Security implications

A proposal cannot execute merely because it was generated or tested. External proof-of-concept material remains untrusted until separately reviewed, isolated and approved by the applicable future provider policy.

## Alternatives considered

1. **Automatic merge after CI.** Rejected because CI does not establish authorization, semantic safety or business relevance.
2. **Automatic promotion based on confidence score.** Rejected because confidence is evidence for review, not authority.
3. **Disable generation entirely.** Rejected because controlled proposals can provide meaningful coverage value.

## Evidence and validation

Future content factories must record reviewer identity, decision, evidence and promotion state. Repository controls continue to require pull requests and green CI for accepted changes.

## Review triggers

Review when promotion authority, generated artefact classes or external content ingestion rules change.
