# ADR-0001 — Plane separation and authorization authority

- **Status:** Accepted
- **Date:** 2026-08-06
- **Decision owners:** `SVP2-A-01`, `EPIC-01`
- **Supersedes:** none
- **Superseded by:** none

## Context

The platform combines planning, security execution, evidence and knowledge. If one component can propose, authorize, execute and attest the same action, there is no independent control boundary and audit conclusions become circular.

## Decision

The platform separates responsibilities as follows:

- the **knowledge plane proposes** validation work;
- **Hermes, as control plane, authorizes and orchestrates** work;
- the **execution plane executes** only typed, bounded requests;
- the **evidence plane attests** observed outcomes;
- the **assurance functions evaluate** evidence and produce findings or reports.

Hermes is the only authorization authority. The execution plane may validate an authorization reference and refuse a request, but it may not create, expand or approve authorization.

No component may simultaneously hold proposal, authorization, execution and attestation authority for the same step.

## Consequences

### Positive

- authorization and execution remain independently auditable;
- knowledge-derived proposals cannot self-authorize;
- execution failures cannot be hidden by self-attestation;
- later protocol and evidence contracts have a stable ownership model.

### Negative

- every cross-plane request needs an explicit contract and correlation data;
- additional refusal and hand-off states must be designed;
- temporary shortcuts that bypass Hermes are not compatible with the target architecture.

## Security implications

- a missing or invalid authorization reference causes refusal before execution;
- knowledge services remain non-executable;
- evidence producers cannot assign a final assurance verdict to their own output;
- secrets and raw evidence are not transferred through proposal interfaces.

## Alternatives considered

1. **Single orchestration and execution service.** Rejected because it combines authorization and execution authority.
2. **Execution plane authorizes from local policy.** Rejected because local policy may restrict an authorization but must not create one.
3. **Knowledge service directly schedules runners.** Rejected because recommendations would become executable without control-plane approval.

## Evidence and validation

- canonical responsibilities are defined in the reference architecture;
- documentation tests verify the decision index and boundary contract;
- runtime enforcement is delivered by later epics and is not claimed by this ADR.

## Review triggers

Review when a component gains a new plane responsibility, an authorization flow changes, or a future implementation appears to bypass Hermes.
