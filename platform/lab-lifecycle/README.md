# Transactional Lab Lifecycle Protocol candidate

This directory contains the repository-level contract candidates for `SVP2-B-03` / issue #81.

## Boundary

The lifecycle candidate validates contracts and transition requests and returns deterministic allow/refuse decisions. The orphan assessor evaluates normalized read-only resource observations and returns `CLEAR`, `TRACKED_RESIDUE`, `ORPHANS_DETECTED` or `INCONCLUSIVE`. Neither path creates, attaches, starts, stops, resets, quarantines, deletes or destroys Docker resources, networks, volumes, processes, mounts or files.

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

## Read-only orphan assessment

`orphan_detector.py::assess_orphans()` is a repository-only assessor over the strict `orphan-observation.schema.json` input contract. It does **not** enumerate runtime resources itself. A future scanner must normalize runtime observations into opaque resource references before they reach this boundary.

The assessor is deliberately non-destructive:

- `cleanup_performed` is fixed to `false` in `orphan-assessment.schema.json`;
- no Docker API, socket, subprocess, shell, network or filesystem cleanup operation exists in the module;
- resource references are opaque identifiers and cannot contain raw paths or URI-like slash syntax;
- duplicate lab records and duplicate resource references fail closed;
- an `UNAVAILABLE` scan carrying observed resources is inconsistent and refused;
- a `PARTIAL` or `UNAVAILABLE` scan with no definite orphan can never produce `CLEAR`;
- definite orphan evidence remains `ORPHANS_DETECTED` even if the scanner reports `PARTIAL`;
- a complete scan containing only live quarantine-retention residue returns `TRACKED_RESIDUE`, never `CLEAR`, so retained residue cannot be confused with a zero-residue proof;
- `CLEAR` therefore means a complete scan with zero orphan findings and zero tracked quarantine residue.

A resource is classified as an orphan candidate when, for example:

- its `lab_id` is absent from lifecycle records;
- its campaign differs from the lifecycle record;
- it exists while the lab is only `DECLARED`;
- it remains after the lab reached `VERIFIED`;
- it belongs to an active-resource state whose contract has expired;
- a quarantined residue has no declared retention window or that window has expired.

Resources in `DESTROYING`, `ROLLING_BACK` or `VERIFYING_RESIDUE` are treated as cleanup-in-progress rather than immediately orphaned. Residue in `QUARANTINED` may be tracked until its explicit retention deadline as `TRACKED_RESIDUE`; this tracking never authorizes reuse and never counts as zero residue.

The assessment output exposes stable classification codes and opaque references only. `sanitized_summary()` exposes counts/codes without resource references.

This logic is **not** the periodic orphan detector runtime. Real resource enumeration, scheduler/cadence, scanner identity, observation authenticity and cleanup/remediation remain separate future capabilities.

## Status

- lifecycle contract and decision logic: `CANDIDATE`;
- zero-residue proof contract/validation: `CANDIDATE`;
- orphan observation/assessment contract and decision logic: `CANDIDATE`;
- runtime resource scanner: `NOT_IMPLEMENTED` / `NOT_RUN`;
- periodic orphan scan scheduler: `NOT_IMPLEMENTED`;
- orphan cleanup/remediation: `NOT_IMPLEMENTED` / `NOT_RUN`;
- Docker lifecycle integration: `NOT_RUN`;
- network-policy enforcement: `NOT_RUN`;
- zero-residue observation against real resources: `NOT_RUN`;
- runtime changes: `NO_RUNTIME_CHANGE`.
