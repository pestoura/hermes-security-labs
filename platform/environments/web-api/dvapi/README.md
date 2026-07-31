# DVAPI Lab

## Source and image

- Canonical repository: `payatu/DVAPI`
- Source commit: `bde30d295aa8bc7f5516396fbae19d9630c11600`
- GHCR package: `ghcr.io/pestoura/hermes-dvapi`
- Runtime image: `ghcr.io/pestoura/hermes-dvapi@sha256:18d9175aa8031568c95e5bd9dcd9597a0b575aec7a742d81c7f34973c506c872`
- Platform: `linux/amd64`
- BuildKit provenance: `mode=max`
- SBOM: attached to the OCI image index
- MongoDB dependency: `docker.io/library/mongo:4.4.29`

The application image is built by the manually dispatched GitHub-hosted publication workflow from the immutable upstream commit and reviewed Node.js 20 recipe. The runtime Compose never builds the application from source and never uses a mutable application tag. MongoDB remains a separately pinned official dependency and is not published or mirrored by Hermes.

## Architecture

- Host target: `http://127.0.0.1:${DVAPI_HOST_PORT:-3000}/`
- Kali target: `http://dvapi:3000/`
- `dvapi-lab`: application publication and temporary Kali network
- `dvapi-db`: internal application/MongoDB network
- MongoDB alias: `mongodb`, matching the upstream source

MongoDB has no host binding and Kali must never join `dvapi-db`.

## Lifecycle

Use the eight executable lifecycle scripts. The first start pulls the immutable GHCR digest when it is absent locally. `start.sh` and `reset.sh` do not build application images. Reset recreates application and database state. Destroy verifies network ownership, disconnects Kali, removes containers, the MongoDB volume and both networks, preserves pulled images and supports a second execution.

Acceptance validates the exact repository SHA, immutable GHCR index digest, OCI labels, application and MongoDB health, loopback-only application mapping, internal database isolation, temporary Kali DNS/TCP/HTTP access to the application only, reset, idempotent destroy, final Kali disconnection and unchanged unrelated Docker resources.

Acceptance is limited to safe connectivity and bounded scanners. Store sanitised evidence in `.runtime/evidence/dvapi/`.
