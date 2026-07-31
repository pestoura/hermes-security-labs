# OWASP NodeGoat Lab

## Source

- Canonical repository: `OWASP/NodeGoat`
- Source commit: `c5cb68a7084e4ae7dcc60e6a98768720a81841e8`
- Runtime image: `ghcr.io/pestoura/hermes-nodegoat@sha256:0e0cbd8b0c82db51b1dfff9c58a391653774fa3b7b4c68ad10e6cda4c173ab6c`
- Application manifest (`linux/amd64`): `sha256:dba288bb8d1b4a476b229398635d498c4aa5887e3a2f68a4ee67ae18bbde39c3`
- Attestation manifest (`unknown/unknown`): `sha256:7d8063eb2150273923ef5c91819c0dfc52483e75b5ff430ccd114a7c7b519bd1`
- Declared upstream base: `node:12-alpine`
- MongoDB dependency: `mongo:4.4.29`

The application image is published by the controlled GHCR workflow with SBOM and BuildKit provenance. Runtime consumption uses the immutable OCI index digest, never a mutable tag or the attestation manifest. The image preserves the accepted upstream Node.js 12 compatibility boundary; modernization is tracked separately from this runtime migration.

## Architecture

- Host target: `http://127.0.0.1:${NODEGOAT_HOST_PORT:-4000}/`
- Kali target: `http://nodegoat:4000/`
- `nodegoat-lab`: non-internal publication/Kali network
- `nodegoat-db`: internal application/database network
- MongoDB has no host publication and Kali must never join `nodegoat-db`.

Startup follows the accepted upstream sequence: wait for MongoDB, reset the training database, then start the application. The lifecycle pulls missing images and does not build application source on the Hermes host.

## Lifecycle

Use the eight executable scripts under `scripts/`. Reset removes project state, recreates the database and application, and runs smoke validation. Destroy disconnects Kali first, verifies network ownership, removes containers, the database volume and both networks, and supports a second execution.

Acceptance is restricted to safe connectivity and bounded scanners. Store sanitised evidence in `.runtime/evidence/nodegoat/`.
