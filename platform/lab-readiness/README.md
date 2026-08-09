# Lab readiness contract (Lane C)

`platform/scripts/lab_readiness.py` separates two questions the lifecycle
dispatcher conflates:

| question | answered by | meaning |
| --- | --- | --- |
| liveness | `lab_lifecycle.py run <env> status` | the container/process exists and is not dead |
| readiness | this adapter contract | the lab answers the way a consumer needs |

**A live container is not a READY lab.** The result model makes the difference
explicit with the `live_not_ready` lifecycle state.

## Result model

`lab_readiness.py status <env_id>` prints a stable JSON document:

```json
{
  "schema_version": 1,
  "lab_id": "vampi",
  "environment_id": "vampi",
  "lifecycle_state": "live_not_ready",
  "live": true,
  "ready": false,
  "liveness": {"state": "pass", "checks": [...]},
  "readiness": {"state": "fail", "checks": [...]},
  "failure_reasons": ["READINESS_CHECK_FAILED: http-root: ..."],
  "adapter": {"env_id": "vampi", "source": "lab-readiness/adapters/vampi.yaml", ...},
  "observed_at": "2026-01-01T00:00:00Z"
}
```

`lifecycle_state` is one of `unknown`, `down`, `live_not_ready`, `ready`.

Exit codes: `0` ready, `1` not ready (down or live-not-ready), `2` fail-closed
(unknown environment, missing or invalid adapter on an executable lab).

## Adapters

One file per environment: `platform/lab-readiness/adapters/<env_id>.yaml`.
The lab manifest schema and the target registry are **not** touched.

Allowlisted check kinds only — there is no command/shell field anywhere:

- `lifecycle_status` (liveness) — runs the allowlisted `status` action through
  the dispatcher;
- `http_get` (readiness) — loopback-only `http://127.0.0.1|localhost` GET, with
  `expect_status` and optional `expect_body_contains`;
- `tcp_connect` (readiness) — loopback host plus port.

Probes never perform offensive activity: no exploitation, no writes, no smoke
attack steps, no non-loopback destination. Timeouts are bounded to 30s.

## Fail-closed rule

An executable environment (dispatchable manifest declaring `start`) with a
missing or invalid adapter reports `lifecycle_state: unknown`, a
`READINESS_ADAPTER_MISSING` / `READINESS_ADAPTER_INVALID` reason, and exit code
2. Absence of evidence is never reported as ready.

Coverage across the catalogue:

```
python3 platform/scripts/lab_readiness.py coverage --json
python3 platform/scripts/lab_readiness.py coverage --strict   # gate
```

`--strict` is intentionally opt-in: the catalogue is being migrated adapter by
adapter, starting with the WrongSecrets and VAmPI references.

## Lane A compatibility

The evaluator ignores unknown manifest keys and resolves the lab identity via a
tolerant lookup (`lab_id`, `lab`, `id`, `environment_id`, `env_id`), so a rebase
onto the Lane A environment contract adds fields without breaking this module.
Adapter documents also ignore unknown top-level keys.
