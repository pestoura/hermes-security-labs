# Release maintenance governance

`hermes-security-labs` adopts JDS-002 for post-baseline change, validation and controlled runtime-promotion governance.

## Product invariants

- Hermes remains the sole execution-authorization authority.
- Repository acceptance never grants target-interacting execution authority.
- Generic execution remains forbidden.
- A Runner effect requires verified authorization plus exact campaign/run/step, operation, capability, intrusiveness, parameter and target binding.
- Canonical transport, resolver and routing policies remain independent promotion gates.
- A target effect is not complete until outcome custody/evidence and reset/known-state evidence are retained where required.
- `PASS-REPO`, `GREEN-REPO`, `NOT_RUN` and live acceptance are distinct states.
- Functional corrections after candidate evidence create a new candidate identity; non-blocking improvements may be deferred.

## Change flow

```text
repository candidate
  -> validation campaign
  -> observation
  -> CHG-HSL-* when remediation is required
  -> bounded implementation lane
  -> security/platform gates
  -> repository revalidation
  -> controlled runtime promotion
  -> authorized target effect
  -> evidence custody
  -> reset / known state
  -> live verification
```

JDS-002 governs the transversal record lifecycle. TB1, Runner Protocol, target registry, adapter registry, transport/routing policy and lab-specific acceptance remain authoritative for execution safety.
