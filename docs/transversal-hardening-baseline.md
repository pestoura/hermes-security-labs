# Transversal hardening baseline

This document records the repository-wide container and CI hardening baseline
that is mechanically enforced by static tests, and the residual gaps that are
tracked as reviewed exceptions.

Enforcement lives in:

- `platform/tests/test_compose_hardening_baseline.py` — every committed Compose
  file, universal invariants plus exception-listed baseline invariants.
- `platform/tests/test_workflow_permissions_baseline.py` — least-privilege token
  scope for every GitHub Actions job.
- `platform/tests/test_kali_script_hygiene.py` — Kali lifecycle script ordering.

Pre-existing per-lab tests (`test_kali_writable_tool_state.py`,
`test_webgoat_egress_proxy.py`) remain the authority for their own laboratories;
the transversal tests are additive and never relax them.

## Universal invariants (no exceptions)

| Invariant | Rationale |
| --- | --- |
| No `privileged: true`, no `cap_add` | container escape surface |
| No `network_mode`, `pid`, `ipc`, `userns_mode` override | namespace isolation |
| No `docker.sock` string anywhere in a Compose file | Docker socket is host root |
| Host bind mounts only from an explicit allowlist | prevents host filesystem reach |
| Published ports bound to `127.0.0.1` only | no laboratory is reachable off-host |
| `cpus`, `memory` and `pids` limits on every service | denial-of-service containment |
| `no-new-privileges` on every service | blocks setuid escalation |
| Some `cap_drop` declared on every service | fail-closed default |

The only approved host bind mounts are the Kali evidence and cache directories
(`./data/results`, `./data/cache`), which are project-relative and hold
sanitized output only.

## Reviewed exceptions

Exceptions are encoded as explicit sets in the test module, so removing one is a
visible diff and adding one requires editing the enforced file. A stale-entry
test guarantees the lists cannot drift away from the real service inventory.

### Writable root filesystem

Upstream vulnerable-lab images that write into their own application directory
and cannot run with `read_only: true` without a rebuilt image. Compensating
controls: capability drop, `no-new-privileges`, resource limits, loopback-only
publication, and per-lab internal networks.

### Partial capability drop (`NET_RAW` only)

Upstream images whose entrypoints still need the default capability set to bind
and to `chown` their runtime directories. `NET_RAW` removal is the meaningful
control here: it blocks raw-socket traffic generation from inside a laboratory.

### Tag-pinned images

None. The exception set is empty and closed: every committed Compose service
references an immutable `@sha256:` digest. The last remaining gap was the crAPI
release train (`1.1.6-rc8`) plus `postgres:14` and `mongo:4.4.29`; all eight
references are now digest-pinned against the digests resolved read-only from
Docker Hub (see `platform/environments/web-api/crapi/README.md`).
`platform/tests/test_compose_hardening_baseline.py` enforces both the universal
digest rule and the emptiness of the exception set.

## Network segregation model

Every laboratory owns its own bridge network; nothing is shared between
laboratories. Where a laboratory holds a data tier, that tier sits on an
`internal: true` network with no route off-host:

| Laboratory | Internal network | Publication path |
| --- | --- | --- |
| crAPI | `crapi-core` | `crapi-web` only |
| DVAPI | `dvapi-db` | `dvapi` only |
| DVWA | `dvwa-db` | `dvwa` only |
| NodeGoat | `nodegoat-db` | `nodegoat` only |
| WebGoat | `webgoat-lab` | `webgoat-proxy` only |
| WrongSecrets | `wrongsecrets-internal` | `wrongsecrets-proxy` only |
| Kali MCP | `hermes-kali-lab` | none (no published port) |

Kali keeps a separate, non-internal `hermes-kali-egress` network reserved for the
`maintenance` profile. The main Kali service never joins it, and
`kali-mcp/scripts/maintenance.sh` fails the run if it observes the main
container attached to the egress network, a published port 5000, or a mounted
Docker socket.

## CI token scope

No workflow may inherit the repository default token permission set, request
`write-all`, or request `contents: write`. `packages: write` is restricted to the
five GHCR publication workflows and is asserted against a named allowlist.

## Known gaps (not fixed here)

These are recorded deliberately and are out of scope for a safe, independent
change; several depend on republished images or on the private-GHCR transition.

1. Pin GitHub Actions to commit SHAs instead of floating major tags
   (`actions/checkout@v4`, `actions/setup-python@v5`,
   `gitleaks/gitleaks-action@v2`).
2. Run laboratory services as an explicit non-root `user:`; the
   `platform/runtime-base` policy already mandates `uid >= 10000` for runners,
   but the laboratory Compose files do not yet set it.
3. Reduce the writable-rootfs and partial-`cap_drop` exception sets by rebuilding
   the affected upstream images.
4. No SBOM or provenance attestation is produced for the project-built GHCR
   images; the DevSecOps pack models SBOM as runbook content only.
