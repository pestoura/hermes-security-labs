# OWASP crAPI Lab

## Canonical version

- Repository: `OWASP/crAPI`
- Upstream reference release: `v1.1.6-rc8`
- Reference commit: `73d309cc8f28bbdeed31dbb35f05dba8354de3c9`
- Official application images use the common available tag `1.1.6-rc8`.

The final `1.1.6` tag is not available consistently across all required official images. The baseline therefore uses the upstream release-candidate tag shared by identity, community, workshop, web, gateway and MailHog. Local acceptance must record the resolved repository digest for every official crAPI image and the PostgreSQL/MongoDB dependencies before promotion from `CURRENT-LIMITED`.

## Baseline services

The baseline includes web, identity, community, workshop, gateway, MailHog, PostgreSQL and MongoDB. The optional chatbot and Chroma services are excluded to avoid external model dependencies and unnecessary resource use.

## Network model

- Host target: `http://127.0.0.1:${CRAPI_HOST_PORT:-8888}/`
- Kali target: `http://crapi:80/`
- `crapi-lab`: non-internal network containing only the web gateway and temporary Kali attachment
- `crapi-core`: internal network containing the web gateway, backends, gateway service, MailHog and databases

Only `crapi-web` publishes a host port. All other services must have empty host port bindings. Kali must never join `crapi-core`.

## Lifecycle

The first start pulls the fixed release-candidate tags and waits for all eight services to become healthy. Reset destroys volumes and recreates a clean environment. Destroy validates network ownership, disconnects Kali, removes containers, PostgreSQL/MongoDB volumes and both networks, preserves images and supports a second execution.

## Acceptance limits

Use only safe connectivity checks, Nmap TCP-connect, Nikto and bounded Gobuster against the registered web target. Do not create abusive accounts, execute injection payloads, shell injection, Log4Shell, brute force, denial of service, external targets or LAN targets.

Evidence belongs in `.runtime/evidence/crapi/` and must be sanitised.
