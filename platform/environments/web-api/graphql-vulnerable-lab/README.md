# Damn Vulnerable GraphQL Application Lab

## Canonical source

- Repository: `dolevf/Damn-Vulnerable-GraphQL-Application`
- Source commit: `a961308c02d1fb462b192681c336b0739e432da7`
- Built image: `hermes/dvga:a961308`

The application source is immutable. A project-contained Python 3.10 Bookworm wrapper replaces unreliable upstream image-build steps and installs `git`, which is required by the pinned VCS dependency in the upstream requirements file.

## Targets

- Host: `http://127.0.0.1:${GRAPHQL_LAB_HOST_PORT:-5013}/`
- Kali: `http://graphql-vulnerable-lab:5013/`

Only loopback is published. Kali attachment is temporary and limited to the lab network.

## Lifecycle

Use the eight executable scripts under `scripts/`. First start builds the immutable source and initializes the local database. Reset recreates application state. Destroy disconnects Kali, removes the project container and network, preserves the image and supports a second execution.

## Acceptance limits

Validation is limited to health, connectivity, TCP-connect Nmap, Nikto and bounded Gobuster. Do not execute GraphQL denial-of-service, command execution, SSRF, injection, file-write, token-forgery, brute-force or exploitation scenarios. Do not use external or LAN targets.

Store sanitised evidence under `.runtime/evidence/graphql-vulnerable-lab/`.
