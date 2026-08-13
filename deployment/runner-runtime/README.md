# Runner runtime deployment boundary (#354, phase A — base HOLD)

Repository-only implementation of the **minimum** Runner runtime deployment
boundary: fail-closed, idempotent and rollbackable. No live deployment is
performed by this directory; the boundary is declared inert and HOLD.

## Scope (phase A)

- Declare the OS identity boundary and the `AF_UNIX` dispatch surface as data.
- Provide a fail-closed, idempotent deployment controller (`runtime_deployment.py`).
- Provide a strictly-HOLD listener (`runner_hold_listener.py`) that reuses the
  canonical `platform/runner-transport/unix_peer_identity.py` `SO_PEERCRED`
  module and then refuses.
- Provide systemd socket activation + service supervision and a tmpfiles.d
  declaration for `/run/hexor`.

## Declared identities (mirror the canonical example descriptor)

| Identity        | UID   | GID   | Kind  |
|-----------------|-------|-------|-------|
| `hexor-gateway` | 4100  | 4100  | user  |
| `hexor-runner`  | 4101  | 4101  | user  |
| `hexor-dispatch`| 4110  | 4110  | group |

These identities are canonical. `install-base` **can materialize** them on a
host: after a fully GREEN preflight it provisions **only the ABSENT** objects,
using `groupadd --gid <gid> <name>` for the two private groups and the shared
`hexor-dispatch` group, `useradd --uid <uid> --gid <gid> --no-create-home
--home-dir /nonexistent --shell /usr/sbin/nologin --no-user-group <name>` for the
two users, and `usermod --append --groups hexor-dispatch <user>` for a missing
supplementary membership. Existing exact identities are an idempotent no-op (zero
commands). No password or credential is ever created.

The exact-aware preflight examines both names and ids before any mutation and
returns `EXACT` / `ABSENT` / `CONFLICT`. A same-name-wrong-id/shell/primary-gid,
or a reserved uid/gid already owned by another name, is a `CONFLICT` and fails
closed; a conflicting id is never reused. The UID and GID namespaces are
distinct, so uid 4100 and gid 4100 are both expected and never reported as a
duplicate collision (`detect_reserved_id_collision`). After provisioning the
identities are re-probed and must be exact before any file/systemd action.

Live runtime status stays `NOT_RUN` until the install is actually executed and
observed on a host; CI is GREEN-REPO only.

## Runtime surface

- `/run/hexor` directory: owner `hexor-runner` (4101), group `hexor-dispatch`
  (4110), mode `0750`.
- `/run/hexor/runner-dispatch.sock` `AF_UNIX` socket: owner `hexor-runner`
  (4101), group `hexor-dispatch` (4110), mode `0660`.
- Socket activation via `systemd/hexor-runner.socket`; supervision via
  `systemd/hexor-runner.service`; runtime dir via `tmpfiles/hexor-runner.conf`.

## HOLD contract (the listener refuses everything)

The listener accepts an `AF_UNIX` connection, derives the kernel peer
credential via the canonical `SO_PEERCRED` module, and **closes/refuses**. It
never:

- reads the request payload;
- authorizes an execution;
- creates a TB1 receipt;
- calls the router, adapter or Evidence Plane;
- touches a target (WebGoat/Kali);
- reads, installs or synthesizes a trust store.

The committed transport policy (`platform/runner-transport/transport-policy.yaml`)
remains `DISABLED` / default-deny / `runtime_status=NOT_RUN` /
`execution_authority=none`. Policies in `runtime-deployment.yaml` keep
`promotion_allowed=false`. No target effect is possible.

## Trust binding (phase B, deferred)

No `/etc/hexor/runner/authorization-trust-store.json` is created or installed by
this boundary. The committed example descriptor is never treated as live, and no
private signing key is ever created or synthesized. A trust binding is only ever
accepted from an **explicit external source**: a public, approved trust store
with a known expected SHA-256, validated fail-closed
(`trust_binding.validate_trust_binding`).

## Idempotency and rollback

- `runtime_deployment.py plan` renders the same install set every run (no live
  mutation by default).
- `install-base --live` provisions only ABSENT canonical identities (see above)
  and copies the inert units/README/listener/descriptor into the canonical
  prefix; it never creates the socket (systemd socket activation owns it) nor a
  trust store. Re-running it on an exact host performs zero identity commands.
- `rollback-base --live` removes only the files this deployment installed. It is
  explicit and fail-closed: users, groups, group memberships and any trust store
  are **never** deleted. They are durable boundary identities; removing them, if
  ever required, is a separate explicit administrative lifecycle operation
  performed by an operator. A partially-provisioned failure surfaces
  `partial_identity_provisioning=true` with the created identities and is left
  for the operator instead of being destructively compensated.

## Validation

    python3 -m pytest -q deployment/tests -p no:cacheprovider
    python3 deployment/runner-runtime/runtime_deployment.py plan
    python3 deployment/runner-runtime/runner_hold_listener.py --check
    python3 -m ruff check --config security/pyproject.toml deployment
    python3 -c "import yaml,sys; yaml.safe_load(open('deployment/runner-runtime/runtime-deployment.yaml'))"

No live deployment, socket bind, user/group creation or trust-store write is
performed by these commands: they are GREEN-REPO only. Live runtime status
remains `NOT_RUN` until `install-base --live` is actually executed and observed on
a host.
