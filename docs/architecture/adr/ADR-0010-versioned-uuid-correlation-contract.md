# ADR-0010 — Versioned UUID correlation contract

- **Status:** Accepted
- **Date:** 2026-08-07
- **Decision owners:** `SVP2-B-01`, `EPIC-03`, with `SVP2-B-02` as downstream consumer
- **Supersedes:** none
- **Superseded by:** none

## Context

The original typed gateway/admission request schemas (`1.0.0`) allow bounded string values for `campaign_id`, `run_id`, `step_id` and `attempt_id`. Later contracts have a stronger invariant:

- the Hermes-issued TB1 authorization receipt uses UUID correlation for campaign/run/step;
- Runner Protocol v2 requires UUID campaign/run/step/attempt identifiers on every message;
- the gateway-to-Runner handoff already fails closed when its four correlation identifiers are not UUIDs.

Silently tightening the existing v1 schema would be a breaking change without a version boundary. Generating replacement UUIDs inside the gateway would be worse: it would manufacture new correlation identity and break end-to-end provenance between the control plane, authorization receipt, gateway, runner and future evidence records.

## Decision

A new request-contract major version, `2.0.0`, is introduced for typed gateway correlation.

1. `admission-request-v2.schema.json` is the canonical external admission contract for new integrations.
2. `gateway-request-v2.schema.json` is the corresponding internal typed-evaluation contract.
3. Both v2 contracts require UUID `campaign_id`, `run_id`, `step_id` and `attempt_id`.
4. The existing v1 schemas remain unchanged as transitional compatibility contracts.
5. The admission layer recognizes v1 and v2 explicitly; unknown versions fail closed.
6. `promote_legacy_request_to_v2()` is the only repository-provided v1→v2 promotion helper. It changes only `schema_version` and succeeds only when all existing request data already satisfies v2.
7. No gateway, migration helper or Runner handoff may generate, map, replace or normalize a correlation identifier to satisfy v2.
8. The Runner handoff retains a defense-in-depth UUID gate. During transition, a v1 request may reach message construction only when its existing correlation IDs already satisfy the UUID invariant.
9. The external admission contract continues to forbid caller-supplied authorization decisions. Internal gateway requests may contain only the RoE decision freshly derived by the canonical admission boundary.

## Consequences

### Positive

- new integrations fail earlier and deterministically when correlation is invalid;
- correlation identity remains end-to-end and auditably owned by the upstream orchestration context;
- Runner Protocol no longer depends on a late implicit conversion that does not exist;
- v1 consumers receive an explicit migration path instead of an in-place breaking schema change;
- future Evidence Plane records can reuse the same correlation identifiers without provenance ambiguity.

### Negative

- two gateway/admission schema generations must coexist during migration;
- consumers must deliberately move to v2;
- v1 retirement requires an explicit future decision and compatibility evidence.

## Security implications

- invalid v2 correlation fails closed before authorization can become a Runner request;
- unknown schema versions fail closed rather than being interpreted as v1 or v2;
- identifier generation inside the execution plane is prohibited because it could sever the binding to Hermes-issued authorization;
- this ADR does not change ADR-0001: Hermes remains the sole execution-authorization authority;
- this ADR does not authorize execution, deployment, target access or generic command surfaces.

## Compatibility and migration

The legacy v1 schemas are not modified by this decision. A v1 request falls into one of two classes:

- **already UUID-compatible:** it may be explicitly promoted to v2 by changing only `schema_version`, after full v2 validation;
- **not UUID-compatible:** promotion is refused with `ADMISSION_V2_MIGRATION_REQUIRED`; the upstream producer must issue proper correlation identifiers. The gateway does not repair the request.

The migration helper is non-mutating with respect to the original request object and no identifier rewriting is permitted.

## Evidence and validation

Repository validation must demonstrate:

- v1 remains structurally compatible with legacy non-UUID values;
- v2 accepts valid UUID correlation;
- v2 rejects each non-UUID correlation field;
- unknown versions are refused explicitly;
- v1→v2 promotion changes only the schema version and preserves every correlation value;
- non-compatible v1 requests are refused rather than rewritten;
- the Runner handoff retains fail-closed UUID validation;
- existing authorization, RoE, security and Runner Protocol conformance suites remain green.

Runtime deployment evidence is explicitly `NOT_RUN`; this ADR records a repository contract decision only.

## Alternatives considered

1. **Tighten v1 in place.** Rejected because it is a silent breaking contract change.
2. **Generate UUIDs in the gateway.** Rejected because it manufactures execution-plane identity and breaks authorization/evidence provenance.
3. **Keep arbitrary strings permanently and rely only on the Runner boundary.** Rejected because invalid correlation would be discovered too late and the canonical contracts would remain inconsistent.
4. **Drop v1 immediately.** Rejected for this block because safe UUID-compatible legacy consumers can migrate without an abrupt compatibility break.

## Review triggers

Review this decision when:

- v1 retirement is proposed;
- correlation ownership moves to another upstream control-plane contract;
- a new protocol requires stronger correlation semantics;
- any implementation proposes identifier rewriting, aliasing or normalization;
- Evidence Plane implementation introduces new cross-plane correlation requirements.
