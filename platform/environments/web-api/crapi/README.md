# OWASP crAPI Lab

## Canonical version

- Repository: `OWASP/crAPI`
- Release: `1.1.6`
- Reference commit: `73d309cc8f28bbdeed31dbb35f05dba8354de3c9`
- Official application images use release tag `1.1.6`.

Local acceptance must record the resolved repository digest for every official crAPI image and the PostgreSQL/MongoDB dependencies before promotion from `CURRENT-LIMITED`.

## Baseline services

The baseline includes web, identity, community, workshop, gateway, MailHog, PostgreSQL and MongoDB. The optional chatbot and Chroma services are excluded to avoid external model dependencies and unnecessary resource use.

## Network model

- Host target: `http://127.0.0.1:${CRAPI_HOST_PORT:-8888}/`
- Kali target: `http://crapi:80/`
- `crapi-lab`: non-internal network containing only the web gateway and temporary Kali attachment
- `crapi-core`: internal network containing the web gateway, backends, gateway service, MailHog and databases

Only `crapi-web` publishes a host port. All other services must have empty host port bindings. Kali must never join `crapi-core`.

## Lifecycle

The first start pulls the fixed release tags and waits for all eight services to become healthy. Reset destroys volumes and recreates a clean environment. Destroy validates network ownership, disconnects Kali, removes containers, PostgreSQL/MongoDB volumes and both networks, preserves images and supports a second execution.

## Acceptance limits

Use only safe connectivity checks, Nmap TCP-connect, Nikto and bounded Gobuster against the registered web target. Do not create abusive accounts, execute injection payloads, shell injection, Log4Shell, brute force, denial of service, external targets or LAN targets.

Evidence belongs in `.runtime/evidence/crapi/` and must be sanitised.
