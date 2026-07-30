# OWASP Juice Shop Lab

## Objective
Deliberately vulnerable web application for security training and tool validation.

## Nature
This lab is **intentionally vulnerable** by design. It must never be exposed to untrusted networks.

## Isolation
- Runs in a dedicated Docker bridge network: `juice-shop_juice-shop-lab` (managed by Compose)
- Published port binds **only to 127.0.0.1:3000**
- No LAN exposure
- Kali MCP connects temporarily only during controlled tests

## Prerequisites
- Docker and Docker Compose
- Kali MCP container (`hermes-kali-mcp`) running
- Hermes profile `pentest-lab` with `kali-lab` MCP configured

## Commands

### Start
```bash
./scripts/start.sh
```
Validates compose, pulls image, starts container, waits for `healthy` status.

### Status
```bash
./scripts/status.sh
```
Read-only status: compose state, container health, port mapping, network, Kali membership.

### Smoke
```bash
./scripts/smoke.sh
```
Validates container running, health `healthy`, and HTTP connectivity to `http://127.0.0.1:3000`.

### Stop
```bash
./scripts/stop.sh
```
Stops the Juice Shop container without removing volumes.

### Reset
```bash
./scripts/reset.sh
```
Disconnects Kali, removes containers/volumes, recreates lab, waits for healthy, runs smoke test.

### Destroy
```bash
./scripts/destroy.sh
```
Removes containers, volumes, project network. Disconnects Kali first. Idempotent.

## Temporary Kali Connection
To run MCP scans, connect Kali to the lab network:

```bash
docker network connect juice-shop_juice-shop-lab hermes-kali-mcp
```

Run authorized local scans against target alias `juice-shop:3000`.

**Disconnect immediately after:**

```bash
docker network disconnect juice-shop_juice-shop-lab hermes-kali-mcp
```

## Authorized Safe Scans (via Kali MCP)
Only these tools against the local target:
- `server_health`
- `execute_command` (DNS, TCP, HTTP basic)
- `nmap_scan` (TCP connect, unprivileged, port 3000)
- `nikto_scan`
- `gobuster_scan`

**Prohibited:** SQLMap, Hydra, Metasploit, brute force, credential attacks, reverse shells, external targets, LAN scans.

## Evidence
Sanitized evidence stored in:
```
.runtime/evidence/juice-shop/
```

No raw logs, tokens, cookies, or offensive outputs in Git.

## Final State
After validation: Juice Shop destroyed, Kali disconnected, network removed.

## Troubleshooting
- If healthcheck fails: check `docker compose logs juice-shop`
- If Kali cannot resolve `juice-shop`: verify network connect and DNS
- If smoke fails: confirm container healthy and port 127.0.0.1:3000 reachable

## Limitations
- Local validation only
- No external target scanning
- No SQLMap, Hydra, Metasploit
- dirb_scan not available in Kali image
- Kali MCP tools via Hermes STDIO
- Image pinned to validated digest

## Warning
**Never** use this lab against unauthorized targets. All scans must target only the local Juice Shop instance in the isolated Docker network.
