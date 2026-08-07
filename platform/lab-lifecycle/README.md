# Transactional Lab Lifecycle Protocol candidate

This directory contains the contract-only first block for `SVP2-B-03` / issue #81.

## Boundary

The candidate validates lifecycle contracts and transition requests and returns a deterministic allow/refuse decision. It does not create, attach, start, stop, reset or destroy Docker resources, networks, volumes, processes or files.

## Fail-closed properties

- only declared state transitions are accepted;
- start and ready transitions require an effective network observation;
- the default network profile is isolated with deny-all egress;
- restricted egress is limited to explicit, owned, approved and time-bounded exceptions;
- open egress, shared networks, privileged mode, host networking, Docker socket and host mounts are forbidden;
- L3/L4 contracts require snapshot and rollback references;
- destroy/rollback cannot reach `VERIFIED` without a complete zero-residue proof;
- missing, partial, unavailable, mismatched or non-zero residue evidence yields `QUARANTINED`, never `PASS`;
- quarantined laboratories cannot be reused;
- decisions contain identifiers and stable codes only.

## Status

- lifecycle contract and decision logic: `CANDIDATE`;
- Docker lifecycle integration: `NOT_RUN`;
- network-policy enforcement: `NOT_RUN`;
- zero-residue observation against real resources: `NOT_RUN`;
- periodic orphan detector: `NOT_IMPLEMENTED`;
- runtime changes: `NO_RUNTIME_CHANGE`.
