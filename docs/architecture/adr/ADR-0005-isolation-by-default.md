# ADR-0005 — Isolation by default

- **Status:** Accepted
- **Date:** 2026-08-06
- **Decision owners:** `SVP2-A-01`, `EPIC-01`
- **Supersedes:** none
- **Superseded by:** none

## Context

Security laboratories intentionally contain vulnerable services and potentially intrusive tooling. Convenience defaults such as shared networks, permanent egress or broad host access would turn a controlled laboratory into an operational risk.

## Decision

Isolation is the default posture:

- one dedicated network context per active laboratory;
- no egress unless an explicit versioned profile permits named destinations or classes;
- no `privileged` containers, host networking, Docker socket, broad host mounts or unrelated host resources;
- target publication, when required, is restricted to loopback;
- execution runtimes attach only for the authorized laboratory step and detach during cleanup;
- cleanup is idempotent and failure to prove the expected terminal state prevents reuse.

Exceptions require an explicit contract, recorded justification, bounded duration and stronger approval appropriate to their impact.

## Consequences

### Positive

- limits cross-laboratory and host exposure;
- makes network intent reviewable;
- reduces residual state between campaigns;
- provides a stable basis for later lifecycle and domain expansion.

### Negative

- some tools or laboratories require additional network design;
- strict egress controls may expose undocumented external dependencies;
- cleanup proof adds operational work.

## Security implications

An absent policy is interpreted as isolated, not unrestricted. A cleanup failure results in failure or quarantine, never silent success. Domain expansion must demonstrate equivalent isolation before activation.

## Alternatives considered

1. **Shared project network.** Rejected because it creates unintended reachability.
2. **Permanent egress with monitoring.** Rejected because observation does not replace prevention.
3. **Privileged runtime for compatibility.** Rejected because it expands host compromise impact.

## Evidence and validation

Later runtime epics must provide network inspection, negative reachability tests, lifecycle idempotency and zero-residue evidence. This ADR does not claim those controls are fully implemented today.

## Review triggers

Review before any new runtime, external hardware integration or proposed exception to the prohibited host-access controls.
