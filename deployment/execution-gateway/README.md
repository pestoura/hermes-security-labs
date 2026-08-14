# Execution Gateway runtime deployment boundary (#79, phase A — base HOLD)

Repository-only implementation of the **minimum** Execution Gateway runtime
deployment boundary: the CLIENT side of the Hexor AF_UNIX dispatch surface. It is
fail-closed, idempotent and HOLD. No live deployment is performed by this
directory; the boundary is declared inert and HOLD.

## Scope (phase A)

- Declare the OS identity boundary and the `AF_UNIX` client surface as data.
- Provide a strictly-HOLD supervisor (`execution_gateway_hold.py`) that runs as the
  `hexor-gateway` identity (4100), is a member of `hexor-dispatch` (4110), and
  connects as a client to `/run/hexor/runner-dispatch.sock`.
- Provide a deterministic deployment descriptor, systemd service unit and
  tmpfiles.d declaration.
- Provide repository-only tests proving the HOLD contract and the read-only/check
  behavior.

This boundary is the SIBLING of the Runner runtime HOLD boundary (`#354`):
both share the canonical identities (`hexor-gateway` 4100, `hexor-runner` 4101,
`hexor-dispatch` 4110) and the same dispatcher socket. The Runner side owns the
socket and refuses; the Gateway side connects as a client and observes the refusal.

## Declared identities (mirror the canonical example descriptor)

| Identity        | UID   | GID   | Kind  |
|-----------------|-------|-------|-------|
| `hexor-gateway` | 4100  | 4100  | user  |
| `hexor-runner`  | 4101  | 4101  | user  |
| `hexor-dispatch`| 4110  | 4110  | group |

The gateway `hexor-gateway` (4100) is a member of `hexor-dispatch` (4110) so it can
connect to the runner:hexor-dispatch socket. Provisioning of these identities, if
ever performed on a host, is owned by the runner runtime boundary controller
(`deployment/runner-runtime/runtime_deployment.py`). This directory never creates,
deletes or relinks them.

## Runtime surface

- The gateway is the AF_UNIX CLIENT for `/run/hexor/runner-dispatch.sock`.
- The socket is owned by the runner side (`hexor-runner` 4101 : `hexor-dispatch`
  4110, mode `0660`); the runtime directory `/run/hexor` is owned
  `hexor-runner:hexor-dispatch` `0750` by the runner tmpfiles.d. The gateway does
  not create or own either; it only connects.
- Supervision via `systemd/hexor-execution-gateway.service`; no socket unit (no
  `ListenStream`) because the gateway is a client, not a listener.

## HOLD contract (the gateway never sends a Runner payload)

The gateway `ExecStart` runs a supervision loop. Each iteration connects to the
dispatcher socket, observes the (server-side) HOLD refusal, and closes. It never:

- sends a Runner payload;
- authorizes an execution;
- creates a TB1 receipt;
- calls the router, adapter or Evidence Plane;
- touches a target (WebGoat/Kali);
- reads, installs or synthesizes a trust store.

The committed transport policy (`platform/runner-transport/transport-policy.yaml`)
remains `DISABLED` / default-deny / `runtime_status=NOT_RUN` /
`execution_authority=none`. The descriptor keeps `promotion_allowed=false`. No
target effect is possible.

## Read-only / check behavior (real PID evidence, no fabricated helper)

- `python3 execution_gateway_hold.py --check` prints the HOLD decision JSON and
  exits. No socket connect, no bind, no process spawned.
- `python3 execution_gateway_hold.py --hold` runs the supervision loop in the
  foreground (the systemd `ExecStart`). It is a real process with a real PID, used
  for userns evidence; it performs only read-only client connects and never sends
  a Runner payload.

## Trust binding (phase B, deferred)

No `/etc/hexor/runner/authorization-trust-store.json` is created or installed by
this boundary. The committed example descriptor is never treated as live, and no
private signing key is ever created or synthesized. A trust binding is only ever
accepted from an **explicit external source**: a public, approved trust store with
a known expected SHA-256, validated fail-closed (the runner boundary's
`trust_binding.validate_trust_binding`).

## Validation

    python3 -m pytest -q deployment/tests/test_execution_gateway_hold.py -p no:cacheprovider
    python3 deployment/execution-gateway/execution_gateway_hold.py --check
    python3 deployment/execution-gateway/execution_gateway_hold.py --probe
    python3 -m ruff check --config security/pyproject.toml deployment/execution-gateway
    python3 -c "import yaml; yaml.safe_load(open('deployment/execution-gateway/execution-gateway-deployment.yaml'))"
    systemd-analyze verify deployment/execution-gateway/systemd/hexor-execution-gateway.service

No live deployment, socket bind, user/group creation or trust-store write is
performed by these commands: they are GREEN-REPO only. Live runtime status remains
`NOT_RUN` until an explicit future promotion installs and observes the gateway on a
host.
