# Canonical target registry

`platform/targets` is the canonical registry of executable targets for the
Hermes Security Labs platform.

## Contract

* **`target_id` is the only execution authority.** A URL, hostname, IP address
  or container name never authorizes execution on its own. Callers resolve a
  `target_id`; anything else fails closed.
* **Offensive execution eligibility is TRUE only for `LAB_ONLY` and
  `AUTHORIZED_TEST_TARGET`.** `UNVERIFIED`, `BLOCKED`, `EXTERNAL`, and any
  missing, unknown or ambiguous value resolve FALSE with an explicit reason.
* **No public or external targets are committed here.** Identities are
  restricted to `lab-internal` or `loopback` reachability, taken from the
  committed environment manifests and Compose files.
* **The resolver is deterministic and side-effect free.** It never touches the
  network, never starts a container and never mutates runtime state.

## Files

| Path | Purpose |
| --- | --- |
| `target-registry.schema.json` | JSON Schema for the registry document |
| `target-registry.yaml` | The canonical registry (executable Docker labs only) |
| `target_registry.py` | Validation, orphan checks, resolver API and CLI |
| `execution_authorization.py` | Fail-closed authorization gate for the semantic/offensive execution boundary |

## Target fields

| Field | Meaning |
| --- | --- |
| `target_id` | Canonical execution authority (unique, lowercase-hyphen) |
| `environment_id` | Must match a known environment manifest `id` |
| `kind` | `network_service` or `application` |
| `identity` | hostname, port, protocol, scheme, path, network, reachability |
| `authorization_state` | `LAB_ONLY`, `AUTHORIZED_TEST_TARGET`, `UNVERIFIED`, `BLOCKED`, `EXTERNAL` |
| `lifecycle` | `PLANNED`, `PROVISIONED`, `ACTIVE`, `SUSPENDED`, `RETIRED` |
| `health` | `UNKNOWN`, `HEALTHY`, `DEGRADED`, `UNHEALTHY` (static registry: `UNKNOWN`) |
| `scope.allowed_operations` | Non-empty allow-list of permitted operations |
| `evidence` | Optional provenance: manifest/compose path, source, verification date |

## CLI

```bash
python3 platform/targets/target_registry.py validate
python3 platform/targets/target_registry.py list
python3 platform/targets/target_registry.py resolve juice-shop-web
python3 platform/targets/target_registry.py resolve juice-shop-web --operation web_vulnerability_scan
```

`validate` checks the contract, per-target invariants and orphan
`environment_id` references against `platform/environments`. `resolve` exits 0
when execution is eligible and 2 when it is not.

## Resolver API

```python
from target_registry import load_registry, resolve_execution_eligibility

registry = load_registry()
decision = resolve_execution_eligibility("juice-shop-web", registry)
decision.eligible  # True
decision.reason    # human-readable justification
```

## Execution authorization (Lane G)

`platform/targets/execution_authorization.py` is the fail-closed authorization
gate for the **semantic / offensive execution boundary**. It reuses the resolver
above; it does not weaken lifecycle cleanup.

```bash
python3 platform/targets/execution_authorization.py authorize juice-shop-web web_vulnerability_scan
python3 platform/targets/execution_authorization.py authorize juice-shop-web lab.lifecycle.destroy --class SAFETY
```

```python
from execution_authorization import authorize_operation, guarded_dispatch

decision = authorize_operation("juice-shop-web", "web_vulnerability_scan")
decision.allowed      # True
decision.reason_code  # ALLOW_OFFENSIVE_OPERATION

# The handler is invoked only when the decision allows.
decision, result = guarded_dispatch("juice-shop-web", "web_vulnerability_scan", handler)
```

Offensive dispatch requires **all** of:

| Condition | Denial reason code |
| --- | --- |
| canonical `target_id` (never a URL/IP/hostname) | `TARGET_ID_MISSING`, `TARGET_ID_NOT_CANONICAL` |
| target present and unambiguous in the registry | `TARGET_UNKNOWN`, `TARGET_REGISTRY_AMBIGUOUS` |
| `authorization_state` in {`LAB_ONLY`, `AUTHORIZED_TEST_TARGET`} | `AUTHORIZATION_STATE_DENIED`, `AUTHORIZATION_STATE_INVALID` |
| `lifecycle` in {`PROVISIONED`, `ACTIVE`} | `TARGET_LIFECYCLE_RETIRED`, `TARGET_LIFECYCLE_NOT_READY` |
| `health` in {`UNKNOWN`, `HEALTHY`} | `TARGET_HEALTH_INCOMPATIBLE` |
| operation inside `scope.allowed_operations` | `TARGET_SCOPE_EMPTY`, `OPERATION_OUT_OF_SCOPE`, `OPERATION_EXPLICITLY_DENIED` |
| operation is not a generic-execution escape | `GENERIC_EXECUTION_FORBIDDEN` |

`UNVERIFIED`, `BLOCKED`, `EXTERNAL`, missing, ambiguous, retired and
out-of-scope inputs deny deterministically **before any tool or handler is
invoked** (`guarded_dispatch` raises `AuthorizationError` and never calls the
handler).

### Safety operations are never blocked

Non-offensive lifecycle operations (`lab.lifecycle.stop|reset|destroy|cleanup`)
resolve `ALLOW_SAFETY_OPERATION` for any resolvable target, whatever its
authorization state, lifecycle or health. A `BLOCKED` target must remain safely
destroyable. Safety classification comes from the internal allow-list only: a
caller cannot re-label an offensive operation as `SAFETY`.

### Audit-friendly decision object

`AuthorizationDecision.as_dict()` emits `target_id`, `operation_id`,
`operation_class`, `allowed`, `reason_code`, `authorization_state`,
`lifecycle`, `health`, `environment_id` and `allowed_operations`. Reason codes
come from a closed enumeration and no raw URL, address or free-form target
label is ever emitted, so the object is safe for evidence and metrics.

## Lane boundary

This lane does **not** wire the resolver into
`platform/lab-lifecycle/lifecycle_protocol.py` or any lifecycle dispatcher, and
it does not modify the lab manifest schema or any executable environment
manifest. Lifecycle and semantic execution lanes integrate the resolver
separately.
