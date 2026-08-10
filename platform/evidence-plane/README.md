# Evidence Plane v2 — contract candidate

This directory contains the repository-owned Evidence Plane contract candidate and the narrow
custody bridges that project Runner evidence into it.

## Guarantees implemented in this block

- every evidence record carries campaign, run, step and attempt correlation IDs;
- payload integrity is represented by a lowercase SHA-256 digest and byte count;
- evidence is explicitly classified as `raw`, `restricted`, `sanitized` or `summary`;
- `sanitized` and `summary` records require a parent record and redaction lineage;
- raw and restricted evidence are not exportable by the default sharing policy;
- record metadata refuses secret-bearing fields, raw commands and raw stdout/stderr;
- replay descriptors contain identifiers, provenance and hashes only, never payload bytes;
- derived evidence chains fail closed when source hashes do not match the parent payload digest;
- terminal Runner outcomes can be projected through `runner_outcome_custody.py` without a parallel evidence store;
- sanitized Runner dispatch-audit events can be projected through `dispatch_audit_custody.py` into the **same Evidence Plane store**, again without a parallel audit datastore.

## Runner terminal-outcome custody

`runner_outcome_custody.py` persists a validated terminal Runner outcome through the existing
execution-scoped evidence bridge. Its canonical policy remains `DISABLED / NOT_RUN`. Exact logical
retries reuse the original execution identity, so custody replay does not imply a second target
effect.

## Runner dispatch-audit custody

`dispatch_audit_custody.py` accepts only a schema-valid event from the Runner dispatch audit
contract and verifies its deterministic event fingerprint before persistence.

The bridge:

- requires an injected canonical Evidence Plane store with `put` and integrity `verify` methods;
- never creates or instantiates its own datastore;
- stores the complete audit event as `restricted` evidence, so it is not exportable by the default sharing policy;
- carries principal/correlation/TB1 binding inside the content-addressed audit event while keeping raw target values and operation parameters out of that event;
- uses the existing `evidence://` namespace and correlation tuple;
- derives retention from the audit occurrence timestamp plus the policy retention period;
- verifies the Evidence Plane record after persistence;
- produces the same evidence ID on an exact replay of the same audit occurrence in the canonical local reference store.

The canonical `dispatch-audit-policy.yaml` is deliberately:

- `state: DISABLED`;
- `default: deny`;
- `runtime_status: NOT_RUN`;
- `execution_authority: none`;
- classification `restricted`;
- raw application payload inclusion disabled.

This closes the **repository custody path** for the audit event. It does not prove a production
durable/append-only/WORM backend, live audit delivery or retention enforcement.

## Deliberate non-claims

This block does **not** implement or validate a production evidence store, encryption at rest,
WORM/immutable storage, retention deletion, production redaction, production replay, object
storage or customer evidence export.

In particular, `LocalEvidenceStore` remains a controlled reference backend. Content-addressed
objects, exclusive immutable creates and integrity sidecars are useful repository/CI guarantees,
but they are **not** a production WORM/durability claim against an actor with write access to the
entire store.

Production audit/evidence durability and live sink observation remain `NOT_IMPLEMENTED / NOT_RUN`
until exercised against the selected backend.

`NO_RUNTIME_CHANGE`.
