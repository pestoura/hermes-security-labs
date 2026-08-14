# Operator harness — remaining non-Vault SAFE-LIVE observations (CHG-HSL-057, privilege flow fixed in CHG-HSL-058)

Deterministic, fail-closed operator harness for the two remaining non-Vault
SAFE-LIVE observations of `VAL-HSL-RUNNER-L1-LIVE-PROMOTION`:

1. `USER_NAMESPACE_MAPPING` — re-attestation of the **current** Gateway/Runner
   processes.
2. `UNAUTHORIZED_PEER_NEGATIVE` — negative test against the **live** Runner HOLD
   AF_UNIX socket.

Module: `deployment/runtime-promotion/operator_live_observation_harness.py`
Tests: `deployment/tests/test_operator_live_observation_harness.py` (mocks/fakes only)

**This harness produces evidence. It never promotes.** `promotion_allowed` is
hardcoded `False`, `runtime_status` is hardcoded `NOT_RUN`, and the campaign stays
`BLOCKED` / `HOLD`. Nothing in Git changes when the harness runs.

## Hard invariants

| Invariant | How it is enforced |
| --- | --- |
| No Runner request payload is ever sent | The probe never calls `send`/`sendall`/`sendmsg`; a source-level test asserts those tokens are absent from the module |
| No Docker, network or target interaction | No `AF_INET`, HTTP client or container call exists in the module (asserted by test) |
| No credential/user/group is created | `setpriv` only *assumes* an identity for one process; `argv` is asserted free of `useradd`/`groupadd`/`usermod`/`chmod`/`chown` |
| No persistent state | The only writes are inside the operator-specified output directory, which must be outside the Git tree |
| PIDs never hardcoded, never scanned | Resolved at execution time from `systemctl show -p MainPID` for the two explicit units only |
| A DAC denial is not peer-negative proof | `EACCES`/`EPERM` maps to `DAC_BLOCKED_NOT_CANONICAL_PROOF`, `canonical_proof=false` |
| No policy enable, trust binding or signer selection | The harness reads nothing from and writes nothing to any policy/trust path |

## Output directory contract

The output directory is **operator-specified, absolute, and outside the Git
working tree**. The harness refuses anything else fail-closed:

- relative path → `OUTPUT_DIRECTORY_INVALID`
- inside the repository or `.git` → `OUTPUT_DIRECTORY_INSIDE_REPOSITORY`

Two artifacts are produced there:

- `reviewed-userns-descriptor.generated.yaml` — the explicit reviewed descriptor,
  generated outside Git, carrying the runtime PIDs and observed maps.
- `operator-live-observation-evidence.json` (+ `.sha256` sidecar) — the
  machine-readable evidence envelope with hashes and runtime PIDs/start times bound.

## Step 1 — plan (no observation, no connection)

```bash
python3 deployment/runtime-promotion/operator_live_observation_harness.py \
  --output-directory /var/tmp/hsl-057-evidence \
  --unauthorized-uid <EPHEMERAL_UID> \
  plan
```

`plan` validates assumptions only: it stats the HOLD socket read-only, echoes the
two unit names, and validates the ephemeral identity plan. It never connects and
never writes evidence. Review the output before collecting.

The `--unauthorized-uid` must be a positive, non-root UID that is **not** a
canonical boundary identity (`0`, `4100` gateway, `4101` runner) and **not** an
authorized peer. Anything else is rejected as `IDENTITY_ASSUMPTION_REJECTED`.

## Step 2 — collect (read-only observation)

```bash
sudo python3 deployment/runtime-promotion/operator_live_observation_harness.py \
  --output-directory /var/tmp/hsl-058-evidence \
  --unauthorized-uid <EPHEMERAL_UID> \
  collect
```

`sudo` is required whenever `--unauthorized-uid` is supplied: the parent must hold
effective root for the privileged userns re-attestation and to drop the peer child.
Without root the run fails closed with `ROOT_REQUIRED` before any observation. The
harness executes the userns observation FIRST under root, then spawns the peer
child — never the reverse. The harness internally drops ONLY the peer child; the
whole harness is never wrapped in `setpriv`.

### Observation 1: `USER_NAMESPACE_MAPPING`

1. PIDs come from `systemctl show -p MainPID --value` for
   `hexor-execution-gateway.service` and `hexor-runner.service` only (the
   canonical socket-activated Runner unit shipped in
   `deployment/runner-runtime/systemd/hexor-runner.service`, matching
   `runtime_boundaries.SYSTEMD_SERVICE_UNIT`).
   No process list is scanned; no unit is started, stopped, reloaded or enabled.
2. Each PID is bound to its `/proc/<pid>/stat` start time. A PID rebound between
   discovery and observation invalidates the re-attestation (fail-closed finding
   `... PID was rebound during observation`).
3. The reviewed descriptor is generated **outside Git** and passed to the
   canonical read-only observer `runtime_userns_evidence.collect_userns_evidence`,
   which performs the comparison independently.
4. `re_attested: true` proves only that maps and the ns/user relationship matched
   the reviewed descriptor at observation time. It grants nothing.

### Observation 2: `UNAUTHORIZED_PEER_NEGATIVE`

The probe runs under a temporary identity carrying supplementary GID `4110`
(`hexor-dispatch`) **solely** so `/run/hexor/runner-dispatch.sock` (mode `0660`,
owner `hexor-runner:hexor-dispatch`) is reachable at the DAC layer, while its UID
is unauthorized.

#### Canonical live form (CHG-HSL-058)

```bash
sudo python3 deployment/runtime-promotion/operator_live_observation_harness.py \
  --output-directory /var/tmp/hsl-058-evidence \
  --unauthorized-uid <EPHEMERAL_UID> \
  collect
```

**The harness internally drops ONLY the peer child.** The parent process stays
privileged (effective root) for the whole run, because dereferencing
`/proc/<pid>/ns/user` of the Gateway/Runner processes for
`USER_NAMESPACE_MAPPING` requires root. Only after the userns observation has
completed under root does the parent spawn one dedicated child:

```text
/usr/bin/setpriv --reuid <EPHEMERAL_UID> --regid <EPHEMERAL_UID> \
  --groups 4110 --no-new-privs -- \
  <python3> <harness.py> peer-child \
    --socket-path /run/hexor/runner-dispatch.sock \
    --unauthorized-uid <EPHEMERAL_UID> --dispatch-gid 4110
```

That child performs the socket connect/observe **only**. It runs no userns
collection, sends no payload, writes no evidence, and returns its outcome to the
parent as a single deterministic machine-readable line
(`HSL058_PEER_CHILD_RESULT {json}`), which the parent decodes into the evidence
envelope. `--unauthorized-uid` is required for the peer-negative observation; when
it is supplied, `collect` **fails closed with `ROOT_REQUIRED`** if the parent is
not effective root.

#### Rejected: wrapping the whole harness in `setpriv`

The pre-CHG-HSL-058 recipe that wrapped the **entire** harness —

```text
# REJECTED — do not use
sudo setpriv --reuid <UID> --regid <UID> --groups 4110 --no-new-privs -- \
  python3 .../operator_live_observation_harness.py ... collect
```

— is **invalid and must not be used**. Dropping the outer process destroys the
parent's ability to dereference `/proc/<pid>/ns/user`, so the
`USER_NAMESPACE_MAPPING` re-attestation cannot be performed and would fail or be
silently degraded. The privileged read must stay in the outer process; only the
peer probe is dropped.

`setpriv` assumes an identity for the lifetime of that one child process; it
creates no user and no group, so zero persistent state remains (no `useradd`,
`groupadd`, `usermod`, `gpasswd`, and no persistent group membership). If
`setpriv` is absent the harness returns `EPHEMERAL_IDENTITY_UNAVAILABLE`, no child
is spawned and the observation stays `NOT_RUN` — it never falls back to a
privileged or authorized identity.

The `--unauthorized-uid` must be a positive, non-root UID that is **not** a
canonical boundary identity (`0`, `4100` gateway, `4101` runner) and **not** an
authorized peer. The child's primary GID is the numeric UID itself and the
supplementary GID set is exactly `{4110}`.

### Outcome codes

| Outcome | `canonical_proof` | Meaning |
| --- | --- | --- |
| `HOLD_REFUSAL_OBSERVED` | `true` | Peer connected under an unauthorized SO_PEERCRED identity; HOLD refused/closed without accepting a request; no payload sent |
| `DAC_BLOCKED_NOT_CANONICAL_PROOF` | `false` | Kernel `EACCES`/`EPERM` at directory/socket DAC. **Explicitly not accepted** as the canonical peer-negative proof |
| `NO_REFUSAL_SIGNAL_OBSERVED` | `false` | Connected (or failed non-DAC) without an observable refusal/close |
| `SOCKET_ABSENT` | `false` | HOLD socket missing or not a socket; nothing is attempted |
| `EPHEMERAL_IDENTITY_UNAVAILABLE` | `false` | No `setpriv`; no connection attempted |
| `IDENTITY_ASSUMPTION_REJECTED` | `false` | Requested UID is privileged, canonical or authorized; no connection attempted |

Only `HOLD_REFUSAL_OBSERVED` with `canonical_proof: true` is acceptable evidence
for the `UNAUTHORIZED_PEER_NEGATIVE` gate. Every other outcome leaves
`UNAUTHORIZED_PEER_NEGATIVE_NOT_PROVEN` in `remaining_evidence`.

## What the harness never does

- Never sends a Runner request payload, and never reads request semantics.
- Never touches Docker, the network or any target.
- Never creates or modifies a user, group, credential, trust store or policy.
- Never enables a policy, binds trust or selects a signer/Vault provider.
- Never writes inside the Git working tree.
- Never sets `promotion_allowed=true`, and never converts a live observation to
  `PASS` in Git. Campaign records stay `BLOCKED` / `HOLD` / `NOT_RUN`.

## Interpreting the evidence

A `true` re-attestation and a `canonical_proof` peer-negative are **evidence
inputs only**. Closing the corresponding campaign observations requires the
canonical review and explicit human promotion decision; repository work and
collected evidence never close an observation on their own. Vault/signer, host
identity/socket trust composition and the live Runner effect remain out of scope
and are always emitted in `remaining_evidence`.
