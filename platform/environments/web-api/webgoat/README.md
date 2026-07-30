# OWASP WebGoat and WebWolf Lab

## Objective
Deliberately vulnerable web application (WebGoat) and attacker simulation tool (WebWolf) for local security testing.

## Nature
Intentionally vulnerable — only run in isolated environments.

## Origin
Official OWASP WebGoat project: https://github.com/WebGoat/WebGoat

## Image
- Image: `webgoat/webgoat@sha256:2775102b8186df1656f8a69cfb7a6bf6c77b43a25fa0accd6d44e6ae04c8d3b7`
- Tag: `2023.4`
- Architecture: linux/amd64 (host validated)

## Architecture
- Single container running both WebGoat and WebWolf
- WebGoat on internal port 8080, context path `/WebGoat/`
- WebWolf on internal port 9090, context path `/login` (root returns 404)
- Isolated Docker bridge network: `webgoat-lab`
- Host ports bound to `127.0.0.1` only (no LAN exposure)

## Endpoints
| Service | Host Default | Internal Target |
|---------|--------------|-----------------|
| WebGoat | `http://127.0.0.1:8080/WebGoat/` | `http://webgoat:8080/WebGoat/` |
| WebWolf | `http://127.0.0.1:9090/login` | `http://webgoat:9090/login` |

> **Note**: WebWolf root path `/` returns 404. Use `/login` for health checks.

## Isolation
- Container runs with all capabilities dropped
- No privileged access
- No host network mode
- No Docker socket access
- No SYS_ADMIN
- Resource limits: 2 CPU, 2GiB RAM, 100 PIDs
- Read-only root filesystem (except `/home/webgoat` volume)
- Network: isolated bridge (host ports published via docker-proxy)
- Egress: not required for startup

## Host Port Override
Default host ports: WebGoat 8080, WebWolf 9090.

If a host port is occupied (e.g., Prometheus on 9090), override at runtime:

```bash
export WEBGOAT_HOST_PORT=8080
export WEBWOLF_HOST_PORT=19090
./scripts/start.sh
```

Internal targets remain `webgoat:8080` and `webgoat:9090` — only the host mapping changes.

## Lifecycle
```bash
./scripts/start.sh      # Validate, pull, up -d, wait healthy
./scripts/status.sh     # Read-only status, mappings, network, Kali
./scripts/smoke.sh      # Health, HTTP, binding, digest, network
./scripts/stop.sh       # Disconnect Kali, stop container
./scripts/reset.sh      # Disconnect Kali, down -v, recreate, smoke
./scripts/destroy.sh    # Disconnect Kali, down -v --remove-orphans, validate cleanup
./scripts/connect-kali.sh    # Attach Kali MCP to webgoat-lab
./scripts/disconnect-kali.sh # Detach Kali MCP
```

### Start
- Validates compose
- Checks image digest exists locally
- Verifies host ports free
- `up -d`, waits for healthy (timeout 180s)

### Status
- Compose state, container health, port mappings, network type, Kali membership, volumes, image digest, internal targets

### Smoke
- Container running, health = healthy
- WebGoat HTTP 2xx/3xx/4xx on host port
- WebWolf HTTP 2xx/3xx/4xx on host port (`/login`)
- Binding only on `127.0.0.1`
- Image digest matches
- Network exists and is bridge

### Stop
- Disconnects Kali from network
- Stops container (preserves volume)

### Reset
- Disconnects Kali
- `down --volumes --remove-orphans`
- Recreates, waits healthy, runs smoke
- Kali remains disconnected

### Destroy
- Trap ensures Kali disconnect on exit
- `down --volumes --remove-orphans`
- Validates: container absent, volumes absent, network absent (if project-owned), Kali running and disconnected, image preserved
- Idempotent: second run exits 0

## Kali MCP Integration
Temporary connection only during controlled validation:

```bash
./scripts/connect-kali.sh
# Inside Kali:
getent hosts webgoat
cat < /dev/null > /dev/tcp/webgoat/8080
cat < /dev/null > /dev/tcp/webgoat/9090
./scripts/disconnect-kali.sh
```

**Authorized internal targets only:**
- `http://webgoat:8080/WebGoat/`
- `http://webgoat:9090/login`

No LAN targets. No external targets. No host Docker socket.

## Validated Tools (MCP)
| Tool | Target | Result |
|------|--------|--------|
| execute_command | id, getent hosts webgoat, TCP 8080/9090, basic HTTP | PASS |
| nikto_scan | WebGoat (`/WebGoat/`) | PASS |
| nikto_scan | WebWolf (`/login`) | PASS |
| gobuster_scan | WebGoat (small wordlist) | PASS |
| nmap_scan (dedicated) | TCP connect, unprivileged, 8080/9090 | DEGRADED (HTTP 500) |
| nmap_scan fallback | `nmap -sT --unprivileged -Pn -p 8080,9090 webgoat` | PASS |

**Not validated / not supported:**
- SQLMap, Hydra, Metasploit
- Credential attacks, brute force, reverse shells
- NSE scripts, UDP scans, full port scans
- External targets, host Docker, LAN

## Limitations
- Local validation only (private repo, GitHub Actions quota exhausted)
- Dedicated `nmap_scan` tool returns HTTP 500 in current Kali MCP (infrastructure)
- `nmap` TCP connect works via `execute_command` fallback
- WebWolf root path `/` returns 404; `/login` used for health
- Network cannot be `internal: true` because Docker requires host port publishing for localhost access
- Host port 9090 conflict with Prometheus documented; override via `WEBWOLF_HOST_PORT`
- No external deployment; Kali MCP accessed via Hermes STDIO (`hermes -p pentest-lab chat --toolsets kali-lab`)

## Evidence
Runtime evidence written to `${EVIDENCE_DIR:-.runtime/evidence/webgoat}` (gitignored):
- Port diagnosis
- Smoke summaries
- MCP tool outputs (sanitized: timestamp, tool, target, args, exit code, duration, classification, short summary)

No HTML pages, cookies, tokens, credentials, raw scanner output, or lesson solutions committed.

## Digest Update
When a new WebGoat release is published:
1. Pull new tag: `docker pull webgoat/webgoat:<new-tag>`
2. Get digest: `docker image inspect webgoat/webgoat:<new-tag> --format '{{json .RepoDigests}}'`
3. Update `compose.yaml` image reference and `manifest.yaml` digest
2. Re-run full lifecycle validation

## Troubleshooting
| Issue | Resolution |
|-------|------------|
| Port 8080/9090/19090 in use | `export WEBWOLF_HOST_PORT=19090` (or other free port) |
| Healthcheck timeout | Increase `start_period` / `retries` in compose |
| WebWolf returns 404 | Use `/login` path, not `/` |
| Kali cannot connect | Ensure `./scripts/connect-kali.sh` ran; verify `getent hosts webgoat` |
| Image pull fails | Verify digest exists on Docker Hub; check architecture |

## Final State After Destroy
- WebGoat/WebWolf container: **removed**
- Volume `webgoat-data`: **removed**
- Network `webgoat-lab`: **removed**
- Kali MCP: **running, healthy, disconnected**
- Other Docker resources: **unchanged**

## Prohibited
- Targets outside `webgoat-lab` network
- LAN / external scans
- Credential attacks, exploitation, reverse shells
- Docker socket exposure, privileged containers, host networking
