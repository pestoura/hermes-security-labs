# OWASP crAPI Lab

## Canonical version

- Repository: `OWASP/crAPI`
- Reference commit: `73d309cc8f28bbdeed31dbb35f05dba8354de3c9`
- Application release baseline: `1.1.6-rc8`

The project Compose file uses the common `1.1.6-rc8` release-candidate tag for all six official crAPI application images, and every reference is additionally pinned to an immutable repository digest. Local acceptance must confirm the effective Compose image references before any pull.

## Pinned image digests

Digests resolved read-only from Docker Hub (registry manifest `HEAD`, `Docker-Content-Digest`); no image was pulled, published or modified upstream. Every value is the OCI image *index* digest, so multi-architecture resolution is preserved.

| Source | Tag | Digest |
| --- | --- | --- |
| `crapi/crapi-identity` | `1.1.6-rc8` | `sha256:5152eaa8b25d8585068ec478c9a2ee886ce1658d8289fd047f83325737490f78` |
| `crapi/crapi-community` | `1.1.6-rc8` | `sha256:ff62181b9089df60379c1cecdcfceb0f54ea6d6c4d7c407bb2f5fd55208f2be0` |
| `crapi/crapi-workshop` | `1.1.6-rc8` | `sha256:b73a2e4aed1a62ba9c626214eca6b66289f2f5cced7169dbd791837edf263de6` |
| `crapi/crapi-web` | `1.1.6-rc8` | `sha256:6cbafa5085cc38199c5f16f71ad11579168e08ca25c22e9b89f55e423caa8746` |
| `crapi/gateway-service` | `1.1.6-rc8` | `sha256:111a996957c1e9f78fe401b4d9a16bb99e6d6a3aa836792382a52c9ecbd39c8c` |
| `crapi/mailhog` | `1.1.6-rc8` | `sha256:c3a74b1f63673996aec82f175ad4dd49cc3152637f68dc3dfc9f765e06c0f5e9` |
| `docker.io/library/postgres` | `14` | `sha256:2f439458ab6a57a925825ae14f9d06910e4fe4a41c8d4a0ae06397e65b707e1b` |
| `docker.io/library/mongo` | `4.4.29` | `sha256:52c42cbab240b3c5b1748582cc13ef46d521ddacae002bbbda645cebed270ec0` |

The functional version is unchanged: each digest is the one the corresponding tag pointed to at resolution time. `docker.io/library/mongo:4.4.29` reuses the digest already pinned by the DVAPI and NodeGoat laboratories. `postgres:14` is a rolling minor tag upstream, so digest pinning freezes the patch level — refreshing it is a deliberate, reviewed change.

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

Every official crAPI image must resolve to `1.1.6-rc8` with the digest listed above. Any effective `1.1.6`, `latest`, `main` or `develop` reference, or a missing/altered digest, is a checkout/configuration failure and must stop the campaign before pulling. `start.sh` enforces this gate automatically by comparing the effective image list against the digest-qualified references.

## Lifecycle

The first start verifies the effective images, pulls the fixed release tags and waits for all eight services to become healthy. Reset destroys volumes and recreates a clean environment. Destroy validates network ownership, disconnects Kali, removes containers, PostgreSQL/MongoDB volumes and both networks, preserves images and supports a second execution.

## Acceptance limits

Use only safe connectivity checks, Nmap TCP-connect, Nikto and bounded Gobuster against the registered web target. Do not create abusive accounts, execute injection payloads, shell injection, Log4Shell, brute force, denial of service, external targets or LAN targets.

Evidence belongs in `.runtime/evidence/crapi/` and must be sanitised.
