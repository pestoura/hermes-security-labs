# Lab Schema v2 and Registry — contract candidate

Repository-owned contract candidate for `SVP2-I-01`.

## Implemented guarantees

- lab types cover fixture, single-service, multi-service, attack-path, Kubernetes, VM, identity, cloud sandbox and external hardware;
- labs are organized by family and variant rather than one lab per vulnerability;
- every family declares `VULNERABLE`, `MITIGATED` and `FIXED` states;
- every state declares both positive and negative controls;
- privileged mode, host networking, Docker socket access and host mounts are forbidden by contract;
- egress defaults to deny and explicit allowlists are bounded;
- resource limits and TTL are mandatory;
- generated or untrusted labs require isolated build status;
- deterministic reset is represented by a stable reset fingerprint;
- cleanup proof and maturity L0-L5 are explicit registry attributes;
- lab selection is deterministic over family, state, type and required capabilities.

## Deliberate non-claims

No container, VM, Kubernetes cluster, cloud sandbox or external hardware lab is started, reset or destroyed by this block. Runtime isolation and cleanup remain `NOT_RUN`.

`NO_RUNTIME_CHANGE`.
