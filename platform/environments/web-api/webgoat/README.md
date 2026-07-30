# OWASP WebGoat and WebWolf Lab

## Objective

Run the deliberately vulnerable OWASP WebGoat application and its WebWolf companion in a controlled local Docker environment.

Use this lab only against the authorised localhost and Docker-network targets documented below.

## Origin and image

- Official project: `OWASP WebGoat`
- Image: `webgoat/webgoat`
- Release metadata: `2023.4`
- Pinned digest: `sha256:2775102b8186df1656f8a69cfb7a6bf6c77b43a25fa0accd6d44e6ae04c8d3b7`
- Validated host architecture: `linux/amd64`

The image digest is intentionally fixed. Updating it requires a deliberate pull, complete local lifecycle validation, and a reviewed commit.

## Architecture

A single container runs both services:

| Service | Container target | Default host target |
|---|---|---|
| WebGoat | `http://webgoat:8080/WebGoat/` | `http://127.0.0.1:8080/WebGoat/` |
| WebWolf | `http://webgoat:9090/login` | `http://127.0.0.1:9090/login` |

WebWolf returns `404` at `/`; use `/login` for health and smoke validation.

Host publication is restricted to `127.0.0.1`. The internal container ports remain `8080` and `9090` even when a host-port override is used.

## Host-port override

The default host ports are WebGoat `8080` and WebWolf `9090`.

When another local service already owns port `9090`, use a free localhost port without changing the internal WebWolf target:

```bash
export WEBGOAT_HOST_PORT=8080
export WEBWOLF_HOST_PORT=19090
./scripts/start.sh
```

## Security boundaries

- All Linux capabilities are dropped.
- `no-new-privileges` is enabled.
- No privileged mode.
- No host networking.
- No Docker socket exposure.
- No `SYS_ADMIN`.
- No broad host bind mounts.
- Resource limits: 2 CPU, 2 GiB memory, 100 PIDs.
- The Compose-managed bridge network is `webgoat-lab`.
- The current versioned baseline declares `internal: false` and `egress: true`.
- Kali MCP is connected only during controlled validation and must be disconnected afterwards.

A differential local test of `internal: true` remains required for the current PR head. That test must distinguish application startup or egress dependency from host port-publication behaviour before the versioned network mode is changed.

## Healthcheck

The container healthcheck performs HTTP requests from inside the container against both services:

- `http://127.0.0.1:8080/WebGoat/`
- `http://127.0.0.1:9090/login`

HTTP status codes in the `2xx`, `3xx`, and `4xx` ranges are accepted. Connection failures and `5xx` responses fail the healthcheck.

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

- `start.sh`: validates Compose and the pinned image, starts the service, and waits for healthy state.
- `status.sh`: reports the actual container, health, published ports, network, volume, Kali membership, and image digest.
- `smoke.sh`: discovers actual host mappings and validates both HTTP endpoints, localhost-only binding, digest, and network.
- `connect-kali.sh`: idempotently connects the running Kali MCP container to the owned lab network.
- `disconnect-kali.sh`: idempotently removes only the WebGoat network from Kali.
- `stop.sh`: disconnects Kali and stops only this project.
- `reset.sh`: disconnects Kali, removes project state, recreates the environment, waits for health, and runs smoke validation.
- `destroy.sh`: always attempts Kali disconnection before teardown, removes only project containers, volume, and network, verifies their absence, preserves the image, and supports a second idempotent execution.

`destroy.sh` must be validated both when Kali is already disconnected and when Kali is initially connected.

## Kali MCP validation

Authorised internal targets only:

- `http://webgoat:8080/WebGoat/`
- `http://webgoat:9090/login`

Validated tool set recorded in the manifest:

- `execute_command`
- `nikto_scan`
- `gobuster_scan`

Known limitations from the previous local run:

- the dedicated `nmap_scan` tool returned HTTP 500;
- TCP-connect Nmap passed through MCP `execute_command`;
- `dirb_scan` is unavailable in the current Kali image;
- `server_health` was not validated directly.

These results must be reconfirmed when a change affects runtime networking, health, or lifecycle behaviour.

Prohibited during validation:

- LAN or external targets;
- host Docker targets;
- SQLMap, Hydra, Metasploit, brute force, exploitation, reverse shells, UDP, or NSE scripts.

## Evidence

Sanitised runtime evidence belongs under:

```text
.runtime/evidence/webgoat/
```

Do not commit HTML pages, cookies, tokens, credentials, lesson solutions, payloads, or raw scanner output.

## Acceptance criteria

The current PR head is accepted only when local validation confirms:

- WebGoat and WebWolf both reach HTTP healthy state;
- actual host mappings remain localhost-only;
- the `internal: true` differential test is classified with evidence;
- Kali DNS and TCP access work only after temporary connection;
- Kali remains running and disconnected after validation;
- `stop`, `reset`, and `destroy` pass;
- `destroy` succeeds with Kali initially connected;
- a second `destroy` returns success;
- container, project volume, and network are absent afterwards;
- unrelated resources, including monitoring services, remain unchanged;
- catalog, shell, and Compose validation pass.

## Digest update

1. Pull the intended official release.
2. Obtain its repository digest.
3. Update `compose.yaml` and `manifest.yaml` together.
4. Repeat the complete acceptance workflow.
5. Record only sanitised evidence.

## Final expected state

- WebGoat/WebWolf container: removed.
- Volume `webgoat_webgoat-data`: removed.
- Network `webgoat-lab`: removed.
- Kali MCP: running and disconnected.
- Image: preserved.
- Other Docker resources: unchanged.
