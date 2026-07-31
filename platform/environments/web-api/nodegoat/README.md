# OWASP NodeGoat Lab

## Source

- Canonical repository: `OWASP/NodeGoat`
- Source commit: `c5cb68a7084e4ae7dcc60e6a98768720a81841e8`
- Local application image: `hermes/nodegoat:c5cb68a`
- MongoDB dependency: `mongo:4.4.29`

## Architecture

- Host target: `http://127.0.0.1:${NODEGOAT_HOST_PORT:-4000}/`
- Kali target: `http://nodegoat:4000/`
- `nodegoat-lab`: non-internal publication/Kali network
- `nodegoat-db`: internal application/database network
- MongoDB has no host publication and Kali must never join `nodegoat-db`.

The app is built from the exact upstream commit. Startup follows the upstream sequence: wait for MongoDB, reset the training database, then start the application.

## Lifecycle

Use the eight executable scripts under `scripts/`. Reset removes project state, recreates the database and application, and runs smoke validation. Destroy disconnects Kali first, verifies network ownership, removes containers, the database volume and both networks, and supports a second execution.

Acceptance is restricted to safe connectivity and bounded scanners. Store sanitised evidence in `.runtime/evidence/nodegoat/`.
