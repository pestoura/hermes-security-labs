# DVAPI Lab

## Source and build

- Canonical repository: `payatu/DVAPI`
- Source commit: `bde30d295aa8bc7f5516396fbae19d9630c11600`
- Local application image: `hermes/dvapi:bde30d2`
- MongoDB dependency: `mongo:4.4.29`

A project-contained inline Dockerfile replaces the upstream `node:latest` base with Node.js 20 while preserving the pinned application source.

## Architecture

- Host target: `http://127.0.0.1:${DVAPI_HOST_PORT:-3000}/`
- Kali target: `http://dvapi:3000/`
- `dvapi-lab`: application publication and temporary Kali network
- `dvapi-db`: internal application/MongoDB network
- MongoDB alias: `mongodb`, matching the upstream source

MongoDB has no host binding and Kali must never join `dvapi-db`.

## Lifecycle

Use the eight executable lifecycle scripts. Reset recreates application and database state. Destroy verifies network ownership, disconnects Kali, removes containers, the MongoDB volume and both networks, preserves built images and supports a second execution.

Acceptance is limited to safe connectivity and bounded scanners. Store sanitised evidence in `.runtime/evidence/dvapi/`.
