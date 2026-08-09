# Lane F — Scenario Registry + Semantic Tool Registry

Wave 1, Lane F. Two canonical, repo-backed registries plus a read-only validator.

## Scope

This lane seeds only what the repository already supports. It does **not** add:

- environment schema, target registry, lifecycle/readiness, evidence-plane code,
  CI workflows, live runtime, or GHCR changes (those are other lanes / out of scope);
- arbitrary command/shell/generic_execution entries anywhere;
- invented scenarios. Every scenario maps to a real environment, an execution-eligible
  `target_id`, a typed gateway operation, and a committed runbook reference.

## Artifacts

| File | Purpose |
|------|---------|
| `scenario-registry.yaml` | Canonical scenarios (schema above). Small, supported set. |
| `scenario-registry.schema.json` | JSON Schema for the scenario registry. |
| `tool-registry.yaml` | Tool → typed semantic operation bridge with availability states. |
| `tool-registry.schema.json` | JSON Schema for the tool registry. |
| `validate_registries.py` | Read-only CLI + `collect_findings()` contract validator. |

## Contract invariants (enforced by the validator)

- `target_id` is the only execution authority (inherited from the target registry).
- `generic_execution` is forbidden in both registries.
- Forbidden fields (`command`, `shell`, `cmd`, `exec`, `argv`, `cwd`, `script`, `run`,
  `generic_execution`) are rejected anywhere in the scenario registry.
- Every scenario binds to a known `environment_id` and an execution-eligible `target_id`
  (resolved via `platform/targets/target_registry.py`, fail-closed).
- Every scenario `semantic_operations` / step `operation` exists in
  `platform/gateway-protocol/operation-registry.yaml`.
- Every scenario `runbook_ref` points at a committed file.
- Every tool maps to exactly one typed operation (`UNMAPPED` is explicit and may not claim
  `READY` or reference scenarios).
- Availability states are evidence-based: only `system.health.read` is `READY` (the
  candidate runtime executes it); all other typed operations are `PRESENT` (declared, no
  live candidate effect); `kali-mcp.audit` is `DEGRADED` (present, not wired to a typed op).

## Run

```bash
# validate (CI-equivalent)
python3 platform/scenario-registry/validate_registries.py

# tests
python3 -m pytest -q platform/tests/test_lane_f_scenario_tool_registry.py -p no:cacheprovider
```

## Seeded scenarios (counts are not inflated)

- `webgoat-tls-transport-review` — read-only transport review (L1).
- `dvwa-sql-injection-screening` — synthetic-only SQLi validation (L2).
- `juice-shop-lab-lifecycle-stop` — controlled lab stop/reset (L2).
