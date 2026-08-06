# ADR-0007 — Evidence classification and controlled publication

- **Status:** Accepted
- **Date:** 2026-08-06
- **Decision owners:** `SVP2-A-01`, `EPIC-01`
- **Supersedes:** none
- **Superseded by:** none

## Context

Security evidence may contain target details, credentials, tokens, response bodies, paths or operational information that is necessary for investigation but inappropriate for general sharing. Treating all evidence as one class creates either excessive exposure or insufficient auditability.

## Decision

Evidence is separated by classification and derivation:

- **raw** — original restricted material retained only where necessary;
- **restricted** — normalized material still containing sensitive operational context;
- **sanitized** — redacted derivative suitable for authorized collaboration;
- **summary** — minimal result and limitation information suitable for reporting.

Publication is a separate trust-boundary crossing (`TB4`). It requires classification validation, contextual redaction and provenance linking the derivative to its source without embedding the source content.

Raw evidence is never committed to Git and is not published directly. Sanitization does not modify or replace the retained source record.

## Consequences

### Positive

- preserves audit material while reducing disclosure;
- makes publication an explicit controlled action;
- supports different retention and access policies;
- allows reports to cite evidence without reproducing sensitive content.

### Negative

- derivation and retention metadata add complexity;
- contextual redaction requires tests beyond pattern matching;
- storage and access controls differ by class.

## Security implications

Tokens, passwords, cookies, authorization headers, private keys and unnecessary personal data are prohibited from sanitized and summary evidence. A failed classification or redaction step blocks publication.

## Alternatives considered

1. **Persist sanitized evidence only.** Rejected because investigation and replay may require restricted source material.
2. **Encrypt and publish raw evidence.** Rejected because encryption does not remove inappropriate distribution or access risk.
3. **Use one retention policy for all evidence.** Rejected because sensitivity and operational need differ by class.

## Evidence and validation

Evidence Plane v2 and redaction epics must implement classification, derivation links, access controls and negative leakage tests. This ADR establishes the canonical ownership and publication boundary.

## Review triggers

Review when a new evidence class, external consumer or retention requirement is introduced.
