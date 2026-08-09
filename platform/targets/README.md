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

## Lane boundary

This lane does **not** wire the resolver into
`platform/lab-lifecycle/lifecycle_protocol.py` or any lifecycle dispatcher, and
it does not modify the lab manifest schema or any executable environment
manifest. Lifecycle and semantic execution lanes integrate the resolver
separately.
