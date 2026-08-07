# Domain Expansion — contract candidate

Repository-owned contract candidate for `SVP2-L-01`.

## Implemented guarantees

- Kubernetes profiles require a unique disposable cluster identity, ephemeral kubeconfig and demonstrated cleanup lifecycle before eligibility;
- identity/Active Directory profiles require snapshot/rollback semantics, resource budgets and cleanup evidence;
- cloud profiles require ephemeral credentials, explicit budget and TTL;
- mobile profiles require an explicit device lifecycle and bounded analysis sidecars;
- IoT/OT profiles distinguish simulator-only operation from external hardware interaction;
- external hardware interaction requires explicit human approval;
- no domain becomes activation-eligible without demonstrated cleanup lifecycle;
- `activation_eligible` is only a contract decision and never means the domain has been activated in runtime.

## Deliberate non-claims

No Kubernetes cluster, VM, Active Directory domain, cloud account, mobile device, MobSF sidecar, USB device, simulator or external hardware is started or accessed by this block.

`NO_RUNTIME_CHANGE`.
