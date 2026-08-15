# DVWA/MariaDB live lifecycle acceptance — 2026-08-15

**Change:** `CHG-HSL-065`  
**Accepted runtime run:** `run_bda5b78321d641b8ba24fc15c3a39970`  
**Evidence-manifest run:** `run_63fe5b16b393481d90ce1cc079ba62ec`  
**Repository revision exercised:** `dd3677b6fb531c72ec7c5ea6fb5f82da94a27f37`  
**Scope:** local DVWA/MariaDB lifecycle only  
**Disposition:** `PASS / ACCEPTED-LIVE-LIFECYCLE`

This record persists the sanitised acceptance result for the canonical DVWA/MariaDB lifecycle. It does **not** authorize Kali target traffic, vulnerability scanning, exploitation, credential use, Runner promotion, signer/trust activation or any other target effect.

## Execution boundary

The accepted run fetched `origin/main` and exercised an exact clean `git archive` export of:

`dd3677b6fb531c72ec7c5ea6fb5f82da94a27f37`

The canonical repository working tree, including unrelated work in progress, was not checked out, reset, stashed, cleaned or edited.

The selected host override was:

- `DVWA_HOST_PORT=14280`

The port was verified free on `127.0.0.1` before mutation. No unrelated service was stopped or altered to obtain the port.

## Accepted lifecycle

The canonical lifecycle completed with exit code `0` at every step:

| Step | Result |
| --- | --- |
| `start.sh` | `PASS` |
| `status.sh` | `PASS` |
| `smoke.sh` | `PASS` |
| `reset.sh` | `PASS` |
| second `status.sh` | `PASS` |
| second `smoke.sh` | `PASS` |
| first `destroy.sh` | `PASS` |
| second `destroy.sh` | `PASS` — idempotence confirmed |

Both DVWA and MariaDB reached the expected healthy state before the smoke and reset gates were accepted.

## Exposure and network isolation

The accepted runtime observations were:

- DVWA host publication: `127.0.0.1:14280 -> 80/tcp` only;
- MariaDB host publication: none (`HostConfig.PortBindings` empty);
- application network: project-owned and non-internal as designed;
- database network `dvwa-db`: project-owned and `internal=true`;
- Kali: not connected to the DVWA networks at any point in this acceptance;
- no Nmap, Nikto, Gobuster, SQLMap, Hydra, Metasploit, login, brute force or exploit action was executed.

## Pinned images observed

The lifecycle retained the repository-pinned image identities:

- DVWA: `ghcr.io/digininja/dvwa:d45ba3c@sha256:091498cedec31b4a3091a1262e6a5a0ce5ec32d4bd26486558818346ccc89d67`
- MariaDB: `docker.io/library/mariadb:10.11.18@sha256:be981e4113326ada8d6004174dd09eeaefc03094037f811182a52d4f2e737350`

The images were preserved after teardown; acceptance required resource cleanup, not image deletion.

## Non-interference

The preflight found no ambiguous or foreign resource claiming ownership of the canonical DVWA Compose project. A read-only baseline of unrelated Docker resources was recorded before mutation.

The lifecycle altered only project-owned DVWA/MariaDB resources. Existing unrelated containers and services remained intact. In particular, Kali remained unchanged and disconnected.

## Final zero-residue proof

After the two canonical destroy operations:

- project-owned DVWA/MariaDB containers: `0`;
- project-owned DVWA/MariaDB volumes: `0`;
- project-owned DVWA/MariaDB networks: `0`;
- localhost port `14280`: free again;
- canonical default host port `4280`: free;
- pinned DVWA and MariaDB images: preserved;
- unrelated Docker resource baseline: unchanged.

The temporary exact-revision export was removed after the run.

## Evidence manifest

The runtime retained two sanitised evidence files under `/home/estourpm/dvwa-acceptance-evidence/`. Their contents are intentionally not committed. The separate read-only manifest run calculated file metadata and SHA-256 values only.

**Manifest format:** `<sha256>  <size>  <relative-path>\n`, sorted deterministically by path.  
**Manifest SHA-256:** `78043138d448fe5a8cafda259e643145546ffe8c8d5bae15c4847d7739351b70`

| Relative path | Bytes | SHA-256 |
| --- | ---: | --- |
| `acceptance.log` | 50931 | `6a30067385062be363a8ce6d9553cd5a3aeedd5c7bb46a5b8f3aceb4b4757bd2` |
| `smoke-summary.txt` | 187 | `3d1659cc4bdd28fb9ac33520d447ddbe3650eca215b3ad9bdee5c151e939b5c6` |

These hashes bind this repository record to the sanitised evidence set observed by Hermes. The local evidence directory is not asserted to provide durable or WORM custody.

## Acceptance boundary

CHG-HSL-065 closes only the DVWA/MariaDB **standalone live lifecycle/readiness/reset/zero-residue acceptance** for the exact repository revision exercised above.

It does not assert that a pentest or exploit path has been executed, does not connect this lab to the Kali Runner, and does not change the governed Runner campaign, signer/trust-store state or promotion authority. The repository may advance after the tested revision; that does not retroactively change which revision this acceptance proves.
