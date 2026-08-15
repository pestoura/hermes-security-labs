# OWASP Juice Shop Lab

## Objective

Run the deliberately vulnerable OWASP Juice Shop application as a disposable local Docker lab for authorised security training and tool validation.

## Nature

This lab is **intentionally vulnerable** by design. It must never be exposed to untrusted networks.

## Isolation

- Runs in the canonical Compose-managed bridge network `juice-shop-lab`.
- The application is published only on `127.0.0.1`.
- Default host publication is `127.0.0.1:3000`, with a supported host-port override.
- The container-internal target remains `juice-shop:3000` regardless of the host-port override.
- No LAN bind, host networking, privileged mode or Docker socket exposure.
- Kali MCP connects temporarily only during separately authorised controlled tests and must be disconnected afterwards.

## Image

- Image: `bkimminich/juice-shop`
- Pinned digest: `sha256:e68144772ebaaca0ec117b38d44903af92416793230288ef7c5437fc4f26850a`

The digest is fixed in `compose.yaml`. Updating it requires deliberate image validation and a complete lifecycle acceptance.

## Host-port override

The default host port is `3000`. When it is already occupied by another local service, choose a verified-free localhost port without changing the container-internal target:

```bash
export JUICE_SHOP_HOST_PORT=13000
./scripts/start.sh
```

Use the same `JUICE_SHOP_HOST_PORT` value for the full lifecycle run. `status.sh` and `smoke.sh` resolve the effective Compose publication; `smoke.sh` does not assume host port `3000`.

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

- `start.sh`: validates Compose, pulls the pinned image when needed, starts the service and waits for `healthy`.
- `status.sh`: reports the actual container state, health, effective port mapping, network, volumes and Kali membership without changing resources.
- `smoke.sh`: resolves the actual host publication, requires a `127.0.0.1:<port>` mapping, checks health and validates HTTP connectivity using that effective port.
- `connect-kali.sh`: validates that `hermes-kali-mcp` is running, verifies `juice-shop-lab` ownership and current endpoints, and idempotently connects Kali only to that owned lab network.
- `disconnect-kali.sh`: idempotently disconnects Kali from the owned Juice Shop network and refuses ambiguous/foreign resources.
- `stop.sh`: stops only this Compose project while preserving its persistent volumes.
- `reset.sh`: disconnects Kali, removes project state, recreates the lab, waits for health and runs smoke validation.
- `destroy.sh`: disconnects Kali first, removes only project-owned containers, volumes and network, verifies absence, preserves the image and supports a second idempotent execution.

## Health and smoke target

The container healthcheck uses the internal service endpoint on port `3000`.

The host smoke test resolves the actual Compose mapping and accepts normal HTTP responses below `500`; connection failures, non-loopback publication and `5xx` responses fail closed.

## Temporary Kali connection

For separately authorised Kali validation, use the canonical scripts rather than raw `docker network connect` / `disconnect` commands:

```bash
./scripts/connect-kali.sh
# authorised target from Kali: http://juice-shop:3000/
./scripts/disconnect-kali.sh
```

The scripts enforce ownership of the canonical `juice-shop-lab` network and reject unexpected endpoints.

## Authorised safe scans via Kali MCP

Only after explicit authorisation for the scan stage, and only against the local lab target:

- `execute_command` for bounded DNS/TCP/HTTP checks;
- `nmap_scan` TCP-connect only — currently degraded in the dedicated endpoint;
- `nikto_scan`;
- `gobuster_scan`.

**Prohibited:** SQLMap, Hydra, Metasploit, brute force, credential attacks, reverse shells, external targets and LAN scans.

Lifecycle acceptance itself does **not** require Kali and should remain lifecycle-only unless a separate validation explicitly authorises target traffic.

## Evidence

Sanitised runtime evidence belongs under:

```text
.runtime/evidence/juice-shop/
```

Do not commit raw HTML/page bodies, tokens, cookies, credentials, payloads or offensive tool output.

## Live lifecycle acceptance pattern

For governed live acceptance, follow `docs/roadmap/lab-live-lifecycle-acceptance-runbook.md` and the dedicated tracking issue. The canonical lifecycle sequence is:

```text
start -> status -> smoke -> reset -> status -> smoke -> destroy -> destroy
```

Acceptance requires exact-revision provenance, loopback-only publication, idempotent destroy, non-interference with unrelated Docker resources and zero project-owned residue.

## Final state

After validation:

- Juice Shop container: absent;
- project volumes `juice-shop-data` and `juice-shop-ftp`: absent;
- canonical network `juice-shop-lab`: absent;
- Kali MCP: running and disconnected from the lab network;
- pinned image: preserved;
- host override port: free again;
- unrelated Docker resources: unchanged.

## Troubleshooting

- If healthcheck fails: inspect only the owned project logs with `docker compose -p juice-shop -f compose.yaml logs juice-shop` from the lab directory.
- If smoke fails: check `status.sh` and the effective `127.0.0.1:<port>` mapping.
- If Kali cannot resolve `juice-shop`: use `connect-kali.sh` and verify that the canonical owned network is `juice-shop-lab`.

## Limitations

- Local validation only.
- No external target scanning.
- No SQLMap, Hydra or Metasploit.
- `dirb_scan` is unavailable in the current Kali image.
- Dedicated `nmap_scan` is currently degraded; TCP-connect Nmap was previously validated through MCP `execute_command`.
- `server_health` is not part of the lab lifecycle acceptance.
- Image remains pinned to the validated digest.

## Warning

**Never** use this lab against unauthorised targets. All target interaction must remain within the explicitly authorised local Juice Shop instance.