# Damn Vulnerable GraphQL Application Lab

## Source and runtime

- Canonical repository: `dolevf/Damn-Vulnerable-GraphQL-Application`
- Source commit: `a961308c02d1fb462b192681c336b0739e432da7`
- Runtime image: `ghcr.io/pestoura/hermes-dvga@sha256:6e5fcb0bca47ac75fc218d2a62858673964d8703341bb6387841a84b7409d2d4`
- Application manifest (`linux/amd64`): `sha256:5d9076ae030a6bf74ab5d8f3848bc0a7a7f8ae990869f595cb7d05d49746b9dc`
- Attestation manifest (`unknown/unknown`): `sha256:515212949b5594ea29cc8c74fe2a089b7de090797e3320222b81b070f4615bc2`
- Declared base: `docker.io/library/python:3.10-slim-bookworm`
- Build recipe: `dvga-python310-vcs-pin-v1`
- Flask-Sockets source commit: `513caf69a053a53c35110a389c9b0d83b2a9d99b`

The application image is published by the controlled GHCR workflow with an SPDX SBOM and SLSA provenance. Runtime consumption uses the accepted immutable OCI index digest, never a mutable tag or the attestation manifest.

The publication recipe preserves DVGA 2.2.0, Python 3.10, the accepted dependency set, SQLite state and the non-root `dvga` runtime. It replaces only the upstream mutable `flask-sockets@master` requirement with the proven immutable commit. The historical local image `hermes/dvga:a961308` remains evidence and is not the versioned runtime.

The observed `wheel 0.46.3` versus `packaging 22.0` compatibility warning exists in both the historical local image and the accepted GHCR image. It is recorded as a non-blocking build-tool observation because runtime dependency parity and the complete lifecycle passed.

## Targets

- Host: `http://127.0.0.1:${GRAPHQL_LAB_HOST_PORT:-5013}/`
- Kali: `http://graphql-vulnerable-lab:5013/`

Only loopback is published. Kali attachment is temporary and limited to the lab network.

## Lifecycle

Use the eight executable scripts under `scripts/`. Start pulls the accepted immutable image only when missing and does not build application source on the Hermes host. Reset destroys application state and recreates it from the same digest. Destroy disconnects Kali, removes the project container and network, preserves images and supports a second execution.

## Acceptance limits

Validation is limited to health and connectivity checks, TCP-connect Nmap, Nikto and bounded Gobuster. Do not execute GraphQL denial-of-service, command execution, SSRF, injection, file-write, token-forgery, brute-force or exploitation scenarios. Do not use external or LAN targets.

Store sanitised evidence under `.runtime/evidence/graphql-vulnerable-lab/`.
