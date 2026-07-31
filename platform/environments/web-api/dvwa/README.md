# Damn Vulnerable Web Application Lab

## Objective

Run the official Damn Vulnerable Web Application (DVWA) and its MariaDB dependency as a disposable local Docker lab for authorised security-tool validation.

Use only the localhost and Docker-network targets documented here. Do not point the lifecycle or Kali tooling at LAN, Internet, host-management, or unrelated container targets.

## Canonical sources and pinned images

- Official project: `https://github.com/digininja/DVWA`
- Official DVWA image: `ghcr.io/digininja/dvwa`
- DVWA commit tag: `d45ba3c`
- DVWA index digest: `sha256:091498cedec31b4a3091a1262e6a5a0ce5ec32d4bd26486558818346ccc89d67`
- Database image: `docker.io/library/mariadb:10.11.18`
- MariaDB index digest: `sha256:be981e4113326ada8d6004174dd09eeaefc03094037f811182a52d4f2e737350`

Both images are immutable in the versioned Compose file. Digest changes require a reviewed update and complete local acceptance.

## Architecture

| Component | Internal target | Host publication |
|---|---|---|
| DVWA | `http://dvwa:80/login.php` | `http://127.0.0.1:4280/login.php` |
| MariaDB | `db:3306` | none |

The default host port can be overridden without changing the internal Kali target:

```bash
export DVWA_HOST_PORT=14280
./scripts/start.sh
```

The environment uses two Compose-managed networks:

- `dvwa-lab`: non-internal bridge used by DVWA for localhost publication and temporary Kali attachment;
- `dvwa-db`: internal bridge used only by DVWA and MariaDB.

MariaDB is never published to the host and Kali is never attached to `dvwa-db`.

## Security boundaries

- DVWA binds only to `127.0.0.1`.
- MariaDB has no host port.
- DVWA and MariaDB both drop `NET_RAW`; the remaining default runtime capabilities are preserved for Apache and MariaDB startup compatibility.
- `no-new-privileges` is enabled on both services.
- No privileged mode, host networking, Docker socket, `SYS_ADMIN`, or host bind mounts.
- CPU, memory, and PID limits are defined.
- Kali MCP is connected only during controlled validation and must be disconnected afterwards.
- Runtime egress from the DVWA service remains possible through `dvwa-lab`; this must be reported accurately rather than represented as blocked.

## Lifecycle

```bash
./scripts/start.sh
./scripts/status.sh
./scripts/smoke.sh
./scripts/connect-kali.sh
./scripts/disconnect-kali.sh
./scripts/stop.sh
./scripts/reset.sh
./scripts/destroy.sh
```

Expected behaviour:

- `start.sh` validates Compose, ownership and the localhost port, pulls missing pinned images, starts both services, and waits for both to become healthy.
- `status.sh` reports service state, health, image references, effective port mapping, networks, volume, and Kali membership without changing resources.
- `smoke.sh` validates HTTP, loopback-only publication, pinned image references, database non-publication, internal database isolation, and Kali disconnection.
- `connect-kali.sh` idempotently attaches only `hermes-kali-mcp` to `dvwa-lab` after ownership and endpoint checks.
- `disconnect-kali.sh` idempotently removes Kali from owned DVWA networks and refuses foreign resources.
- `stop.sh` disconnects Kali and stops only this project while preserving the database volume.
- `reset.sh` disconnects Kali, removes project state, recreates the environment, waits for health, and runs smoke validation.
- `destroy.sh` disconnects Kali, removes only owned project containers, volume, and networks, verifies absence, preserves images, and supports a second idempotent execution.

## Health and smoke targets

Container healthchecks:

- DVWA: HTTP body retrieval from `http://127.0.0.1/login.php` using PHP already present in the official image;
- MariaDB: official `healthcheck.sh --connect --innodb_initialized`.

The smoke test accepts normal `2xx`, `3xx`, or expected `4xx` HTTP responses and rejects connection failures and `5xx` responses.

## Kali MCP validation

Authorised target:

```text
http://dvwa:80/login.php
```

Initial supported-tool candidates:

- `execute_command`;
- `nikto_scan`;
- `gobuster_scan`.

Use TCP-connect Nmap through `execute_command` if the dedicated `nmap_scan` endpoint remains degraded. Do not list a tool in `supported_tools` unless it passes on this exact environment.

Acceptance validation must not execute SQLMap, Hydra, Metasploit, password brute force, exploitation, reverse shells, UDP scans, NSE scripts, external targets, or LAN targets.

## Evidence

Sanitised runtime evidence belongs under:

```text
.runtime/evidence/dvwa/
```

Do not commit credentials, cookies, session data, HTML bodies, database contents, lesson solutions, payloads, or raw scanner output.

## Default application access

DVWA upstream defaults include:

- username: `admin`;
- password: `password`;
- security level configured here: `low`;
- authentication remains enabled.

These credentials are intentionally local lab defaults and must not be reused elsewhere.

## Digest update procedure

1. Identify an official DVWA commit tag and GHCR index digest.
2. Identify an official MariaDB fixed version and index digest.
3. Update `compose.yaml`, `manifest.yaml`, and this README together.
4. Pull deliberately on the Hermes host.
5. Repeat static, runtime, Kali, reset, destroy, and idempotency acceptance.
6. Record only sanitised results.

## Final expected state

- DVWA container: absent;
- MariaDB container: absent;
- volume `dvwa_dvwa-db-data`: absent;
- networks `dvwa-lab` and `dvwa-db`: absent;
- Kali MCP: running and disconnected from `dvwa-lab`;
- pinned images: preserved;
- unrelated Docker resources: unchanged.
