# ADR-0009 — Runtime source of truth and drift semantics

- **Status:** Accepted
- **Date:** 2026-08-06
- **Decision owners:** `SVP2-A-01`, `EPIC-02`
- **Supersedes:** none
- **Superseded by:** none

## Context

The repository already contains a runtime registry, rollout plan, runtime profiles,
laboratory manifests and deployment tracking. Applied state and host observations are
necessary evidence, but allowing them to become desired state would create parallel and
unreviewed sources of truth.

The epic also requires a stable decision for image identity. Repeating a digest in every
environment would create unnecessary duplication and inconsistent updates; omitting an
identity when a release requires one would make reproducibility unverifiable.

## Decision

`platform/registry.yaml` is the canonical catalogue root for runtime declarations. It
references, rather than duplicates, the authoritative rollout plan, runtime profiles,
environment manifests, runtime templates and their schemas.

The following are explicitly non-authoritative:

- `.deployment.json` applied-state records;
- live host/container/network observations;
- issue descriptions and comments;
- generated, cached and temporary output.

They may prove or challenge the declared state, but cannot redefine it.

Drift has exactly three states:

- `IN_SYNC` — sufficient valid observation proves equality with the expected declaration;
- `DRIFT_DETECTED` — sufficient valid observation proves a material difference;
- `UNKNOWN` — observation is missing, malformed, stale, incompatible or otherwise
  unverifiable.

Automatic reconciliation is forbidden. Drift requires explicit review and a deliberate
Git change, deployment or rollback.

Image digests are owned by an immutable **runtime release**, not copied into each
environment manifest. An environment references the applicable release/profile. An image
release declared `PINNED` requires a valid `sha256` digest. A missing required digest maps
to `UNKNOWN`, not to a presumed current or safe state. Existing host-level runtime profiles
that do not themselves identify a container image use `NOT_APPLICABLE`; this does not waive
digest requirements for laboratory or runner image releases.

## Consequences

### Positive

- desired state remains reviewable and versioned in Git;
- observation cannot silently overwrite intent;
- missing evidence cannot become a false green;
- runtime profile metadata has one schema and one authoritative file;
- image identity is reusable and consistent across environments.

### Negative

- drift is not self-healing;
- runtime releases need an explicit manifest before they can be declared pinned;
- historical local state may remain `UNKNOWN` until sufficient evidence is collected;
- catalogue changes require coordinated repository updates.

## Security implications

- observed secrets or raw runtime output are not copied into Git;
- unsafe paths, duplicate identifiers, orphan profiles and unresolved runtime references
  fail repository validation;
- an `UNKNOWN` result blocks claims of synchronization or reproducibility;
- issue comments and local emergency edits never acquire configuration authority.

## Alternatives considered

1. **Treat `.deployment.json` as desired state.** Rejected because it is generated applied
   evidence and may be absent, stale or locally modified.
2. **Use the live host as source of truth.** Rejected because host state is weakly reviewed,
   mutable and difficult to reproduce.
3. **Pin image digests per environment.** Rejected because it duplicates release identity and
   permits environments referring to the same release to diverge.
4. **Automatically reconcile drift.** Rejected because an incorrect desired declaration or
   observation could cause uncontrolled runtime changes.

## Evidence and validation

- `platform/registry.yaml` contains the machine-readable policy and references;
- `platform/schemas/runtime-profile.schema.json` validates runtime profiles;
- `platform/scripts/validate_source_of_truth.py` validates uniqueness, paths, references and
  fail-safe drift policy;
- positive and negative tests are executed by the repository CI workflow;
- the existing deployment comparator remains unchanged and continues to report tri-state
  outcomes.

## Review triggers

Review when a new authoritative artefact class is introduced, runtime release manifests are
implemented, a consumer proposes local override authority, or drift remediation becomes an
operational requirement.
