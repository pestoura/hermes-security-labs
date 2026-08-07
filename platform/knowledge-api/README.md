# Security Knowledge API — contract candidate

Repository-owned contract candidate for `SVP2-E-02`.

## Implemented guarantees

- every query is bound to an immutable knowledge snapshot identifier;
- every query declares a minimum confidence threshold in the closed interval `[0,1]`;
- campaign records persist the exact knowledge snapshot used for planning;
- EPSS, KEV and VEX temporal observations are represented as append-only time series entries;
- campaign proposals are planning artefacts only and are never executable;
- executable authorization remains exclusively in the control plane;
- proposal payloads reject command-shaped execution fields.

## Deliberate non-claims

No HTTP service, database, graph query engine, external feed synchronization or production campaign planner is deployed by this block. Runtime API serving, persistence and production temporal-series ingestion remain `NOT_RUN` or `NOT_IMPLEMENTED`.

`NO_RUNTIME_CHANGE`.
