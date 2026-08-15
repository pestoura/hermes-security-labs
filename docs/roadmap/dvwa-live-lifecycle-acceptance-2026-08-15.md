# DVWA live lifecycle acceptance — 2026-08-15

**Change:** `CHG-HSL-069`  \
**Issue:** `#393`  \
**Accepted runtime run:** `run_8f2174dc4c87452098b700ff556ac978`  \
**Evidence-manifest run:** `run_3174fc965b7b404c9bf842f5c65632ac`  \
**Repository revision exercised:** `e3fb2554c9a5d354b82a29edfbd0830fa78fc471`  \
**Scope:** local OWASP DVWA lifecycle only  \
**Disposition:** `PASS / ACCEPTED-LIVE-LIFECYCLE`

This record persists the sanitised acceptance result for the DVWA lifecycle. It does **not** authorize Runner promotion, signer/trust activation, Kali target traffic, exploitation or any other lab.

## Accepted execution

The accepted run required `origin/main` to equal:

`e3fb2554c9a5d354b82a29edfbd0830fa78fc471`

A clean temporary `git archive` export of that exact revision was used. The existing canonical working tree was not checked out, reset, stashed, cleaned or edited.

Host-port override was:

- `DVWA_HOST_PORT=14280`

Port `14280` was verified free on `127.0.0.1` before mutation. Container-internal service port remained `80`.

Preflight gates all passed:

- exact origin/main/export SHA MATCH (no other revision trusted or executed);
- zero pre-existing DVWA project containers, networks and volumes;
- `14280` free and loopback-only;
- Kali `hermes-kali-mcp` running only on its own network `hermes-kali-mcp_hermes-kali-lab` and disconnected from `dvwa-lab`/`dvwa-db`;
- workspace at `/home/estourpm/hermes-labs/hermes-security-labs` NOT reset/stashed/cleaned.

The canonical lifecycle completed with exit code `0` at every step:

| Step | Result |
| --- | --- |
| `start.sh` | `PASS` |
| `status.sh` (1) | `PASS` |
| `smoke.sh` (1) | `PASS` |
| `reset.sh` | `PASS` |
| `status.sh` (2) | `PASS` |
| `smoke.sh` (2) | `PASS` |
| first `destroy.sh` | `PASS` |
| second `destroy.sh` | `PASS` — idempotence confirmed |

DVWA + MariaDB were healthy throughout the lifecycle. Published mapping was `127.0.0.1:14280->80/tcp`. MariaDB host bindings were `{}` (never published to host); `dvwa-db` was `internal=true` with only the DVWA/DB endpoints.

## Isolation and non-interference

The accepted run did not connect Kali and did not perform scanning, exploitation or external target traffic.

The DVWA lifecycle mutated **only** dvwa-owned resources:

- `dvwa-dvwa-1`, `dvwa-db-1` (create/start/stop/kill/destroy);
- `dvwa-lab`, `dvwa-db` (network create/destroy);
- `dvwa_dvwa-db-data` (volume create/destroy).

Docker events/Compose ownership distinguish this from the rest of the host. The recorded Docker event log during the run window shows no dvwa script acting on a non-dvwa container/network/volume.

**Concurrent external activity (documented separately, not a DVWA-lifecycle effect).** After the DVWA sequence completed (dvwa destroy #2 ended `2026-08-15T18:09:31Z`), two non-DVWA `m365-ui-mcp` containers (`m365-ui-mcp-browser-worker-1`, `m365-ui-mcp-control-plane-1`, later visible as `planner-mcp-*`) were destroyed and recreated at `2026-08-15T18:10:57Z` — 86 seconds later — by a separate external controller. They are under a different Compose project label and were NOT adopted by the dvwa project. They were live again after that external operation. This is observed concurrent external M365 activity, not a DVWA lifecycle mutation; do not claim the entire host was static.

The run explicitly left the following unrelated resources unchanged by the DVWA lifecycle:

- `hermes-kali-mcp`;
- `hermes-mcp-bridge`;
- `monitoring-prometheus-1` / `monitoring-cadvisor-1`;
- `n8n-n8n-1`;
- `firecrawl-*` stack;
- `jarvas-diun` / `jarvas-docker-api`;
- `eager_solomon` (non-owned WebGoat image container);
- `dreamy_ishizaka` / `frosty_neumann` / `strange_bouman` (nginx);
- `planner-mcp-*` / `m365-ui-mcp-*` (external controller resources).

No signer, trust-store, Runner-promotion, policy, systemd, Gateway, Bridge, WebGoat or Juice Shop state was changed by the DVWA lifecycle.

## Final zero-residue proof

After the two canonical destroy operations:

- project-owned DVWA containers: `0`;
- project-owned DVWA networks: `0`;
- project-owned DVWA volumes: `0`;
- localhost port `14280`: free again;
- Kali remained running and disconnected from `dvwa-lab`/`dvwa-db`;
- the transient exact-revision export was removed after the run.

## Evidence manifest

The runtime produced eleven sanitised local evidence files under `/tmp/hsl-issue393-dvwa-evidence/`. Their contents are intentionally not committed. A separate read-only run calculated file hashes and a deterministic aggregate manifest.

**Manifest format:** `<sha256>  <size>  <relative-path>`, sorted deterministically by path.  \
**Manifest SHA-256:** `4360328356b21efc3fdc6e394c413d4add14fc8c2c3fe87af6bd121721f8c504`

| Relative path | Bytes | SHA-256 |
| --- | ---: | --- |
| `01-start.log` | 1534 | `906a2009a239df8905d38e1bf39886e82349eb8bfa661470c54892437877b155` |
| `02-status1.log` | 1606 | `85ff62a34a31bfb00699ce533cbc74df8074ad7777c7f3009bfd55e633c48171` |
| `03-smoke1.log` | 180 | `d3b6e72fbe1e09e69c2c26471af5b36581ce3c20bd9c1dca663810a74bf20245` |
| `04-reset.log` | 2588 | `e7d2b7713fa34f3e6ce846bfdfc086b72bd7ea6ac6c6ebe51cfefb2947fc898a` |
| `05-status2.log` | 1606 | `cece293ecbd10f322b9f830138b5b4fa141e1ca5cf9af89ab1e3bff8d876bf69` |
| `06-smoke2.log` | 180 | `47127546427c904d8af1655b4c9a37b70e5872a227f02ff9a2d3063c3fb18b2c` |
| `07-destroy1.log` | 922 | `eba8634e8e75d2ff00fb37e150c5539b6114dbde63d3784841ceff1bedb4e6fc` |
| `08-destroy2.log` | 562 | `3bb91c45eee3d131356acdadee6e44dba829f2cebad6c3d024dd23a841357b4c` |
| `baseline.txt` | 2632 | `bc831d785b9e8aa554290ddacea55701d18928ee05563b898642362bbf0c9a6e` |
| `final-proof.txt` | 3948 | `184a9c24efbba24f2c840fe5b1baf3e2ee27b5b6256d53c1228f1d8c9d66ffe5` |
| `smoke-summary.txt` | 187 | `3d1659cc4bdd28fb9ac33520d447ddbe3650eca215b3ad9bdee5c151e939b5c6` |

These hashes bind this audit record to the evidence set observed by the Hermes runtime. The `/tmp` files remain ephemeral local evidence and are not asserted to be durable/WORM custody.

## Acceptance boundary

CHG-HSL-069 closes only the DVWA **live lifecycle/readiness/reset/zero-residue acceptance** for the revision tested above.

It does not change the governed Runner campaign `VAL-HSL-RUNNER-L1-LIVE-PROMOTION.yaml`, which remains `BLOCKED` / `HOLD` with `promotion_allowed=false`, candidate commit `a63ef01925e5c1b925936c1e73b11b2d6cd2a6a5` unchanged, and `VAL-HSL-RUNNER-L1-LIVE-PROMOTION` unaffected. DVWA acceptance is an independent lifecycle-evidence record; it grants no Runner, signer, trust-store, supplier-selection, assurance-profile, #53, or PROD/LAB_L1 promotion authority.

Juice Shop live lifecycle acceptance remains pending (#394, after #393).
