# Backend abstraction (Lane H)

Minimal, deterministic backend layer for Hermes Security Labs. It turns the
`backend` field that executable manifests already declare into a typed,
fail-closed contract, without rewriting the lifecycle dispatcher.

## What is here

| Path | Role |
| --- | --- |
| `platform/backends/backend-registry.yaml` | Declarative registry: one entry per backend type with support state, readiness and capability requirements. |
| `platform/scripts/lab_backends.py` | Contract, registry loader, adapter interface, Docker Compose adapter, resolver and a read-only CLI. |
| `platform/tests/test_backend_abstraction_contract.py` | Conformance tests (hermetic, no runtime). |

## Backend types and honest state

| Backend | Support state | Readiness | Adapter |
| --- | --- | --- | --- |
| `DOCKER` | SUPPORTED | READY | `docker_compose` |
| `KUBERNETES` | DEFINED | NOT_READY | none |
| `VM` | DEFINED | NOT_READY | none |
| `CLOUD` | DEFINED | NOT_READY | none |
| `REMOTE_ISOLATED` | DEFINED | NOT_READY | none |

Only Docker Compose is implemented, and it is implemented by *delegating* to the
lifecycle scripts each environment already ships. Every other backend is modelled
explicitly: it declares the capabilities it would need and the ones that are
missing, and every operation against it raises `BackendError` with reason code
`BACKEND_NOT_SUPPORTED`. Nothing pretends to work.

## Backend API

Bounded operation vocabulary — nothing else exists:

```
provision | status | reset | destroy
```

For `DOCKER` these map onto the allowlisted lifecycle actions
`start | status | reset | destroy`.

The adapter interface exposes **planning only**:

```python
class BackendAdapter:
    def capability_report(self) -> dict: ...
    def plan(self, env_id: str, operation: str) -> BackendPlan: ...
```

A `BackendPlan` is inert: it names the operation, the resolved lifecycle action,
whether the operation is destructive, and — when the environment ships a script
that `lab_lifecycle.resolve` validates — the argv vector. This module never runs
anything: it imports neither `subprocess` nor `os`, and a conformance test asserts
that at AST level. There is no free-form command field anywhere, in code or in the
registry.

## Resolver semantics (fail closed)

`resolve_backend(manifest)`:

* rejects manifests that are not `execution_class: executable` (catalog-only
  entries make no runtime claim) — `BACKEND_FIELD_MISSING`;
* rejects a missing or empty `backend` field — `BACKEND_FIELD_MISSING`;
* rejects an unknown `backend` value, with no default and no guessing —
  `BACKEND_UNKNOWN`;
* maps known aliases (`docker-compose` → `DOCKER`, `kind` → `KUBERNETES`, ...),
  case-insensitively, with duplicate aliases rejected at registry load time.

Registry load is itself fail-closed: wrong schema version, missing backend type,
`READY` without `SUPPORTED`, `NOT_READY` without declared missing capabilities, a
`DEFINED` backend that maps operations or names an adapter, or an attempt to widen
the operation vocabulary all raise `BACKEND_REGISTRY_INVALID`.

## CLI (read-only)

```bash
python3 platform/scripts/lab_backends.py list                    # backend types + state
python3 platform/scripts/lab_backends.py matrix                  # per-environment bindings
python3 platform/scripts/lab_backends.py plan dvwa provision     # describe, never execute
python3 platform/scripts/lab_backends.py plan kind-rbac-synthetic provision   # fails closed
```

Exit codes: `0` plan is executable, `1` plan is descriptive only (no shipped
script), `2` fail closed.

## Non-goals / boundaries

* the lifecycle dispatcher, the target registry, the scenario/tool registry, the
  evidence core, CI workflows and GHCR are untouched;
* no manifest schema change: the `backend` field already existed;
* the seam onto `lab_lifecycle.resolve` is optional and defensive — if the import
  fails, planning degrades to a descriptive plan instead of breaking a caller;
* nothing here provisions, starts, resets or destroys a lab.
