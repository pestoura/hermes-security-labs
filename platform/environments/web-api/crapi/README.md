# OWASP crAPI Lab

## Canonical version

- Repository: `OWASP/crAPI`
- Reference commit: `73d309cc8f28bbdeed31dbb35f05dba8354de3c9`
- Application release baseline: `1.1.6-rc8`

The project Compose file uses the common `1.1.6-rc8` release-candidate tag for all six official crAPI application images. Local acceptance must confirm the effective Compose image references before any pull and record the resolved repository digest for every image before promotion from `CURRENT-LIMITED`.

## Baseline services

The baseline includes web, identity, community, workshop, gateway, MailHog, PostgreSQL and MongoDB. The optional chatbot and Chroma services are excluded to avoid external model dependencies and unnecessary resource use.

## Network model

- Host target: `http://127.0.0.1:${CRAPI_HOST_PORT:-8888}/`
- Kali target: `http://crapi:80/`
- `crapi-lab`: non-internal network containing only the web gateway and temporary Kali attachment
- `crapi-core`: internal network containing the web gateway, backends, gateway service, MailHog and databases

Only `crapi-web` publishes a host port. All other services must have empty host port bindings. Kali must never join `crapi-core`.

## Pre-pull integrity gate

Before `start.sh`, inspect the effective Compose model:

```bash
docker compose -p crapi -f compose.yaml config --images
```

Every official crAPI image must resolve to `1.1.6-rc8`. Any effective `1.1.6`, `latest`, `main` or `develop` reference is a checkout/configuration failure and must stop the campaign before pulling. `start.sh` enforces this gate automatically.

## Lifecycle

The first start verifies the effective images, pulls the fixed release tags and waits for all eight services to become healthy. Reset destroys volumes and recreates a clean environment. Destroy validates network ownership, disconnects Kali, removes containers, PostgreSQL/MongoDB volumes and both networks, preserves images and supports a second execution.

## Acceptance limits

Use only safe connectivity checks, Nmap TCP-connect, Nikto and bounded Gobuster against the registered web target. Do not create abusive accounts, execute injection payloads, shell injection, Log4Shell, brute force, denial of service, external targets or LAN targets.

Evidence belongs in `.runtime/evidence/crapi/` and must be sanitised.
