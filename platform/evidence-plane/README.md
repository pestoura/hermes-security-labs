# Evidence Plane v2 — contract candidate

This directory contains the repository-owned contract candidate for `SVP2-D-01`.

## Guarantees implemented in this block

- every evidence record carries campaign, run, step and attempt correlation IDs;
- payload integrity is represented by a lowercase SHA-256 digest and byte count;
- evidence is explicitly classified as `raw`, `restricted`, `sanitized` or `summary`;
- `sanitized` and `summary` records require a parent record and redaction lineage;
- raw and restricted evidence are not exportable by the default sharing policy;
- record metadata refuses secret-bearing fields, raw commands and raw stdout/stderr;
- replay descriptors contain identifiers, provenance and hashes only, never payload bytes;
- derived evidence chains fail closed when source hashes do not match the parent payload digest.

## Deliberate non-claims

This block does **not** implement or validate a production evidence store, encryption at rest, WORM/immutable storage, retention deletion, production redaction, production replay, object storage or customer evidence export.

Those capabilities remain `NOT_IMPLEMENTED` or `NOT_RUN` until exercised against the selected runtime and storage backend.

`NO_RUNTIME_CHANGE`.
